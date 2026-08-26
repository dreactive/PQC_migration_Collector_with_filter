from datetime import datetime, timezone

from pqc_collector.reports import report_paths


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
