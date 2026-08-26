import json

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


def write_dedupe_summary_report(conn, batch_id, output_path=None, root=None):
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
        "skipped_query_page_count": 0,
        "skipped_file_fetch_count": 0,
        "skipped_commit_fetch_count": 0,
    }
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return report_path
