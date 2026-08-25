import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pqc_collector.util import ensure_dirs  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(description="PQC migration collector runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "init-skeleton",
        help="Create and report the standard collector workspace directories.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-skeleton":
        result = ensure_dirs(PROJECT_ROOT)
        print(json.dumps(result, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
