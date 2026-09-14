import base64
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pqc_collector.core import (
    diff_file_key as make_diff_file_key,
    file_key,
    normalize_path,
    project_paths,
    query_page_key,
    repository_key,
    search_item_key,
)


RAW_RESPONSE_PREFIXES = {
    "rate_limit": "rate_limit",
    "query_page": "query_page",
    "file": "file",
    "commit_list": "commit_list",
    "commit": "commit",
    "pr": "pr",
}


def connect(path=None, root=None):
    """Open a SQLite connection for collector storage."""
    db_path = path if path is not None else project_paths(root)["data"] / "collector.sqlite"
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_columns(conn, table, columns):
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_query_pages_table(conn):
    """Create the query page storage table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS query_pages (
            query_page_key TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            query_key TEXT NOT NULL,
            query_group TEXT NOT NULL,
            page INTEGER NOT NULL,
            page_size INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            item_count INTEGER NOT NULL,
            new_unique_item_count INTEGER NOT NULL,
            duplicate_item_count INTEGER NOT NULL,
            duplicate_ratio REAL NOT NULL,
            raw_path TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def init_repositories_table(conn):
    """Create the GitHub repository metadata table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repositories (
            repository_key TEXT PRIMARY KEY,
            repository_id INTEGER NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            html_url TEXT NOT NULL,
            first_seen_batch_id TEXT NOT NULL,
            last_seen_batch_id TEXT NOT NULL
        )
        """
    )
    conn.commit()


def init_raw_search_items_table(conn):
    """Create the raw GitHub code search item table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_search_items (
            search_item_key TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            query_key TEXT NOT NULL,
            query_page_key TEXT NOT NULL,
            repository_key TEXT NOT NULL,
            repository_id INTEGER NOT NULL,
            repository_full_name TEXT NOT NULL,
            repository_url TEXT NOT NULL,
            path TEXT NOT NULL,
            normalized_path TEXT NOT NULL,
            blob_sha TEXT NOT NULL,
            file_api_url TEXT NOT NULL,
            html_url TEXT NOT NULL,
            status TEXT NOT NULL,
            first_seen_batch_id TEXT NOT NULL,
            last_seen_batch_id TEXT NOT NULL,
            raw_query_page_path TEXT NOT NULL,
            FOREIGN KEY (query_page_key) REFERENCES query_pages (query_page_key),
            FOREIGN KEY (repository_key) REFERENCES repositories (repository_key)
        )
        """
    )
    conn.commit()


def init_raw_search_item_occurrences_table(conn):
    """Create the raw search item occurrence history table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_search_item_occurrences (
            search_item_key TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            query_key TEXT NOT NULL,
            query_page_key TEXT NOT NULL,
            raw_query_page_path TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (search_item_key, batch_id, query_page_key),
            FOREIGN KEY (search_item_key) REFERENCES raw_search_items (search_item_key),
            FOREIGN KEY (query_page_key) REFERENCES query_pages (query_page_key)
        )
        """
    )
    conn.commit()


def backfill_raw_search_item_occurrences(conn):
    """Seed occurrence history from the current raw item rows when upgrading a DB."""
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    conn.execute(
        """
        INSERT OR IGNORE INTO raw_search_item_occurrences (
            search_item_key,
            batch_id,
            query_key,
            query_page_key,
            raw_query_page_path,
            seen_at
        )
        SELECT
            r.search_item_key,
            r.batch_id,
            r.query_key,
            r.query_page_key,
            r.raw_query_page_path,
            COALESCE(q.fetched_at, ?)
        FROM raw_search_items AS r
        LEFT JOIN query_pages AS q
            ON q.query_page_key = r.query_page_key
        """,
        (checked_at,),
    )
    conn.commit()


def init_f0_results_table(conn):
    """Create the F0 path quality result table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS f0_results (
            batch_id TEXT NOT NULL,
            search_item_key TEXT NOT NULL,
            repository_full_name TEXT NOT NULL,
            path TEXT NOT NULL,
            normalized_path TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            passed INTEGER NOT NULL,
            reason_codes_json TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, search_item_key)
        )
        """
    )
    conn.commit()


def init_files_table(conn):
    """Create the fetched file snapshot table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_snapshots (
            file_key TEXT PRIMARY KEY,
            repository_key TEXT NOT NULL,
            repository_id INTEGER NOT NULL,
            repository_full_name TEXT NOT NULL,
            path TEXT NOT NULL,
            normalized_path TEXT NOT NULL,
            blob_sha TEXT NOT NULL,
            file_api_url TEXT NOT NULL,
            html_url TEXT NOT NULL,
            download_url TEXT,
            encoding TEXT NOT NULL,
            content_text TEXT NOT NULL,
            content_size INTEGER NOT NULL,
            raw_file_path TEXT NOT NULL,
            first_seen_batch_id TEXT NOT NULL,
            last_seen_batch_id TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            FOREIGN KEY (repository_key) REFERENCES repositories (repository_key)
        )
        """
    )
    conn.commit()


def init_file_fetch_results_table(conn):
    """Create the per-search-item file fetch status table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_fetch_results (
            batch_id TEXT NOT NULL,
            search_item_key TEXT NOT NULL,
            file_key TEXT,
            status TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 1,
            raw_file_path TEXT,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, search_item_key),
            FOREIGN KEY (search_item_key) REFERENCES raw_search_items (search_item_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_file_fetch_results_status
        ON file_fetch_results (batch_id, status)
        """
    )
    conn.commit()


def init_f1_results_table(conn):
    """Create the F1 static candidate result table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS f1_results (
            batch_id TEXT NOT NULL,
            search_item_key TEXT NOT NULL,
            file_key TEXT NOT NULL,
            path TEXT NOT NULL,
            language TEXT,
            passed INTEGER NOT NULL,
            target_libraries_json TEXT NOT NULL,
            matched_library_signals_json TEXT NOT NULL,
            matched_pqc_api_signals_json TEXT NOT NULL,
            matched_provider_signals_json TEXT NOT NULL,
            library_evidence_json TEXT NOT NULL DEFAULT '[]',
            strong_signal_evidence_json TEXT NOT NULL DEFAULT '[]',
            quality_json TEXT NOT NULL,
            reason_codes_json TEXT NOT NULL,
            raw_file_path TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, search_item_key),
            FOREIGN KEY (file_key) REFERENCES file_snapshots (file_key)
        )
        """
    )
    _ensure_columns(
        conn,
        "f1_results",
        {
            "library_evidence_json": "TEXT NOT NULL DEFAULT '[]'",
            "strong_signal_evidence_json": "TEXT NOT NULL DEFAULT '[]'",
        },
    )
    conn.commit()


def init_diff_evidence_table(conn):
    """Create the D0 exact diff evidence result table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS d0_results (
            batch_id TEXT NOT NULL,
            search_item_key TEXT NOT NULL,
            file_key TEXT NOT NULL,
            diff_file_key TEXT,
            repository_full_name TEXT NOT NULL,
            search_item_path TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            commit_url TEXT NOT NULL,
            matched_changed_path TEXT,
            exact_path_match INTEGER NOT NULL,
            patch_available INTEGER NOT NULL,
            passed INTEGER NOT NULL,
            changed_files_json TEXT NOT NULL DEFAULT '[]',
            review_evidence_json TEXT NOT NULL DEFAULT '[]',
            reason_codes_json TEXT NOT NULL,
            raw_commit_path TEXT NOT NULL,
            patch_path TEXT,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, search_item_key, commit_sha),
            FOREIGN KEY (batch_id, search_item_key)
                REFERENCES f1_results (batch_id, search_item_key),
            FOREIGN KEY (file_key) REFERENCES file_snapshots (file_key)
        )
        """
    )
    _ensure_columns(
        conn,
        "d0_results",
        {
            "evidence_status": "TEXT NOT NULL DEFAULT 'processed'",
            "evidence_reason_code": "TEXT",
            "d0_status": "TEXT NOT NULL DEFAULT 'processed'",
        },
    )
    conn.commit()


def init_d0_history_tables(conn):
    """Create D0 history traversal, per-commit status, and commit cache tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS d0_history_state (
            batch_id TEXT NOT NULL,
            search_item_key TEXT NOT NULL,
            file_key TEXT,
            repository_full_name TEXT NOT NULL,
            search_item_path TEXT NOT NULL,
            status TEXT NOT NULL,
            next_page INTEGER NOT NULL DEFAULT 1,
            last_processed_commit_sha TEXT,
            listed_commit_count INTEGER NOT NULL DEFAULT 0,
            processed_commit_count INTEGER NOT NULL DEFAULT 0,
            skipped_commit_count INTEGER NOT NULL DEFAULT 0,
            pass_commit_count INTEGER NOT NULL DEFAULT 0,
            drop_commit_count INTEGER NOT NULL DEFAULT 0,
            evidence_unavailable_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            resume_after TEXT,
            error_type TEXT,
            error_message TEXT,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            PRIMARY KEY (batch_id, search_item_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS d0_commit_status (
            batch_id TEXT NOT NULL,
            search_item_key TEXT NOT NULL,
            file_key TEXT,
            repository_id INTEGER,
            repository_full_name TEXT NOT NULL,
            search_item_path TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            status TEXT NOT NULL,
            reason_code TEXT,
            error_type TEXT,
            error_message TEXT,
            raw_commit_path TEXT,
            patch_path TEXT,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, search_item_key, commit_sha)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS commit_details (
            repository_key TEXT NOT NULL,
            repository_id INTEGER,
            repository_full_name TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            raw_commit_path TEXT NOT NULL,
            status TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (repository_key, commit_sha)
        )
        """
    )
    conn.commit()


def init_f2_results_table(conn):
    """Create the F2 migration classifier result table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS f2_results (
            batch_id TEXT NOT NULL,
            search_item_key TEXT NOT NULL,
            file_key TEXT NOT NULL,
            diff_file_key TEXT,
            candidate_evidence_key TEXT NOT NULL,
            repository_id INTEGER,
            repository_full_name TEXT NOT NULL,
            repository_url TEXT,
            commit_sha TEXT NOT NULL,
            commit_url TEXT NOT NULL,
            matched_changed_path TEXT NOT NULL,
            changed_files_json TEXT NOT NULL DEFAULT '[]',
            final_label TEXT NOT NULL,
            classification_json TEXT NOT NULL,
            signals_json TEXT NOT NULL,
            review_evidence_json TEXT NOT NULL DEFAULT '[]',
            quality_json TEXT NOT NULL DEFAULT '{}',
            reason_codes_json TEXT NOT NULL,
            raw_commit_path TEXT,
            patch_path TEXT,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, search_item_key, commit_sha),
            FOREIGN KEY (batch_id, search_item_key, commit_sha)
                REFERENCES d0_results (batch_id, search_item_key, commit_sha),
            FOREIGN KEY (file_key) REFERENCES file_snapshots (file_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_f2_results_batch_label
        ON f2_results (batch_id, final_label)
        """
    )
    _ensure_columns(
        conn,
        "f2_results",
        {
            "repository_url": "TEXT",
            "changed_files_json": "TEXT NOT NULL DEFAULT '[]'",
            "quality_json": "TEXT NOT NULL DEFAULT '{}'",
        },
    )
    conn.commit()


def init_db(conn):
    """Create the collector storage schema without deleting existing data."""
    init_query_pages_table(conn)
    init_repositories_table(conn)
    init_raw_search_items_table(conn)
    init_raw_search_item_occurrences_table(conn)
    backfill_raw_search_item_occurrences(conn)
    init_f0_results_table(conn)
    init_files_table(conn)
    init_file_fetch_results_table(conn)
    init_f1_results_table(conn)
    init_diff_evidence_table(conn)
    init_d0_history_tables(conn)
    init_f2_results_table(conn)


def write_raw_response(batch_id, response_kind, response_key, payload, root=None):
    """Write one raw GitHub API response and return its path."""
    prefix = RAW_RESPONSE_PREFIXES.get(response_kind)
    if prefix is None:
        valid_kinds = ", ".join(sorted(RAW_RESPONSE_PREFIXES))
        raise KeyError(f"unknown raw response kind: {response_kind}. valid kinds: {valid_kinds}")

    raw_dir = project_paths(root)["raw_github"] / str(batch_id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = raw_dir / f"{prefix}_{response_key}.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path


def write_raw_patch(batch_id, response_key, patch_text, root=None):
    """Write one raw changed-file patch and return its path."""
    raw_dir = project_paths(root)["raw_github"] / str(batch_id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe_key = hashlib.sha256(str(response_key).encode("utf-8")).hexdigest()
    output_path = raw_dir / f"diff_file_{safe_key}.patch"
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(str(patch_text or ""))
        if patch_text and not str(patch_text).endswith("\n"):
            handle.write("\n")
    return output_path


def _write_jsonl_rows(rows, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_rows = [dict(row) for row in rows]
    normalized_rows.sort(
        key=lambda row: row.get("candidate_key") or row.get("candidate_evidence_key") or ""
    )
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in normalized_rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return output_path


def write_batch_export(rows, batch_id, root=None):
    """Write export-eligible candidate rows for one batch as JSONL."""
    output_path = project_paths(root)["report_batches"] / str(batch_id) / "export_candidates.jsonl"
    return _write_jsonl_rows(rows, output_path)


def write_non_exported_candidates(rows, batch_id, root=None):
    """Write non-exported candidate rows for one batch as JSONL."""
    output_path = project_paths(root)["report_batches"] / str(batch_id) / "non_exported_candidates.jsonl"
    return _write_jsonl_rows(rows, output_path)


def upsert_query_page(
    conn,
    batch_id,
    query,
    page,
    payload,
    raw_path,
    new_unique_item_count=0,
    duplicate_item_count=0,
    fetched_at=None,
):
    """Insert one query page row, or return the existing row without overwriting it."""
    page_size = int(query["page_size"])
    page_key = query_page_key(query["query_text"], page, page_size)
    existing = conn.execute(
        "SELECT * FROM query_pages WHERE query_page_key = ?",
        (page_key,),
    ).fetchone()
    if existing:
        row = dict(existing)
        row["status"] = "existing"
        return row

    item_count = len(payload.get("items", []))
    duplicate_ratio = duplicate_item_count / item_count if item_count else 0.0
    checked_at = fetched_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    row = {
        "query_page_key": page_key,
        "batch_id": batch_id,
        "query_key": query["query_key"],
        "query_group": query["query_group"],
        "page": int(page),
        "page_size": page_size,
        "total_count": int(payload.get("total_count", item_count)),
        "item_count": item_count,
        "new_unique_item_count": int(new_unique_item_count),
        "duplicate_item_count": int(duplicate_item_count),
        "duplicate_ratio": duplicate_ratio,
        "raw_path": str(raw_path),
        "fetched_at": checked_at,
    }
    conn.execute(
        """
        INSERT INTO query_pages (
            query_page_key,
            batch_id,
            query_key,
            query_group,
            page,
            page_size,
            total_count,
            item_count,
            new_unique_item_count,
            duplicate_item_count,
            duplicate_ratio,
            raw_path,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(row.values()),
    )
    conn.commit()
    row["status"] = "new"
    return row


def store_search_page(conn, batch_id, query, page, payload, root=None, fetched_at=None):
    """Store one fixture GitHub code search page without calling the GitHub API."""
    page_size = int(query["page_size"])
    page_key = query_page_key(query["query_text"], page, page_size)
    existing_page = conn.execute(
        "SELECT raw_path FROM query_pages WHERE query_page_key = ?",
        (page_key,),
    ).fetchone()
    if existing_page:
        return {
            "batch_id": batch_id,
            "query_page_key": page_key,
            "status": "existing",
            "raw_path": existing_page["raw_path"],
            "raw_item_seen_count": 0,
            "new_unique_item_count": 0,
            "previous_duplicate_count": 0,
            "current_batch_duplicate_count": 0,
            "skipped_query_page_count": 1,
            "raw_search_items": [],
        }

    raw_path = write_raw_response(batch_id, "query_page", page_key, payload, root)
    seen_item_keys = set()
    unique_items = []
    new_unique_item_count = 0
    previous_duplicate_count = 0
    current_batch_duplicate_count = 0

    for item in payload.get("items", []):
        item_key = search_item_key(item["repository"]["id"], item["path"], item["sha"])
        if item_key in seen_item_keys:
            current_batch_duplicate_count += 1
            continue
        seen_item_keys.add(item_key)
        unique_items.append(item)
        existing_item = conn.execute(
            "SELECT 1 FROM raw_search_items WHERE search_item_key = ?",
            (item_key,),
        ).fetchone()
        if existing_item:
            previous_duplicate_count += 1
        else:
            new_unique_item_count += 1

    duplicate_item_count = previous_duplicate_count + current_batch_duplicate_count
    query_page_row = upsert_query_page(
        conn,
        batch_id,
        query,
        page,
        payload,
        raw_path,
        new_unique_item_count,
        duplicate_item_count,
        fetched_at,
    )
    raw_search_items = [
        upsert_raw_search_item(
            conn,
            batch_id,
            query["query_key"],
            page_key,
            item,
            raw_path,
        )
        for item in unique_items
    ]

    return {
        "batch_id": batch_id,
        "query_page_key": page_key,
        "status": query_page_row["status"],
        "raw_path": str(raw_path),
        "raw_item_seen_count": len(payload.get("items", [])),
        "new_unique_item_count": new_unique_item_count,
        "previous_duplicate_count": previous_duplicate_count,
        "current_batch_duplicate_count": current_batch_duplicate_count,
        "skipped_query_page_count": 0,
        "raw_search_items": raw_search_items,
    }


def upsert_repository(conn, batch_id, repository):
    """Insert or update one GitHub repository metadata row."""
    repo_id = int(repository["id"])
    repo_key = repository_key(repo_id)
    full_name = repository["full_name"]
    html_url = repository.get("html_url") or repository.get("url")

    existing = conn.execute(
        "SELECT first_seen_batch_id FROM repositories WHERE repository_key = ?",
        (repo_key,),
    ).fetchone()
    status = "existing" if existing else "new"
    first_seen_batch_id = existing["first_seen_batch_id"] if existing else batch_id

    conn.execute(
        """
        INSERT INTO repositories (
            repository_key,
            repository_id,
            full_name,
            html_url,
            first_seen_batch_id,
            last_seen_batch_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(repository_key) DO UPDATE SET
            full_name = excluded.full_name,
            html_url = excluded.html_url,
            last_seen_batch_id = excluded.last_seen_batch_id
        """,
        (repo_key, repo_id, full_name, html_url, first_seen_batch_id, batch_id),
    )
    conn.commit()

    return {
        "repository_key": repo_key,
        "repository_id": repo_id,
        "full_name": full_name,
        "html_url": html_url,
        "status": status,
        "first_seen_batch_id": first_seen_batch_id,
        "last_seen_batch_id": batch_id,
    }


def upsert_raw_search_item(conn, batch_id, query_key, query_page_key, item, raw_query_page_path):
    """Insert or update one raw GitHub code search item row."""
    repository = item["repository"]
    repo_row = upsert_repository(conn, batch_id, repository)
    normalized_path = normalize_path(item["path"])
    item_key = search_item_key(repository["id"], normalized_path, item["sha"])

    existing = conn.execute(
        "SELECT first_seen_batch_id FROM raw_search_items WHERE search_item_key = ?",
        (item_key,),
    ).fetchone()
    status = "existing" if existing else "new"
    first_seen_batch_id = existing["first_seen_batch_id"] if existing else batch_id
    repository_url = repository.get("html_url") or repository.get("url")
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    conn.execute(
        """
        INSERT INTO raw_search_items (
            search_item_key,
            batch_id,
            query_key,
            query_page_key,
            repository_key,
            repository_id,
            repository_full_name,
            repository_url,
            path,
            normalized_path,
            blob_sha,
            file_api_url,
            html_url,
            status,
            first_seen_batch_id,
            last_seen_batch_id,
            raw_query_page_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(search_item_key) DO UPDATE SET
            batch_id = excluded.batch_id,
            query_key = excluded.query_key,
            query_page_key = excluded.query_page_key,
            status = excluded.status,
            last_seen_batch_id = excluded.last_seen_batch_id,
            raw_query_page_path = excluded.raw_query_page_path
        """,
        (
            item_key,
            batch_id,
            query_key,
            query_page_key,
            repo_row["repository_key"],
            int(repository["id"]),
            repository["full_name"],
            repository_url,
            item["path"],
            normalized_path,
            item["sha"],
            item["url"],
            item["html_url"],
            status,
            first_seen_batch_id,
            batch_id,
            str(raw_query_page_path),
        ),
    )
    conn.execute(
        """
        INSERT INTO raw_search_item_occurrences (
            search_item_key,
            batch_id,
            query_key,
            query_page_key,
            raw_query_page_path,
            seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(search_item_key, batch_id, query_page_key) DO UPDATE SET
            query_key = excluded.query_key,
            raw_query_page_path = excluded.raw_query_page_path,
            seen_at = excluded.seen_at
        """,
        (
            item_key,
            batch_id,
            query_key,
            query_page_key,
            str(raw_query_page_path),
            checked_at,
        ),
    )
    conn.commit()

    return {
        "search_item_key": item_key,
        "repository_key": repo_row["repository_key"],
        "repository_full_name": repository["full_name"],
        "path": item["path"],
        "normalized_path": normalized_path,
        "blob_sha": item["sha"],
        "status": status,
        "first_seen_batch_id": first_seen_batch_id,
        "last_seen_batch_id": batch_id,
        "raw_query_page_path": str(raw_query_page_path),
    }


def iter_raw_search_items(conn, batch_id, limit=None):
    """Yield raw search item rows for one batch in a stable order."""
    params = [batch_id]
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(0, int(limit)))

    rows = conn.execute(
        f"""
        SELECT
            batch_id,
            search_item_key,
            query_key,
            repository_id,
            repository_full_name,
            repository_url,
            path,
            normalized_path,
            blob_sha,
            file_api_url,
            html_url,
            status,
            first_seen_batch_id,
            last_seen_batch_id,
            raw_query_page_path
        FROM raw_search_items
        WHERE batch_id = ?
        ORDER BY repository_full_name, normalized_path, blob_sha
        {limit_clause}
        """,
        tuple(params),
    ).fetchall()
    for row in rows:
        yield dict(row)


def get_next_unprocessed_f0_batch_id(conn):
    """Return the oldest collected batch with raw items not yet processed by F0."""
    row = conn.execute(
        """
        WITH raw_batches AS (
            SELECT
                raw_search_items.batch_id AS batch_id,
                COUNT(DISTINCT raw_search_items.search_item_key) AS raw_count,
                MIN(query_pages.fetched_at) AS first_fetched_at
            FROM raw_search_items
            INNER JOIN query_pages
                ON query_pages.query_page_key = raw_search_items.query_page_key
            GROUP BY raw_search_items.batch_id
        ),
        f0_batches AS (
            SELECT
                raw_search_items.batch_id AS batch_id,
                COUNT(DISTINCT f0_results.search_item_key) AS f0_count
            FROM raw_search_items
            INNER JOIN f0_results
                ON f0_results.batch_id = raw_search_items.batch_id
                AND f0_results.search_item_key = raw_search_items.search_item_key
            GROUP BY raw_search_items.batch_id
        )
        SELECT raw_batches.batch_id
        FROM raw_batches
        LEFT JOIN f0_batches
            ON f0_batches.batch_id = raw_batches.batch_id
        WHERE raw_batches.raw_count > COALESCE(f0_batches.f0_count, 0)
        ORDER BY raw_batches.first_fetched_at ASC, raw_batches.batch_id ASC
        LIMIT 1
        """
    ).fetchone()
    return row["batch_id"] if row else None


def iter_f0_passed_items(conn, batch_id, limit=None):
    """Yield F0-passed raw search items as the file fetch queue."""
    params = [batch_id]
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(0, int(limit)))

    rows = conn.execute(
        f"""
        SELECT
            f0_results.batch_id AS batch_id,
            raw_search_items.batch_id AS current_raw_batch_id,
            raw_search_items.search_item_key AS search_item_key,
            raw_search_items.query_key AS query_key,
            raw_search_items.repository_key AS repository_key,
            raw_search_items.repository_id AS repository_id,
            raw_search_items.repository_full_name AS repository_full_name,
            raw_search_items.repository_url AS repository_url,
            raw_search_items.path AS path,
            raw_search_items.normalized_path AS normalized_path,
            raw_search_items.blob_sha AS blob_sha,
            raw_search_items.file_api_url AS file_api_url,
            raw_search_items.html_url AS html_url,
            raw_search_items.raw_query_page_path AS raw_query_page_path,
            f0_results.source_kind AS source_kind,
            f0_results.reason_codes_json AS f0_reason_codes_json,
            f0_results.checked_at AS f0_checked_at
        FROM f0_results
        INNER JOIN raw_search_items
            ON raw_search_items.search_item_key = f0_results.search_item_key
        WHERE f0_results.batch_id = ?
            AND f0_results.passed = 1
        ORDER BY
            raw_search_items.repository_full_name,
            raw_search_items.normalized_path,
            raw_search_items.blob_sha
        {limit_clause}
        """,
        tuple(params),
    ).fetchall()
    for row in rows:
        item = dict(row)
        item["f0_reason_codes"] = json.loads(item.pop("f0_reason_codes_json"))
        yield item


def read_file_snapshot(conn, key):
    """Return one stored file snapshot summary by file key, if it exists."""
    row = conn.execute(
        """
        SELECT
            file_key,
            repository_full_name,
            path,
            normalized_path,
            blob_sha,
            encoding,
            content_size,
            raw_file_path,
            first_seen_batch_id,
            last_seen_batch_id
        FROM file_snapshots
        WHERE file_key = ?
        """,
        (key,),
    ).fetchone()
    return dict(row) if row else None


def iter_files_for_f1(conn, batch_id, limit=None):
    """Yield fetched F0-passed file snapshots as the F1 input queue."""
    params = [batch_id]
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(0, int(limit)))

    rows = conn.execute(
        f"""
        SELECT
            f0_results.batch_id AS batch_id,
            raw_search_items.batch_id AS current_raw_batch_id,
            raw_search_items.search_item_key AS search_item_key,
            raw_search_items.query_key AS query_key,
            raw_search_items.repository_key AS repository_key,
            raw_search_items.repository_id AS repository_id,
            raw_search_items.repository_full_name AS repository_full_name,
            raw_search_items.repository_url AS repository_url,
            raw_search_items.path AS path,
            raw_search_items.normalized_path AS normalized_path,
            raw_search_items.blob_sha AS blob_sha,
            raw_search_items.file_api_url AS file_api_url,
            raw_search_items.html_url AS html_url,
            f0_results.source_kind AS source_kind,
            f0_results.reason_codes_json AS f0_reason_codes_json,
            f0_results.checked_at AS f0_checked_at,
            file_snapshots.file_key AS file_key,
            file_snapshots.encoding AS encoding,
            file_snapshots.content_text AS content_text,
            file_snapshots.content_size AS content_size,
            file_snapshots.raw_file_path AS raw_file_path,
            file_snapshots.fetched_at AS file_fetched_at
        FROM f0_results
        INNER JOIN raw_search_items
            ON raw_search_items.search_item_key = f0_results.search_item_key
        INNER JOIN file_snapshots
            ON file_snapshots.repository_id = raw_search_items.repository_id
            AND file_snapshots.normalized_path = raw_search_items.normalized_path
            AND file_snapshots.blob_sha = raw_search_items.blob_sha
        WHERE f0_results.batch_id = ?
            AND f0_results.passed = 1
        ORDER BY
            raw_search_items.repository_full_name,
            raw_search_items.normalized_path,
            raw_search_items.blob_sha
        {limit_clause}
        """,
        tuple(params),
    ).fetchall()
    for row in rows:
        item = dict(row)
        item["f0_reason_codes"] = json.loads(item.pop("f0_reason_codes_json"))
        yield item


