"""Fetch immutable review dossiers and persist explicitly authored assessments."""

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from collect import PROJECT_ROOT, load_env_file


POLICY = {
    "version": "classical-to-pqc-review-v1",
    "accept": "A commit changes an existing cryptographic workflow from classical "
    "cryptography to PQC, or integrates a selectable/mandatory PQC or hybrid path "
    "into that existing workflow. Before/after and integration evidence are required.",
    "exclude": ["standalone initial implementation", "benchmark/conformance probe",
                "standalone example without a migrated legacy workflow",
                "dependency/vendor snapshot", "existing PQC refactor or bug fix",
                "PQC algorithm rename or parameter/provider change",
                "library capability without adoption into an existing workflow",
                "scanner inventory or test fixture", "reverse migration"],
    "uncertain": "Use needs_review for inconclusive semantics; inaccessible for failed "
    "remote verification. Neither is an accepted dataset row.",
    "review_method": "Codex reads freshly retrieved commit diffs, parent/current "
    "files and the export evidence, then explicitly authors per-candidate decisions. "
    "The runner does not infer migration labels from keywords.",
    "verification_level": "Static source-level migration assessment, not a runtime "
    "test, deployment confirmation or cryptographic security audit. Educational "
    "clients with concrete before/after workflows retain their source-kind label.",
}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare(run):
    source = PROJECT_ROOT / "data/exports/migration_candidates.jsonl"
    if (run / "manifest.json").exists():
        return read_json(run / "manifest.json")
    content = source.read_bytes()
    rows = [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    if len({r["candidate_key"] for r in rows}) != len(rows):
        raise ValueError("Duplicate candidate keys in export")
    run.mkdir(parents=True, exist_ok=True)
    (run / "export_snapshot.jsonl").write_bytes(content)
    manifest = {"run_id": run.name, "created_at": now(), "source": str(source),
                "source_sha256": digest(content), "candidate_count": len(rows), "policy": POLICY}
    write_json(run / "manifest.json", manifest)
    write_json(run / "inventory.json", [
        {"ordinal": i, "candidate_key": r["candidate_key"], "repository": r["repository"]["full_name"],
         "sha": r["source"]["commit_sha"], "path": r["source"]["primary_path"]}
        for i, r in enumerate(rows, 1)])
    return manifest


class Remote:
    def __init__(self, run):
        self.run = run
        load_env_file(PROJECT_ROOT / ".env")
        self.token = os.environ.get("GITHUB_TOKEN")

    def get(self, endpoint):
        url = "https://api.github.com" + endpoint
        cache = self.run / "remote" / (digest(url.encode()) + ".json")
        if cache.exists():
            result = read_json(cache)
            if result["status"] in (200, 404):
                return result
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "pqc-migration-review",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers=headers), timeout=40) as response:
                    body = response.read()
                    result = {"url": url, "fetched_at": now(), "status": response.status,
                              "sha256": digest(body), "payload": json.loads(body),
                              "link": response.headers.get("Link"),
                              "remaining": response.headers.get("X-RateLimit-Remaining")}
                break
            except HTTPError as error:
                result = {"url": url, "fetched_at": now(), "status": error.code,
                          "error": "HTTP " + str(error.code)}
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    break
                time.sleep(2 ** attempt)
            except (URLError, TimeoutError, OSError) as error:
                result = {"url": url, "fetched_at": now(), "status": 0, "error": type(error).__name__}
                if attempt == 2:
                    break
                time.sleep(2 ** attempt)
        write_json(cache, result)
        return result

    def commit(self, repo, sha):
        first = self.get(f"/repos/{repo}/commits/{sha}?per_page=100&page=1")
        if first["status"] != 200:
            return first
        payload = dict(first["payload"])
        payload["files"] = list(payload.get("files", []))
        current = first
        page = 1
        while current.get("link") and 'rel="next"' in current["link"] and page < 30:
            page += 1
            current = self.get(f"/repos/{repo}/commits/{sha}?per_page=100&page={page}")
            if current["status"] != 200:
                break
            payload["files"].extend(current["payload"].get("files", []))
        return {**first, "payload": payload, "pages": page,
                "files_complete": current["status"] == 200 and not
                (current.get("link") and 'rel="next"' in current["link"])}

    def file(self, repo, path, sha):
        if not sha:
            return {"status": "no_parent", "text": ""}
        result = self.get(f"/repos/{repo}/contents/{quote(path, safe='/')}?" + urlencode({"ref": sha}))
        if result["status"] == 200:
            payload = result["payload"]
            if payload.get("encoding") != "base64":
                result = self.get(f"/repos/{repo}/git/blobs/{payload['sha']}")
                payload = result.get("payload", {})
            if result["status"] == 200 and payload.get("encoding") == "base64":
                data = base64.b64decode(payload["content"])
                return {"status": 200, "url": result["url"], "fetched_at": result["fetched_at"],
                        "blob_sha": payload["sha"], "sha256": digest(data),
                        "text": data.decode("utf-8", errors="replace")}
        return {k: v for k, v in result.items() if k != "payload"}


