import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pqc_collector.reports import report_schemas, write_schema_preview  # noqa: E402
from pqc_collector.util import ensure_dirs  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(description="PQC migration collector runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "init-skeleton",
        help="Create and report the standard collector workspace directories.",
    )
    schema_preview = subparsers.add_parser(
        "schema-preview",
        help="Write a JSON preview of collector, filter, and export report schemas.",
    )
    schema_preview.add_argument(
        "--output",
        default=PROJECT_ROOT / "reports" / "batches" / "schema-preview" / "schema_preview.json",
        type=Path,
        help="Path to write the schema preview JSON.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-skeleton":
        result = ensure_dirs(PROJECT_ROOT)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "schema-preview":
        output_path = write_schema_preview(args.output)
        result = {
            "output_path": str(output_path),
            "schema_count": len(report_schemas()),
        }
        print(json.dumps(result, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
