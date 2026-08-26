import json

from pqc_collector.api_usage import write_api_usage_report
from pqc_collector.collection_summary import write_collection_summary_report
from pqc_collector.frontier import write_query_frontier_report
from pqc_collector.reports import report_paths


def write_query_pages_report(conn, batch_id, output_path=None, root=None):
    """Write query_pages rows for one batch as JSONL."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["query_pages"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT
            batch_id,
            query_page_key,
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
        FROM query_pages
        WHERE batch_id = ?
        ORDER BY query_key, page
        """,
        (batch_id,),
    ).fetchall()
    with report_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return report_path


def write_raw_search_items_report(conn, batch_id, output_path=None, root=None):
    """Write raw_search_items rows for one batch as JSONL."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["raw_search_items"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
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
        """,
        (batch_id,),
    ).fetchall()
    with report_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return report_path


def write_dedupe_summary_report(
    conn,
    batch_id,
    output_path=None,
    root=None,
    skipped_query_page_count=0,
):
    """Write stored dedupe counts for one batch as JSON."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["dedupe_summary"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    page_counts = conn.execute(
        """
        SELECT
            COALESCE(SUM(item_count), 0) AS raw_item_seen_count,
            COALESCE(SUM(new_unique_item_count), 0) AS new_unique_item_count,
            COALESCE(SUM(duplicate_item_count), 0) AS duplicate_item_count
        FROM query_pages
        WHERE batch_id = ?
        """,
        (batch_id,),
    ).fetchone()
    previous_duplicates = conn.execute(
        """
        SELECT COUNT(*) AS previous_duplicate_count
        FROM raw_search_items
        WHERE batch_id = ?
            AND status = 'existing'
            AND first_seen_batch_id <> ?
        """,
        (batch_id, batch_id),
    ).fetchone()["previous_duplicate_count"]
    duplicate_item_count = int(page_counts["duplicate_item_count"])
    summary = {
        "batch_id": batch_id,
        "raw_item_seen_count": int(page_counts["raw_item_seen_count"]),
        "new_unique_item_count": int(page_counts["new_unique_item_count"]),
        "previous_duplicate_count": int(previous_duplicates),
        "current_batch_duplicate_count": max(
            0,
            duplicate_item_count - int(previous_duplicates),
        ),
        "query_page_duplicate_count": 0,
        "skipped_query_page_count": int(skipped_query_page_count),
        "skipped_file_fetch_count": 0,
        "skipped_commit_fetch_count": 0,
    }
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return report_path


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
        "collector_status": result.get("collector_status", "idle"),
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
        "sleep_until": result.get("sleep_until"),
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
