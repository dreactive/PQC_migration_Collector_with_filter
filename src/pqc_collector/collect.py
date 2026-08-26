import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pqc_collector.core import query_page_key
from pqc_collector.reports import (
    write_dedupe_summary_report,
    write_one_page_collection_reports,
    write_query_pages_report,
    write_raw_search_items_report,
)
from pqc_collector.storage import connect, init_db, store_search_page, write_raw_response


DEFAULT_SEARCH_REMAINING_FLOOR = 2
DEFAULT_CORE_REMAINING_FLOOR = 100
DEFAULT_RESUME_SAFETY_DELAY_SECONDS = 30


class GitHubApiError(RuntimeError):
    """Raised when GitHub returns a non-2xx API response."""


class GitHubClient:
    """Small GitHub REST client for collector API calls."""

    def __init__(
        self,
        token=None,
        base_url="https://api.github.com",
        user_agent="pqc-migration-collector",
        timeout=30,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout

    def _headers(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, path, params=None):
        path = "/" + path.lstrip("/")
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def get_json(self, path, params=None):
        """GET one GitHub JSON API resource."""
        request = Request(self._url(path, params), headers=self._headers())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body) if body else {}
                return {
                    "status_code": response.status,
                    "headers": dict(response.headers.items()),
                    "payload": payload,
                }
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            raise GitHubApiError(
                f"GitHub API error {exc.code} for {request.full_url}: {payload}"
            ) from exc

    def rate_limit(self):
        """Fetch GitHub rate limit status."""
        return self.get_json("/rate_limit")

    def search_code(self, query_text, page=1, per_page=50):
        """Fetch one GitHub code search result page."""
        return self.get_json(
            "/search/code",
            {
                "q": query_text,
                "page": int(page),
                "per_page": int(per_page),
            },
        )


def _resource_snapshot(resources, name):
    resource = resources.get(name, {})
    return {
        "limit": resource.get("limit"),
        "remaining": resource.get("remaining"),
        "reset": resource.get("reset"),
    }


def _sleep_until(blocked_resources, safety_delay_seconds):
    reset_values = [
        resource["reset"]
        for resource in blocked_resources
        if isinstance(resource.get("reset"), int)
    ]
    if not reset_values:
        return None
    resume_at = max(reset_values) + int(safety_delay_seconds)
    return datetime.fromtimestamp(resume_at, timezone.utc).isoformat().replace("+00:00", "Z")


def evaluate_rate_limit_floor(
    rate_limit_payload,
    search_remaining_floor=DEFAULT_SEARCH_REMAINING_FLOOR,
    core_remaining_floor=DEFAULT_CORE_REMAINING_FLOOR,
    resume_safety_delay_seconds=DEFAULT_RESUME_SAFETY_DELAY_SECONDS,
):
    """Evaluate whether GitHub rate limit floors require sleeping."""
    resources = rate_limit_payload.get("resources", rate_limit_payload)
    search = _resource_snapshot(resources, "search")
    core = _resource_snapshot(resources, "core")
    floors = {
        "search": int(search_remaining_floor),
        "core": int(core_remaining_floor),
    }
    blocked_resources = []
    for name, snapshot in (("search", search), ("core", core)):
        remaining = snapshot.get("remaining")
        if remaining is not None and int(remaining) <= floors[name]:
            blocked_resources.append({"resource": name, **snapshot, "floor": floors[name]})

    blocked = bool(blocked_resources)
    return {
        "collector_status": "sleeping_rate_limit" if blocked else "idle",
        "blocked": blocked,
        "blocked_resources": blocked_resources,
        "search": {**search, "floor": floors["search"]},
        "core": {**core, "floor": floors["core"]},
        "sleep_until": _sleep_until(blocked_resources, resume_safety_delay_seconds),
        "resume_safety_delay_seconds": int(resume_safety_delay_seconds),
    }


def _resource_snapshots(rate_limit_response):
    resources = rate_limit_response["payload"].get("resources", {})
    return {
        name: {
            "limit": resources.get(name, {}).get("limit"),
            "remaining": resources.get(name, {}).get("remaining"),
            "reset": resources.get(name, {}).get("reset"),
        }
        for name in ("search", "core")
    }


def make_query(query_key, query_group, query_text, page_size):
    """Build the explicit one-page query object used by the collector flow."""
    return {
        "query_key": query_key,
        "query_group": query_group,
        "query_text": query_text,
        "page_size": int(page_size),
    }


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
            "dedupe_summary": str(
                write_dedupe_summary_report(
                    conn,
                    batch_id,
                    root=root,
                    skipped_query_page_count=1,
                )
            ),
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
    result = store_search_page(conn, batch_id, query, page, response["payload"], root)
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


def collect_one_page_batch(
    batch_id,
    query,
    page=1,
    root=None,
    search_remaining_floor=2,
    core_remaining_floor=100,
    generated_at=None,
):
    """Run one Phase 3 collection cycle for exactly one GitHub search page."""
    page = int(page)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    client = GitHubClient(
        token=os.environ.get("GITHUB_TOKEN"),
        base_url=os.environ.get("GITHUB_API_BASE") or "https://api.github.com",
    )
    rate_limit_response = client.rate_limit()
    call_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_rate_limit_path = write_raw_response(
        batch_id,
        "rate_limit",
        call_id,
        rate_limit_response,
        root,
    )
    rate_limit_snapshot = _resource_snapshots(rate_limit_response)
    rate_limit_policy = evaluate_rate_limit_floor(
        rate_limit_response["payload"],
        search_remaining_floor,
        core_remaining_floor,
    )

    conn = connect(root=root)
    try:
        init_db(conn)
        if rate_limit_policy["blocked"]:
            result = {
                "batch_id": batch_id,
                "query_key": query["query_key"],
                "query_page_key": query_page_key(
                    query["query_text"],
                    page,
                    query["page_size"],
                ),
                "status": "sleeping_rate_limit",
                "collector_status": "sleeping_rate_limit",
                "sleep_until": rate_limit_policy["sleep_until"],
                "api_call_count_rate_limit": 1,
                "api_call_count_search": 0,
                "raw_item_seen_count": 0,
                "new_unique_item_count": 0,
                "previous_duplicate_count": 0,
                "current_batch_duplicate_count": 0,
                "skipped_query_page_count": 0,
                "report_paths": {},
                "sample_search_item_key": None,
            }
        else:
            result = collect_one_query_page(conn, batch_id, query, page, root)
            result["api_call_count_rate_limit"] = 1

        collection_reports = write_one_page_collection_reports(
            batch_id,
            query,
            page,
            result,
            rate_limit_snapshot,
            rate_limit_snapshot,
            root=root,
            generated_at=timestamp,
        )
    finally:
        conn.close()

    result["raw_rate_limit_path"] = str(raw_rate_limit_path)
    result["rate_limit_policy"] = rate_limit_policy
    result["report_paths"] = {
        **result.get("report_paths", {}),
        **collection_reports["report_paths"],
    }
    result["frontier_row"] = collection_reports["frontier_row"]
    result["summary"] = collection_reports["summary"]
    return result
