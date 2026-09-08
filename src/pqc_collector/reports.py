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

VIEWER_SECTIONS = (
    ("hybrid_migration", "Hybrid Migration Review"),
    ("partial_migration", "Partial Migration Review"),
    ("full_migration", "Full Migration Review"),
    ("pqc_addition_only", "PQC Addition Only"),
    ("dropped", "Dropped / Non Exported"),
)

VIEWER_SECTION_TITLES = dict(VIEWER_SECTIONS)
EXPORT_VIEWER_LABELS = {section_id for section_id, _title in VIEWER_SECTIONS[:-1]}

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


def _read_jsonl_file(path):
    rows = []
    invalid_lines = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                invalid_lines.append({"line_number": line_number, "error": str(exc)})
    return rows, invalid_lines


def _resolve_report_path(path, root=None):
    source_path = Path(path)
    if source_path.is_absolute():
        return source_path
    return project_paths(root)["root"] / source_path


def _row_identity(row, index):
    return row.get("candidate_key") or row.get("candidate_evidence_key") or f"row:{index}"


def _missing_required_fields(row, required_fields):
    return [field for field in required_fields if field not in row]


def _raw_paths_from_export_row(row):
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    paths = [source.get("raw_commit_path"), source.get("patch_path")]
    for evidence in row.get("review_evidence") or []:
        if not isinstance(evidence, dict):
            continue
        paths.extend([evidence.get("raw_path"), evidence.get("patch_path")])
    return [path for path in dict.fromkeys(paths) if path]


def _missing_raw_paths(row, root=None):
    base = project_paths(root)["root"]
    missing = []
    for raw_path in _raw_paths_from_export_row(row):
        path = Path(raw_path)
        resolved = path if path.is_absolute() else base / path
        if not resolved.exists():
            missing.append(raw_path)
    return missing


def _missing_evidence_fields(evidence):
    required = ("line_number", "context", "signal", "signal_type", "source_field", "raw_path")
    missing = [field for field in required if field not in evidence]
    source_field = evidence.get("source_field")
    kind = evidence.get("kind")
    if source_field == "patch" or str(kind or "").startswith("patch_"):
        patch_fields = ("patch_hunk_header", "patch_line_no")
        missing.extend(field for field in patch_fields if field not in evidence)
        if kind == "patch_added_line" and "new_file_line" not in evidence:
            missing.append("new_file_line")
        if kind == "patch_removed_line" and "old_file_line" not in evidence:
            missing.append("old_file_line")
    return missing


def inspect_export_file(source, root=None, schema_name="export_candidates", sample_limit=3):
    """Inspect export JSONL rows for schema and evidence traceability."""
    source_path = _resolve_report_path(source, root)
    if not source_path.exists():
        return {
            "source_path": str(source_path),
            "status": "source_not_found",
            "row_count": 0,
            "is_traceable": False,
        }

    rows, invalid_lines = _read_jsonl_file(source_path)
    required_fields = report_schemas().get(schema_name, {}).get("required_fields", [])
    missing_required = []
    rows_without_review_evidence = []
    rows_with_untraceable_evidence = []
    rows_with_missing_raw_paths = []
    evidence_count = 0
    raw_path_count = 0

    for index, row in enumerate(rows, start=1):
        row_id = _row_identity(row, index)
        missing = _missing_required_fields(row, required_fields)
        if missing:
            missing_required.append({"row": row_id, "missing_fields": missing})

        review_evidence = row.get("review_evidence") or []
        if not review_evidence:
            rows_without_review_evidence.append(row_id)
        evidence_count += len(review_evidence)

        bad_evidence = []
        for evidence_index, evidence in enumerate(review_evidence, start=1):
            if not isinstance(evidence, dict):
                bad_evidence.append({"evidence_index": evidence_index, "missing_fields": ["object"]})
                continue
            evidence_missing = _missing_evidence_fields(evidence)
            if evidence_missing:
                bad_evidence.append(
                    {
                        "evidence_index": evidence_index,
                        "evidence_id": evidence.get("evidence_id"),
                        "missing_fields": evidence_missing,
                    }
                )
        if bad_evidence:
            rows_with_untraceable_evidence.append({"row": row_id, "evidence": bad_evidence})

        raw_paths = _raw_paths_from_export_row(row)
        raw_path_count += len(raw_paths)
        missing_paths = _missing_raw_paths(row, root)
        if missing_paths:
            rows_with_missing_raw_paths.append({"row": row_id, "missing_raw_paths": missing_paths})

    is_traceable = not any(
        (
            invalid_lines,
            missing_required,
            rows_without_review_evidence,
            rows_with_untraceable_evidence,
            rows_with_missing_raw_paths,
        )
    )
    return {
        "source_path": str(source_path),
        "schema_name": schema_name,
        "status": "traceable" if is_traceable else "needs_review",
        "is_traceable": is_traceable,
        "row_count": len(rows),
        "invalid_json_line_count": len(invalid_lines),
        "rows_missing_required_fields_count": len(missing_required),
        "rows_without_review_evidence_count": len(rows_without_review_evidence),
        "rows_with_untraceable_evidence_count": len(rows_with_untraceable_evidence),
        "rows_with_missing_raw_paths_count": len(rows_with_missing_raw_paths),
        "review_evidence_count": evidence_count,
        "raw_path_count": raw_path_count,
        "invalid_json_lines": invalid_lines[:sample_limit],
        "rows_missing_required_fields": missing_required[:sample_limit],
        "rows_without_review_evidence": rows_without_review_evidence[:sample_limit],
        "rows_with_untraceable_evidence": rows_with_untraceable_evidence[:sample_limit],
        "rows_with_missing_raw_paths": rows_with_missing_raw_paths[:sample_limit],
        "sample_rows": rows[:sample_limit],
    }


