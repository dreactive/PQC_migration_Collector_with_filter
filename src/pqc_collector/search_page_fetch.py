import os

from pqc_collector.collector import store_search_page
from pqc_collector.collector_reports import (
    write_dedupe_summary_report,
    write_query_pages_report,
    write_raw_search_items_report,
)
from pqc_collector.github_client import GitHubClient
from pqc_collector.keys import query_page_key
from pqc_collector.raw_store import write_raw_response


def fetch_search_page_raw(batch_id, query_text, page=1, per_page=50, root=None):
    """Fetch one GitHub code search page and write its raw API response."""
    page = int(page)
    per_page = int(per_page)
    client = GitHubClient(
        token=os.environ.get("GITHUB_TOKEN"),
        base_url=os.environ.get("GITHUB_API_BASE") or "https://api.github.com",
    )
    response = client.search_code(query_text, page=page, per_page=per_page)
    page_key = query_page_key(query_text, page, per_page)
    raw_path = write_raw_response(batch_id, "query_page", page_key, response, root)
    payload = response["payload"]
    items = payload.get("items", [])
    first_item = items[0] if items else {}
    first_repo = first_item.get("repository", {})
    return {
        "batch_id": batch_id,
        "query_page_key": page_key,
        "status_code": response["status_code"],
        "raw_path": str(raw_path),
        "total_count": payload.get("total_count"),
        "item_count": len(items),
        "first_item": {
            "repository_full_name": first_repo.get("full_name"),
            "path": first_item.get("path"),
            "sha": first_item.get("sha"),
            "html_url": first_item.get("html_url"),
        },
    }


def collect_one_query_page(conn, batch_id, query, page=1, root=None):
    """Fetch, store, and report one GitHub code search page."""
    page = int(page)
    page_size = int(query["page_size"])
    page_key = query_page_key(query["query_text"], page, page_size)
    existing_page = conn.execute(
        "SELECT raw_path FROM query_pages WHERE query_page_key = ?",
        (page_key,),
    ).fetchone()
    if existing_page:
        report_paths = {
            "query_pages": str(write_query_pages_report(conn, batch_id, root=root)),
            "raw_search_items": str(write_raw_search_items_report(conn, batch_id, root=root)),
            "dedupe_summary": str(write_dedupe_summary_report(conn, batch_id, root=root)),
        }
        sample_item = conn.execute(
            """
            SELECT search_item_key
            FROM raw_search_items
            WHERE query_page_key = ?
            ORDER BY repository_full_name, normalized_path, blob_sha
            LIMIT 1
            """,
            (page_key,),
        ).fetchone()
        return {
            "batch_id": batch_id,
            "query_key": query["query_key"],
            "query_page_key": page_key,
            "status": "existing",
            "api_call_count_search": 0,
            "raw_path": existing_page["raw_path"],
            "raw_item_seen_count": 0,
            "new_unique_item_count": 0,
            "previous_duplicate_count": 0,
            "current_batch_duplicate_count": 0,
            "skipped_query_page_count": 1,
            "report_paths": report_paths,
            "sample_search_item_key": (
                sample_item["search_item_key"] if sample_item else None
            ),
        }

    client = GitHubClient(
        token=os.environ.get("GITHUB_TOKEN"),
        base_url=os.environ.get("GITHUB_API_BASE") or "https://api.github.com",
    )
    response = client.search_code(query["query_text"], page=page, per_page=page_size)
    result = store_search_page(
        conn,
        batch_id,
        query,
        page,
        response["payload"],
        root,
    )
    report_paths = {
        "query_pages": str(write_query_pages_report(conn, batch_id, root=root)),
        "raw_search_items": str(write_raw_search_items_report(conn, batch_id, root=root)),
        "dedupe_summary": str(write_dedupe_summary_report(conn, batch_id, root=root)),
    }
    first_item = result["raw_search_items"][0] if result["raw_search_items"] else {}
    return {
        "batch_id": batch_id,
        "query_key": query["query_key"],
        "query_page_key": page_key,
        "status": result["status"],
        "api_call_count_search": 1,
        "raw_path": result["raw_path"],
        "raw_item_seen_count": result["raw_item_seen_count"],
        "new_unique_item_count": result["new_unique_item_count"],
        "previous_duplicate_count": result["previous_duplicate_count"],
        "current_batch_duplicate_count": result["current_batch_duplicate_count"],
        "skipped_query_page_count": result["skipped_query_page_count"],
        "report_paths": report_paths,
        "sample_search_item_key": first_item.get("search_item_key"),
    }