def fetch_dossier(remote, row, ordinal):
    repo = row["repository"]["full_name"]
    source = row["source"]
    sha, path = source["commit_sha"], source["primary_path"]
    repository = remote.get(f"/repos/{repo}")
    commit = remote.commit(repo, sha)
    dossier = {"ordinal": ordinal, "candidate_key": row["candidate_key"], "repository": repo,
               "sha": sha, "path": path, "export_label": row["final_label"],
               "commit_url": source["commit_url"], "fetched_at": now(),
               "repository_response": repository, "commit_response": commit,
               "export_evidence": row["review_evidence"]}
    if repository["status"] != 200 or commit["status"] != 200:
        dossier["remote_status"] = "inaccessible"
        return dossier
    payload = commit["payload"]
    if payload["sha"] != sha:
        raise ValueError("GitHub commit SHA mismatch")
    if repository["payload"]["id"] != row["repository"]["id"]:
        raise ValueError("GitHub repository identity mismatch")
    parents = payload.get("parents", [])
    parent = parents[0]["sha"] if parents else None
    primary = next((f for f in payload.get("files", []) if f["filename"] == path), None)
    dossier["primary"] = primary
    dossier["parent_sha"] = parent
    dossier["before"] = remote.file(repo, (primary or {}).get("previous_filename", path), parent)
    dossier["after"] = remote.file(repo, path, sha)
    patch = (primary or {}).get("patch", "")
    message = payload.get("commit", {}).get("message", "")
    checks = []
    for ev in row["review_evidence"]:
        context = ev.get("context") or ev.get("snippet") or ""
        field = ev.get("source_field")
        haystack = patch if field == "patch" else message if field in ("commit_message", "message") else ""
        checks.append({"evidence_id": ev.get("evidence_id"), "source_field": field,
                       "context_matches_remote": context in haystack if haystack and context else None})
    dossier["evidence_audit"] = checks
    old_patch = Path(source["patch_path"])
    dossier["export_patch_matches_remote"] = old_patch.exists() and old_patch.read_text(encoding="utf-8").strip() == patch.strip()
    before_ok = dossier["before"]["status"] == 200 or (
        dossier["before"]["status"] in (404, "no_parent") and primary and primary["status"] == "added")
    after_ok = dossier["after"]["status"] == 200 or (
        dossier["after"]["status"] == 404 and primary and primary["status"] == "removed")
    dossier["remote_status"] = "verified" if primary and before_ok and after_ok else "incomplete"
    return dossier


def fetch(run, start, end):
    prepare(run)
    remote = Remote(run)
    rows = [json.loads(line) for line in (run / "export_snapshot.jsonl").read_text(encoding="utf-8").splitlines()]
    for ordinal, row in enumerate(rows, 1):
        if ordinal < start or ordinal > end:
            continue
        target = run / "dossiers" / f"{ordinal:03}.json"
        if target.exists() and read_json(target).get("remote_status") == "verified":
            print(f"{ordinal:03} cached", flush=True)
            continue
        try:
            dossier = fetch_dossier(remote, row, ordinal)
        except Exception as error:
            dossier = {"ordinal": ordinal, "candidate_key": row["candidate_key"],
                       "remote_status": "inaccessible", "error": type(error).__name__, "fetched_at": now()}
        write_json(target, dossier)
        print(f"{ordinal:03} {dossier['remote_status']} {row['repository']['full_name']} {row['source']['primary_path']}", flush=True)