def _evidence_list(row):
    review_evidence = row.get("review_evidence")
    if isinstance(review_evidence, list):
        return [item for item in review_evidence if isinstance(item, dict)]
    evidence = row.get("evidence")
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]
    return []


def _text_blob(*values):
    parts = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(item) for item in value)
        elif isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
        else:
            parts.append(str(value))
    return " ".join(parts).lower()


def _evidence_blob(evidence):
    return _text_blob(
        evidence.get("kind"),
        evidence.get("signal"),
        evidence.get("signal_type"),
        evidence.get("near"),
        evidence.get("source_field"),
        evidence.get("context"),
        evidence.get("supports"),
        evidence.get("reason_codes"),
    )


def _append_once(target, evidence):
    identity = json.dumps(evidence, sort_keys=True, ensure_ascii=True)
    if identity not in target["_seen"]:
        target["_seen"].add(identity)
        target["rows"].append(evidence)


def group_review_evidence(row):
    """Group row-level review evidence into manual validation sections."""
    groups = {
        "pqc_added": {"rows": [], "_seen": set()},
        "legacy_removed": {"rows": [], "_seen": set()},
        "intent": {"rows": [], "_seen": set()},
        "hybrid": {"rows": [], "_seen": set()},
        "partial": {"rows": [], "_seen": set()},
        "full": {"rows": [], "_seen": set()},
        "exact_path": {"rows": [], "_seen": set()},
        "other": {"rows": [], "_seen": set()},
        "all": {"rows": [], "_seen": set()},
    }

    for evidence in _evidence_list(row):
        blob = _evidence_blob(evidence)
        matched = False
        _append_once(groups["all"], evidence)

        if (
            evidence.get("kind") == "patch_added_line"
            or "pqc_added" in blob
            or evidence.get("signal_type") in {"pqc_api", "pqc_provider", "pqc_group"}
        ):
            _append_once(groups["pqc_added"], evidence)
            matched = True
        if (
            evidence.get("kind") == "patch_removed_line"
            or "legacy_removed" in blob
            or "removed_legacy" in blob
            or evidence.get("signal_type") == "legacy_removed"
        ):
            _append_once(groups["legacy_removed"], evidence)
            matched = True
        if (
            evidence.get("source_field") == "commit_message"
            or evidence.get("signal_type") == "intent"
            or "intent" in blob
            or "migration_intent" in blob
        ):
            _append_once(groups["intent"], evidence)
            matched = True
        if "hybrid" in blob:
            _append_once(groups["hybrid"], evidence)
            matched = True
        if "partial" in blob:
            _append_once(groups["partial"], evidence)
            matched = True
        if "full" in blob or "complete_migration" in blob:
            _append_once(groups["full"], evidence)
            matched = True
        if evidence.get("signal_type") == "exact_path" or "exact_path" in blob:
            _append_once(groups["exact_path"], evidence)
            matched = True
        if not matched:
            _append_once(groups["other"], evidence)

    return {name: value["rows"] for name, value in groups.items()}


