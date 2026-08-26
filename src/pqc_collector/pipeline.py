"""Batch pipeline orchestration for collector and filter stages."""

from pqc_collector.filter import run_f0_for_item
from pqc_collector.reports import summarize_f0_results, write_f0_report
from pqc_collector.storage import iter_raw_search_items, upsert_f0_result


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
