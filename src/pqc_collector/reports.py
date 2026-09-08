import json
from datetime import datetime, timezone
from pathlib import Path

from pqc_collector.core import project_paths


COLLECTOR_REPORT_FILES = {
    "collection_summary": "collection_summary.md",
    "api_usage": "api_usage.json",
    "query_frontier": "query_frontier.json",
    "query_pages": "query_pages.jsonl",
    "raw_search_items": "raw_search_items.jsonl",
    "dedupe_summary": "dedupe_summary.json",
    "collector_events": "collector_events.jsonl",
}

FILTER_REPORT_FILES = {
    "filter_f0_path_quality": "filter_f0_path_quality.jsonl",
    "filter_f1_static_candidate": "filter_f1_static_candidate.jsonl",
    "filter_d0_diff_evidence": "filter_d0_diff_evidence.jsonl",
    "filter_f2_migration_classifier": "filter_f2_migration_classifier.jsonl",
    "filter_summary_json": "filter_summary.json",
    "filter_summary_md": "filter_summary.md",
}

DEFAULT_EXPORT_LABELS = ("hybrid_migration", "partial_migration", "full_migration")
REVIEW_DROP_SOURCE_KINDS = {
    "docs",
    "dependency",
    "vendor_or_generated",
    "test",
    "example",
    "fuzz_or_benchmark",
    "tooling_metadata",
    "unknown",
}

EXPORT_REPORT_FILES = {
    "export_candidates": "export_candidates.jsonl",
    "non_exported_candidates": "non_exported_candidates.jsonl",
}

REPORT_SCHEMAS = {
    "collection_summary": {
        "format": "md",
        "required_fields": [
            "batch_id",
            "generated_at",
            "collector_status",
            "query_group",
            "query_count",
            "query_pages_fetched",
            "query_pages_skipped",
            "raw_item_seen_count",
            "new_unique_item_count",
            "previous_duplicate_count",
            "current_batch_duplicate_count",
            "api_call_count_search",
            "api_call_count_core",
            "rate_limit_start",
            "rate_limit_end",
            "sleep_until",
            "high_yield_queries",
            "low_yield_queries",
            "next_recommended_query_group",
        ],
    },
    "api_usage": {
        "format": "json",
        "required_fields": [
            "batch_id",
            "generated_at",
            "calls",
            "rate_limit_start",
            "rate_limit_end",
        ],
    },
    "query_frontier": {
        "format": "json",
        "required_fields": [
            "query_key",
            "query_group",
            "next_page_to_fetch",
            "fetched_pages",
            "exhausted",
            "low_yield",
            "consecutive_duplicate_pages",
            "last_run_at",
            "last_duplicate_ratio",
        ],
    },
    "query_pages": {
        "format": "jsonl",
        "required_fields": [
            "batch_id",
            "query_page_key",
            "query_key",
            "query_group",
            "page",
            "page_size",
            "total_count",
            "item_count",
            "new_unique_item_count",
            "duplicate_item_count",
            "duplicate_ratio",
            "raw_path",
            "fetched_at",
        ],
    },
    "raw_search_items": {
        "format": "jsonl",
        "required_fields": [
            "batch_id",
            "search_item_key",
            "query_key",
            "repository_id",
            "repository_full_name",
            "repository_url",
            "path",
            "normalized_path",
            "blob_sha",
            "file_api_url",
            "html_url",
            "status",
            "first_seen_batch_id",
            "last_seen_batch_id",
            "raw_query_page_path",
        ],
    },
    "dedupe_summary": {
        "format": "json",
        "required_fields": [
            "batch_id",
            "raw_item_seen_count",
            "new_unique_item_count",
            "previous_duplicate_count",
            "current_batch_duplicate_count",
            "query_page_duplicate_count",
            "skipped_query_page_count",
            "skipped_file_fetch_count",
            "skipped_commit_fetch_count",
        ],
    },
    "collector_events": {
        "format": "jsonl",
        "required_fields": [
            "timestamp",
            "level",
            "event",
            "batch_id",
            "query_key",
            "entity_key",
            "message",
            "details",
        ],
    },
    "filter_f0_path_quality": {
        "format": "jsonl",
        "required_fields": [
            "batch_id",
            "search_item_key",
            "repository_full_name",
            "path",
            "normalized_path",
            "source_kind",
            "passed",
            "reason_codes",
            "checked_at",
        ],
    },
    "filter_f1_static_candidate": {
        "format": "jsonl",
        "required_fields": [
            "batch_id",
            "search_item_key",
            "file_key",
            "path",
            "language",
            "passed",
            "target_libraries",
            "matched_library_signals",
            "matched_pqc_api_signals",
            "matched_provider_signals",
            "library_evidence",
            "strong_signal_evidence",
            "quality",
            "reason_codes",
            "raw_file_path",
            "checked_at",
        ],
    },
    "filter_d0_diff_evidence": {
        "format": "jsonl",
        "required_fields": [
            "batch_id",
            "search_item_key",
            "file_key",
            "diff_file_key",
            "repository_full_name",
            "search_item_path",
            "commit_sha",
            "commit_url",
            "matched_changed_path",
            "exact_path_match",
            "patch_available",
            "passed",
            "changed_files",
            "review_evidence",
            "reason_codes",
            "raw_commit_path",
            "patch_path",
            "checked_at",
        ],
    },
    "filter_f2_migration_classifier": {
        "format": "jsonl",
        "required_fields": [
            "batch_id",
            "candidate_evidence_key",
            "search_item_key",
            "file_key",
            "diff_file_key",
            "repository",
            "source",
            "final_label",
            "classification",
            "signals",
            "reason_codes",
            "review_evidence",
            "evidence",
            "quality",
            "checked_at",
        ],
    },
    "filter_summary_json": {
        "format": "json",
        "required_fields": ["batch_id", "generated_at", "f0", "f1", "d0", "f2", "export"],
    },
    "filter_summary_md": {
        "format": "md",
        "required_fields": ["batch_id", "generated_at", "f0", "f1", "d0", "f2", "export"],
    },
    "export_candidates": {
        "format": "jsonl",
        "required_fields": [
            "candidate_key",
            "candidate_key_components",
            "batch_id",
            "first_exported_batch_id",
            "last_updated_batch_id",
            "source_batch_ids",
            "final_label",
            "repository",
            "source",
            "classification",
            "signals",
            "reason_codes",
            "review_evidence",
            "evidence",
            "quality",
            "exported_at",
        ],
    },
    "non_exported_candidates": {
        "format": "jsonl",
        "required_fields": [
            "batch_id",
            "final_label",
            "repository",
            "source",
            "reason_codes",
            "review_evidence",
            "evidence",
            "quality",
            "checked_at",
        ],
    },
    "cumulative_export": {
        "format": "jsonl",
        "required_fields": [
            "candidate_key",
            "candidate_key_components",
            "batch_id",
            "first_exported_batch_id",
            "last_updated_batch_id",
            "source_batch_ids",
            "final_label",
            "repository",
            "source",
            "classification",
            "signals",
            "reason_codes",
            "review_evidence",
            "evidence",
            "quality",
            "exported_at",
        ],
    },
}