def iter_f1_passed_items(conn, batch_id, limit=None):
    """Yield F1-passed rows as the D0 diff evidence input queue."""
    params = [batch_id]
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(0, int(limit)))

    rows = conn.execute(
        f"""
        SELECT
            f1_results.batch_id AS batch_id,
            raw_search_items.batch_id AS current_raw_batch_id,
            raw_search_items.search_item_key AS search_item_key,
            raw_search_items.query_key AS query_key,
            raw_search_items.repository_key AS repository_key,
            raw_search_items.repository_id AS repository_id,
            raw_search_items.repository_full_name AS repository_full_name,
            raw_search_items.repository_url AS repository_url,
            raw_search_items.path AS search_item_path,
            raw_search_items.normalized_path AS normalized_path,
            raw_search_items.blob_sha AS blob_sha,
            raw_search_items.file_api_url AS file_api_url,
            raw_search_items.html_url AS search_item_html_url,
            raw_search_items.raw_query_page_path AS raw_query_page_path,
            file_snapshots.file_key AS file_key,
            file_snapshots.raw_file_path AS raw_file_path,
            f1_results.language AS language,
            f1_results.target_libraries_json AS target_libraries_json,
            f1_results.matched_library_signals_json AS matched_library_signals_json,
            f1_results.matched_pqc_api_signals_json AS matched_pqc_api_signals_json,
            f1_results.matched_provider_signals_json AS matched_provider_signals_json,
            f1_results.library_evidence_json AS library_evidence_json,
            f1_results.strong_signal_evidence_json AS strong_signal_evidence_json,
            f1_results.quality_json AS quality_json,
            f1_results.reason_codes_json AS f1_reason_codes_json,
            f1_results.checked_at AS f1_checked_at
        FROM f1_results
        INNER JOIN raw_search_items
            ON raw_search_items.search_item_key = f1_results.search_item_key
        INNER JOIN file_snapshots
            ON file_snapshots.file_key = f1_results.file_key
        WHERE f1_results.batch_id = ?
            AND f1_results.passed = 1
        ORDER BY
            raw_search_items.repository_full_name,
            raw_search_items.normalized_path,
            raw_search_items.blob_sha
        {limit_clause}
        """,
        tuple(params),
    ).fetchall()
    for row in rows:
        item = dict(row)
        item["target_libraries"] = json.loads(item.pop("target_libraries_json"))
        item["matched_library_signals"] = json.loads(item.pop("matched_library_signals_json"))
        item["matched_pqc_api_signals"] = json.loads(item.pop("matched_pqc_api_signals_json"))
        item["matched_provider_signals"] = json.loads(item.pop("matched_provider_signals_json"))
        item["library_evidence"] = json.loads(item.pop("library_evidence_json"))
        item["strong_signal_evidence"] = json.loads(item.pop("strong_signal_evidence_json"))
        item["quality"] = json.loads(item.pop("quality_json"))
        item["f1_reason_codes"] = json.loads(item.pop("f1_reason_codes_json"))
        yield item


