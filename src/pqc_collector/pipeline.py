"""Batch pipeline orchestration for collector and filter stages."""

import hashlib

from pqc_collector.core import file_key
from pqc_collector.filter import run_f0_for_item, run_f1
from pqc_collector.reports import (
    summarize_f0_results,
    summarize_f1_results,
    write_f0_report,
    write_f1_report,
)
from pqc_collector.storage import (
    iter_f0_passed_items,
    iter_files_for_f1,
    iter_raw_search_items,
    read_file_snapshot,
    upsert_f0_result,
    upsert_f1_result,
    upsert_file_snapshot,
    write_raw_response,
)


def run_f0_batch(conn, batch_id, limit=None, root=None, rules=None, checked_at=None):
    """Run F0 path quality filtering for raw search items in one batch."""
    raw_items = list(iter_raw_search_items(conn, batch_id, limit))
    f0_rows = []
    new_result_count = 0
    updated_result_count = 0

    for item in raw_items:
        f0_row = run_f0_for_item(item, rules=rules, checked_at=checked_at)
        stored_row = upsert_f0_result(conn, batch_id, f0_row)
        if stored_row["status"] == "new":
            new_result_count += 1
        else:
            updated_result_count += 1
        f0_rows.append(f0_row)

    report_path = write_f0_report(f0_rows, batch_id, root=root)
    summary = summarize_f0_results(f0_rows)
    return {
        "batch_id": batch_id,
        "status": "completed",
        "raw_item_count": len(raw_items),
        "processed_item_count": len(f0_rows),
        "new_result_count": new_result_count,
        "updated_result_count": updated_result_count,
        "report_paths": {
            "filter_f0_path_quality": str(report_path),
        },
        "summary": summary,
        "sample_row": f0_rows[0] if f0_rows else None,
    }


def _raw_file_response_key(item):
    key = file_key(item["repository_id"], item["normalized_path"], item["blob_sha"])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def fetch_file_batch(conn, batch_id, client, limit=None, root=None):
    """Fetch and store file snapshots for F0-passed items in one batch."""
    queue = list(iter_f0_passed_items(conn, batch_id, limit))
    fetched_rows = []
    skipped_rows = []
    new_snapshot_count = 0
    updated_snapshot_count = 0

    for item in queue:
        key = file_key(item["repository_id"], item["normalized_path"], item["blob_sha"])
        existing = read_file_snapshot(conn, key)
        if existing:
            existing["status"] = "existing"
            skipped_rows.append(existing)
            continue

        response = client.get_file(item["file_api_url"])
        raw_path = write_raw_response(
            batch_id,
            "file",
            _raw_file_response_key(item),
            response,
            root,
        )
        stored_row = upsert_file_snapshot(conn, batch_id, item, response, raw_path)
        if stored_row["status"] == "new":
            new_snapshot_count += 1
        else:
            updated_snapshot_count += 1
        fetched_rows.append(stored_row)

    return {
        "batch_id": batch_id,
        "status": "completed",
        "queued_item_count": len(queue),
        "fetched_item_count": len(fetched_rows),
        "skipped_existing_count": len(skipped_rows),
        "new_snapshot_count": new_snapshot_count,
        "updated_snapshot_count": updated_snapshot_count,
        "raw_file_paths": [row["raw_file_path"] for row in fetched_rows],
        "sample_fetched_row": fetched_rows[0] if fetched_rows else None,
        "sample_skipped_row": skipped_rows[0] if skipped_rows else None,
    }


def run_f1_batch(conn, batch_id, limit=None, root=None, configs=None, checked_at=None):
    """Run F1 static candidate filtering for fetched F0-passed files."""
    file_rows = list(iter_files_for_f1(conn, batch_id, limit))
    f1_rows = []
    new_result_count = 0
    updated_result_count = 0

    for file_row in file_rows:
        f0_result = {
            "passed": True,
            "source_kind": file_row.get("source_kind"),
            "reason_codes": file_row.get("f0_reason_codes", []),
        }
        f1_row = run_f1(
            file_row,
            f0_result=f0_result,
            configs=configs,
            checked_at=checked_at,
        )
        stored_row = upsert_f1_result(conn, batch_id, f1_row)
        if stored_row["status"] == "new":
            new_result_count += 1
        else:
            updated_result_count += 1
        f1_rows.append(f1_row)

    report_path = write_f1_report(f1_rows, batch_id, root=root)
    summary = summarize_f1_results(f1_rows)
    return {
        "batch_id": batch_id,
        "status": "completed",
        "queued_file_count": len(file_rows),
        "processed_file_count": len(f1_rows),
        "new_result_count": new_result_count,
        "updated_result_count": updated_result_count,
        "report_paths": {
            "filter_f1_static_candidate": str(report_path),
        },
        "summary": summary,
        "sample_row": f1_rows[0] if f1_rows else None,
    }