def report_paths(batch_id, root=None):
    """Return canonical report paths for a batch."""
    paths = project_paths(root)
    batch_dir = paths["report_batches"] / batch_id
    reports = {
        "batch_dir": batch_dir,
        "collector": {
            name: batch_dir / file_name
            for name, file_name in COLLECTOR_REPORT_FILES.items()
        },
        "filter": {
            name: batch_dir / file_name for name, file_name in FILTER_REPORT_FILES.items()
        },
        "export": {
            name: batch_dir / file_name for name, file_name in EXPORT_REPORT_FILES.items()
        },
        "cumulative_export": paths["exports"] / "migration_candidates.jsonl",
    }
    return reports


def report_schemas():
    """Return required fields for each collector, filter, and export report."""
    return REPORT_SCHEMAS


def write_schema_preview(output_path):
    """Write a JSON preview of report schemas for human review."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema_count": len(report_schemas()),
        "schemas": report_schemas(),
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


API_CALL_KINDS = ("rate_limit", "search", "contents", "commits", "pulls")


def normalize_api_calls(calls):
    """Return all supported API call counters with missing kinds set to zero."""
    return {kind: int(calls.get(kind, 0)) for kind in API_CALL_KINDS}


def write_api_usage_report(
    batch_id,
    calls,
    rate_limit_start=None,
    rate_limit_end=None,
    output_path=None,
    root=None,
    generated_at=None,
):
    """Write GitHub API usage summary for one collector batch."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["api_usage"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "batch_id": batch_id,
        "generated_at": timestamp,
        "calls": normalize_api_calls(calls),
        "rate_limit_start": rate_limit_start or {},
        "rate_limit_end": rate_limit_end or {},
    }
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return report_path


FRONTIER_DEFAULTS = {
    "next_page_to_fetch": 1,
    "fetched_pages": 0,
    "exhausted": False,
    "low_yield": False,
    "consecutive_duplicate_pages": 0,
    "last_run_at": None,
    "last_duplicate_ratio": 0.0,
}


def normalize_frontier_row(row):
    """Return one query frontier row with all required fields."""
    frontier = dict(FRONTIER_DEFAULTS)
    frontier.update(row)
    return {
        "query_key": frontier["query_key"],
        "query_group": frontier["query_group"],
        "next_page_to_fetch": int(frontier["next_page_to_fetch"]),
        "fetched_pages": int(frontier["fetched_pages"]),
        "exhausted": bool(frontier["exhausted"]),
        "low_yield": bool(frontier["low_yield"]),
        "consecutive_duplicate_pages": int(frontier["consecutive_duplicate_pages"]),
        "last_run_at": frontier["last_run_at"],
        "last_duplicate_ratio": float(frontier["last_duplicate_ratio"]),
    }