def iter_d0_passed_rows(conn, batch_id, limit=None):
    """Yield D0-passed rows as the F2 migration classifier input queue."""
    params = [batch_id]
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(0, int(limit)))

    rows = conn.execute(
        f"""
        SELECT
            d0_results.batch_id AS batch_id,
            raw_search_items.batch_id AS current_raw_batch_id,
            d0_results.search_item_key AS search_item_key,
            d0_results.file_key AS file_key,
            d0_results.diff_file_key AS diff_file_key,
            raw_search_items.repository_id AS repository_id,
            d0_results.repository_full_name AS repository_full_name,
            raw_search_items.repository_url AS repository_url,
            d0_results.search_item_path AS search_item_path,
            d0_results.commit_sha AS commit_sha,
            d0_results.commit_url AS commit_url,
            d0_results.matched_changed_path AS matched_changed_path,
            d0_results.changed_files_json AS changed_files_json,
            d0_results.review_evidence_json AS review_evidence_json,
            d0_results.reason_codes_json AS d0_reason_codes_json,
            d0_results.raw_commit_path AS raw_commit_path,
            d0_results.patch_path AS patch_path,
            d0_results.evidence_status AS evidence_status,
            d0_results.evidence_reason_code AS evidence_reason_code,
            d0_results.d0_status AS d0_status,
            d0_results.checked_at AS d0_checked_at,
            f1_results.language AS language,
            f1_results.target_libraries_json AS target_libraries_json,
            f1_results.matched_library_signals_json AS matched_library_signals_json,
            f1_results.matched_pqc_api_signals_json AS matched_pqc_api_signals_json,
            f1_results.matched_provider_signals_json AS matched_provider_signals_json,
            f1_results.library_evidence_json AS library_evidence_json,
            f1_results.strong_signal_evidence_json AS strong_signal_evidence_json,
            f1_results.quality_json AS quality_json,
            file_snapshots.raw_file_path AS raw_file_path
        FROM d0_results
        INNER JOIN raw_search_items
            ON raw_search_items.search_item_key = d0_results.search_item_key
        INNER JOIN f1_results
            ON f1_results.batch_id = d0_results.batch_id
            AND f1_results.search_item_key = d0_results.search_item_key
        INNER JOIN file_snapshots
            ON file_snapshots.file_key = d0_results.file_key
        WHERE d0_results.batch_id = ?
            AND d0_results.passed = 1
        ORDER BY
            d0_results.repository_full_name,
            d0_results.search_item_path,
            d0_results.commit_sha
        {limit_clause}
        """,
        tuple(params),
    ).fetchall()
    for row in rows:
        item = dict(row)
        item["changed_files"] = json.loads(item.pop("changed_files_json"))
        item["review_evidence"] = json.loads(item.pop("review_evidence_json"))
        item["d0_reason_codes"] = json.loads(item.pop("d0_reason_codes_json"))
        item["target_libraries"] = json.loads(item.pop("target_libraries_json"))
        item["matched_library_signals"] = json.loads(item.pop("matched_library_signals_json"))
        item["matched_pqc_api_signals"] = json.loads(item.pop("matched_pqc_api_signals_json"))
        item["matched_provider_signals"] = json.loads(item.pop("matched_provider_signals_json"))
        item["library_evidence"] = json.loads(item.pop("library_evidence_json"))
        item["strong_signal_evidence"] = json.loads(item.pop("strong_signal_evidence_json"))
        item["quality"] = json.loads(item.pop("quality_json"))
        yield item


