"""Batch pipeline orchestration for collector and filter stages."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pqc_collector.collect import GitHubApiError, GitHubRateLimitError
from pqc_collector.core import file_key
from pqc_collector.filter import (
    build_export_row,
    classify_migration,
    find_exact_changed_file,
    is_export_eligible,
    run_d0_for_item as build_d0_row,
    run_f0_for_item,
    run_f1,
)
from pqc_collector.reports import (
    normalize_f2_report_row,
    summarize_d0_results,
    summarize_f0_results,
    summarize_f1_results,
    summarize_f2_results,
    summarize_filter_results,
    write_d0_report,
    write_f0_report,
    write_f1_report,
    write_f2_report,
    write_filter_summary_json,
    write_filter_summary_md,
)
from pqc_collector.storage import (
    iter_f0_passed_items,
    iter_f1_passed_items,
    iter_d0_passed_rows,
    iter_files_for_f1,
    iter_raw_search_items,
    read_commit_detail,
    read_d0_commit_status,
    read_d0_history_state,
    read_export_candidates,
    read_file_snapshot,
    rebuild_cumulative_export,
    upsert_commit_detail,
    upsert_d0_commit_status,
    upsert_d0_history_state,
    upsert_diff_evidence,
    upsert_f0_result,
    upsert_f2_result,
    upsert_f1_result,
    upsert_file_fetch_result,
    upsert_file_snapshot,
    write_batch_export,
    write_non_exported_candidates,
    write_raw_patch,
    write_raw_response,
)


DEFAULT_D0_COMMIT_HISTORY_PER_PAGE = 100
COMPLETED_D0_COMMIT_STATUSES = {
    "processed",
    "skipped",
    "evidence_unavailable",
    "access_error",
    "error",
}


def run_f0_batch(conn, batch_id, limit=None, root=None, rules=None, checked_at=None):
    """Run F0 path quality filtering for raw search items in one batch."""
    raw_items = list(iter_raw_search_items(conn, batch_id, limit))
    f0_rows = []
    new_result_count = 0
    updated_result_count = 0

    for item in raw_items:
        f0_row = run_f0_for_item(item, rules=rules, checked_at=checked_at)
        stored_row = upsert_f0_result(conn, batch_id, f0_row)
        if stored_row["status"] == "new":
            new_result_count += 1
        else:
            updated_result_count += 1
        f0_rows.append(f0_row)

    report_path = write_f0_report(f0_rows, batch_id, root=root)
    summary = summarize_f0_results(f0_rows)
    return {
        "batch_id": batch_id,
        "status": "completed",
        "raw_item_count": len(raw_items),
        "processed_item_count": len(f0_rows),
        "new_result_count": new_result_count,
        "updated_result_count": updated_result_count,
        "report_paths": {
            "filter_f0_path_quality": str(report_path),
        },
        "summary": summary,
        "sample_row": f0_rows[0] if f0_rows else None,
    }


def _raw_file_response_key(item):
    key = file_key(item["repository_id"], item["normalized_path"], item["blob_sha"])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def fetch_file_batch(conn, batch_id, client, limit=None, root=None):
    """Fetch and store file snapshots for F0-passed items in one batch."""
    queue = list(iter_f0_passed_items(conn, batch_id, limit))
    fetched_rows = []
    skipped_rows = []
    error_rows = []
    new_snapshot_count = 0
    updated_snapshot_count = 0

    for item in queue:
        key = file_key(item["repository_id"], item["normalized_path"], item["blob_sha"])
        existing = read_file_snapshot(conn, key)
        if existing:
            existing["status"] = "existing"
            upsert_file_fetch_result(
                conn,
                batch_id,
                item,
                "existing",
                file_key_value=key,
                raw_file_path=existing.get("raw_file_path"),
            )
            skipped_rows.append(existing)
            continue

        try:
            response = client.get_file(item["file_api_url"])
        except Exception as exc:
            error_rows.append(
                upsert_file_fetch_result(
                    conn,
                    batch_id,
                    item,
                    "error",
                    file_key_value=key,
                    error=exc,
                )
            )
            continue
        raw_path = write_raw_response(
            batch_id,
            "file",
            _raw_file_response_key(item),
            response,
            root,
        )
        stored_row = upsert_file_snapshot(conn, batch_id, item, response, raw_path)
        upsert_file_fetch_result(
            conn,
            batch_id,
            item,
            "fetched",
            file_key_value=stored_row["file_key"],
            raw_file_path=stored_row["raw_file_path"],
        )
        if stored_row["status"] == "new":
            new_snapshot_count += 1
        else:
            updated_snapshot_count += 1
        fetched_rows.append(stored_row)

    return {
        "batch_id": batch_id,
        "status": "completed_with_errors" if error_rows else "completed",
        "queued_item_count": len(queue),
        "fetched_item_count": len(fetched_rows),
        "skipped_existing_count": len(skipped_rows),
        "error_item_count": len(error_rows),
        "new_snapshot_count": new_snapshot_count,
        "updated_snapshot_count": updated_snapshot_count,
        "raw_file_paths": [row["raw_file_path"] for row in fetched_rows],
        "errors": error_rows,
        "sample_fetched_row": fetched_rows[0] if fetched_rows else None,
        "sample_skipped_row": skipped_rows[0] if skipped_rows else None,
        "sample_error_row": error_rows[0] if error_rows else None,
    }


def run_f1_batch(conn, batch_id, limit=None, root=None, configs=None, checked_at=None):
    """Run F1 static candidate filtering for fetched F0-passed files."""
    file_rows = list(iter_files_for_f1(conn, batch_id, limit))
    f1_rows = []
    new_result_count = 0
    updated_result_count = 0

    for file_row in file_rows:
        f0_result = {
            "passed": True,
            "source_kind": file_row.get("source_kind"),
            "reason_codes": file_row.get("f0_reason_codes", []),
        }
        f1_row = run_f1(
            file_row,
            f0_result=f0_result,
            configs=configs,
            checked_at=checked_at,
        )
        stored_row = upsert_f1_result(conn, batch_id, f1_row)
        if stored_row["status"] == "new":
            new_result_count += 1
        else:
            updated_result_count += 1
        f1_rows.append(f1_row)

    report_path = write_f1_report(f1_rows, batch_id, root=root)
    summary = summarize_f1_results(f1_rows)
    return {
        "batch_id": batch_id,
        "status": "completed",
        "queued_file_count": len(file_rows),
        "processed_file_count": len(f1_rows),
        "new_result_count": new_result_count,
        "updated_result_count": updated_result_count,
        "report_paths": {
            "filter_f1_static_candidate": str(report_path),
        },
        "summary": summary,
        "sample_row": f1_rows[0] if f1_rows else None,
    }


def _d0_timestamp(value=None):
    return value or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resume_after_for_rate_limit(error):
    if getattr(error, "reset_at", None):
        return error.reset_at
    retry_after = getattr(error, "retry_after_seconds", None)
    if retry_after is None:
        return None
    resume_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(retry_after)))
    return resume_at.isoformat().replace("+00:00", "Z")


def _call_list_commits(client, repo, path, page, per_page):
    try:
        return client.list_commits_for_path(
            repo,
            path,
            page=page,
            per_page=per_page,
            wait_on_rate_limit=False,
        )
    except TypeError:
        return client.list_commits_for_path(repo, path, page=page, per_page=per_page)


def _call_get_commit(client, repo, sha):
    try:
        return client.get_commit(repo, sha, wait_on_rate_limit=False)
    except TypeError:
        return client.get_commit(repo, sha)


def _cached_commit_response(conn, item, commit_sha):
    cached = read_commit_detail(conn, item, commit_sha)
    if not cached:
        return None, None
    raw_path = cached.get("raw_commit_path")
    if raw_path and Path(raw_path).exists():
        return _read_json_file(raw_path), raw_path
    return None, None


def _get_or_fetch_commit_response(conn, batch_id, item, commit_sha, client, root=None):
    cached_response, cached_path = _cached_commit_response(conn, item, commit_sha)
    if cached_response is not None:
        return cached_response, cached_path, True
    commit_response = _call_get_commit(client, item["repository_full_name"], commit_sha)
    raw_commit_path = write_raw_response(batch_id, "commit", commit_sha, commit_response, root)
    upsert_commit_detail(conn, item, commit_sha, str(raw_commit_path))
    return commit_response, str(raw_commit_path), False


def _d0_row_with_status(d0_row):
    evidence_status = "processed"
    evidence_reason_code = None
    d0_status = "processed"
    if d0_row.get("exact_path_match") and not d0_row.get("patch_available"):
        evidence_status = "unavailable"
        evidence_reason_code = "d0_patch_missing"
        d0_status = "evidence_unavailable"
        reason_codes = list(d0_row.get("reason_codes") or [])
        if evidence_reason_code not in reason_codes:
            reason_codes.append(evidence_reason_code)
        d0_row["reason_codes"] = reason_codes
    d0_row["evidence_status"] = evidence_status
    d0_row["evidence_reason_code"] = evidence_reason_code
    d0_row["d0_status"] = d0_status
    return d0_row


def _process_d0_commit(conn, batch_id, item, commit_summary, client, root=None, checked_at=None):
    commit_sha = commit_summary.get("sha")
    if not commit_sha:
        return {
            "status": "skipped",
            "reason_code": "d0_missing_commit_sha",
            "stored_row": None,
            "cache_hit": False,
        }

    existing = read_d0_commit_status(conn, batch_id, item["search_item_key"], commit_sha)
    if existing and existing.get("status") in COMPLETED_D0_COMMIT_STATUSES:
        return {
            "status": "skipped_existing",
            "reason_code": existing.get("reason_code"),
            "stored_row": None,
            "cache_hit": True,
        }

    try:
        commit_response, raw_commit_path, cache_hit = _get_or_fetch_commit_response(
            conn,
            batch_id,
            item,
            commit_sha,
            client,
            root=root,
        )
    except GitHubRateLimitError:
        raise
    except GitHubApiError as error:
        upsert_d0_commit_status(
            conn,
            batch_id,
            item,
            commit_sha,
            status="access_error",
            reason_code="d0_commit_access_error",
            error=error,
            checked_at=checked_at,
        )
        return {
            "status": "access_error",
            "reason_code": "d0_commit_access_error",
            "stored_row": None,
            "cache_hit": False,
        }

    payload = commit_response.get("payload", {})
    matched_file = find_exact_changed_file(item["normalized_path"], payload.get("files", []))
    patch_path = None
    if matched_file and matched_file.get("patch_available"):
        preview_row = build_d0_row(
            item,
            commit_response,
            raw_commit_path=raw_commit_path,
            checked_at=checked_at,
        )
        patch_path = write_raw_patch(
            batch_id,
            preview_row["diff_file_key"],
            matched_file["patch"],
            root,
        )

    d0_row = build_d0_row(
        item,
        commit_response,
        raw_commit_path=raw_commit_path,
        patch_path=str(patch_path) if patch_path else None,
        checked_at=checked_at,
    )
    stored_row = upsert_diff_evidence(conn, batch_id, _d0_row_with_status(d0_row))
    status = "processed" if stored_row.get("evidence_status") == "processed" else "evidence_unavailable"
    reason_code = stored_row.get("evidence_reason_code")
    if status == "processed":
        reason_code = "d0_pass" if stored_row.get("passed") else "d0_drop"
    upsert_d0_commit_status(
        conn,
        batch_id,
        item,
        commit_sha,
        status=status,
        reason_code=reason_code,
        raw_commit_path=raw_commit_path,
        patch_path=str(patch_path) if patch_path else None,
        checked_at=checked_at,
    )
    return {
        "status": status,
        "reason_code": reason_code,
        "stored_row": stored_row,
        "raw_commit_path": raw_commit_path,
        "patch_path": str(patch_path) if patch_path else None,
        "cache_hit": cache_hit,
    }


def run_d0_for_item(
    conn,
    batch_id,
    item,
    client,
    root=None,
    checked_at=None,
    commit_history_per_page=DEFAULT_D0_COMMIT_HISTORY_PER_PAGE,
    max_history_pages=None,
    force_history=False,
):
    """Fetch and store D0 exact diff evidence across the full file commit history."""
    timestamp = _d0_timestamp(checked_at)
    state = read_d0_history_state(conn, batch_id, item["search_item_key"])
    start_page = 1
    if state and state.get("status") != "completed" and not force_history:
        start_page = max(1, int(state.get("next_page") or 1))

    counters = {
        "listed_commit_count": 0,
        "processed_commit_count": 0,
        "skipped_commit_count": 0,
        "pass_commit_count": 0,
        "drop_commit_count": 0,
        "evidence_unavailable_count": 0,
        "error_count": 0,
    }
    outcomes = []
    stored_rows = []
    page = start_page
    pages_seen = 0
    last_processed_commit_sha = None
    upsert_d0_history_state(
        conn,
        batch_id,
        item,
        status="running",
        next_page=page,
        counters=counters,
        checked_at=timestamp,
    )

    while True:
        if max_history_pages is not None and pages_seen >= int(max_history_pages):
            upsert_d0_history_state(
                conn,
                batch_id,
                item,
                status="partial",
                next_page=page,
                last_processed_commit_sha=last_processed_commit_sha,
                counters=counters,
                checked_at=timestamp,
            )
            break
        try:
            commits_response = _call_list_commits(
                client,
                item["repository_full_name"],
                item["normalized_path"],
                page,
                commit_history_per_page,
            )
        except GitHubRateLimitError as error:
            upsert_d0_history_state(
                conn,
                batch_id,
                item,
                status="waiting_rate_limit",
                next_page=page,
                last_processed_commit_sha=last_processed_commit_sha,
                counters=counters,
                resume_after=_resume_after_for_rate_limit(error),
                error=error,
                checked_at=timestamp,
            )
            return {
                "batch_id": batch_id,
                "search_item_key": item["search_item_key"],
                "status": "waiting_rate_limit",
                "commit_count": counters["listed_commit_count"],
                "stored_row": stored_rows[0] if stored_rows else None,
                "stored_rows": stored_rows,
                "outcomes": outcomes,
                **counters,
            }

        commits = commits_response.get("payload", [])
        pages_seen += 1
        if not commits:
            completed_at = _d0_timestamp()
            final_status = "no_commits_found" if counters["listed_commit_count"] == 0 else "completed"
            upsert_d0_history_state(
                conn,
                batch_id,
                item,
                status=final_status,
                next_page=page,
                last_processed_commit_sha=last_processed_commit_sha,
                counters=counters,
                checked_at=timestamp,
                completed_at=completed_at,
            )
            break

        counters["listed_commit_count"] += len(commits)
        for commit_summary in commits:
            try:
                outcome = _process_d0_commit(
                    conn,
                    batch_id,
                    item,
                    commit_summary,
                    client,
                    root=root,
                    checked_at=timestamp,
                )
            except GitHubRateLimitError as error:
                upsert_d0_history_state(
                    conn,
                    batch_id,
                    item,
                    status="waiting_rate_limit",
                    next_page=page,
                    last_processed_commit_sha=last_processed_commit_sha,
                    counters=counters,
                    resume_after=_resume_after_for_rate_limit(error),
                    error=error,
                    checked_at=timestamp,
                )
                return {
                    "batch_id": batch_id,
                    "search_item_key": item["search_item_key"],
                    "status": "waiting_rate_limit",
                    "commit_count": counters["listed_commit_count"],
                    "stored_row": stored_rows[0] if stored_rows else None,
                    "stored_rows": stored_rows,
                    "outcomes": outcomes,
                    **counters,
                }
            outcomes.append(outcome)
            commit_sha = commit_summary.get("sha")
            if commit_sha:
                last_processed_commit_sha = commit_sha
            stored_row = outcome.get("stored_row")
            if outcome["status"] == "skipped_existing":
                counters["skipped_commit_count"] += 1
                continue
            if outcome["status"] in ("access_error", "error"):
                counters["error_count"] += 1
                continue
            counters["processed_commit_count"] += 1
            if stored_row:
                stored_rows.append(stored_row)
                if stored_row.get("passed"):
                    counters["pass_commit_count"] += 1
                else:
                    counters["drop_commit_count"] += 1
                if stored_row.get("evidence_status") == "unavailable":
                    counters["evidence_unavailable_count"] += 1

        page += 1
        upsert_d0_history_state(
            conn,
            batch_id,
            item,
            status="running",
            next_page=page,
            last_processed_commit_sha=last_processed_commit_sha,
            counters=counters,
            checked_at=timestamp,
        )

    status = "completed_with_errors" if counters["error_count"] else "completed"
    if counters["listed_commit_count"] == 0:
        status = "no_commits_found"
    return {
        "batch_id": batch_id,
        "search_item_key": item["search_item_key"],
        "status": status,
        "commit_count": counters["listed_commit_count"],
        "stored_row": stored_rows[0] if stored_rows else None,
        "stored_rows": stored_rows,
        "outcomes": outcomes,
        **counters,
    }


def _d0_rows_for_batch(conn, batch_id):
    return conn.execute(
        """
        SELECT *
        FROM d0_results
        WHERE batch_id = ?
        ORDER BY repository_full_name, search_item_path, commit_sha
        """,
        (batch_id,),
    ).fetchall()


def run_d0_batch(
    conn,
    batch_id,
    client,
    limit=None,
    root=None,
    checked_at=None,
    commit_history_per_page=DEFAULT_D0_COMMIT_HISTORY_PER_PAGE,
    max_history_pages=None,
    force_history=False,
):
    """Run D0 exact diff evidence collection for F1-passed items in one batch."""
    queue = list(iter_f1_passed_items(conn, batch_id, limit))
    outcomes = []
    new_result_count = 0
    updated_result_count = 0
    no_commits_count = 0
    waiting_rate_limit_count = 0
    totals = {
        "listed_commit_count": 0,
        "processed_commit_count": 0,
        "skipped_commit_count": 0,
        "pass_commit_count": 0,
        "drop_commit_count": 0,
        "evidence_unavailable_count": 0,
        "error_count": 0,
    }

    for item in queue:
        outcome = run_d0_for_item(
            conn,
            batch_id,
            item,
            client,
            root=root,
            checked_at=checked_at,
            commit_history_per_page=commit_history_per_page,
            max_history_pages=max_history_pages,
            force_history=force_history,
        )
        outcomes.append(outcome)
        if outcome.get("status") == "waiting_rate_limit":
            waiting_rate_limit_count += 1
        if outcome.get("status") == "no_commits_found":
            no_commits_count += 1
        for key in totals:
            totals[key] += int(outcome.get(key) or 0)
        for stored_row in outcome.get("stored_rows") or []:
            if stored_row["status"] == "new":
                new_result_count += 1
            else:
                updated_result_count += 1

    d0_rows = [dict(row) for row in _d0_rows_for_batch(conn, batch_id)]
    report_path = write_d0_report(d0_rows, batch_id, root=root)
    summary = summarize_d0_results(d0_rows)
    status = "completed"
    if waiting_rate_limit_count:
        status = "waiting_rate_limit"
    elif totals["error_count"]:
        status = "completed_with_errors"
    return {
        "batch_id": batch_id,
        "status": status,
        "queued_item_count": len(queue),
        "processed_item_count": len(outcomes),
        "stored_result_count": len(d0_rows),
        "new_result_count": new_result_count,
        "updated_result_count": updated_result_count,
        "no_commits_count": no_commits_count,
        "waiting_rate_limit_count": waiting_rate_limit_count,
        **totals,
        "report_paths": {
            "filter_d0_diff_evidence": str(report_path),
        },
        "summary": summary,
        "sample_row": d0_rows[0] if d0_rows else None,
        "sample_outcome": outcomes[0] if outcomes else None,
    }


def _read_text_file(path):
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def _read_json_file(path):
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _commit_message_from_raw(raw_commit_path):
    raw = _read_json_file(raw_commit_path)
    payload = raw.get("payload", raw) if isinstance(raw, dict) else {}
    commit = payload.get("commit", {}) if isinstance(payload, dict) else {}
    return commit.get("message") or payload.get("message") or ""


def _f2_input_row(item):
    row = dict(item)
    row["patch"] = _read_text_file(row.get("patch_path"))
    row["message"] = _commit_message_from_raw(row.get("raw_commit_path"))
    return row


def run_f2_batch(conn, batch_id, limit=None, root=None, configs=None, checked_at=None):
    """Run F2 migration classification for D0-passed exact diff rows."""
    queue = list(iter_d0_passed_rows(conn, batch_id, limit))
    f2_rows = []
    new_result_count = 0
    updated_result_count = 0
    timestamp = checked_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    for item in queue:
        f2_row = classify_migration(_f2_input_row(item), configs=configs)
        f2_row["checked_at"] = timestamp
        stored_row = upsert_f2_result(conn, batch_id, f2_row)
        if stored_row["status"] == "new":
            new_result_count += 1
        else:
            updated_result_count += 1
        f2_rows.append(stored_row)

    report_path = write_f2_report(f2_rows, batch_id, root=root)
    summary = summarize_f2_results(f2_rows)
    filter_summary = summarize_filter_results(conn, batch_id)
    filter_summary_json_path = write_filter_summary_json(filter_summary, batch_id, root=root)
    filter_summary_md_path = write_filter_summary_md(filter_summary, batch_id, root=root)
    return {
        "batch_id": batch_id,
        "status": "completed",
        "queued_item_count": len(queue),
        "processed_item_count": len(f2_rows),
        "new_result_count": new_result_count,
        "updated_result_count": updated_result_count,
        "report_paths": {
            "filter_f2_migration_classifier": str(report_path),
            "filter_summary_json": str(filter_summary_json_path),
            "filter_summary_md": str(filter_summary_md_path),
        },
        "summary": summary,
        "filter_summary": filter_summary,
        "sample_row": f2_rows[0] if f2_rows else None,
    }


def _candidate_raw_evidence_paths(candidate):
    paths = []
    for key in ("raw_commit_path", "patch_path"):
        value = candidate.get(key)
        if value:
            paths.append(value)
    for evidence in candidate.get("review_evidence") or []:
        for key in ("raw_path", "patch_path"):
            value = evidence.get(key) if isinstance(evidence, dict) else None
            if value:
                paths.append(value)
    return list(dict.fromkeys(paths))


def _missing_raw_evidence_paths(candidate, root=None):
    base = Path(root).resolve() if root is not None else Path.cwd().resolve()
    missing = []
    for raw_path in _candidate_raw_evidence_paths(candidate):
        path = Path(raw_path)
        resolved = path if path.is_absolute() else base / path
        if not resolved.exists():
            missing.append(str(raw_path))
    return missing


def _export_exclusion_reason_codes(
    candidate,
    include_pqc_addition_only=False,
    missing_raw_paths=None,
):
    label = candidate.get("final_label")
    allowed_labels = {"hybrid_migration", "partial_migration", "full_migration"}
    if include_pqc_addition_only:
        allowed_labels.add("pqc_addition_only")

    reason_codes = []
    if label not in allowed_labels:
        if label == "pqc_addition_only":
            reason_codes.append("exclude_pqc_addition_only_requires_option")
        else:
            reason_codes.append("exclude_non_export_label")
    if not candidate.get("review_evidence"):
        reason_codes.append("exclude_missing_review_evidence")
    if missing_raw_paths:
        reason_codes.append("exclude_missing_raw_evidence_path")
    return reason_codes or ["exclude_not_export_eligible"]


def _jsonl_count(path):
    output_path = Path(path)
    if not output_path.exists():
        return 0
    with output_path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def export_batch(conn, batch_id, include_pqc_addition_only=False, root=None, exported_at=None):
    """Write batch and cumulative export JSONL files from stored F2 results."""
    candidates = read_export_candidates(conn, batch_id)
    timestamp = exported_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    export_rows = []
    non_export_rows = []

    for candidate in candidates:
        missing_raw_paths = _missing_raw_evidence_paths(candidate, root=root)
        if is_export_eligible(candidate, include_pqc_addition_only) and not missing_raw_paths:
            export_rows.append(
                build_export_row(
                    candidate,
                    include_pqc_addition_only=include_pqc_addition_only,
                    exported_at=timestamp,
                )
            )
            continue

        non_export_row = normalize_f2_report_row(batch_id, candidate)
        non_export_row["export_eligible"] = False
        non_export_row["export_exclusion_reason_codes"] = _export_exclusion_reason_codes(
            candidate,
            include_pqc_addition_only=include_pqc_addition_only,
            missing_raw_paths=missing_raw_paths,
        )
        non_export_row["missing_raw_evidence_paths"] = missing_raw_paths
        non_export_rows.append(non_export_row)

    export_path = write_batch_export(export_rows, batch_id, root=root)
    non_exported_path = write_non_exported_candidates(non_export_rows, batch_id, root=root)
    cumulative_path = rebuild_cumulative_export(
        conn,
        root=root,
        include_pqc_addition_only=include_pqc_addition_only,
        path_validator=lambda candidate: not _missing_raw_evidence_paths(candidate, root=root),
    )
    summary = summarize_filter_results(conn, batch_id)
    summary["export"] = {
        "default_export_count": len(export_rows),
        "non_exported_count": len(non_export_rows),
        "cumulative_export_count": _jsonl_count(cumulative_path),
        "include_pqc_addition_only": bool(include_pqc_addition_only),
    }
    summary_json_path = write_filter_summary_json(summary, batch_id, root=root)
    summary_md_path = write_filter_summary_md(summary, batch_id, root=root)

    return {
        "batch_id": batch_id,
        "status": "completed",
        "candidate_count": len(candidates),
        "exported_count": len(export_rows),
        "non_exported_count": len(non_export_rows),
        "cumulative_export_count": summary["export"]["cumulative_export_count"],
        "include_pqc_addition_only": bool(include_pqc_addition_only),
        "report_paths": {
            "export_candidates": str(export_path),
            "non_exported_candidates": str(non_exported_path),
            "cumulative_export": str(cumulative_path),
            "filter_summary_json": str(summary_json_path),
            "filter_summary_md": str(summary_md_path),
        },
        "summary": summary,
        "sample_export_row": export_rows[0] if export_rows else None,
        "sample_non_exported_row": non_export_rows[0] if non_export_rows else None,
    }
