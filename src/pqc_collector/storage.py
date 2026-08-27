import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pqc_collector.core import (
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
    "commit": "commit",
    "pr": "pr",
}


def connect(path=None, root=None):
    """Open a SQLite connection for collector storage."""
    db_path = path if path is not None else project_paths(root)["data"] / "collector.sqlite"
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


def init_db(conn):
    """Create the collector storage schema without deleting existing data."""
    init_query_pages_table(conn)
    init_repositories_table(conn)
    init_raw_search_items_table(conn)
    init_f0_results_table(conn)


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
            raw_search_items.batch_id AS batch_id,
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
            ON raw_search_items.batch_id = f0_results.batch_id
            AND raw_search_items.search_item_key = f0_results.search_item_key
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