def _source_dict(row):
    return row.get("source") if isinstance(row.get("source"), dict) else {}


def _repository_dict(row):
    return row.get("repository") if isinstance(row.get("repository"), dict) else {}


def _final_label(row):
    classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
    return row.get("final_label") or classification.get("migration_type") or "dropped"


def _viewer_section_id(row):
    label = _final_label(row)
    if label in EXPORT_VIEWER_LABELS:
        return label
    return "dropped"


def group_by_migration_type(rows):
    """Group export rows or viewer candidates by manual review section."""
    groups = {section_id: [] for section_id, _title in VIEWER_SECTIONS}
    for row in rows:
        groups[_viewer_section_id(row)].append(row)
    return groups


def _unique_nonempty(values):
    return [value for value in dict.fromkeys(values) if value]


def _row_primary_path(row, source):
    return (
        source.get("primary_path")
        or row.get("matched_changed_path")
        or row.get("path")
        or row.get("search_item_path")
    )


def _row_repository_name(row, repository):
    return repository.get("full_name") or row.get("repository_full_name")


def _candidate_review_checklist(row, evidence_groups):
    source = _source_dict(row)
    repository = _repository_dict(row)
    label = _final_label(row)
    reason_codes = row.get("reason_codes") or []
    checklist = [
        {
            "id": "repository",
            "label": "Repository",
            "passed": bool(_row_repository_name(row, repository)),
            "details": _row_repository_name(row, repository),
        },
        {
            "id": "commit_or_pr_url",
            "label": "Commit or PR URL",
            "passed": bool(source.get("commit_url") or source.get("pr_url") or row.get("commit_url")),
            "details": source.get("commit_url") or source.get("pr_url") or row.get("commit_url"),
        },
        {
            "id": "changed_path",
            "label": "Changed path",
            "passed": bool(_row_primary_path(row, source)),
            "details": _row_primary_path(row, source),
        },
        {
            "id": "review_evidence",
            "label": "Review evidence",
            "passed": bool(evidence_groups.get("all")),
            "details": f"{len(evidence_groups.get('all', []))} evidence rows",
        },
    ]
    if label == "hybrid_migration":
        checklist.extend(
            [
                {
                    "id": "pqc_added_evidence",
                    "label": "PQC added evidence",
                    "passed": bool(evidence_groups.get("pqc_added")),
                    "details": f"{len(evidence_groups.get('pqc_added', []))} rows",
                },
                {
                    "id": "hybrid_evidence",
                    "label": "Hybrid evidence",
                    "passed": bool(evidence_groups.get("hybrid")),
                    "details": f"{len(evidence_groups.get('hybrid', []))} rows",
                },
            ]
        )
    elif label == "partial_migration":
        checklist.extend(
            [
                {
                    "id": "pqc_added_evidence",
                    "label": "PQC added evidence",
                    "passed": bool(evidence_groups.get("pqc_added")),
                    "details": f"{len(evidence_groups.get('pqc_added', []))} rows",
                },
                {
                    "id": "partial_evidence",
                    "label": "Partial evidence",
                    "passed": bool(evidence_groups.get("partial") or evidence_groups.get("other")),
                    "details": f"{len(evidence_groups.get('partial', []))} partial rows",
                },
            ]
        )
    elif label == "full_migration":
        checklist.extend(
            [
                {
                    "id": "pqc_added_evidence",
                    "label": "PQC added evidence",
                    "passed": bool(evidence_groups.get("pqc_added")),
                    "details": f"{len(evidence_groups.get('pqc_added', []))} rows",
                },
                {
                    "id": "legacy_removed_evidence",
                    "label": "Legacy removed evidence",
                    "passed": bool(evidence_groups.get("legacy_removed")),
                    "details": f"{len(evidence_groups.get('legacy_removed', []))} rows",
                },
                {
                    "id": "full_or_intent_evidence",
                    "label": "Full or intent evidence",
                    "passed": bool(evidence_groups.get("full") or evidence_groups.get("intent")),
                    "details": (
                        f"{len(evidence_groups.get('full', []))} full rows, "
                        f"{len(evidence_groups.get('intent', []))} intent rows"
                    ),
                },
            ]
        )
    elif label == "pqc_addition_only":
        checklist.append(
            {
                "id": "pqc_added_evidence",
                "label": "PQC added evidence",
                "passed": bool(evidence_groups.get("pqc_added")),
                "details": f"{len(evidence_groups.get('pqc_added', []))} rows",
            }
        )
    else:
        checklist.append(
            {
                "id": "drop_reason",
                "label": "Drop reason",
                "passed": bool(reason_codes),
                "details": ", ".join(reason_codes),
            }
        )
    return checklist