def _file_payload(response):
    """Return a GitHub contents payload from either a raw payload or API wrapper."""
    if isinstance(response, dict) and "payload" in response:
        return response["payload"]
    return response


def _decode_file_content(payload):
    """Decode the textual content from one GitHub contents payload."""
    encoding = (payload.get("encoding") or "plain").lower()
    content = payload.get("content") or ""
    if encoding == "base64":
        compact_content = "".join(str(content).split())
        return base64.b64decode(compact_content).decode("utf-8", errors="replace")
    return str(content)


def upsert_file_snapshot(conn, batch_id, item, response, raw_path, fetched_at=None):
    """Insert or update one fetched file snapshot without duplicating the blob."""
    payload = _file_payload(response)
    normalized_path = normalize_path(item["path"])
    key = file_key(item["repository_id"], normalized_path, item["blob_sha"])
    existing = conn.execute(
        "SELECT first_seen_batch_id FROM file_snapshots WHERE file_key = ?",
        (key,),
    ).fetchone()
    status = "existing" if existing else "new"
    first_seen_batch_id = existing["first_seen_batch_id"] if existing else batch_id
    checked_at = fetched_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    content_text = _decode_file_content(payload)
    content_size = int(payload.get("size") or len(content_text.encode("utf-8")))
    row = {
        "file_key": key,
        "repository_key": item["repository_key"],
        "repository_id": int(item["repository_id"]),
        "repository_full_name": item["repository_full_name"],
        "path": item["path"],
        "normalized_path": normalized_path,
        "blob_sha": item["blob_sha"],
        "file_api_url": item["file_api_url"],
        "html_url": item["html_url"],
        "download_url": payload.get("download_url"),
        "encoding": payload.get("encoding") or "plain",
        "content_text": content_text,
        "content_size": content_size,
        "raw_file_path": str(raw_path),
        "first_seen_batch_id": first_seen_batch_id,
        "last_seen_batch_id": batch_id,
        "fetched_at": checked_at,
    }

    conn.execute(
        """
        INSERT INTO file_snapshots (
            file_key,
            repository_key,
            repository_id,
            repository_full_name,
            path,
            normalized_path,
            blob_sha,
            file_api_url,
            html_url,
            download_url,
            encoding,
            content_text,
            content_size,
            raw_file_path,
            first_seen_batch_id,
            last_seen_batch_id,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_key) DO UPDATE SET
            repository_full_name = excluded.repository_full_name,
            file_api_url = excluded.file_api_url,
            html_url = excluded.html_url,
            download_url = excluded.download_url,
            encoding = excluded.encoding,
            content_text = excluded.content_text,
            content_size = excluded.content_size,
            raw_file_path = excluded.raw_file_path,
            last_seen_batch_id = excluded.last_seen_batch_id,
            fetched_at = excluded.fetched_at
        """,
        tuple(row.values()),
    )
    conn.commit()

    return {
        "status": status,
        "file_key": key,
        "repository_full_name": row["repository_full_name"],
        "path": row["path"],
        "normalized_path": row["normalized_path"],
        "blob_sha": row["blob_sha"],
        "encoding": row["encoding"],
        "content_size": row["content_size"],
        "content_text_length": len(content_text),
        "raw_file_path": row["raw_file_path"],
        "first_seen_batch_id": first_seen_batch_id,
        "last_seen_batch_id": batch_id,
    }


