import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pqc_collector.core import ensure_dirs, project_paths  # noqa: E402
from pqc_collector.collect import (  # noqa: E402
    GitHubClient,
    collect_one_page_batch,
    fetch_search_page_raw,
    make_query,
)
from pqc_collector.pipeline import fetch_file_batch, run_f0_batch, run_f1_batch  # noqa: E402
from pqc_collector.reports import (  # noqa: E402
    report_schemas,
    write_dedupe_summary_report,
    write_query_pages_report,
    write_raw_search_items_report,
    write_schema_preview,
)
from pqc_collector.storage import (  # noqa: E402
    connect,
    get_next_unprocessed_f0_batch_id,
    init_db,
    store_search_page,
    write_raw_response,
)


def load_env_file(path):
    """Load simple KEY=VALUE lines without printing secret values."""
    loaded = []
    if not path.exists():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
            loaded.append(key)
    return loaded


def store_sample_search(batch_id):
    """Store one fixture search page and write Phase 2 collector reports."""
    query = {
        "query_key": "openssl_evp_mlkem_ctx",
        "query_group": "openssl_pqc_api",
        "query_text": "EVP_PKEY_CTX_new_from_name ML-KEM language:C",
        "page_size": 50,
    }
    repository = {
        "id": 123,
        "full_name": "owner/repo",
        "html_url": "https://github.com/owner/repo",
    }
    payload = {
        "total_count": 1,
        "items": [
            {
                "sha": "abc123",
                "path": "src/crypto/kem.c",
                "url": (
                    "https://api.github.com/repos/owner/repo/contents/"
                    "src/crypto/kem.c"
                ),
                "html_url": (
                    "https://github.com/owner/repo/blob/main/src/crypto/kem.c"
                ),
                "repository": repository,
            }
        ],
    }
    conn = connect(root=PROJECT_ROOT)
    try:
        init_db(conn)
        result = store_search_page(conn, batch_id, query, 1, payload, PROJECT_ROOT)
        reports = {
            "query_pages": str(write_query_pages_report(conn, batch_id, root=PROJECT_ROOT)),
            "raw_search_items": str(
                write_raw_search_items_report(conn, batch_id, root=PROJECT_ROOT)
            ),
            "dedupe_summary": str(
                write_dedupe_summary_report(conn, batch_id, root=PROJECT_ROOT)
            ),
        }
        sample_item = conn.execute(
            """
            SELECT search_item_key
            FROM raw_search_items
            WHERE batch_id = ?
            ORDER BY repository_full_name, normalized_path, blob_sha
            LIMIT 1
            """,
            (batch_id,),
        ).fetchone()
    finally:
        conn.close()
    return {
        "batch_id": batch_id,
        "query_page_key": result["query_page_key"],
        "status": result["status"],
        "raw_path": result["raw_path"],
        "raw_item_seen_count": result["raw_item_seen_count"],
        "new_unique_item_count": result["new_unique_item_count"],
        "previous_duplicate_count": result["previous_duplicate_count"],
        "current_batch_duplicate_count": result["current_batch_duplicate_count"],
        "skipped_query_page_count": result["skipped_query_page_count"],
        "report_paths": reports,
        "sample_search_item_key": sample_item["search_item_key"] if sample_item else None,
    }


def _safe_batch_dir(parent, batch_id):
    """Return a batch directory only when it stays inside its expected parent."""
    parent = Path(parent).resolve()
    batch_dir = (parent / batch_id).resolve()
    if batch_dir.parent != parent:
        raise ValueError(f"unsafe batch id: {batch_id}")
    return batch_dir


