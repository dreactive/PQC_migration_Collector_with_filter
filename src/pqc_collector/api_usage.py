import json
from datetime import datetime, timezone

from pqc_collector.reports import report_paths


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
