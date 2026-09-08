#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/bin:/bin:/mingw64/bin:${PATH:-}"

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
if [[ "$SCRIPT_DIR" == "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="."
fi
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
BATCH_PREFIX="${BATCH_PREFIX:-live}"
QUERY_GROUP="${QUERY_GROUP:-}"
QUERY_KEY="${QUERY_KEY:-}"
START_PAGE="${START_PAGE:-1}"
MAX_PAGES_PER_QUERY="${MAX_PAGES_PER_QUERY:-10}"
STAGE_LIMIT="${STAGE_LIMIT:-1000}"
COLLECT_THROTTLE_SECONDS="${COLLECT_THROTTLE_SECONDS:-3}"
RETRY_COUNT="${RETRY_COUNT:-3}"
RETRY_SLEEP_SECONDS="${RETRY_SLEEP_SECONDS:-10}"
POLL_SECONDS="${POLL_SECONDS:-2}"
RUN_REPORTS="${RUN_REPORTS:-1}"
RUN_EXPORT="${RUN_EXPORT:-1}"
RUN_VIEWER="${RUN_VIEWER:-1}"
CHECK_RATE_LIMIT="${CHECK_RATE_LIMIT:-1}"
DRY_RUN="${DRY_RUN:-0}"

RUN_DIR="temp/async_pipeline/$RUN_ID"
QUEUE_DIR="$RUN_DIR/queues"
LOG_DIR="$RUN_DIR/logs"
STATE_DIR="$RUN_DIR/state"
mkdir -p "$QUEUE_DIR"/{f0,files,f1,d0,f2,final,failed} "$LOG_DIR" "$STATE_DIR"

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -n "$line" ]] || continue
    [[ "$line" == \#* ]] && continue
    [[ "$line" == *"="* ]] || continue
    local key="${line%%=*}"
    local value="${line#*=}"
    key="$(printf '%s' "$key" | xargs)"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    [[ -n "$key" ]] || continue
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done < "$env_file"
}

normalize_python_bin() {
  local candidate="${PY:-python}"
  if command -v cygpath >/dev/null 2>&1 && [[ "$candidate" == *\\* ]]; then
    cygpath -u "$candidate"
  else
    printf '%s\n' "$candidate"
  fi
}

safe_name() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'
}

queue_put() {
  local queue="$1"
  local batch_id="$2"
  local file="$QUEUE_DIR/$queue/$(safe_name "$batch_id").ready"
  printf '%s\n' "$batch_id" > "$file"
}

queue_done() {
  local queue="$1"
  touch "$STATE_DIR/$queue.done"
}

mark_failed() {
  local stage="$1"
  local batch_id="$2"
  printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$stage" "$batch_id" \
    >> "$QUEUE_DIR/failed/failures.tsv"
}

log_line() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_DIR/pipeline.log"
}

run_with_retry() {
  local stage="$1"
  local batch_id="$2"
  shift 2
  local log_file="$LOG_DIR/${stage}_$(safe_name "$batch_id").log"
  if [[ "$DRY_RUN" == "1" ]]; then
    log_line "dry-run stage=$stage batch=$batch_id command=$*"
    return 0
  fi
  local attempt=1
  while (( attempt <= RETRY_COUNT )); do
    log_line "start stage=$stage batch=$batch_id attempt=$attempt"
    if "$@" > "$log_file" 2>&1; then
      log_line "ok stage=$stage batch=$batch_id log=$log_file"
      return 0
    fi
    log_line "retry stage=$stage batch=$batch_id attempt=$attempt log=$log_file"
    attempt=$((attempt + 1))
    sleep "$RETRY_SLEEP_SECONDS"
  done
  log_line "failed stage=$stage batch=$batch_id log=$log_file"
  mark_failed "$stage" "$batch_id"
  return 1
}