def cleanup_sample_search(batch_id, apply=False):
    """Remove one sample batch from collector DB and generated batch files."""
    paths = project_paths(PROJECT_ROOT)
    raw_dir = _safe_batch_dir(paths["raw_github"], batch_id)
    report_dir = _safe_batch_dir(paths["report_batches"], batch_id)
    conn = connect(root=PROJECT_ROOT)
    try:
        init_db(conn)
        counts_before = {
            "query_pages": conn.execute(
                "SELECT COUNT(*) FROM query_pages WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()[0],
            "raw_search_items": conn.execute(
                "SELECT COUNT(*) FROM raw_search_items WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()[0],
            "repositories_seen": conn.execute(
                """
                SELECT COUNT(*)
                FROM repositories
                WHERE first_seen_batch_id = ? OR last_seen_batch_id = ?
                """,
                (batch_id, batch_id),
            ).fetchone()[0],
        }
        if apply:
            conn.execute("DELETE FROM raw_search_items WHERE batch_id = ?", (batch_id,))
            conn.execute("DELETE FROM query_pages WHERE batch_id = ?", (batch_id,))
            conn.execute(
                """
                DELETE FROM repositories
                WHERE first_seen_batch_id = ? AND last_seen_batch_id = ?
                """,
                (batch_id, batch_id),
            )
            conn.commit()
    finally:
        conn.close()

    existing_dirs = [path for path in (raw_dir, report_dir) if path.exists()]
    if apply:
        for path in existing_dirs:
            shutil.rmtree(path)

    return {
        "batch_id": batch_id,
        "applied": bool(apply),
        "db_rows_before": counts_before,
        "directories": {
            "raw_github": str(raw_dir),
            "reports": str(report_dir),
        },
        "directories_existing_before": [str(path) for path in existing_dirs],
    }


def check_rate_limit(batch_id):
    """Call GitHub /rate_limit once, store raw response, and return a summary."""
    loaded_env_keys = load_env_file(PROJECT_ROOT / ".env")
    token = os.environ.get("GITHUB_TOKEN")
    base_url = os.environ.get("GITHUB_API_BASE") or "https://api.github.com"
    client = GitHubClient(token=token, base_url=base_url)
    response = client.rate_limit()
    call_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = write_raw_response(batch_id, "rate_limit", call_id, response, PROJECT_ROOT)
    resources = response["payload"].get("resources", {})
    search = resources.get("search", {})
    core = resources.get("core", {})
    return {
        "batch_id": batch_id,
        "status_code": response["status_code"],
        "authenticated": bool(token),
        "loaded_env_keys": sorted(loaded_env_keys),
        "raw_path": str(raw_path),
        "search_remaining": search.get("remaining"),
        "search_limit": search.get("limit"),
        "search_reset": search.get("reset"),
        "core_remaining": core.get("remaining"),
        "core_limit": core.get("limit"),
        "core_reset": core.get("reset"),
    }


def build_parser():
    parser = argparse.ArgumentParser(description="PQC migration collector runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "init-skeleton",
        help="Create and report the standard collector workspace directories.",
    )
    schema_preview = subparsers.add_parser(
        "schema-preview",
        help="Write a JSON preview of collector, filter, and export report schemas.",
    )
    schema_preview.add_argument(
        "--output",
        default=PROJECT_ROOT / "reports" / "batches" / "schema-preview" / "schema_preview.json",
        type=Path,
        help="Path to write the schema preview JSON.",
    )
    store_sample = subparsers.add_parser(
        "store-sample-search",
        help="Store one fixture search page and write Phase 2 reports.",
    )
    store_sample.add_argument(
        "--batch-id",
        default="batch-sample-search",
        help="Batch id used for the sample search storage run.",
    )
    cleanup_sample = subparsers.add_parser(
        "cleanup-sample-search",
        help="Remove one sample search batch from DB and generated files.",
    )
    cleanup_sample.add_argument(
        "--batch-id",
        default="batch-sample-search",
        help="Sample batch id to remove.",
    )
    cleanup_sample.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows and batch directories. Omit for dry-run.",
    )
    rate_limit = subparsers.add_parser("check-rate-limit", help="Call GitHub /rate_limit once.")
    rate_limit.add_argument("--batch-id", default="batch-rate-limit")
    search_page = subparsers.add_parser("fetch-search-page", help="Fetch one raw search page.")
    search_page.add_argument("--batch-id", required=True)
    search_page.add_argument("--query-text", required=True)
    search_page.add_argument("--page", default=1, type=int)
    search_page.add_argument("--per-page", default=50, type=int)
    collect_page = subparsers.add_parser("collect-one-page", help="Collect and report one page.")
    collect_page.add_argument("--batch-id", required=True)
    collect_page.add_argument("--query-key", required=True)
    collect_page.add_argument("--query-group", required=True)
    collect_page.add_argument("--query-text", required=True)
    collect_page.add_argument("--page", default=1, type=int)
    collect_page.add_argument("--page-size", default=50, type=int)
    run_f0 = subparsers.add_parser("run-f0", help="Run F0 path quality filter for one batch.")
    f0_target = run_f0.add_mutually_exclusive_group(required=True)
    f0_target.add_argument("--batch-id", help="Explicit batch id to process.")
    f0_target.add_argument(
        "--next",
        action="store_true",
        help="Process the oldest batch with raw items not fully processed by F0.",
    )
    run_f0.add_argument("--limit", default=None, type=int)
    fetch_files = subparsers.add_parser(
        "fetch-files",
        help="Fetch file snapshots for F0-passed items in one batch.",
    )
    fetch_files.add_argument("--batch-id", required=True)
    fetch_files.add_argument("--limit", default=None, type=int)
    run_f1 = subparsers.add_parser(
        "run-f1",
        help="Run F1 static candidate filter for fetched F0-passed files.",
    )
    run_f1.add_argument("--batch-id", required=True)
    run_f1.add_argument("--limit", default=None, type=int)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-skeleton":
        result = ensure_dirs(PROJECT_ROOT)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "schema-preview":
        output_path = write_schema_preview(args.output)
        result = {
            "output_path": str(output_path),
            "schema_count": len(report_schemas()),
        }
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "store-sample-search":
        result = store_sample_search(args.batch_id)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "cleanup-sample-search":
        result = cleanup_sample_search(args.batch_id, args.apply)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "check-rate-limit":
        result = check_rate_limit(args.batch_id)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "fetch-search-page":
        load_env_file(PROJECT_ROOT / ".env")
        result = fetch_search_page_raw(
            args.batch_id,
            args.query_text,
            args.page,
            args.per_page,
            PROJECT_ROOT,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "collect-one-page":
        load_env_file(PROJECT_ROOT / ".env")
        query = make_query(args.query_key, args.query_group, args.query_text, args.page_size)
        result = collect_one_page_batch(args.batch_id, query, args.page, PROJECT_ROOT)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "run-f0":
        conn = connect(root=PROJECT_ROOT)
        try:
            init_db(conn)
            batch_id = args.batch_id
            if args.next:
                batch_id = get_next_unprocessed_f0_batch_id(conn)
            if batch_id is None:
                result = {
                    "requested_batch_id": "next",
                    "batch_id": None,
                    "status": "no_unprocessed_f0_batch",
                    "raw_item_count": 0,
                    "processed_item_count": 0,
                    "new_result_count": 0,
                    "updated_result_count": 0,
                    "report_paths": {},
                    "summary": {},
                    "sample_row": None,
                }
            else:
                result = run_f0_batch(conn, batch_id, args.limit, PROJECT_ROOT)
                result["requested_batch_id"] = "next" if args.next else args.batch_id
        finally:
            conn.close()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "fetch-files":
        load_env_file(PROJECT_ROOT / ".env")
        token = os.environ.get("GITHUB_TOKEN")
        base_url = os.environ.get("GITHUB_API_BASE") or "https://api.github.com"
        client = GitHubClient(token=token, base_url=base_url)
        conn = connect(root=PROJECT_ROOT)
        try:
            init_db(conn)
            result = fetch_file_batch(conn, args.batch_id, client, args.limit, PROJECT_ROOT)
        finally:
            conn.close()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "run-f1":
        conn = connect(root=PROJECT_ROOT)
        try:
            init_db(conn)
            result = run_f1_batch(conn, args.batch_id, args.limit, PROJECT_ROOT)
        finally:
            conn.close()
        print(json.dumps(result, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
