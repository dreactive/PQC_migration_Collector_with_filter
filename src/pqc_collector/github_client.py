import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