next_ready_file() {
  local queue="$1"
  local file
  shopt -s nullglob
  for file in "$QUEUE_DIR/$queue"/*.ready; do
    printf '%s\n' "$file"
    shopt -u nullglob
    return 0
  done
  shopt -u nullglob
  return 1
}

stage_worker() {
  local stage="$1"
  local in_queue="$2"
  local out_queue="$3"
  local in_done="$4"

  while true; do
    local ready_file=""
    if ready_file="$(next_ready_file "$in_queue")"; then
      local work_file="${ready_file%.ready}.work"
      if ! mv "$ready_file" "$work_file" 2>/dev/null; then
        sleep "$POLL_SECONDS"
        continue
      fi
      local batch_id
      batch_id="$(tr -d '\r\n' < "$work_file")"
      local ok=0

      case "$stage" in
        f0)
          run_with_retry "$stage" "$batch_id" "$PYTHON_BIN" runner/collect.py \
            run-f0 --batch-id "$batch_id" --limit "$STAGE_LIMIT" || ok=$?
          ;;
        files)
          run_with_retry "$stage" "$batch_id" "$PYTHON_BIN" runner/collect.py \
            fetch-files --batch-id "$batch_id" --limit "$STAGE_LIMIT" || ok=$?
          ;;
        f1)
          run_with_retry "$stage" "$batch_id" "$PYTHON_BIN" runner/collect.py \
            run-f1 --batch-id "$batch_id" --limit "$STAGE_LIMIT" || ok=$?
          ;;
        d0)
          run_with_retry "$stage" "$batch_id" "$PYTHON_BIN" runner/collect.py \
            run-d0 --batch-id "$batch_id" --limit "$STAGE_LIMIT" || ok=$?
          ;;
        f2)
          run_with_retry "$stage" "$batch_id" "$PYTHON_BIN" runner/collect.py \
            run-f2 --batch-id "$batch_id" --limit "$STAGE_LIMIT" || ok=$?
          ;;
        final)
          if [[ "$RUN_REPORTS" == "1" ]]; then
            run_with_retry report-filters "$batch_id" "$PYTHON_BIN" runner/collect.py \
              report-filters --batch-id "$batch_id" --sample-limit 3 || ok=$?
          fi
          if [[ "$ok" == "0" && "$RUN_EXPORT" == "1" ]]; then
            run_with_retry export "$batch_id" "$PYTHON_BIN" runner/collect.py \
              export --batch-id "$batch_id" || ok=$?
          fi
          if [[ "$ok" == "0" && "$RUN_VIEWER" == "1" ]]; then
            run_with_retry build-viewer "$batch_id" "$PYTHON_BIN" runner/collect.py \
              build-viewer --source "reports/batches/$batch_id/export_candidates.jsonl" || ok=$?
          fi
          ;;
        *)
          log_line "unknown stage=$stage"
          ok=2
          ;;
      esac

      rm -f "$work_file"
      if [[ "$ok" == "0" && -n "$out_queue" ]]; then
        queue_put "$out_queue" "$batch_id"
      fi
      continue
    fi

    if [[ -f "$STATE_DIR/$in_done.done" ]]; then
      [[ -n "$out_queue" ]] && queue_done "$out_queue"
      log_line "done stage=$stage"
      break
    fi
    sleep "$POLL_SECONDS"
  done
}

emit_query_rows() {
  "$PYTHON_BIN" - "$QUERY_GROUP" "$QUERY_KEY" <<'PY'
import json
import pathlib
import sys

group_filter = sys.argv[1]
key_filter = sys.argv[2]
config = json.loads(pathlib.Path("config/collection_queries.json").read_text(encoding="utf-8"))
for group, queries in config.get("query_groups", {}).items():
    if group_filter and group != group_filter:
        continue
    for query in queries:
        if key_filter and query.get("query_key") != key_filter:
            continue
        print(
            "\t".join(
                [
                    group,
                    query["query_key"],
                    query["query_text"],
                    str(query.get("page_size", 50)),
                ]
            )
        )
PY
}

collector_worker() {
  local rows=()
  mapfile -t rows < <(emit_query_rows)
  if (( ${#rows[@]} == 0 )); then
    log_line "no query matched group=$QUERY_GROUP key=$QUERY_KEY"
    queue_done f0
    return 1
  fi

  local row group key text page_size page batch_id
  for row in "${rows[@]}"; do
    IFS=$'\t' read -r group key text page_size <<< "$row"
    for (( page=START_PAGE; page<START_PAGE + MAX_PAGES_PER_QUERY; page++ )); do
      batch_id="${BATCH_PREFIX}-${RUN_ID}-$(safe_name "$key")-p${page}"
      if run_with_retry collect "$batch_id" "$PYTHON_BIN" runner/collect.py \
        collect-one-page \
        --batch-id "$batch_id" \
        --query-key "$key" \
        --query-group "$group" \
        --query-text "$text" \
        --page "$page" \
        --page-size "$page_size"; then
        queue_put f0 "$batch_id"
      fi
      if [[ "$COLLECT_THROTTLE_SECONDS" != "0" ]]; then
        sleep "$COLLECT_THROTTLE_SECONDS"
      fi
    done
  done
  queue_done f0
}

load_env_file "$ROOT_DIR/.env"
PYTHON_BIN="$(normalize_python_bin)"

log_line "run_id=$RUN_ID root=$ROOT_DIR"
log_line "query_group=$QUERY_GROUP query_key=$QUERY_KEY start_page=$START_PAGE pages=$MAX_PAGES_PER_QUERY limit=$STAGE_LIMIT"

if [[ "$CHECK_RATE_LIMIT" == "1" ]]; then
  run_with_retry rate-limit "$RUN_ID" "$PYTHON_BIN" runner/collect.py \
    check-rate-limit --batch-id "rate-limit-$RUN_ID"
fi

stage_worker f0 f0 files f0 &
stage_worker files files f1 files &
stage_worker f1 f1 d0 f1 &
stage_worker d0 d0 f2 d0 &
stage_worker f2 f2 final f2 &
stage_worker final final "" final &
collector_worker &

wait

log_line "pipeline complete"
if [[ -f "$QUEUE_DIR/failed/failures.tsv" ]]; then
  log_line "failures recorded at $QUEUE_DIR/failed/failures.tsv"
  exit 1
fi
