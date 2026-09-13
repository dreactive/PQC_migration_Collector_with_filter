import base64
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pqc_collector.pipeline import fetch_file_batch
from pqc_collector.storage import (
    compute_pipeline_handoff_status,
    init_db,
    iter_d0_passed_rows,
    iter_f1_passed_items,
    pending_pipeline_batches,
    store_search_page,
    upsert_diff_evidence,
    upsert_f0_result,
    upsert_file_fetch_result,
    upsert_f1_result,
    upsert_file_snapshot,
)


class FakeFileClient:
    def __init__(self, failing_paths=()):
        self.failing_paths = set(failing_paths)

    def get_file(self, file_url):
        path = file_url.rsplit("/", 1)[-1].split("?", 1)[0]
        if path in self.failing_paths:
            raise RuntimeError(f"cannot fetch {path}")
        text = f"content for {path}\n"
        return {
            "status_code": 200,
            "headers": {},
            "payload": {
                "download_url": f"https://example.test/{path}",
                "encoding": "base64",
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                "size": len(text.encode("utf-8")),
            },
        }


class PipelineHandoffReliabilityTests(unittest.TestCase):
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

    def add_search_page(self, batch_id, paths, query_text=None):
        query = {
            "query_key": f"query-{batch_id}",
            "query_group": "tests",
            "query_text": query_text or f"query text {batch_id}",
            "page_size": 50,
        }
        repository = {
            "id": 100,
            "full_name": "owner/repo",
            "html_url": "https://github.com/owner/repo",
        }
        payload = {
            "total_count": len(paths),
            "items": [
                {
                    "sha": f"sha-{path}",
                    "path": path,
                    "url": f"https://api.github.com/repositories/100/contents/{path}?ref=main",
                    "html_url": f"https://github.com/owner/repo/blob/main/{path}",
                    "repository": repository,
                }
                for path in paths
            ],
        }
        return store_search_page(self.conn, batch_id, query, 1, payload, self.root)

    def pass_f0_for_batch(self, batch_id):
        rows = self.conn.execute(
            "SELECT * FROM raw_search_items WHERE batch_id = ? ORDER BY path",
            (batch_id,),
        ).fetchall()
        for row in rows:
            upsert_f0_result(
                self.conn,
                batch_id,
                {
                    "search_item_key": row["search_item_key"],
                    "repository_full_name": row["repository_full_name"],
                    "path": row["path"],
                    "normalized_path": row["normalized_path"],
                    "source_kind": "source",
                    "passed": True,
                    "reason_codes": ["test_pass"],
                    "checked_at": "2026-09-13T00:00:00Z",
                },
            )
        return rows

    def store_snapshot(self, batch_id, raw_row):
        return upsert_file_snapshot(
            self.conn,
            batch_id,
            dict(raw_row),
            {
                "status_code": 200,
                "headers": {},
                "payload": {
                    "download_url": "https://example.test/file.c",
                    "encoding": "plain",
                    "content": "EVP_PKEY ML-KEM\n",
                    "size": 15,
                },
            },
            self.root / "raw.json",
            fetched_at="2026-09-13T00:01:00Z",
        )

    def pass_f1(self, batch_id, raw_row, file_row):
        return upsert_f1_result(
            self.conn,
            batch_id,
            {
                "search_item_key": raw_row["search_item_key"],
                "file_key": file_row["file_key"],
                "path": raw_row["path"],
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

    def pass_d0(self, batch_id, raw_row, file_row):
        return upsert_diff_evidence(
            self.conn,
            batch_id,
            {
                "search_item_key": raw_row["search_item_key"],
                "file_key": file_row["file_key"],
                "repository_id": raw_row["repository_id"],
                "repository_full_name": raw_row["repository_full_name"],
                "search_item_path": raw_row["path"],
                "commit_sha": "commit-a",
                "commit_url": "https://github.com/owner/repo/commit/commit-a",
                "matched_changed_path": raw_row["path"],
                "exact_path_match": True,
                "patch_available": True,
                "passed": True,
                "changed_files": [raw_row["path"]],
                "review_evidence": [{"kind": "test"}],
                "reason_codes": ["test_pass"],
                "raw_commit_path": str(self.root / "commit.json"),
                "patch_path": str(self.root / "patch.diff"),
                "checked_at": "2026-09-13T00:03:00Z",
            },
        )

    def test_file_fetch_records_item_errors_without_blocking_successful_items(self):
        self.add_search_page("batch-a", ["ok1.c", "bad.c", "ok2.c"])
        self.pass_f0_for_batch("batch-a")

        result = fetch_file_batch(
            self.conn,
            "batch-a",
            FakeFileClient(failing_paths={"bad.c"}),
            root=self.root,
        )

        self.assertEqual(result["status"], "completed_with_errors")
        self.assertEqual(result["fetched_item_count"], 2)
        self.assertEqual(result["error_item_count"], 1)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM file_snapshots").fetchone()[0],
            2,
        )
        error = self.conn.execute(
            "SELECT status, error_type, error_message FROM file_fetch_results"
        ).fetchone()
        self.assertEqual(error["status"], "error")
        self.assertEqual(error["error_type"], "RuntimeError")
        self.assertIn("bad.c", error["error_message"])

    def test_f1_passed_items_survive_raw_batch_id_change(self):
        first = self.add_search_page("batch-a", ["src/kem.c"])["raw_search_items"][0]
        raw_a = self.pass_f0_for_batch("batch-a")[0]
        file_row = self.store_snapshot("batch-a", raw_a)
        self.pass_f1("batch-a", raw_a, file_row)

        self.add_search_page("batch-b", ["src/kem.c"], query_text="different query")

        rows = list(iter_f1_passed_items(self.conn, "batch-a"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["search_item_key"], first["search_item_key"])
        self.assertEqual(rows[0]["batch_id"], "batch-a")

    def test_d0_passed_items_survive_raw_batch_id_change(self):
        self.add_search_page("batch-a", ["src/kem.c"])
        raw_a = self.pass_f0_for_batch("batch-a")[0]
        file_row = self.store_snapshot("batch-a", raw_a)
        self.pass_f1("batch-a", raw_a, file_row)
        self.pass_d0("batch-a", raw_a, file_row)

        self.add_search_page("batch-b", ["src/kem.c"], query_text="different query")

        rows = list(iter_d0_passed_rows(self.conn, "batch-a"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["search_item_key"], raw_a["search_item_key"])
        self.assertEqual(rows[0]["batch_id"], "batch-a")

    def test_occurrences_and_handoff_status_explain_pending_items(self):
        self.add_search_page("batch-a", ["src/kem.c"])
        raw_a = self.pass_f0_for_batch("batch-a")[0]
        self.add_search_page("batch-b", ["src/kem.c"], query_text="different query")

        occurrence_count = self.conn.execute(
            "SELECT COUNT(*) FROM raw_search_item_occurrences WHERE search_item_key = ?",
            (raw_a["search_item_key"],),
        ).fetchone()[0]
        status = compute_pipeline_handoff_status(self.conn, "batch-a")

        self.assertEqual(occurrence_count, 2)
        self.assertEqual(status["files"]["pending"], 1)
        self.assertEqual(status["files"]["error"], 0)
        self.assertEqual(status["f1"]["pending"], 0)

    def test_file_error_recovery_requires_explicit_include_errors(self):
        self.add_search_page("batch-a", ["src/kem.c"])
        raw_a = self.pass_f0_for_batch("batch-a")[0]
        upsert_file_fetch_result(
            self.conn,
            "batch-a",
            dict(raw_a),
            "error",
            error=RuntimeError("temporary fetch failure"),
        )

        without_errors = pending_pipeline_batches(self.conn, "files")
        with_errors = pending_pipeline_batches(self.conn, "files", include_errors=True)

        self.assertEqual(without_errors, [])
        self.assertEqual(
            with_errors,
            [{"stage": "files", "batch_id": "batch-a", "pending_count": 1}],
        )

    def test_init_db_backfills_occurrences_for_existing_raw_items(self):
        self.add_search_page("batch-a", ["src/kem.c"])
        self.conn.execute("DELETE FROM raw_search_item_occurrences")
        self.conn.commit()

        init_db(self.conn)

        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM raw_search_item_occurrences").fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