def show(run, start, end, mode, pattern, line_start=1, line_end=100000, grep=None):
    import re
    for ordinal in range(start, end + 1):
        path = run / "dossiers" / f"{ordinal:03}.json"
        if not path.exists():
            continue
        d = read_json(path)
        print(f"\n=== {ordinal:03} {d.get('repository')} {d.get('path')} [{d['remote_status']}] ===")
        payload = d.get("commit_response", {}).get("payload", {})
        message = payload.get("commit", {}).get("message", "")
        print(message[:1400] + ("\n[message excerpt]" if len(message) > 1400 else ""))
        print("PARENT", d.get("parent_sha"), "FILE", (d.get("primary") or {}).get("status"),
              "PATCH_MATCH", d.get("export_patch_matches_remote"), "FILES_COMPLETE", d.get("commit_response", {}).get("files_complete"))
        if mode == "summary":
            print(json.dumps({"files": [(f["filename"], f.get("status"), f.get("changes")) for f in payload.get("files", [])],
                              "export_evidence": [{k: e.get(k) for k in ("signal_type", "source_field", "context", "patch_line_no")} for e in d.get("export_evidence", [])]}, ensure_ascii=True))
        else:
            if mode in ("before", "after"):
                sources = [(d.get("path"), d.get(mode, {}).get("text", ""))]
            elif mode == "primary":
                sources = [(d.get("path"), (d.get("primary") or {}).get("patch", ""))]
            else:
                sources = [(f["filename"], f.get("patch", "")) for f in payload.get("files", []) if not pattern or re.search(pattern, f["filename"], re.I)]
            for name, content in sources:
                print("FILE", name)
                lines = content.splitlines()
                selected = set(range(max(1, line_start), min(len(lines), line_end) + 1))
                if grep:
                    matches = {i for i, line in enumerate(lines, 1) if re.search(grep, line, re.I)}
                    selected &= {j for i in matches for j in range(max(1, i - 3), min(len(lines), i + 3) + 1)}
                print("\n".join(f"{i}: {lines[i - 1]}" for i in sorted(selected)))
                print(f"[shown {len(selected)}/{len(lines)} lines]")


def resolve_reference(dossier, ref):
    kind = ref["kind"]
    path = ref.get("path", dossier["path"])
    if kind in ("before", "after"):
        if path != dossier["path"]:
            raise ValueError("Snapshot reference must use the primary path")
        text = dossier[kind]["text"]
        sha = dossier["parent_sha"] if kind == "before" else dossier["sha"]
        actual_path = (dossier["primary"].get("previous_filename", path) if kind == "before" else path)
        url = f"https://github.com/{dossier['repository']}/blob/{sha}/{quote(actual_path)}"
    elif kind == "patch":
        file = next(f for f in dossier["commit_response"]["payload"]["files"] if f["filename"] == path)
        text = file.get("patch", "")
        url = dossier["commit_url"]
    else:
        raise ValueError("Evidence kind must be before, after or patch")
    needle = ref["contains"]
    lines = text.splitlines()
    positions = [i for i, line in enumerate(lines, 1) if needle in line]
    if not positions:
        raise ValueError(f"Evidence not present for {dossier['ordinal']}: {needle}")
    line = positions[0]
    return {**ref, "path": path, "line": line, "matched_line": lines[line - 1],
            "source_url": url + (f"#L{line}" if kind != "patch" else ""),
            "line_type": "patch_line" if kind == "patch" else "file_line"}