def _raw_paths_for_viewer(row, evidence_rows):
    source = _source_dict(row)
    paths = [
        source.get("raw_commit_path"),
        source.get("patch_path"),
        row.get("raw_commit_path"),
        row.get("patch_path"),
        row.get("raw_file_path"),
    ]
    for evidence in evidence_rows:
        paths.extend([evidence.get("raw_path"), evidence.get("patch_path")])
    return _unique_nonempty(paths)


def _viewer_candidate(row, index):
    source = _source_dict(row)
    repository = _repository_dict(row)
    evidence_groups = group_review_evidence(row)
    label = _final_label(row)
    evidence_rows = evidence_groups.get("all", [])
    return {
        "index": index,
        "candidate_key": row.get("candidate_key") or row.get("candidate_evidence_key") or f"row:{index}",
        "batch_id": row.get("batch_id"),
        "source_batch_ids": row.get("source_batch_ids") or [],
        "final_label": label,
        "section_id": _viewer_section_id(row),
        "section_title": VIEWER_SECTION_TITLES[_viewer_section_id(row)],
        "repository": {
            "id": repository.get("id") or row.get("repository_id"),
            "full_name": _row_repository_name(row, repository),
            "html_url": repository.get("html_url") or row.get("repository_url"),
        },
        "source": {
            "primary_path": _row_primary_path(row, source),
            "changed_paths": source.get("changed_paths") or row.get("changed_files") or [],
            "commit_sha": source.get("commit_sha") or row.get("commit_sha"),
            "commit_url": source.get("commit_url") or row.get("commit_url"),
            "pr_number": source.get("pr_number") or row.get("pr_number"),
            "pr_url": source.get("pr_url") or row.get("pr_url"),
            "raw_commit_path": source.get("raw_commit_path") or row.get("raw_commit_path"),
            "patch_path": source.get("patch_path") or row.get("patch_path"),
        },
        "classification": row.get("classification") or {},
        "signals": row.get("signals") or {},
        "quality": row.get("quality") or {},
        "reason_codes": row.get("reason_codes") or [],
        "migration_checklist": _candidate_review_checklist(row, evidence_groups),
        "review_evidence": evidence_rows,
        "evidence_groups": evidence_groups,
        "raw_paths": _raw_paths_for_viewer(row, evidence_rows),
    }


def build_viewer_dataset(export_path, root=None):
    """Build the JSON payload used by the static manual review viewer."""
    source_path = _resolve_report_path(export_path, root)
    if source_path.exists():
        rows, invalid_lines = _read_jsonl_file(source_path)
        status = "ready"
    else:
        rows, invalid_lines = [], []
        status = "source_not_found"

    candidates = [_viewer_candidate(row, index) for index, row in enumerate(rows, start=1)]
    grouped = group_by_migration_type(candidates)
    label_counts = {section_id: len(grouped.get(section_id, [])) for section_id, _title in VIEWER_SECTIONS}
    sections = [
        {
            "id": section_id,
            "title": title,
            "count": len(grouped.get(section_id, [])),
            "candidates": grouped.get(section_id, []),
        }
        for section_id, title in VIEWER_SECTIONS
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_path": str(source_path),
        "status": status,
        "candidate_count": len(candidates),
        "invalid_json_line_count": len(invalid_lines),
        "invalid_json_lines": invalid_lines,
        "label_counts": label_counts,
        "sections": sections,
        "candidates": candidates,
    }


