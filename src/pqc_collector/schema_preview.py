import json
from datetime import datetime, timezone
from pathlib import Path


def write_schema_preview(output_path, schemas):
    """Write a JSON preview of report schemas for human review."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema_count": len(schemas),
        "schemas": schemas,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
