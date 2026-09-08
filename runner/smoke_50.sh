#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BATCH="${1:-${BATCH:-batch-smoke-50-20260908}}"
DEFAULT_PY="/c/Users/dreac/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
PY_BIN="${PY:-$DEFAULT_PY}"

if [[ ! -x "$PY_BIN" ]]; then
  if command -v python >/dev/null 2>&1; then
    PY_BIN="$(command -v python)"
  else
    echo "Python executable not found: $PY_BIN" >&2
    echo "Set PY to a valid python.exe path and retry." >&2
    exit 1
  fi
fi

echo "Using Python: $PY_BIN"
echo "Using batch: $BATCH"

"$PY_BIN" runner/collect.py collect-one-page \
  --batch-id "$BATCH" \
  --query-key openssl_evp_mlkem_ctx \
  --query-group openssl_pqc_api \
  --query-text '"EVP_PKEY_CTX_new_from_name" "ML-KEM" language:C' \
  --page 1 \
  --page-size 50

"$PY_BIN" runner/collect.py run-f0 --batch-id "$BATCH" --limit 50
"$PY_BIN" runner/collect.py fetch-files --batch-id "$BATCH" --limit 50
"$PY_BIN" runner/collect.py run-f1 --batch-id "$BATCH" --limit 50
"$PY_BIN" runner/collect.py run-d0 --batch-id "$BATCH" --limit 50
"$PY_BIN" runner/collect.py run-f2 --batch-id "$BATCH" --limit 50
"$PY_BIN" runner/collect.py report-filters --batch-id "$BATCH" --sample-limit 3
"$PY_BIN" runner/collect.py export --batch-id "$BATCH"
"$PY_BIN" runner/collect.py inspect-export \
  --source "reports/batches/$BATCH/export_candidates.jsonl"
"$PY_BIN" runner/collect.py build-viewer \
  --source "reports/batches/$BATCH/export_candidates.jsonl"