def upsert_file_fetch_result(
    conn,
    batch_id,
    item,
    status,
    file_key_value=None,
    error=None,
    raw_file_path=None,
    checked_at=None,
):
    """Insert or update one file-fetch status row for a search item."""
    timestamp = checked_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    search_key = item["search_item_key"]
    key = file_key_value
    if key is None and all(item.get(name) is not None for name in ("repository_id", "normalized_path", "blob_sha")):
        key = file_key(item["repository_id"], item["normalized_path"], item["blob_sha"])
    existing = conn.execute(
        """
        SELECT attempt_count
        FROM file_fetch_results
        WHERE batch_id = ? AND search_item_key = ?
        """,
        (batch_id, search_key),
    ).fetchone()
    attempt_count = int(existing["attempt_count"]) + 1 if existing else 1
    error_type = type(error).__name__ if error is not None else None
    error_message = str(error)[:1000] if error is not None else None
    conn.execute(
        """
        INSERT INTO file_fetch_results (
            batch_id,
            search_item_key,
            file_key,
            status,
            error_type,
            error_message,
            attempt_count,
            raw_file_path,
            checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id, search_item_key) DO UPDATE SET
            file_key = excluded.file_key,
            status = excluded.status,
            error_type = excluded.error_type,
            error_message = excluded.error_message,
            attempt_count = excluded.attempt_count,
            raw_file_path = excluded.raw_file_path,
            checked_at = excluded.checked_at
        """,
        (
            batch_id,
            search_key,
            key,
            status,
            error_type,
            error_message,
            attempt_count,
            raw_file_path,
            timestamp,
        ),
    )
    conn.commit()
    return {
        "batch_id": batch_id,
        "search_item_key": search_key,
        "file_key": key,
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "attempt_count": attempt_count,
        "raw_file_path": raw_file_path,
        "checked_at": timestamp,
    }


