import json

from pqc_collector.reports import report_paths


FRONTIER_DEFAULTS = {
    "next_page_to_fetch": 1,
    "fetched_pages": 0,
    "exhausted": False,
    "low_yield": False,
    "consecutive_duplicate_pages": 0,
    "last_run_at": None,
    "last_duplicate_ratio": 0.0,
}


def normalize_frontier_row(row):
    """Return one query frontier row with all required fields."""
    frontier = dict(FRONTIER_DEFAULTS)
    frontier.update(row)
    return {
        "query_key": frontier["query_key"],
        "query_group": frontier["query_group"],
        "next_page_to_fetch": int(frontier["next_page_to_fetch"]),
        "fetched_pages": int(frontier["fetched_pages"]),
        "exhausted": bool(frontier["exhausted"]),
        "low_yield": bool(frontier["low_yield"]),
        "consecutive_duplicate_pages": int(frontier["consecutive_duplicate_pages"]),
        "last_run_at": frontier["last_run_at"],
        "last_duplicate_ratio": float(frontier["last_duplicate_ratio"]),
    }


def write_query_frontier_report(batch_id, rows, output_path=None, root=None):
    """Write query frontier state rows for one collector batch."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["query_frontier"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    frontier_rows = sorted(
        (normalize_frontier_row(row) for row in rows),
        key=lambda row: (row["query_group"], row["query_key"]),
    )
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(frontier_rows, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return report_path
