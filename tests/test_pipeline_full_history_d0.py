import base64
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pqc_collector.collect import GitHubClient, GitHubRateLimitError
from pqc_collector.pipeline import run_d0_batch
from pqc_collector.reports import summarize_filter_results
from pqc_collector.storage import (
    init_db,
    iter_d0_passed_rows,
    store_search_page,
    upsert_f0_result,
    upsert_f1_result,
    upsert_file_snapshot,
)


class FakeHistoryClient:
    def __init__(self, pages, commits, errors=None):
        self.pages = pages
        self.commits = commits
        self.errors = errors or {}
        self.list_calls = []
        self.commit_calls = []

    def list_commits_for_path(self, repo, path, page=1, per_page=100):
        self.list_calls.append((repo, path, page, per_page))
        return {"status_code": 200, "headers": {}, "payload": self.pages.get(page, [])}

    def get_commit(self, repo, sha):
        self.commit_calls.append((repo, sha))
        if sha in self.errors:
            raise self.errors[sha]
        return {"status_code": 200, "headers": {}, "payload": self.commits[sha]}


class FakeHttpResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload
        self.headers = {"x-ratelimit-remaining": "42"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FullHistoryD0Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temporary.cleanup()

    def seed_f1_passed_item(self, batch_id, path="src/kem.c", blob_sha="blob-a"):
        query = {
            "query_key": f"query-{batch_id}-{path}",
            "query_group": "tests",
            "query_text": f"ML-KEM EVP_PKEY {path}",
            "page_size": 50,
        }
        repository = {
            "id": 100,
            "full_name": "owner/repo",
            "html_url": "https://github.com/owner/repo",
        }
        payload = {
            "total_count": 1,
            "items": [
                {
                    "sha": blob_sha,
                    "path": path,
                    "url": f"https://api.github.com/repositories/100/contents/{path}?ref=main",
                    "html_url": f"https://github.com/owner/repo/blob/main/{path}",
                    "repository": repository,
                }
            ],
        }
        stored = store_search_page(self.conn, batch_id, query, 1, payload, self.root)
        raw_key = stored["raw_search_items"][0]["search_item_key"]
        raw = dict(
            self.conn.execute(
                "SELECT * FROM raw_search_items WHERE search_item_key = ?",
                (raw_key,),
            ).fetchone()
        )
        upsert_f0_result(
            self.conn,
            batch_id,
            {
                "search_item_key": raw["search_item_key"],
                "repository_full_name": raw["repository_full_name"],
                "path": raw["path"],
                "normalized_path": raw["normalized_path"],
                "source_kind": "source",
                "passed": True,
                "reason_codes": ["test_pass"],
                "checked_at": "2026-09-13T00:00:00Z",
            },
        )
        file_row = upsert_file_snapshot(
            self.conn,
            batch_id,
            dict(raw),
            {
                "status_code": 200,
                "headers": {},
                "payload": {
                    "download_url": f"https://example.test/{path}",
                    "encoding": "base64",
                    "content": base64.b64encode(b"EVP_PKEY ML-KEM\n").decode("ascii"),
                    "size": 15,
                },
            },
            self.root / f"{path.replace('/', '_')}.json",
            fetched_at="2026-09-13T00:01:00Z",
        )
        upsert_f1_result(
            self.conn,
            batch_id,
            {
                "search_item_key": raw["search_item_key"],
                "file_key": file_row["file_key"],
                "path": raw["path"],
                "language": "c",
                "passed": True,
                "target_libraries": ["openssl"],
                "matched_library_signals": ["openssl"],
                "matched_pqc_api_signals": ["ML-KEM"],
                "matched_provider_signals": [],
                "library_evidence": [],
                "strong_signal_evidence": [],
                "quality": {"source_kind": "source"},
                "reason_codes": ["test_pass"],
                "raw_file_path": file_row["raw_file_path"],
                "checked_at": "2026-09-13T00:02:00Z",
            },
        )
        return raw

    def commit_summary(self, sha):
        return {"sha": sha}

    def commit_payload(self, sha, path, patch_text=None):
        changed = {"filename": path, "status": "modified", "additions": 1, "deletions": 0}
        if patch_text is not None:
            changed["patch"] = patch_text
        return {
            "sha": sha,
            "html_url": f"https://github.com/owner/repo/commit/{sha}",
            "commit": {"message": f"commit {sha}"},
            "files": [changed],
        }

    def test_d0_traverses_all_history_pages_and_stores_each_matching_commit(self):
        self.seed_f1_passed_item("batch-a")
        client = FakeHistoryClient(
            {
                1: [self.commit_summary("latest"), self.commit_summary("middle")],
                2: [self.commit_summary("intro")],
                3: [],
            },
            {
                "latest": self.commit_payload("latest", "docs/readme.md", "@@ -1 +1 @@\n+doc"),
                "middle": self.commit_payload("middle", "src/kem.c", "@@ -1 +1 @@\n+ML-KEM"),
                "intro": self.commit_payload("intro", "src/kem.c", "@@ -1 +1 @@\n+EVP_PKEY"),
            },
        )

        result = run_d0_batch(
            self.conn,
            "batch-a",
            client,
            root=self.root,
            commit_history_per_page=2,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["listed_commit_count"], 3)
        self.assertEqual(result["stored_result_count"], 3)
        self.assertEqual([call[2] for call in client.list_calls], [1, 2, 3])
        f2_queue = list(iter_d0_passed_rows(self.conn, "batch-a"))
        self.assertEqual({row["commit_sha"] for row in f2_queue}, {"middle", "intro"})

    def test_d0_resume_skips_previously_processed_commits_and_uses_detail_cache(self):
        self.seed_f1_passed_item("batch-a")
        pages = {1: [self.commit_summary("a"), self.commit_summary("b")], 2: []}
        commits = {
            "a": self.commit_payload("a", "src/kem.c", "@@ -1 +1 @@\n+ML-KEM"),
            "b": self.commit_payload("b", "src/kem.c", "@@ -1 +1 @@\n+ML-KEM"),
        }
        first_client = FakeHistoryClient(pages, commits)
        run_d0_batch(self.conn, "batch-a", first_client, root=self.root)

        second_client = FakeHistoryClient(pages, commits)
        second = run_d0_batch(self.conn, "batch-a", second_client, root=self.root)

        self.assertEqual(second["skipped_commit_count"], 2)
        self.assertEqual(second_client.commit_calls, [])

    def test_commit_detail_cache_deduplicates_same_commit_across_files(self):
        self.seed_f1_passed_item("batch-a", path="src/kem.c", blob_sha="blob-a")
        self.seed_f1_passed_item("batch-a", path="src/tls.c", blob_sha="blob-b")
        client = FakeHistoryClient(
            {1: [self.commit_summary("shared")], 2: []},
            {
                "shared": {
                    "sha": "shared",
                    "html_url": "https://github.com/owner/repo/commit/shared",
                    "commit": {"message": "shared"},
                    "files": [
                        {
                            "filename": "src/kem.c",
                            "status": "modified",
                            "patch": "@@ -1 +1 @@\n+ML-KEM",
                        },
                        {
                            "filename": "src/tls.c",
                            "status": "modified",
                            "patch": "@@ -1 +1 @@\n+X25519MLKEM768",
                        },
                    ],
                }
            },
        )

        result = run_d0_batch(self.conn, "batch-a", client, root=self.root)

        self.assertEqual(result["stored_result_count"], 2)
        self.assertEqual(client.commit_calls, [("owner/repo", "shared")])

    def test_patch_missing_is_recorded_as_evidence_unavailable(self):
        self.seed_f1_passed_item("batch-a")
        client = FakeHistoryClient(
            {1: [self.commit_summary("too-big")], 2: []},
            {"too-big": self.commit_payload("too-big", "src/kem.c", None)},
        )

        result = run_d0_batch(self.conn, "batch-a", client, root=self.root)
        row = self.conn.execute("SELECT * FROM d0_results").fetchone()
        summary = summarize_filter_results(self.conn, "batch-a")

        self.assertEqual(result["evidence_unavailable_count"], 1)
        self.assertEqual(row["evidence_status"], "unavailable")
        self.assertEqual(row["evidence_reason_code"], "d0_patch_missing")
        self.assertEqual(summary["d0"]["evidence_status_counts"], {"unavailable": 1})

    def test_rate_limit_error_can_wait_then_retry(self):
        calls = []

        def fake_urlopen(request, timeout=30):
            calls.append(request.full_url)
            if len(calls) == 1:
                error = HTTPError(
                    request.full_url,
                    403,
                    "rate limited",
                    {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1"},
                    None,
                )
                error.fp = FakeHttpResponse({"message": "API rate limit exceeded"})
                raise error
            return FakeHttpResponse({"ok": True})

        with patch("pqc_collector.collect.urlopen", fake_urlopen), patch(
            "pqc_collector.collect.time.sleep"
        ) as sleep:
            response = GitHubClient(base_url="https://api.github.test").get_json(
                "/rate_limit",
                max_rate_limit_wait_seconds=0,
            )

        self.assertEqual(response["payload"], {"ok": True})
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(0)

    def test_rate_limit_error_can_be_returned_to_resume_later(self):
        def fake_urlopen(request, timeout=30):
            error = HTTPError(
                request.full_url,
                429,
                "rate limited",
                {"retry-after": "60"},
                None,
            )
            error.fp = FakeHttpResponse({"message": "secondary limit"})
            raise error

        with patch("pqc_collector.collect.urlopen", fake_urlopen):
            with self.assertRaises(GitHubRateLimitError) as raised:
                GitHubClient(base_url="https://api.github.test").get_json(
                    "/rate_limit",
                    wait_on_rate_limit=False,
                )

        self.assertEqual(raised.exception.retry_after_seconds, 60)


if __name__ == "__main__":
    unittest.main()