def upsert_f0_result(conn, batch_id, row):
    """Insert or update one F0 path quality result row."""
    existing = conn.execute(
        """
        SELECT 1 FROM f0_results
        WHERE batch_id = ? AND search_item_key = ?
        """,
        (batch_id, row["search_item_key"]),
    ).fetchone()
    status = "updated" if existing else "new"
    reason_codes = list(row.get("reason_codes", []))
    checked_at = row.get("checked_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    normalized_path = row.get("normalized_path") or normalize_path(row["path"])
    values = {
        "batch_id": batch_id,
        "search_item_key": row["search_item_key"],
        "repository_full_name": row["repository_full_name"],
        "path": row["path"],
        "normalized_path": normalized_path,
        "source_kind": row["source_kind"],
        "passed": bool(row["passed"]),
        "reason_codes": reason_codes,
        "checked_at": checked_at,
    }

    conn.execute(
        """
        INSERT INTO f0_results (
            batch_id,
            search_item_key,
            repository_full_name,
            path,
            normalized_path,
            source_kind,
            passed,
            reason_codes_json,
            checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id, search_item_key) DO UPDATE SET
            repository_full_name = excluded.repository_full_name,
            path = excluded.path,
            normalized_path = excluded.normalized_path,
            source_kind = excluded.source_kind,
            passed = excluded.passed,
            reason_codes_json = excluded.reason_codes_json,
            checked_at = excluded.checked_at
        """,
        (
            values["batch_id"],
            values["search_item_key"],
            values["repository_full_name"],
            values["path"],
            values["normalized_path"],
            values["source_kind"],
            int(values["passed"]),
            json.dumps(reason_codes, ensure_ascii=True, sort_keys=True),
            values["checked_at"],
        ),
    )
    conn.commit()

    values["status"] = status
    return values


def upsert_f1_result(conn, batch_id, row):
    """Insert or update one F1 static candidate result row."""
    existing = conn.execute(
        """
        SELECT 1 FROM f1_results
        WHERE batch_id = ? AND search_item_key = ?
        """,
        (batch_id, row["search_item_key"]),
    ).fetchone()
    status = "updated" if existing else "new"
    values = {
        "batch_id": batch_id,
        "search_item_key": row["search_item_key"],
        "file_key": row["file_key"],
        "path": row["path"],
        "language": row.get("language"),
        "passed": bool(row["passed"]),
        "target_libraries": list(row.get("target_libraries", [])),
        "matched_library_signals": list(row.get("matched_library_signals", [])),
        "matched_pqc_api_signals": list(row.get("matched_pqc_api_signals", [])),
        "matched_provider_signals": list(row.get("matched_provider_signals", [])),
        "library_evidence": list(row.get("library_evidence", [])),
        "strong_signal_evidence": list(row.get("strong_signal_evidence", [])),
        "quality": dict(row.get("quality", {})),
        "reason_codes": list(row.get("reason_codes", [])),
        "raw_file_path": row["raw_file_path"],
        "checked_at": row.get("checked_at")
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    conn.execute(
        """
        INSERT INTO f1_results (
            batch_id,
            search_item_key,
            file_key,
            path,
            language,
            passed,
            target_libraries_json,
            matched_library_signals_json,
            matched_pqc_api_signals_json,
            matched_provider_signals_json,
            library_evidence_json,
            strong_signal_evidence_json,
            quality_json,
            reason_codes_json,
            raw_file_path,
            checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id, search_item_key) DO UPDATE SET
            file_key = excluded.file_key,
            path = excluded.path,
            language = excluded.language,
            passed = excluded.passed,
            target_libraries_json = excluded.target_libraries_json,
            matched_library_signals_json = excluded.matched_library_signals_json,
            matched_pqc_api_signals_json = excluded.matched_pqc_api_signals_json,
            matched_provider_signals_json = excluded.matched_provider_signals_json,
            library_evidence_json = excluded.library_evidence_json,
            strong_signal_evidence_json = excluded.strong_signal_evidence_json,
            quality_json = excluded.quality_json,
            reason_codes_json = excluded.reason_codes_json,
            raw_file_path = excluded.raw_file_path,
            checked_at = excluded.checked_at
        """,
        (
            values["batch_id"],
            values["search_item_key"],
            values["file_key"],
            values["path"],
            values["language"],
            int(values["passed"]),
            json.dumps(values["target_libraries"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["matched_library_signals"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["matched_pqc_api_signals"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["matched_provider_signals"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["library_evidence"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["strong_signal_evidence"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["quality"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["reason_codes"], ensure_ascii=True, sort_keys=True),
            values["raw_file_path"],
            values["checked_at"],
        ),
    )
    conn.commit()

    values["status"] = status
    return values


def _d0_diff_file_key(row):
    key = row.get("diff_file_key")
    if key:
        return key
    repository_id = row.get("repository_id")
    commit_sha = row.get("commit_sha")
    path = row.get("matched_changed_path") or row.get("search_item_path")
    if repository_id is None or not commit_sha or not path:
        return None
    return make_diff_file_key(repository_id, commit_sha, path)


def _timestamp(value=None):
    return value or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repository_cache_key(item):
    repository_id = item.get("repository_id")
    if repository_id is not None:
        return f"id:{int(repository_id)}"
    return f"name:{item['repository_full_name']}"


def read_d0_history_state(conn, batch_id, search_item_key):
    """Return saved D0 history traversal state for one file, if present."""
    row = conn.execute(
        """
        SELECT *
        FROM d0_history_state
        WHERE batch_id = ? AND search_item_key = ?
        """,
        (batch_id, search_item_key),
    ).fetchone()
    return dict(row) if row else None


def upsert_d0_history_state(
    conn,
    batch_id,
    item,
    *,
    status,
    next_page=1,
    last_processed_commit_sha=None,
    counters=None,
    resume_after=None,
    error=None,
    completed_at=None,
    checked_at=None,
):
    """Insert or update resumable D0 history traversal state for one file."""
    counters = counters or {}
    timestamp = _timestamp(checked_at)
    error_type = type(error).__name__ if error else None
    error_message = str(error) if error else None
    values = {
        "batch_id": batch_id,
        "search_item_key": item["search_item_key"],
        "file_key": item.get("file_key"),
        "repository_full_name": item["repository_full_name"],
        "search_item_path": normalize_path(
            item.get("normalized_path") or item.get("search_item_path") or item.get("path")
        ),
        "status": status,
        "next_page": max(1, int(next_page or 1)),
        "last_processed_commit_sha": last_processed_commit_sha,
        "listed_commit_count": int(counters.get("listed_commit_count", 0)),
        "processed_commit_count": int(counters.get("processed_commit_count", 0)),
        "skipped_commit_count": int(counters.get("skipped_commit_count", 0)),
        "pass_commit_count": int(counters.get("pass_commit_count", 0)),
        "drop_commit_count": int(counters.get("drop_commit_count", 0)),
        "evidence_unavailable_count": int(counters.get("evidence_unavailable_count", 0)),
        "error_count": int(counters.get("error_count", 0)),
        "resume_after": resume_after,
        "error_type": error_type,
        "error_message": error_message,
        "updated_at": timestamp,
        "completed_at": completed_at,
    }
    conn.execute(
        """
        INSERT INTO d0_history_state (
            batch_id,
            search_item_key,
            file_key,
            repository_full_name,
            search_item_path,
            status,
            next_page,
            last_processed_commit_sha,
            listed_commit_count,
            processed_commit_count,
            skipped_commit_count,
            pass_commit_count,
            drop_commit_count,
            evidence_unavailable_count,
            error_count,
            resume_after,
            error_type,
            error_message,
            updated_at,
            completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id, search_item_key) DO UPDATE SET
            file_key = excluded.file_key,
            repository_full_name = excluded.repository_full_name,
            search_item_path = excluded.search_item_path,
            status = excluded.status,
            next_page = excluded.next_page,
            last_processed_commit_sha = excluded.last_processed_commit_sha,
            listed_commit_count = excluded.listed_commit_count,
            processed_commit_count = excluded.processed_commit_count,
            skipped_commit_count = excluded.skipped_commit_count,
            pass_commit_count = excluded.pass_commit_count,
            drop_commit_count = excluded.drop_commit_count,
            evidence_unavailable_count = excluded.evidence_unavailable_count,
            error_count = excluded.error_count,
            resume_after = excluded.resume_after,
            error_type = excluded.error_type,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at,
            completed_at = excluded.completed_at
        """,
        (
            values["batch_id"],
            values["search_item_key"],
            values["file_key"],
            values["repository_full_name"],
            values["search_item_path"],
            values["status"],
            values["next_page"],
            values["last_processed_commit_sha"],
            values["listed_commit_count"],
            values["processed_commit_count"],
            values["skipped_commit_count"],
            values["pass_commit_count"],
            values["drop_commit_count"],
            values["evidence_unavailable_count"],
            values["error_count"],
            values["resume_after"],
            values["error_type"],
            values["error_message"],
            values["updated_at"],
            values["completed_at"],
        ),
    )
    conn.commit()
    return values


def read_d0_commit_status(conn, batch_id, search_item_key, commit_sha):
    """Return D0 status for one already-seen file commit, if present."""
    row = conn.execute(
        """
        SELECT *
        FROM d0_commit_status
        WHERE batch_id = ? AND search_item_key = ? AND commit_sha = ?
        """,
        (batch_id, search_item_key, commit_sha),
    ).fetchone()
    return dict(row) if row else None


def upsert_d0_commit_status(
    conn,
    batch_id,
    item,
    commit_sha,
    *,
    status,
    reason_code=None,
    error=None,
    raw_commit_path=None,
    patch_path=None,
    checked_at=None,
):
    """Insert or update the processing status for one file commit."""
    timestamp = _timestamp(checked_at)
    error_type = type(error).__name__ if error else None
    error_message = str(error) if error else None
    values = {
        "batch_id": batch_id,
        "search_item_key": item["search_item_key"],
        "file_key": item.get("file_key"),
        "repository_id": item.get("repository_id"),
        "repository_full_name": item["repository_full_name"],
        "search_item_path": normalize_path(
            item.get("normalized_path") or item.get("search_item_path") or item.get("path")
        ),
        "commit_sha": commit_sha,
        "status": status,
        "reason_code": reason_code,
        "error_type": error_type,
        "error_message": error_message,
        "raw_commit_path": raw_commit_path,
        "patch_path": patch_path,
        "checked_at": timestamp,
    }
    conn.execute(
        """
        INSERT INTO d0_commit_status (
            batch_id,
            search_item_key,
            file_key,
            repository_id,
            repository_full_name,
            search_item_path,
            commit_sha,
            status,
            reason_code,
            error_type,
            error_message,
            raw_commit_path,
            patch_path,
            checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id, search_item_key, commit_sha) DO UPDATE SET
            file_key = excluded.file_key,
            repository_id = excluded.repository_id,
            repository_full_name = excluded.repository_full_name,
            search_item_path = excluded.search_item_path,
            status = excluded.status,
            reason_code = excluded.reason_code,
            error_type = excluded.error_type,
            error_message = excluded.error_message,
            raw_commit_path = excluded.raw_commit_path,
            patch_path = excluded.patch_path,
            checked_at = excluded.checked_at
        """,
        (
            values["batch_id"],
            values["search_item_key"],
            values["file_key"],
            values["repository_id"],
            values["repository_full_name"],
            values["search_item_path"],
            values["commit_sha"],
            values["status"],
            values["reason_code"],
            values["error_type"],
            values["error_message"],
            values["raw_commit_path"],
            values["patch_path"],
            values["checked_at"],
        ),
    )
    conn.commit()
    return values


def read_commit_detail(conn, item, commit_sha):
    """Return cached raw commit metadata for one repository commit, if present."""
    row = conn.execute(
        """
        SELECT *
        FROM commit_details
        WHERE repository_key = ? AND commit_sha = ? AND status = 'fetched'
        """,
        (_repository_cache_key(item), commit_sha),
    ).fetchone()
    return dict(row) if row else None


def upsert_commit_detail(
    conn,
    item,
    commit_sha,
    raw_commit_path,
    *,
    status="fetched",
    error=None,
    fetched_at=None,
):
    """Insert or update the repository-scoped commit detail cache."""
    timestamp = _timestamp(fetched_at)
    error_type = type(error).__name__ if error else None
    error_message = str(error) if error else None
    values = {
        "repository_key": _repository_cache_key(item),
        "repository_id": item.get("repository_id"),
        "repository_full_name": item["repository_full_name"],
        "commit_sha": commit_sha,
        "raw_commit_path": raw_commit_path,
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "fetched_at": timestamp,
    }
    conn.execute(
        """
        INSERT INTO commit_details (
            repository_key,
            repository_id,
            repository_full_name,
            commit_sha,
            raw_commit_path,
            status,
            error_type,
            error_message,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repository_key, commit_sha) DO UPDATE SET
            repository_id = excluded.repository_id,
            repository_full_name = excluded.repository_full_name,
            raw_commit_path = excluded.raw_commit_path,
            status = excluded.status,
            error_type = excluded.error_type,
            error_message = excluded.error_message,
            fetched_at = excluded.fetched_at
        """,
        (
            values["repository_key"],
            values["repository_id"],
            values["repository_full_name"],
            values["commit_sha"],
            values["raw_commit_path"],
            values["status"],
            values["error_type"],
            values["error_message"],
            values["fetched_at"],
        ),
    )
    conn.commit()
    return values


def upsert_diff_evidence(conn, batch_id, row):
    """Insert or update one D0 exact diff evidence result row."""
    existing = conn.execute(
        """
        SELECT 1 FROM d0_results
        WHERE batch_id = ? AND search_item_key = ? AND commit_sha = ?
        """,
        (batch_id, row["search_item_key"], row["commit_sha"]),
    ).fetchone()
    status = "updated" if existing else "new"
    values = {
        "batch_id": batch_id,
        "search_item_key": row["search_item_key"],
        "file_key": row["file_key"],
        "diff_file_key": _d0_diff_file_key(row),
        "repository_full_name": row["repository_full_name"],
        "search_item_path": row["search_item_path"],
        "commit_sha": row["commit_sha"],
        "commit_url": row["commit_url"],
        "matched_changed_path": row.get("matched_changed_path"),
        "exact_path_match": bool(row.get("exact_path_match")),
        "patch_available": bool(row.get("patch_available")),
        "passed": bool(row.get("passed")),
        "changed_files": list(row.get("changed_files", [])),
        "review_evidence": list(row.get("review_evidence", [])),
        "reason_codes": list(row.get("reason_codes", [])),
        "raw_commit_path": row["raw_commit_path"],
        "patch_path": row.get("patch_path"),
        "evidence_status": row.get("evidence_status") or "processed",
        "evidence_reason_code": row.get("evidence_reason_code"),
        "d0_status": row.get("d0_status") or "processed",
        "checked_at": row.get("checked_at")
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    conn.execute(
        """
        INSERT INTO d0_results (
            batch_id,
            search_item_key,
            file_key,
            diff_file_key,
            repository_full_name,
            search_item_path,
            commit_sha,
            commit_url,
            matched_changed_path,
            exact_path_match,
            patch_available,
            passed,
            changed_files_json,
            review_evidence_json,
            reason_codes_json,
            raw_commit_path,
            patch_path,
            evidence_status,
            evidence_reason_code,
            d0_status,
            checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id, search_item_key, commit_sha) DO UPDATE SET
            file_key = excluded.file_key,
            diff_file_key = excluded.diff_file_key,
            repository_full_name = excluded.repository_full_name,
            search_item_path = excluded.search_item_path,
            commit_url = excluded.commit_url,
            matched_changed_path = excluded.matched_changed_path,
            exact_path_match = excluded.exact_path_match,
            patch_available = excluded.patch_available,
            passed = excluded.passed,
            changed_files_json = excluded.changed_files_json,
            review_evidence_json = excluded.review_evidence_json,
            reason_codes_json = excluded.reason_codes_json,
            raw_commit_path = excluded.raw_commit_path,
            patch_path = excluded.patch_path,
            evidence_status = excluded.evidence_status,
            evidence_reason_code = excluded.evidence_reason_code,
            d0_status = excluded.d0_status,
            checked_at = excluded.checked_at
        """,
        (
            values["batch_id"],
            values["search_item_key"],
            values["file_key"],
            values["diff_file_key"],
            values["repository_full_name"],
            values["search_item_path"],
            values["commit_sha"],
            values["commit_url"],
            values["matched_changed_path"],
            int(values["exact_path_match"]),
            int(values["patch_available"]),
            int(values["passed"]),
            json.dumps(values["changed_files"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["review_evidence"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["reason_codes"], ensure_ascii=True, sort_keys=True),
            values["raw_commit_path"],
            values["patch_path"],
            values["evidence_status"],
            values["evidence_reason_code"],
            values["d0_status"],
            values["checked_at"],
        ),
    )
    conn.commit()

    values["status"] = status
    return values


def _f2_candidate_evidence_key(batch_id, row):
    existing = row.get("candidate_evidence_key")
    if existing:
        return existing
    key_parts = [
        str(batch_id),
        str(row.get("search_item_key") or ""),
        str(row.get("commit_sha") or ""),
        str(row.get("diff_file_key") or ""),
    ]
    digest = hashlib.sha256("\n".join(key_parts).encode("utf-8")).hexdigest()[:24]
    return f"f2:{digest}"


def upsert_f2_result(conn, batch_id, row):
    """Insert or update one F2 migration classifier result row."""
    existing = conn.execute(
        """
        SELECT 1 FROM f2_results
        WHERE batch_id = ? AND search_item_key = ? AND commit_sha = ?
        """,
        (batch_id, row["search_item_key"], row["commit_sha"]),
    ).fetchone()
    status = "updated" if existing else "new"
    values = {
        "batch_id": batch_id,
        "search_item_key": row["search_item_key"],
        "file_key": row["file_key"],
        "diff_file_key": row.get("diff_file_key"),
        "candidate_evidence_key": _f2_candidate_evidence_key(batch_id, row),
        "repository_id": row.get("repository_id"),
        "repository_full_name": row["repository_full_name"],
        "repository_url": row.get("repository_url"),
        "commit_sha": row["commit_sha"],
        "commit_url": row["commit_url"],
        "matched_changed_path": normalize_path(row["matched_changed_path"]),
        "changed_files": list(row.get("changed_files", [])),
        "final_label": row["final_label"],
        "classification": dict(row.get("classification", {})),
        "signals": dict(row.get("signals", {})),
        "review_evidence": list(row.get("review_evidence", [])),
        "quality": dict(row.get("quality", {})),
        "reason_codes": list(row.get("reason_codes", [])),
        "raw_commit_path": row.get("raw_commit_path"),
        "patch_path": row.get("patch_path"),
        "checked_at": row.get("checked_at")
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    conn.execute(
        """
        INSERT INTO f2_results (
            batch_id,
            search_item_key,
            file_key,
            diff_file_key,
            candidate_evidence_key,
            repository_id,
            repository_full_name,
            repository_url,
            commit_sha,
            commit_url,
            matched_changed_path,
            changed_files_json,
            final_label,
            classification_json,
            signals_json,
            review_evidence_json,
            quality_json,
            reason_codes_json,
            raw_commit_path,
            patch_path,
            checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_id, search_item_key, commit_sha) DO UPDATE SET
            file_key = excluded.file_key,
            diff_file_key = excluded.diff_file_key,
            candidate_evidence_key = excluded.candidate_evidence_key,
            repository_id = excluded.repository_id,
            repository_full_name = excluded.repository_full_name,
            repository_url = excluded.repository_url,
            commit_url = excluded.commit_url,
            matched_changed_path = excluded.matched_changed_path,
            changed_files_json = excluded.changed_files_json,
            final_label = excluded.final_label,
            classification_json = excluded.classification_json,
            signals_json = excluded.signals_json,
            review_evidence_json = excluded.review_evidence_json,
            quality_json = excluded.quality_json,
            reason_codes_json = excluded.reason_codes_json,
            raw_commit_path = excluded.raw_commit_path,
            patch_path = excluded.patch_path,
            checked_at = excluded.checked_at
        """,
        (
            values["batch_id"],
            values["search_item_key"],
            values["file_key"],
            values["diff_file_key"],
            values["candidate_evidence_key"],
            values["repository_id"],
            values["repository_full_name"],
            values["repository_url"],
            values["commit_sha"],
            values["commit_url"],
            values["matched_changed_path"],
            json.dumps(values["changed_files"], ensure_ascii=True, sort_keys=True),
            values["final_label"],
            json.dumps(values["classification"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["signals"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["review_evidence"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["quality"], ensure_ascii=True, sort_keys=True),
            json.dumps(values["reason_codes"], ensure_ascii=True, sort_keys=True),
            values["raw_commit_path"],
            values["patch_path"],
            values["checked_at"],
        ),
    )
    conn.commit()

    values["status"] = status
    return values


def _json_column(row, key, default):
    value = row.get(key)
    if value not in (None, ""):
        return value
    json_value = row.get(f"{key}_json")
    return json.loads(json_value) if json_value else default


def _f2_export_candidate_row(row):
    item = dict(row)
    item["changed_files"] = _json_column(item, "changed_files", [])
    item["classification"] = _json_column(item, "classification", {})
    item["signals"] = _json_column(item, "signals", {})
    item["review_evidence"] = _json_column(item, "review_evidence", [])
    item["quality"] = _json_column(item, "quality", {})
    item["reason_codes"] = _json_column(item, "reason_codes", [])
    return item


def read_export_candidates(conn, batch_id=None):
    """Return stored F2 rows as export-candidate input rows."""
    params = []
    batch_filter = ""
    if batch_id is not None:
        batch_filter = "WHERE batch_id = ?"
        params.append(batch_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM f2_results
        {batch_filter}
        ORDER BY checked_at, batch_id, repository_full_name, matched_changed_path, commit_sha
        """,
        tuple(params),
    ).fetchall()
    return [_f2_export_candidate_row(row) for row in rows]


def _batch_filter(alias, batch_id, params):
    if batch_id is None:
        return ""
    params.append(batch_id)
    return f"AND {alias}.batch_id = ?"


def _count_query(conn, sql, params=()):
    return int(conn.execute(sql, tuple(params)).fetchone()[0])


def compute_pipeline_handoff_status(conn, batch_id=None):
    """Return pending and error counts at each pipeline handoff boundary."""
    raw_params = []
    raw_batch_filter = _batch_filter("r", batch_id, raw_params)
    f0_params = []
    f0_batch_filter = _batch_filter("f0", batch_id, f0_params)
    f1_params = []
    f1_batch_filter = _batch_filter("f1", batch_id, f1_params)
    d0_params = []
    d0_batch_filter = _batch_filter("d0", batch_id, d0_params)
    status = {
        "batch_id": batch_id,
        "f0": {
            "pending": _count_query(
                conn,
                f"""
                SELECT COUNT(*)
                FROM raw_search_items AS r
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM f0_results AS f0
                    WHERE f0.search_item_key = r.search_item_key
                )
                {raw_batch_filter}
                """,
                raw_params,
            ),
            "error": 0,
        },
        "files": {
            "pending": _count_query(
                conn,
                f"""
                SELECT COUNT(*)
                FROM f0_results AS f0
                INNER JOIN raw_search_items AS r
                    ON r.search_item_key = f0.search_item_key
                LEFT JOIN file_snapshots AS fs
                    ON fs.repository_id = r.repository_id
                    AND fs.normalized_path = r.normalized_path
                    AND fs.blob_sha = r.blob_sha
                LEFT JOIN file_fetch_results AS ff
                    ON ff.batch_id = f0.batch_id
                    AND ff.search_item_key = f0.search_item_key
                    AND ff.status = 'error'
                WHERE f0.passed = 1
                    AND fs.file_key IS NULL
                    AND ff.search_item_key IS NULL
                    {f0_batch_filter}
                """,
                f0_params,
            ),
            "error": _count_query(
                conn,
                f"""
                SELECT COUNT(*)
                FROM file_fetch_results AS ff
                WHERE ff.status = 'error'
                {"AND ff.batch_id = ?" if batch_id is not None else ""}
                """,
                (batch_id,) if batch_id is not None else (),
            ),
        },
        "f1": {
            "pending": _count_query(
                conn,
                f"""
                SELECT COUNT(*)
                FROM f0_results AS f0
                INNER JOIN raw_search_items AS r
                    ON r.search_item_key = f0.search_item_key
                INNER JOIN file_snapshots AS fs
                    ON fs.repository_id = r.repository_id
                    AND fs.normalized_path = r.normalized_path
                    AND fs.blob_sha = r.blob_sha
                WHERE f0.passed = 1
                    AND NOT EXISTS (
                        SELECT 1
                        FROM f1_results AS f1
                        WHERE f1.batch_id = f0.batch_id
                            AND f1.search_item_key = f0.search_item_key
                    )
                    {f0_batch_filter}
                """,
                f0_params,
            ),
            "error": 0,
        },
        "d0": {
            "pending": _count_query(
                conn,
                f"""
                SELECT COUNT(*)
                FROM f1_results AS f1
                WHERE f1.passed = 1
                    AND NOT EXISTS (
                        SELECT 1
                        FROM d0_results AS d0
                        WHERE d0.batch_id = f1.batch_id
                            AND d0.search_item_key = f1.search_item_key
                    )
                    {f1_batch_filter}
                """,
                f1_params,
            ),
            "error": 0,
        },
        "f2": {
            "pending": _count_query(
                conn,
                f"""
                SELECT COUNT(*)
                FROM d0_results AS d0
                WHERE d0.passed = 1
                    AND NOT EXISTS (
                        SELECT 1
                        FROM f2_results AS f2
                        WHERE f2.batch_id = d0.batch_id
                            AND f2.search_item_key = d0.search_item_key
                            AND f2.commit_sha = d0.commit_sha
                    )
                    {d0_batch_filter}
                """,
                d0_params,
            ),
            "error": 0,
        },
    }
    status["total_pending"] = sum(stage["pending"] for stage in status.values() if isinstance(stage, dict))
    status["total_error"] = sum(stage["error"] for stage in status.values() if isinstance(stage, dict))
    return status


def _pending_batches(conn, sql, params=(), limit=None):
    rows = conn.execute(sql, tuple(params)).fetchall()
    results = [
        {
            "stage": row["stage"],
            "batch_id": row["batch_id"],
            "pending_count": int(row["pending_count"]),
        }
        for row in rows
    ]
    if limit is not None:
        return results[: max(0, int(limit))]
    return results


def pending_pipeline_batches(conn, stage="all", limit=None, include_errors=False):
    """Return batches that have DB-visible work missing at a later stage."""
    stage = str(stage or "all").lower()
    file_error_filter = "" if include_errors else "AND ff.search_item_key IS NULL"
    queries = {
        "f0": """
            SELECT 'f0' AS stage, r.batch_id AS batch_id, COUNT(*) AS pending_count
            FROM raw_search_items AS r
            WHERE NOT EXISTS (
                SELECT 1 FROM f0_results AS f0
                WHERE f0.search_item_key = r.search_item_key
            )
            GROUP BY r.batch_id
            HAVING pending_count > 0
            ORDER BY r.batch_id
        """,
        "files": """
            SELECT 'files' AS stage, f0.batch_id AS batch_id, COUNT(*) AS pending_count
            FROM f0_results AS f0
            INNER JOIN raw_search_items AS r
                ON r.search_item_key = f0.search_item_key
            LEFT JOIN file_snapshots AS fs
                ON fs.repository_id = r.repository_id
                AND fs.normalized_path = r.normalized_path
                AND fs.blob_sha = r.blob_sha
            LEFT JOIN file_fetch_results AS ff
                ON ff.batch_id = f0.batch_id
                AND ff.search_item_key = f0.search_item_key
                AND ff.status = 'error'
            WHERE f0.passed = 1
                AND fs.file_key IS NULL
                {file_error_filter}
            GROUP BY f0.batch_id
            HAVING pending_count > 0
            ORDER BY f0.batch_id
        """.format(file_error_filter=file_error_filter),
        "f1": """
            SELECT 'f1' AS stage, f0.batch_id AS batch_id, COUNT(*) AS pending_count
            FROM f0_results AS f0
            INNER JOIN raw_search_items AS r
                ON r.search_item_key = f0.search_item_key
            INNER JOIN file_snapshots AS fs
                ON fs.repository_id = r.repository_id
                AND fs.normalized_path = r.normalized_path
                AND fs.blob_sha = r.blob_sha
            WHERE f0.passed = 1
                AND NOT EXISTS (
                    SELECT 1 FROM f1_results AS f1
                    WHERE f1.batch_id = f0.batch_id
                        AND f1.search_item_key = f0.search_item_key
                )
            GROUP BY f0.batch_id
            HAVING pending_count > 0
            ORDER BY f0.batch_id
        """,
        "d0": """
            SELECT 'd0' AS stage, f1.batch_id AS batch_id, COUNT(*) AS pending_count
            FROM f1_results AS f1
            WHERE f1.passed = 1
                AND NOT EXISTS (
                    SELECT 1 FROM d0_results AS d0
                    WHERE d0.batch_id = f1.batch_id
                        AND d0.search_item_key = f1.search_item_key
                )
            GROUP BY f1.batch_id
            HAVING pending_count > 0
            ORDER BY f1.batch_id
        """,
        "f2": """
            SELECT 'f2' AS stage, d0.batch_id AS batch_id, COUNT(*) AS pending_count
            FROM d0_results AS d0
            WHERE d0.passed = 1
                AND NOT EXISTS (
                    SELECT 1 FROM f2_results AS f2
                    WHERE f2.batch_id = d0.batch_id
                        AND f2.search_item_key = d0.search_item_key
                        AND f2.commit_sha = d0.commit_sha
                )
            GROUP BY d0.batch_id
            HAVING pending_count > 0
            ORDER BY d0.batch_id
        """,
    }
    selected = queries if stage == "all" else {stage: queries[stage]}
    batches = []
    for sql in selected.values():
        batches.extend(_pending_batches(conn, sql))
    if limit is not None:
        return batches[: max(0, int(limit))]
    return batches


def _merge_export_row(existing, new_row):
    source_batch_ids = []
    for row in (existing, new_row):
        for batch_id in row.get("source_batch_ids", []):
            if batch_id not in source_batch_ids:
                source_batch_ids.append(batch_id)
    first_batch = existing.get("first_exported_batch_id") or new_row.get("first_exported_batch_id")
    merged = dict(new_row)
    merged["first_exported_batch_id"] = first_batch
    merged["source_batch_ids"] = source_batch_ids
    return merged


def rebuild_cumulative_export(
    conn,
    root=None,
    include_pqc_addition_only=False,
    path_validator=None,
):
    """Rebuild the cumulative export JSONL without blind append."""
    from pqc_collector.filter import build_export_row, is_export_eligible

    export_rows_by_key = {}
    for candidate in read_export_candidates(conn):
        if not is_export_eligible(candidate, include_pqc_addition_only):
            continue
        if path_validator is not None and not path_validator(candidate):
            continue
        export_row = build_export_row(
            candidate,
            include_pqc_addition_only=include_pqc_addition_only,
        )
        key = export_row["candidate_key"]
        if key in export_rows_by_key:
            export_rows_by_key[key] = _merge_export_row(export_rows_by_key[key], export_row)
        else:
            export_rows_by_key[key] = export_row

    output_path = project_paths(root)["exports"] / "migration_candidates.jsonl"
    return _write_jsonl_rows(export_rows_by_key.values(), output_path)
