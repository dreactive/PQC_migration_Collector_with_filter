import json

from pqc_collector.util import project_paths


RAW_RESPONSE_PREFIXES = {
    "rate_limit": "rate_limit",
    "query_page": "query_page",
    "file": "file",
    "commit": "commit",
    "pr": "pr",
}


def write_raw_response(batch_id, response_kind, response_key, payload, root=None):
    """Write one raw GitHub API response and return its path."""
    prefix = RAW_RESPONSE_PREFIXES.get(response_kind)
    if prefix is None:
        valid_kinds = ", ".join(sorted(RAW_RESPONSE_PREFIXES))
        raise KeyError(f"unknown raw response kind: {response_kind}. valid kinds: {valid_kinds}")

    raw_dir = project_paths(root)["raw_github"] / str(batch_id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = raw_dir / f"{prefix}_{response_key}.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path