def persist(run, dry_run=False):
    manifest = read_json(run / "manifest.json")
    snapshot = (run / "export_snapshot.jsonl").read_bytes()
    if digest(snapshot) != manifest["source_sha256"]:
        raise ValueError("Export snapshot changed")
    rows = [json.loads(line) for line in snapshot.decode("utf-8").splitlines()]
    if len(rows) != manifest["candidate_count"] or len({r["candidate_key"] for r in rows}) != len(rows):
        raise ValueError("Snapshot candidate identity/count mismatch")
    decisions = read_json(run / "decisions.json")
    by_ordinal = {x["ordinal"]: x for x in decisions}
    if len(by_ordinal) != len(decisions) or set(by_ordinal) != set(range(1, len(rows) + 1)):
        raise ValueError("Exactly one explicit decision required for every export row")
    reviews = []
    for ordinal, row in enumerate(rows, 1):
        decision = by_ordinal[ordinal]
        dossier_path = run / "dossiers" / f"{ordinal:03}.json"
        dossier = read_json(dossier_path)
        if dossier["candidate_key"] != row["candidate_key"]:
            raise ValueError("Dossier identity mismatch")
        verdict = decision["verdict"]
        if verdict not in ("accepted", "rejected", "needs_review", "inaccessible"):
            raise ValueError("Invalid verdict")
        if verdict in ("accepted", "rejected") and dossier["remote_status"] != "verified":
            raise ValueError("Conclusive decisions require remote verification")
        refs = [resolve_reference(dossier, ref) for ref in decision.get("evidence", [])]
        if verdict in ("accepted", "rejected") and not refs:
            raise ValueError("Conclusive decisions require source evidence")
        if verdict == "accepted" and (not decision.get("before_behavior") or not decision.get("after_behavior") or not decision.get("migration_type")):
            raise ValueError("Accepted rows require migration type and before/after descriptions")
        reviews.append({**decision, "candidate_key": row["candidate_key"], "repository": row["repository"]["full_name"],
                        "commit_sha": row["source"]["commit_sha"], "primary_path": row["source"]["primary_path"],
                        "commit_url": row["source"]["commit_url"], "original_label": row["final_label"],
                        "remote_status": dossier["remote_status"], "parent_sha": dossier.get("parent_sha"),
                        "dossier_path": str(dossier_path), "dossier_sha256": digest(dossier_path.read_bytes()),
                        "evidence": refs, "checked_at": now(), "source_row": row})
    counts = dict(Counter(r["verdict"] for r in reviews))
    summary = {"run_id": run.name, "total": len(reviews), "verdicts": counts,
               "reason_codes": dict(Counter(r["reason_code"] for r in reviews)),
               "source_export_unchanged": digest(Path(manifest["source"]).read_bytes()) == manifest["source_sha256"],
               "evidence_reference_count": sum(len(r["evidence"]) for r in reviews),
               "remote_verified": sum(r["remote_status"] == "verified" for r in reviews),
               "verification_level": POLICY["verification_level"]}
    if dry_run:
        print(json.dumps(summary, indent=2))
        return summary
    conn = sqlite3.connect(PROJECT_ROOT / "data/collector.sqlite", timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS migration_verification_runs (
            run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, completed_at TEXT NOT NULL,
            export_sha256 TEXT NOT NULL, candidate_count INTEGER NOT NULL,
            policy_json TEXT NOT NULL, summary_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS migration_candidate_reviews (
            run_id TEXT NOT NULL REFERENCES migration_verification_runs(run_id),
            candidate_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
            repository_full_name TEXT NOT NULL, commit_sha TEXT NOT NULL,
            primary_path TEXT NOT NULL, original_label TEXT NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN ('accepted','rejected','needs_review','inaccessible')),
            reason_code TEXT NOT NULL, rationale TEXT NOT NULL, migration_type TEXT,
            before_behavior TEXT, after_behavior TEXT, remote_status TEXT NOT NULL,
            evidence_json TEXT NOT NULL, dossier_path TEXT NOT NULL, dossier_sha256 TEXT NOT NULL,
            reviewed_at TEXT NOT NULL, review_json TEXT NOT NULL,
            PRIMARY KEY(run_id, candidate_key), UNIQUE(run_id, ordinal)
        );
        CREATE TABLE IF NOT EXISTS verified_migration_dataset (
            run_id TEXT NOT NULL, candidate_key TEXT NOT NULL,
            repository_full_name TEXT NOT NULL, commit_sha TEXT NOT NULL, parent_sha TEXT,
            primary_path TEXT NOT NULL, migration_type TEXT NOT NULL,
            before_behavior TEXT NOT NULL, after_behavior TEXT NOT NULL,
            rationale TEXT NOT NULL, evidence_json TEXT NOT NULL, source_export_json TEXT NOT NULL,
            reviewed_at TEXT NOT NULL, PRIMARY KEY(run_id, candidate_key),
            FOREIGN KEY(run_id,candidate_key) REFERENCES migration_candidate_reviews(run_id,candidate_key)
        );
        CREATE INDEX IF NOT EXISTS idx_migration_reviews_verdict ON migration_candidate_reviews(run_id,verdict);
    """)
    with conn:
        conn.execute("INSERT INTO migration_verification_runs VALUES (?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET completed_at=excluded.completed_at,policy_json=excluded.policy_json,summary_json=excluded.summary_json",
                     (run.name, manifest["created_at"], now(), manifest["source_sha256"], len(rows), json.dumps(POLICY), json.dumps(summary)))
        conn.execute("DELETE FROM verified_migration_dataset WHERE run_id=?", (run.name,))
        conn.execute("DELETE FROM migration_candidate_reviews WHERE run_id=?", (run.name,))
        for r in reviews:
            evidence = json.dumps(r["evidence"], ensure_ascii=False)
            conn.execute("INSERT INTO migration_candidate_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (run.name, r["candidate_key"], r["ordinal"], r["repository"], r["commit_sha"], r["primary_path"],
                          r["original_label"], r["verdict"], r["reason_code"], r["rationale"], r.get("migration_type"),
                          r.get("before_behavior"), r.get("after_behavior"), r["remote_status"], evidence,
                          r["dossier_path"], r["dossier_sha256"], r["checked_at"], json.dumps(r, ensure_ascii=False)))
            if r["verdict"] == "accepted":
                conn.execute("INSERT INTO verified_migration_dataset VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (run.name, r["candidate_key"], r["repository"], r["commit_sha"], r["parent_sha"], r["primary_path"],
                              r["migration_type"], r["before_behavior"], r["after_behavior"], r["rationale"], evidence,
                              json.dumps(r["source_row"], ensure_ascii=False), r["checked_at"]))
        actual = conn.execute("SELECT count(*) FROM migration_candidate_reviews WHERE run_id=?", (run.name,)).fetchone()[0]
        accepted = conn.execute("SELECT count(*) FROM verified_migration_dataset WHERE run_id=?", (run.name,)).fetchone()[0]
        if actual != len(rows) or accepted != counts.get("accepted", 0):
            raise ValueError("Stored row counts do not match completed review")
    conn.close()
    write_json(run / "reviews.json", reviews)
    write_json(run / "summary.json", summary)
    write_json(run / "review_policy.json", POLICY)
    (run / "accepted.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reviews if r["verdict"] == "accepted"), encoding="utf-8")
    report = ["# Export Candidate Verification", "", f"Run: `{run.name}`", "",
              f"Reviewed {len(reviews)} candidates: {counts}.", "", POLICY["verification_level"], "",
              "Database: `data/collector.sqlite`", "",
              "- All verdicts: `migration_candidate_reviews`",
              "- Accepted dataset only: `verified_migration_dataset`",
              "- Run manifest and policy: `migration_verification_runs`", "",
              "## Accepted", ""]
    for r in reviews:
        if r["verdict"] != "accepted":
            continue
        report.extend([f"### {r['ordinal']:03} {r['repository']}", "",
                       f"`{r['primary_path']}` | `{r['migration_type']}` | `{r.get('source_kind')}`", "",
                       "Before: " + r["before_behavior"], "", "After: " + r["after_behavior"], "",
                       r["rationale"], "", r.get("limitations", ""), "",
                       f"[Commit]({r['commit_url']})", ""])
    report.extend(["## All Candidate Decisions", ""])
    for r in reviews:
        report.extend([f"### {r['ordinal']:03} {r['repository']} ({r['verdict']})", "",
                       f"`{r['primary_path']}` | `{r['reason_code']}`", "", r["rationale"], "",
                       f"[Commit]({r['commit_url']})", ""])
        for ref in r["evidence"]:
            report.append(f"- [{ref['path']}:{ref['line']}]({ref['source_url']}) ({ref['line_type']}): `{ref['matched_line'].strip().replace('`', '')}`")
        report.append("")
    (run / "review_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "fetch", "show", "validate", "persist"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=100000)
    parser.add_argument("--mode", choices=("summary", "primary", "commit", "before", "after"), default="primary")
    parser.add_argument("--pattern")
    parser.add_argument("--line-start", type=int, default=1)
    parser.add_argument("--line-end", type=int, default=100000)
    parser.add_argument("--grep")
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
        parser.error("run-id must be a directory name")
    run = PROJECT_ROOT / "reports/verification" / args.run_id
    if args.command == "prepare":
        print(json.dumps(prepare(run), indent=2))
    elif args.command == "fetch":
        fetch(run, args.start, args.end)
    elif args.command == "show":
        show(run, args.start, min(args.end, read_json(run / "manifest.json")["candidate_count"]), args.mode, args.pattern, args.line_start, args.line_end, args.grep)
    else:
        persist(run, dry_run=args.command == "validate")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