def _viewer_index_html(embedded_json):
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PQC Migration Review</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">PQC Collector</p>
      <h1>Manual Migration Review</h1>
    </div>
    <div class="summary" id="summary"></div>
  </header>
  <main class="layout">
    <aside class="sidebar">
      <div id="sectionNav" class="section-nav"></div>
      <label class="search">
        <span>Search</span>
        <input id="searchInput" type="search" autocomplete="off">
      </label>
      <div id="candidateList" class="candidate-list"></div>
    </aside>
    <section id="detail" class="detail"></section>
  </main>
  <script id="viewer-data" type="application/json">__VIEWER_DATA__</script>
  <script src="app.js"></script>
</body>
</html>
"""
    return template.replace("__VIEWER_DATA__", embedded_json)


def _viewer_app_js():
    return """const dataNode = document.getElementById("viewer-data");
const dataset = dataNode ? JSON.parse(dataNode.textContent) : { sections: [], candidates: [] };
const firstSection = (dataset.sections || []).find((section) => section.count > 0) || (dataset.sections || [])[0];
let activeSectionId = firstSection ? firstSection.id : null;
let activeCandidateKey = null;
let query = "";

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function link(url, label) {
  if (!url) return "";
  return `<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(label || url)}</a>`;
}

function activeSection() {
  return (dataset.sections || []).find((section) => section.id === activeSectionId) || { candidates: [] };
}

function filteredCandidates() {
  const text = query.trim().toLowerCase();
  const candidates = activeSection().candidates || [];
  if (!text) return candidates;
  return candidates.filter((candidate) => JSON.stringify(candidate).toLowerCase().includes(text));
}

function renderSummary() {
  const counts = dataset.label_counts || {};
  document.getElementById("summary").innerHTML = `
    <span>${esc(dataset.status || "ready")}</span>
    <span>${esc(dataset.candidate_count || 0)} candidates</span>
    <span>${esc(dataset.source_path || "")}</span>
  `;
  return counts;
}

function renderSections() {
  const nav = document.getElementById("sectionNav");
  nav.innerHTML = (dataset.sections || []).map((section) => `
    <button class="section-button ${section.id === activeSectionId ? "active" : ""}" data-section="${esc(section.id)}">
      <span>${esc(section.title)}</span>
      <strong>${esc(section.count || 0)}</strong>
    </button>
  `).join("");
  nav.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeSectionId = button.dataset.section;
      activeCandidateKey = null;
      render();
    });
  });
}

function candidateTitle(candidate) {
  const repo = candidate.repository && candidate.repository.full_name ? candidate.repository.full_name : "unknown/repo";
  const path = candidate.source && candidate.source.primary_path ? candidate.source.primary_path : "unknown path";
  return `${repo} :: ${path}`;
}

function renderCandidateList() {
  const list = document.getElementById("candidateList");
  const candidates = filteredCandidates();
  if (!activeCandidateKey && candidates.length) activeCandidateKey = candidates[0].candidate_key;
  list.innerHTML = candidates.map((candidate) => `
    <button class="candidate-row ${candidate.candidate_key === activeCandidateKey ? "active" : ""}" data-key="${esc(candidate.candidate_key)}">
      <span>${esc(candidateTitle(candidate))}</span>
      <small>${esc(candidate.final_label)}</small>
    </button>
  `).join("") || `<p class="empty">No candidates</p>`;
  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeCandidateKey = button.dataset.key;
      renderDetail();
      renderCandidateList();
    });
  });
}

function activeCandidate() {
  const candidates = filteredCandidates();
  return candidates.find((candidate) => candidate.candidate_key === activeCandidateKey) || candidates[0] || null;
}

function chips(values) {
  const items = Array.isArray(values) ? values : Object.entries(values || {}).map(([key, value]) => `${key}: ${value}`);
  return `<div class="chips">${items.map((item) => `<span>${esc(item)}</span>`).join("")}</div>`;
}

function renderChecklist(items) {
  return `<div class="checklist">${(items || []).map((item) => `
    <div class="check ${item.passed ? "ok" : "missing"}">
      <b>${esc(item.passed ? "OK" : "Missing")}</b>
      <span>${esc(item.label)}</span>
      <small>${esc(item.details || "")}</small>
    </div>
  `).join("")}</div>`;
}