def write_query_frontier_report(batch_id, rows, output_path=None, root=None):
    """Write query frontier state rows for one collector batch."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["query_frontier"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    frontier_rows = sorted(
        (normalize_frontier_row(row) for row in rows),
        key=lambda row: (row["query_group"], row["query_key"]),
    )
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(frontier_rows, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return report_path


SUMMARY_DEFAULTS = {
    "collector_status": "idle",
    "query_group": None,
    "query_count": 0,
    "query_pages_fetched": 0,
    "query_pages_skipped": 0,
    "raw_item_seen_count": 0,
    "new_unique_item_count": 0,
    "previous_duplicate_count": 0,
    "current_batch_duplicate_count": 0,
    "api_call_count_search": 0,
    "api_call_count_core": 0,
    "rate_limit_start": None,
    "rate_limit_end": None,
    "sleep_until": None,
    "high_yield_queries": [],
    "low_yield_queries": [],
    "next_recommended_query_group": None,
}


def normalize_collection_summary(batch_id, summary, generated_at=None):
    """Return a collection summary row with all required fields."""
    row = dict(SUMMARY_DEFAULTS)
    row.update(summary)
    row["batch_id"] = batch_id
    row["generated_at"] = generated_at or datetime.now(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )
    return row


def _format_value(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "[]"
    if isinstance(value, dict):
        parts = []
        for key, nested in sorted(value.items()):
            if isinstance(nested, dict):
                details = ", ".join(f"{name}={val}" for name, val in sorted(nested.items()))
                parts.append(f"{key}({details})")
            else:
                parts.append(f"{key}={nested}")
        return "; ".join(parts) if parts else "{}"
    return "null" if value is None else str(value)


def write_collection_summary_report(
    batch_id,
    summary,
    output_path=None,
    root=None,
    generated_at=None,
):
    """Write a human-readable collector summary for one batch."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["collection_summary"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    row = normalize_collection_summary(batch_id, summary, generated_at)
    field_order = ("batch_id", "generated_at", *SUMMARY_DEFAULTS.keys())
    lines = ["# Collection Summary", ""]
    lines.extend(f"- `{field}`: {_format_value(row[field])}" for field in field_order)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


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


def normalize_f0_report_row(batch_id, row):
    """Return one F0 report row with the public JSONL schema."""
    item = dict(row)
    reason_codes = item.get("reason_codes", [])
    if not reason_codes and item.get("reason_codes_json"):
        reason_codes = json.loads(item["reason_codes_json"])
    return {
        "batch_id": batch_id,
        "search_item_key": item["search_item_key"],
        "repository_full_name": item["repository_full_name"],
        "path": item["path"],
        "normalized_path": item["normalized_path"],
        "source_kind": item["source_kind"],
        "passed": bool(item["passed"]),
        "reason_codes": list(reason_codes),
        "checked_at": item["checked_at"],
    }


