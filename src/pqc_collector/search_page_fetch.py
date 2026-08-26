import os

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
