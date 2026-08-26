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
