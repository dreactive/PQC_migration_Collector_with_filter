import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pqc_collector.reports import report_schemas, write_schema_preview  # noqa: E402
from pqc_collector.collector import store_search_page  # noqa: E402
from pqc_collector.collector_reports import (  # noqa: E402
    write_dedupe_summary_report,
    write_query_pages_report,
    write_raw_search_items_report,
)
from pqc_collector.database import connect, init_db  # noqa: E402
from pqc_collector.util import ensure_dirs, project_paths  # noqa: E402


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

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
