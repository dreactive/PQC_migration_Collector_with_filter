import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))
import verify_exports as review


class VerificationStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.root_patch = patch.object(review, "PROJECT_ROOT", self.root)
        self.root_patch.start()
        self.run = self.root / "reports/verification/test-run"
        source = self.root / "data/exports/migration_candidates.jsonl"
        source.parent.mkdir(parents=True)
        rows = [{"candidate_key": f"candidate:{i}", "repository": {"full_name": "owner/repo"},
                 "final_label": "hybrid_migration", "source": {"commit_sha": "head",
                 "commit_url": "https://github.com/owner/repo/commit/head", "primary_path": f"file{i}.c"}}
                for i in (1, 2)]
        source.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        review.prepare(self.run)
        self.decisions = []
        for ordinal, row in enumerate(rows, 1):
            dossier = {"ordinal": ordinal, "candidate_key": row["candidate_key"],
                       "repository": "owner/repo", "sha": "head", "path": f"file{ordinal}.c",
                       "parent_sha": "parent", "commit_url": row["source"]["commit_url"],
                       "remote_status": "verified", "primary": {"filename": f"file{ordinal}.c"},
                       "before": {"text": "classical_exchange();\n"}, "after": {"text": "hybrid_exchange();\n"}}
            review.write_json(self.run / "dossiers" / f"{ordinal:03}.json", dossier)
            self.decisions.append({"ordinal": ordinal, "verdict": "accepted" if ordinal == 1 else "rejected",
                                   "reason_code": "fixture", "rationale": "An explicit assessment.",
                                   "migration_type": "hybrid_migration", "before_behavior": "Classical exchange",
                                   "after_behavior": "Hybrid exchange", "evidence": [
                                       {"kind": "before", "contains": "classical_exchange"},
                                       {"kind": "after", "contains": "hybrid_exchange"}]})
        self.save_decisions()

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def save_decisions(self):
        review.write_json(self.run / "decisions.json", self.decisions)

    def persist(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return review.persist(self.run, **kwargs)

    def test_all_rows_saved_and_accepted_subset_is_idempotent(self):
        db = self.root / "data/collector.sqlite"
        with contextlib.closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("CREATE TABLE existing_data(value TEXT)")
            conn.execute("INSERT INTO existing_data VALUES ('keep')")
        self.persist()
        self.persist()
        with contextlib.closing(sqlite3.connect(db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM migration_candidate_reviews").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT count(*) FROM verified_migration_dataset").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT value FROM existing_data").fetchone()[0], "keep")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.decisions[0]["verdict"] = "rejected"
        self.save_decisions()
        self.persist()
        with contextlib.closing(sqlite3.connect(db)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM verified_migration_dataset").fetchone()[0], 0)

    def test_missing_and_duplicate_decisions_rejected(self):
        original = self.decisions.copy()
        for invalid in (original[:1], original + original[:1]):
            self.decisions = invalid
            self.save_decisions()
            with self.assertRaisesRegex(ValueError, "Exactly one"):
                self.persist()
        self.assertFalse((self.root / "data/collector.sqlite").exists())

    def test_unfounded_evidence_rejected_before_database_write(self):
        self.decisions[0]["evidence"][0]["contains"] = "nonexistent source assertion"
        self.save_decisions()
        with self.assertRaisesRegex(ValueError, "Evidence not present"):
            self.persist()
        self.assertFalse((self.root / "data/collector.sqlite").exists())

    def test_failed_remote_access_cannot_be_accepted(self):
        path = self.run / "dossiers/001.json"
        dossier = review.read_json(path)
        dossier["remote_status"] = "inaccessible"
        review.write_json(path, dossier)
        with self.assertRaisesRegex(ValueError, "remote verification"):
            self.persist()

    def test_snapshot_tampering_rejected(self):
        path = self.run / "export_snapshot.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.persist()

    def test_dry_run_checks_every_reference_without_creating_database(self):
        result = self.persist(dry_run=True)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["evidence_reference_count"], 4)
        self.assertFalse((self.root / "data/collector.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