function evidenceValue(row, key) {
  const value = row[key];
  if (Array.isArray(value)) return value.join(", ");
  return value ?? "";
}

function renderEvidenceTable(title, rows) {
  const fields = [
    "signal", "signal_type", "near", "source_field", "file_path",
    "patch_hunk_header", "patch_line_no", "new_file_line", "old_file_line",
    "line_number", "context", "raw_path"
  ];
  if (!rows || !rows.length) {
    return `<section class="evidence-section"><h3>${esc(title)}</h3><p class="empty">No evidence</p></section>`;
  }
  return `<section class="evidence-section">
    <h3>${esc(title)}</h3>
    <div class="table-wrap"><table>
      <thead><tr>${fields.map((field) => `<th>${esc(field)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${fields.map((field) => `<td>${esc(evidenceValue(row, field))}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>
  </section>`;
}

function renderRawPaths(paths) {
  if (!paths || !paths.length) return `<p class="empty">No raw paths</p>`;
  return `<ul class="raw-paths">${paths.map((path) => `<li>${esc(path)}</li>`).join("")}</ul>`;
}

function renderDetail() {
  const detail = document.getElementById("detail");
  const candidate = activeCandidate();
  if (!candidate) {
    detail.innerHTML = `<p class="empty">No candidate selected</p>`;
    return;
  }
  activeCandidateKey = candidate.candidate_key;
  const source = candidate.source || {};
  const repo = candidate.repository || {};
  const groups = candidate.evidence_groups || {};
  detail.innerHTML = `
    <div class="detail-header">
      <div>
        <p class="eyebrow">${esc(candidate.section_title)}</p>
        <h2>${esc(candidateTitle(candidate))}</h2>
      </div>
      <span class="label">${esc(candidate.final_label)}</span>
    </div>
    <section class="facts">
      <div><b>Repository</b><span>${link(repo.html_url, repo.full_name) || esc(repo.full_name || "")}</span></div>
      <div><b>Commit</b><span>${link(source.commit_url, source.commit_sha) || esc(source.commit_sha || "")}</span></div>
      <div><b>Pull request</b><span>${link(source.pr_url, source.pr_number ? `#${source.pr_number}` : "")}</span></div>
      <div><b>Changed path</b><span>${esc(source.primary_path || "")}</span></div>
    </section>
    <section class="block"><h3>Reason Codes</h3>${chips(candidate.reason_codes || [])}</section>
    <section class="block"><h3>Signals</h3>${chips(candidate.signals || {})}</section>
    <section class="block"><h3>Migration Checklist</h3>${renderChecklist(candidate.migration_checklist || [])}</section>
    ${renderEvidenceTable("PQC Added Evidence", groups.pqc_added)}
    ${renderEvidenceTable("Legacy Removed Evidence", groups.legacy_removed)}
    ${renderEvidenceTable("Intent Evidence", groups.intent)}
    ${renderEvidenceTable("Hybrid Evidence", groups.hybrid)}
    ${renderEvidenceTable("Partial Evidence", groups.partial)}
    ${renderEvidenceTable("Full Evidence", groups.full)}
    ${renderEvidenceTable("Exact Path Evidence", groups.exact_path)}
    ${renderEvidenceTable("Other Review Evidence", groups.other)}
    <section class="block"><h3>Raw Paths</h3>${renderRawPaths(candidate.raw_paths)}</section>
  `;
}

function render() {
  renderSummary();
  renderSections();
  renderCandidateList();
  renderDetail();
}

document.getElementById("searchInput").addEventListener("input", (event) => {
  query = event.target.value;
  activeCandidateKey = null;
  renderCandidateList();
  renderDetail();
});

render();
"""


def _viewer_styles_css():
    return """:root {
  color-scheme: light;
  --bg: #f5f7f9;
  --panel: #ffffff;
  --ink: #1b2633;
  --muted: #667386;
  --line: #d7dee8;
  --accent: #116466;
  --accent-soft: #d8eeee;
  --warn: #b45309;
  --ok: #166534;
  --missing: #991b1b;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: Arial, Helvetica, sans-serif;
  font-size: 14px;
}

a {
  color: var(--accent);
  overflow-wrap: anywhere;
}

.topbar {
  min-height: 82px;
  padding: 18px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
}

h1,
h2,
h3 {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: 24px;
}

h2 {
  font-size: 20px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

h3 {
  font-size: 15px;
  margin-bottom: 10px;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  color: var(--muted);
  max-width: 55vw;
}

.summary span,
.chips span,
.label {
  border: 1px solid var(--line);
  background: #f8fafc;
  border-radius: 999px;
  padding: 5px 9px;
  overflow-wrap: anywhere;
}

.layout {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  min-height: calc(100vh - 83px);
}

.sidebar {
  border-right: 1px solid var(--line);
  background: #eef3f6;
  padding: 14px;
  overflow: auto;
}

.section-nav,
.candidate-list,
.checklist,
.chips {
  display: grid;
  gap: 8px;
}

button,
input {
  font: inherit;
}

.section-button,
.candidate-row {
  width: 100%;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--ink);
  border-radius: 6px;
  padding: 10px;
  text-align: left;
  cursor: pointer;
}

.section-button {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.section-button.active,
.candidate-row.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.candidate-row span,
.candidate-row small {
  display: block;
  overflow-wrap: anywhere;
}

.candidate-row small {
  margin-top: 4px;
  color: var(--muted);
}

.search {
  display: grid;
  gap: 5px;
  margin: 14px 0;
  color: var(--muted);
  font-size: 12px;
}

.search input {
  min-height: 36px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 10px;
  color: var(--ink);
  background: var(--panel);
}

.detail {
  padding: 20px 24px 40px;
  overflow: auto;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--line);
  background: var(--line);
  margin-bottom: 16px;
}

.facts div,
.block,
.evidence-section {
  background: var(--panel);
}

.facts div {
  padding: 12px;
  min-width: 0;
}

.facts b,
.facts span,
.check span,
.check small {
  display: block;
  overflow-wrap: anywhere;
}

.facts b,
.check b {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 5px;
}

.block,
.evidence-section {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 14px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
}

.checklist {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.check {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  min-height: 82px;
  background: #fbfcfd;
}

.check.ok b {
  color: var(--ok);
}

.check.missing b {
  color: var(--missing);
}

.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1100px;
}

th,
td {
  border-bottom: 1px solid var(--line);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  max-width: 320px;
  overflow-wrap: anywhere;
}

th {
  position: sticky;
  top: 0;
  background: #edf2f7;
  color: var(--muted);
  font-size: 12px;
}

.raw-paths {
  margin: 0;
  padding-left: 18px;
}

.raw-paths li {
  margin: 4px 0;
  overflow-wrap: anywhere;
}

.empty {
  margin: 0;
  color: var(--muted);
}

@media (max-width: 900px) {
  .topbar,
  .detail-header {
    display: grid;
  }

  .summary {
    max-width: none;
    justify-content: flex-start;
  }

  .layout {
    grid-template-columns: 1fr;
  }

  .sidebar {
    border-right: 0;
    border-bottom: 1px solid var(--line);
    max-height: 52vh;
  }

  .facts {
    grid-template-columns: 1fr;
  }
}
"""


def write_viewer_files(dataset, root=None):
    """Write the static manual review viewer files."""
    paths = project_paths(root)
    viewer_dir = paths["root"] / "view"
    viewer_dir.mkdir(parents=True, exist_ok=True)
    dataset_json = json.dumps(dataset, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    embedded_json = json.dumps(dataset, sort_keys=True, ensure_ascii=True).replace("</", "<\\/")

    data_path = viewer_dir / "viewer_data.json"
    index_path = viewer_dir / "index.html"
    app_path = viewer_dir / "app.js"
    styles_path = viewer_dir / "styles.css"

    data_path.write_text(dataset_json, encoding="utf-8")
    index_path.write_text(_viewer_index_html(embedded_json), encoding="utf-8")
    app_path.write_text(_viewer_app_js(), encoding="utf-8")
    styles_path.write_text(_viewer_styles_css(), encoding="utf-8")

    return {
        "viewer_dir": str(viewer_dir),
        "index_html": str(index_path),
        "app_js": str(app_path),
        "styles_css": str(styles_path),
        "viewer_data_json": str(data_path),
        "index_url": index_path.resolve().as_uri(),
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