def write_f0_report(rows, batch_id, output_path=None, root=None):
    """Write F0 path quality rows for one batch as JSONL."""
    report_path = output_path or report_paths(batch_id, root)["filter"]["filter_f0_path_quality"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_rows = []
    for row in rows:
        item = dict(row)
        if item.get("batch_id", batch_id) == batch_id:
            normalized_rows.append(normalize_f0_report_row(batch_id, item))
    normalized_rows.sort(key=lambda row: (row["passed"], row["source_kind"], row["path"]))

    with report_path.open("w", encoding="utf-8") as handle:
        for row in normalized_rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return report_path


def summarize_f0_results(rows):
    """Return pass/drop counts for F0 path quality results."""
    summary = {
        "total": 0,
        "pass": 0,
        "drop": 0,
        "pass_by_source_kind": {},
        "drop_by_source_kind": {},
        "reason_counts": {},
    }
    for row in rows:
        item = dict(row)
        passed = bool(item["passed"])
        source_kind = item.get("source_kind") or "unknown"
        by_source_key = "pass_by_source_kind" if passed else "drop_by_source_kind"
        count_key = "pass" if passed else "drop"
        reason_codes = item.get("reason_codes", [])
        if not reason_codes and item.get("reason_codes_json"):
            reason_codes = json.loads(item["reason_codes_json"])

        summary["total"] += 1
        summary[count_key] += 1
        summary[by_source_key][source_kind] = summary[by_source_key].get(source_kind, 0) + 1
        for reason_code in reason_codes:
            summary["reason_counts"][reason_code] = summary["reason_counts"].get(reason_code, 0) + 1

    summary["pass_by_source_kind"] = dict(sorted(summary["pass_by_source_kind"].items()))
    summary["drop_by_source_kind"] = dict(sorted(summary["drop_by_source_kind"].items()))
    summary["reason_counts"] = dict(sorted(summary["reason_counts"].items()))
    return summary


def _json_list_field(item, key):
    value = item.get(key, [])
    if value:
        return list(value)
    json_value = item.get(f"{key}_json")
    return json.loads(json_value) if json_value else []


def _json_dict_field(item, key):
    value = item.get(key, {})
    if value:
        return dict(value)
    json_value = item.get(f"{key}_json")
    return json.loads(json_value) if json_value else {}


def normalize_f1_report_row(batch_id, row):
    """Return one F1 report row with the public JSONL schema."""
    item = dict(row)
    return {
        "batch_id": batch_id,
        "search_item_key": item["search_item_key"],
        "file_key": item["file_key"],
        "path": item["path"],
        "language": item.get("language"),
        "passed": bool(item["passed"]),
        "target_libraries": _json_list_field(item, "target_libraries"),
        "matched_library_signals": _json_list_field(item, "matched_library_signals"),
        "matched_pqc_api_signals": _json_list_field(item, "matched_pqc_api_signals"),
        "matched_provider_signals": _json_list_field(item, "matched_provider_signals"),
        "library_evidence": _json_list_field(item, "library_evidence"),
        "strong_signal_evidence": _json_list_field(item, "strong_signal_evidence"),
        "quality": _json_dict_field(item, "quality"),
        "reason_codes": _json_list_field(item, "reason_codes"),
        "raw_file_path": item["raw_file_path"],
        "checked_at": item["checked_at"],
    }


def write_f1_report(rows, batch_id, output_path=None, root=None):
    """Write F1 static candidate rows for one batch as JSONL."""
    report_path = output_path or report_paths(batch_id, root)["filter"]["filter_f1_static_candidate"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_rows = []
    for row in rows:
        item = dict(row)
        if item.get("batch_id", batch_id) == batch_id:
            normalized_rows.append(normalize_f1_report_row(batch_id, item))
    normalized_rows.sort(key=lambda row: (row["passed"], row["language"] or "", row["path"]))

    with report_path.open("w", encoding="utf-8") as handle:
        for row in normalized_rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return report_path


def summarize_f1_results(rows):
    """Return pass/drop counts for F1 static candidate results."""
    summary = {
        "total": 0,
        "pass": 0,
        "drop": 0,
        "pass_by_language": {},
        "drop_by_language": {},
        "target_library_counts": {},
        "pqc_api_signal_counts": {},
        "provider_signal_counts": {},
        "library_evidence_count": 0,
        "strong_signal_evidence_count": 0,
        "reason_counts": {},
    }
    for row in rows:
        item = dict(row)
        passed = bool(item["passed"])
        count_key = "pass" if passed else "drop"
        language_key = "pass_by_language" if passed else "drop_by_language"
        language = item.get("language") or "unsupported"
        target_libraries = _json_list_field(item, "target_libraries")
        pqc_signals = _json_list_field(item, "matched_pqc_api_signals")
        provider_signals = _json_list_field(item, "matched_provider_signals")
        library_evidence = _json_list_field(item, "library_evidence")
        strong_signal_evidence = _json_list_field(item, "strong_signal_evidence")
        reason_codes = _json_list_field(item, "reason_codes")

        summary["total"] += 1
        summary[count_key] += 1
        summary[language_key][language] = summary[language_key].get(language, 0) + 1
        summary["library_evidence_count"] += len(library_evidence)
        summary["strong_signal_evidence_count"] += len(strong_signal_evidence)
        for target_library in target_libraries:
            counts = summary["target_library_counts"]
            counts[target_library] = counts.get(target_library, 0) + 1
        for signal in pqc_signals:
            counts = summary["pqc_api_signal_counts"]
            counts[signal] = counts.get(signal, 0) + 1
        for signal in provider_signals:
            counts = summary["provider_signal_counts"]
            counts[signal] = counts.get(signal, 0) + 1
        for reason_code in reason_codes:
            summary["reason_counts"][reason_code] = summary["reason_counts"].get(reason_code, 0) + 1

    for key in (
        "pass_by_language",
        "drop_by_language",
        "target_library_counts",
        "pqc_api_signal_counts",
        "provider_signal_counts",
        "reason_counts",
    ):
        summary[key] = dict(sorted(summary[key].items()))
    return summary


def normalize_d0_report_row(batch_id, row):
    """Return one D0 report row with the public JSONL schema."""
    item = dict(row)
    return {
        "batch_id": batch_id,
        "search_item_key": item["search_item_key"],
        "file_key": item["file_key"],
        "diff_file_key": item.get("diff_file_key"),
        "repository_full_name": item["repository_full_name"],
        "search_item_path": item["search_item_path"],
        "commit_sha": item["commit_sha"],
        "commit_url": item["commit_url"],
        "matched_changed_path": item.get("matched_changed_path"),
        "exact_path_match": bool(item["exact_path_match"]),
        "patch_available": bool(item["patch_available"]),
        "passed": bool(item["passed"]),
        "changed_files": _json_list_field(item, "changed_files"),
        "review_evidence": _json_list_field(item, "review_evidence"),
        "reason_codes": _json_list_field(item, "reason_codes"),
        "raw_commit_path": item["raw_commit_path"],
        "patch_path": item.get("patch_path"),
        "checked_at": item["checked_at"],
    }


def write_d0_report(rows, batch_id, output_path=None, root=None):
    """Write D0 exact diff evidence rows for one batch as JSONL."""
    report_path = output_path or report_paths(batch_id, root)["filter"]["filter_d0_diff_evidence"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_rows = []
    for row in rows:
        item = dict(row)
        if item.get("batch_id", batch_id) == batch_id:
            normalized_rows.append(normalize_d0_report_row(batch_id, item))
    normalized_rows.sort(
        key=lambda row: (
            row["passed"],
            row["repository_full_name"],
            row["search_item_path"],
            row["commit_sha"],
        )
    )

    with report_path.open("w", encoding="utf-8") as handle:
        for row in normalized_rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return report_path


def summarize_d0_results(rows):
    """Return pass/drop counts for D0 exact diff evidence results."""
    summary = {
        "total": 0,
        "pass": 0,
        "drop": 0,
        "exact_path_match_count": 0,
        "patch_available_count": 0,
        "review_evidence_count": 0,
        "reason_counts": {},
    }
    for row in rows:
        item = dict(row)
        passed = bool(item["passed"])
        summary["total"] += 1
        summary["pass" if passed else "drop"] += 1
        if item.get("exact_path_match"):
            summary["exact_path_match_count"] += 1
        if item.get("patch_available"):
            summary["patch_available_count"] += 1
        summary["review_evidence_count"] += len(_json_list_field(item, "review_evidence"))
        for reason_code in _json_list_field(item, "reason_codes"):
            summary["reason_counts"][reason_code] = summary["reason_counts"].get(reason_code, 0) + 1

    summary["reason_counts"] = dict(sorted(summary["reason_counts"].items()))
    return summary


def normalize_f2_report_row(batch_id, row):
    """Return one F2 report row with the public JSONL schema."""
    item = dict(row)
    changed_path = item.get("matched_changed_path")
    changed_files = _json_list_field(item, "changed_files")
    if changed_path and changed_path not in changed_files:
        changed_files = [changed_path, *changed_files]
    repository = {
        "id": item.get("repository_id"),
        "full_name": item["repository_full_name"],
        "html_url": item.get("repository_url"),
    }
    source = {
        "commit_sha": item["commit_sha"],
        "commit_url": item["commit_url"],
        "pr_number": item.get("pr_number"),
        "pr_url": item.get("pr_url"),
        "primary_path": changed_path,
        "changed_paths": changed_files,
        "raw_commit_path": item.get("raw_commit_path"),
        "patch_path": item.get("patch_path"),
    }
    review_evidence = _json_list_field(item, "review_evidence")
    return {
        "batch_id": batch_id,
        "candidate_evidence_key": item["candidate_evidence_key"],
        "search_item_key": item["search_item_key"],
        "file_key": item["file_key"],
        "diff_file_key": item.get("diff_file_key"),
        "repository": repository,
        "source": source,
        "final_label": item["final_label"],
        "classification": _json_dict_field(item, "classification"),
        "signals": _json_dict_field(item, "signals"),
        "reason_codes": _json_list_field(item, "reason_codes"),
        "review_evidence": review_evidence,
        "evidence": review_evidence,
        "quality": _json_dict_field(item, "quality"),
        "checked_at": item["checked_at"],
    }


def write_f2_report(rows, batch_id, output_path=None, root=None):
    """Write F2 migration classifier rows for one batch as JSONL."""
    report_path = output_path or report_paths(batch_id, root)["filter"]["filter_f2_migration_classifier"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_rows = []
    for row in rows:
        item = dict(row)
        if item.get("batch_id", batch_id) == batch_id:
            normalized_rows.append(normalize_f2_report_row(batch_id, item))
    normalized_rows.sort(
        key=lambda row: (
            row["final_label"],
            row["repository"]["full_name"],
            row["source"]["primary_path"] or "",
            row["source"]["commit_sha"],
        )
    )

    with report_path.open("w", encoding="utf-8") as handle:
        for row in normalized_rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    return report_path


def summarize_f2_results(rows):
    """Return label, signal, and evidence counts for F2 classifier results."""
    summary = {
        "total": 0,
        "label_counts": {},
        "reason_counts": {},
        "signal_true_counts": {},
        "review_evidence_count": 0,
        "rows_without_review_evidence": 0,
    }
    for row in rows:
        item = dict(row)
        final_label = item.get("final_label") or "unknown"
        signals = _json_dict_field(item, "signals")
        review_evidence = _json_list_field(item, "review_evidence")

        summary["total"] += 1
        summary["label_counts"][final_label] = summary["label_counts"].get(final_label, 0) + 1
        summary["review_evidence_count"] += len(review_evidence)
        if not review_evidence:
            summary["rows_without_review_evidence"] += 1
        for reason_code in _json_list_field(item, "reason_codes"):
            summary["reason_counts"][reason_code] = summary["reason_counts"].get(reason_code, 0) + 1
        for signal_name, value in signals.items():
            if value is True:
                counts = summary["signal_true_counts"]
                counts[signal_name] = counts.get(signal_name, 0) + 1

    for key in ("label_counts", "reason_counts", "signal_true_counts"):
        summary[key] = dict(sorted(summary[key].items()))
    return summary


def _batch_rows(conn, table, batch_id):
    return conn.execute(
        f"SELECT * FROM {table} WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()


def summarize_filter_results(conn, batch_id):
    """Return the combined F0/F1/D0/F2 filter summary for one batch."""
    f0_rows = _batch_rows(conn, "f0_results", batch_id)
    f1_rows = _batch_rows(conn, "f1_results", batch_id)
    d0_rows = _batch_rows(conn, "d0_results", batch_id)
    f2_rows = _batch_rows(conn, "f2_results", batch_id)
    return {
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "f0": summarize_f0_results(f0_rows),
        "f1": summarize_f1_results(f1_rows),
        "d0": summarize_d0_results(d0_rows),
        "f2": summarize_f2_results(f2_rows),
        "export": {
            "default_export_count": 0,
            "non_exported_count": 0,
            "cumulative_export_count": 0,
        },
    }


def write_filter_summary_json(summary, batch_id, output_path=None, root=None):
    """Write combined filter summary JSON for one batch."""
    report_path = output_path or report_paths(batch_id, root)["filter"]["filter_summary_json"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(summary)
    row.setdefault("batch_id", batch_id)
    row.setdefault(
        "generated_at",
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    row.setdefault("f0", {})
    row.setdefault("f1", {})
    row.setdefault("d0", {})
    row.setdefault("f2", {})
    row.setdefault("export", {})
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(row, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return report_path


def _summary_count_lines(prefix, mapping):
    if not mapping:
        return [f"- `{prefix}`: {{}}"]
    return [f"- `{prefix}.{key}`: {value}" for key, value in sorted(mapping.items())]


def write_filter_summary_md(summary, batch_id, output_path=None, root=None):
    """Write a human-readable combined filter summary for one batch."""
    report_path = output_path or report_paths(batch_id, root)["filter"]["filter_summary_md"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(summary)
    row.setdefault("batch_id", batch_id)
    row.setdefault(
        "generated_at",
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    lines = [
        "# Filter Summary",
        "",
        f"- `batch_id`: {row['batch_id']}",
        f"- `generated_at`: {row['generated_at']}",
        "",
    ]
    for stage in ("f0", "f1", "d0", "f2", "export"):
        data = row.get(stage, {})
        lines.append(f"## {stage.upper()}")
        if stage == "f2":
            lines.extend(_summary_count_lines("label_counts", data.get("label_counts", {})))
            lines.extend(_summary_count_lines("reason_counts", data.get("reason_counts", {})))
            lines.append(f"- `review_evidence_count`: {data.get('review_evidence_count', 0)}")
            lines.append(
                f"- `rows_without_review_evidence`: {data.get('rows_without_review_evidence', 0)}"
            )
        elif stage == "export":
            lines.extend(f"- `{key}`: {value}" for key, value in sorted(data.items()))
        else:
            lines.append(f"- `total`: {data.get('total', 0)}")
            lines.append(f"- `pass`: {data.get('pass', 0)}")
            lines.append(f"- `drop`: {data.get('drop', 0)}")
            lines.extend(_summary_count_lines("reason_counts", data.get("reason_counts", {})))
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _f2_rows_for_label(conn, batch_id, label, limit):
    return conn.execute(
        """
        SELECT *
        FROM f2_results
        WHERE batch_id = ? AND final_label = ?
        ORDER BY repository_full_name, matched_changed_path, commit_sha
        LIMIT ?
        """,
        (batch_id, label, int(limit)),
    ).fetchall()


def _f2_label_counts(conn, batch_id):
    rows = conn.execute(
        """
        SELECT final_label, COUNT(*) AS count
        FROM f2_results
        WHERE batch_id = ?
        GROUP BY final_label
        ORDER BY final_label
        """,
        (batch_id,),
    ).fetchall()
    return {row["final_label"]: int(row["count"]) for row in rows}


def _sample_rows_for_labels(conn, batch_id, labels, limit_per_label):
    samples = []
    for label in labels:
        samples.extend(
            normalize_f2_report_row(batch_id, row)
            for row in _f2_rows_for_label(conn, batch_id, label, limit_per_label)
        )
    return samples


def _non_export_labels(label_counts, export_labels):
    return [label for label in sorted(label_counts) if label not in set(export_labels)]


def _sample_source_kind(sample):
    return sample.get("quality", {}).get("source_kind") or "unknown"


def _f2_rows_for_labels(conn, batch_id, labels):
    labels = tuple(labels)
    if not labels:
        return []
    placeholders = ", ".join("?" for _ in labels)
    return conn.execute(
        f"""
        SELECT *
        FROM f2_results
        WHERE batch_id = ? AND final_label IN ({placeholders})
        ORDER BY final_label, repository_full_name, matched_changed_path, commit_sha
        """,
        (batch_id, *labels),
    ).fetchall()


def _candidate_keys(rows):
    return [row["candidate_evidence_key"] for row in rows]


def _rows_without_review_evidence(rows):
    return [
        row
        for row in rows
        if not _json_list_field(dict(row), "review_evidence")
    ]


def _rows_with_drop_source_kind(rows):
    return [
        row
        for row in rows
        if _json_dict_field(dict(row), "quality").get("source_kind") in REVIEW_DROP_SOURCE_KINDS
    ]


def _rows_without_patch_path(rows):
    return [row for row in rows if not row["patch_path"]]


def _rows_without_d0_pass(conn, batch_id, export_labels):
    export_labels = tuple(export_labels)
    if not export_labels:
        return []
    placeholders = ", ".join("?" for _ in export_labels)
    return conn.execute(
        f"""
        SELECT f2.candidate_evidence_key
        FROM f2_results AS f2
        LEFT JOIN d0_results AS d0
            ON d0.batch_id = f2.batch_id
            AND d0.search_item_key = f2.search_item_key
            AND d0.commit_sha = f2.commit_sha
            AND d0.passed = 1
        WHERE f2.batch_id = ?
            AND f2.final_label IN ({placeholders})
            AND d0.search_item_key IS NULL
        ORDER BY f2.repository_full_name, f2.matched_changed_path, f2.commit_sha
        """,
        (batch_id, *export_labels),
    ).fetchall()


def _review_sample_checks(conn, batch_id, export_labels, export_samples, non_export_samples):
    export_rows = _f2_rows_for_labels(conn, batch_id, export_labels)
    return {
        "export_sample_count": len(export_samples),
        "non_export_sample_count": len(non_export_samples),
        "export_candidate_count_checked": len(export_rows),
        "export_candidates_without_review_evidence": _candidate_keys(
            _rows_without_review_evidence(export_rows)
        ),
        "export_candidates_with_drop_source_kind": _candidate_keys(
            _rows_with_drop_source_kind(export_rows)
        ),
        "export_candidates_without_patch_path": _candidate_keys(_rows_without_patch_path(export_rows)),
        "export_candidates_without_d0_pass": _candidate_keys(
            _rows_without_d0_pass(conn, batch_id, export_labels)
        ),
        "export_samples_without_review_evidence": [
            sample["candidate_evidence_key"] for sample in export_samples if not sample.get("review_evidence")
        ],
        "export_samples_with_drop_source_kind": [
            sample["candidate_evidence_key"]
            for sample in export_samples
            if _sample_source_kind(sample) in REVIEW_DROP_SOURCE_KINDS
        ],
        "export_samples_without_patch_path": [
            sample["candidate_evidence_key"]
            for sample in export_samples
            if not sample.get("source", {}).get("patch_path")
        ],
    }


def select_review_samples(conn, batch_id, limit_per_label=3, export_labels=None):
    """Return F2 report review samples before export is built."""
    export_labels = tuple(export_labels or DEFAULT_EXPORT_LABELS)
    label_counts = _f2_label_counts(conn, batch_id)
    non_export_labels = _non_export_labels(label_counts, export_labels)
    export_samples = _sample_rows_for_labels(conn, batch_id, export_labels, limit_per_label)
    non_export_samples = _sample_rows_for_labels(
        conn,
        batch_id,
        non_export_labels,
        limit_per_label,
    )
    export_candidate_count = sum(label_counts.get(label, 0) for label in export_labels)
    return {
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "export_labels": list(export_labels),
        "non_export_labels": non_export_labels,
        "label_counts": label_counts,
        "export_candidate_count": export_candidate_count,
        "non_export_candidate_count": sum(label_counts.values()) - export_candidate_count,
        "export_candidate_samples": export_samples,
        "non_export_candidate_samples": non_export_samples,
        "checks": _review_sample_checks(
            conn,
            batch_id,
            export_labels,
            export_samples,
            non_export_samples,
        ),
    }


def build_filter_review_status(summary, review_samples):
    """Return Phase 9 review gate status and next recommendations."""
    f2_summary = summary.get("f2", {}) if isinstance(summary, dict) else {}
    checks = review_samples.get("checks", {}) if isinstance(review_samples, dict) else {}
    blocker_fields = (
        "export_candidates_without_review_evidence",
        "export_candidates_with_drop_source_kind",
        "export_candidates_without_patch_path",
        "export_candidates_without_d0_pass",
    )
    blockers = {
        field: checks.get(field, [])
        for field in blocker_fields
        if checks.get(field)
    }
    f2_total = int(f2_summary.get("total", 0) or 0)
    export_candidate_count = int(review_samples.get("export_candidate_count", 0) or 0)

    if f2_total == 0:
        status = "needs_f2_results"
        ready_for_export = False
        recommendations = [
            "run-f2 결과를 만든 뒤 report-filters를 다시 실행한다.",
            "D0 pass 결과가 비어 있으면 run-d0 단계의 exact diff evidence를 먼저 확인한다.",
        ]
    elif blockers:
        status = "needs_manual_review"
        ready_for_export = False
        recommendations = [
            "checks에 표시된 candidate_evidence_key의 F2 report row를 먼저 검토한다.",
            "review_evidence, source.patch_path, quality.source_kind, D0 pass 연결을 보강한 뒤 report-filters를 다시 실행한다.",
        ]
    elif export_candidate_count == 0:
        status = "no_export_candidates"
        ready_for_export = False
        recommendations = [
            "non_export_candidate_samples의 reason_codes를 보고 필터가 과하게 보수적인지 확인한다.",
            "추가 수집 또는 F2 signal rule 보강 후 report-filters를 다시 실행한다.",
        ]
    else:
        status = "ready_for_export_phase"
        ready_for_export = True
        recommendations = [
            "export 구현으로 넘어가기 전에 export_candidate_samples의 raw patch와 evidence line을 눈으로 확인한다.",
            "다음 요청에서 Phase 10 export 기능 구현을 시작한다.",
        ]

    return {
        "status": status,
        "ready_for_export_phase": ready_for_export,
        "checked_items": {
            "f0_reason_distribution_available": bool(summary.get("f0")),
            "f1_reason_distribution_available": bool(summary.get("f1")),
            "d0_pass_drop_distribution_available": bool(summary.get("d0")),
            "f2_label_distribution_available": bool(f2_summary.get("label_counts")),
            "export_candidate_samples_available": bool(
                review_samples.get("export_candidate_samples")
            ),
            "non_export_candidate_samples_available": bool(
                review_samples.get("non_export_candidate_samples")
            ),
            "export_candidate_quality_checks_available": bool(checks),
        },
        "blockers": blockers,
        "next_recommendations": recommendations,
    }


def write_dedupe_summary_report(
    conn,
    batch_id,
    output_path=None,
    root=None,
    skipped_query_page_count=0,
):
    """Write stored dedupe counts for one batch as JSON."""
    report_path = output_path or report_paths(batch_id, root)["collector"]["dedupe_summary"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    page_counts = conn.execute(
        """
        SELECT
            COALESCE(SUM(item_count), 0) AS raw_item_seen_count,
            COALESCE(SUM(new_unique_item_count), 0) AS new_unique_item_count,
            COALESCE(SUM(duplicate_item_count), 0) AS duplicate_item_count
        FROM query_pages
        WHERE batch_id = ?
        """,
        (batch_id,),
    ).fetchone()
    previous_duplicates = conn.execute(
        """
        SELECT COUNT(*) AS previous_duplicate_count
        FROM raw_search_items
        WHERE batch_id = ?
            AND status = 'existing'
            AND first_seen_batch_id <> ?
        """,
        (batch_id, batch_id),
    ).fetchone()["previous_duplicate_count"]
    duplicate_item_count = int(page_counts["duplicate_item_count"])
    summary = {
        "batch_id": batch_id,
        "raw_item_seen_count": int(page_counts["raw_item_seen_count"]),
        "new_unique_item_count": int(page_counts["new_unique_item_count"]),
        "previous_duplicate_count": int(previous_duplicates),
        "current_batch_duplicate_count": max(
            0,
            duplicate_item_count - int(previous_duplicates),
        ),
        "query_page_duplicate_count": 0,
        "skipped_query_page_count": int(skipped_query_page_count),
        "skipped_file_fetch_count": 0,
        "skipped_commit_fetch_count": 0,
    }
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return report_path


def _duplicate_ratio(result):
    seen = int(result.get("raw_item_seen_count", 0))
    if not seen:
        return 0.0
    duplicates = int(result.get("previous_duplicate_count", 0)) + int(
        result.get("current_batch_duplicate_count", 0)
    )
    return duplicates / seen


def write_one_page_collection_reports(
    batch_id,
    query,
    page,
    result,
    rate_limit_start=None,
    rate_limit_end=None,
    root=None,
    generated_at=None,
    low_yield_duplicate_ratio=0.8,
):
    """Write batch reports derived from one collect_one_query_page result."""
    page = int(page)
    rate_limit_calls = int(
        result.get("api_call_count_rate_limit", 1 if rate_limit_start or rate_limit_end else 0)
    )
    search_calls = int(result.get("api_call_count_search", 0))
    skipped_pages = int(result.get("skipped_query_page_count", 0))
    fetched_pages = 1 if search_calls else 0
    duplicate_ratio = _duplicate_ratio(result)
    low_yield = bool(fetched_pages and duplicate_ratio >= low_yield_duplicate_ratio)
    frontier_row = {
        "query_key": query["query_key"],
        "query_group": query["query_group"],
        "next_page_to_fetch": page + fetched_pages,
        "fetched_pages": fetched_pages,
        "exhausted": False,
        "low_yield": low_yield,
        "consecutive_duplicate_pages": 1 if low_yield else 0,
        "last_run_at": generated_at,
        "last_duplicate_ratio": duplicate_ratio,
    }
    summary = {
        "collector_status": result.get("collector_status", "idle"),
        "query_group": query["query_group"],
        "query_count": 1,
        "query_pages_fetched": fetched_pages,
        "query_pages_skipped": skipped_pages,
        "raw_item_seen_count": result.get("raw_item_seen_count", 0),
        "new_unique_item_count": result.get("new_unique_item_count", 0),
        "previous_duplicate_count": result.get("previous_duplicate_count", 0),
        "current_batch_duplicate_count": result.get("current_batch_duplicate_count", 0),
        "api_call_count_search": search_calls,
        "api_call_count_core": 0,
        "rate_limit_start": rate_limit_start,
        "rate_limit_end": rate_limit_end,
        "sleep_until": result.get("sleep_until"),
        "high_yield_queries": [query["query_key"]] if fetched_pages and not low_yield else [],
        "low_yield_queries": [query["query_key"]] if low_yield else [],
        "next_recommended_query_group": query["query_group"],
    }
    paths = {
        "api_usage": str(
            write_api_usage_report(
                batch_id,
                {"rate_limit": rate_limit_calls, "search": search_calls},
                rate_limit_start,
                rate_limit_end,
                root=root,
                generated_at=generated_at,
            )
        ),
        "query_frontier": str(
            write_query_frontier_report(batch_id, [frontier_row], root=root)
        ),
        "collection_summary": str(
            write_collection_summary_report(
                batch_id,
                summary,
                root=root,
                generated_at=generated_at,
            )
        ),
    }
    return {
        "batch_id": batch_id,
        "report_paths": paths,
        "frontier_row": frontier_row,
        "summary": summary,
    }
