from pqc_collector.api_usage import write_api_usage_report
from pqc_collector.collection_summary import write_collection_summary_report
from pqc_collector.frontier import write_query_frontier_report


def _duplicate_ratio(result):
    seen = int(result.get("raw_item_seen_count", 0))
    if not seen:
        return 0.0
    duplicates = int(result.get("previous_duplicate_count", 0)) + int(
        result.get("current_batch_duplicate_count", 0)
    )
    return duplicates / seen


def write_one_page_collection_reports(
    batch_id,
    query,
    page,
    result,
    rate_limit_start=None,
    rate_limit_end=None,
    root=None,
    generated_at=None,
    low_yield_duplicate_ratio=0.8,
):
    """Write batch reports derived from one collect_one_query_page result."""
    page = int(page)
    rate_limit_calls = int(
        result.get("api_call_count_rate_limit", 1 if rate_limit_start or rate_limit_end else 0)
    )
    search_calls = int(result.get("api_call_count_search", 0))
    skipped_pages = int(result.get("skipped_query_page_count", 0))
    fetched_pages = 1 if search_calls else 0
    duplicate_ratio = _duplicate_ratio(result)
    low_yield = bool(fetched_pages and duplicate_ratio >= low_yield_duplicate_ratio)
    frontier_row = {
        "query_key": query["query_key"],
        "query_group": query["query_group"],
        "next_page_to_fetch": page + fetched_pages,
        "fetched_pages": fetched_pages,
        "exhausted": False,
        "low_yield": low_yield,
        "consecutive_duplicate_pages": 1 if low_yield else 0,
        "last_run_at": generated_at,
        "last_duplicate_ratio": duplicate_ratio,
    }
    summary = {
        "collector_status": "idle",
        "query_group": query["query_group"],
        "query_count": 1,
        "query_pages_fetched": fetched_pages,
        "query_pages_skipped": skipped_pages,
        "raw_item_seen_count": result.get("raw_item_seen_count", 0),
        "new_unique_item_count": result.get("new_unique_item_count", 0),
        "previous_duplicate_count": result.get("previous_duplicate_count", 0),
        "current_batch_duplicate_count": result.get("current_batch_duplicate_count", 0),
        "api_call_count_search": search_calls,
        "api_call_count_core": 0,
        "rate_limit_start": rate_limit_start,
        "rate_limit_end": rate_limit_end,
        "high_yield_queries": [query["query_key"]] if fetched_pages and not low_yield else [],
        "low_yield_queries": [query["query_key"]] if low_yield else [],
        "next_recommended_query_group": query["query_group"],
    }
    paths = {
        "api_usage": str(
            write_api_usage_report(
                batch_id,
                {"rate_limit": rate_limit_calls, "search": search_calls},
                rate_limit_start,
                rate_limit_end,
                root=root,
                generated_at=generated_at,
            )
        ),
        "query_frontier": str(
            write_query_frontier_report(batch_id, [frontier_row], root=root)
        ),
        "collection_summary": str(
            write_collection_summary_report(
                batch_id,
                summary,
                root=root,
                generated_at=generated_at,
            )
        ),
    }
    return {
        "batch_id": batch_id,
        "report_paths": paths,
        "frontier_row": frontier_row,
        "summary": summary,
    }
