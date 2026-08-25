from pqc_collector.util import project_paths


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
            "repository_full_name",
            "search_item_path",
            "commit_sha",
            "matched_changed_path",
            "exact_path_match",
            "patch_available",
            "passed",
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
