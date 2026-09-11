# PQC Migration Collector

GitHub code search에서 PQC(Post-Quantum Cryptography) migration 후보를 수집하고, 파일/패치 기반 필터를 거쳐 수동 검토 가능한 export row와 viewer를 생성하는 collector다.

핵심 원칙은 검색 결과와 export 근거를 분리하는 것이다. 검색 결과는 후보 발견 신호일 뿐이며, export 가능한 후보는 commit/patch changed file 기준의 evidence를 가져야 한다.

## 현재 구조

```text
config/                  실행용 query/filter 설정
data/                    SQLite DB, raw GitHub response, cumulative export
reports/batches/         batch별 collection/filter/export report
runner/collect.py        단일 CLI entrypoint
scripts/smoke_50.sh      50건 순차 smoke 실행
scripts/run_async_pipeline.sh
                          수집과 필터 worker를 병행 실행
src/pqc_collector/       collector, filter, storage, reports, pipeline 코드
view/                    manual review viewer
```

## 실행 전 준비

`.env`에 아래 값이 있어야 한다.

```text
GITHUB_TOKEN=...
GITHUB_API_BASE=https://api.github.com
PY=C:\Users\dreac\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

Notion 관련 값이 있어도 현재 GitHub 수집/필터 pipeline에서는 사용하지 않는다.

## 50건 Smoke 실행

처음 본수집 전에 약 50건만 수집하고 전체 필터/export/viewer까지 순차적으로 확인하려면 아래 명령을 사용한다.

```powershell
bash scripts/smoke_50.sh
```

batch id를 직접 지정하려면:

```powershell
bash scripts/smoke_50.sh batch-smoke-50-20260908
```

이 스크립트는 아래 순서로 실행된다.

```text
collect-one-page
run-f0
fetch-files
run-f1
run-d0
run-f2
report-filters
export
inspect-export
build-viewer
```

기본 쿼리는 `openssl_evp_mlkem_ctx`이며 `page_size=50`이다.

## 비동기 본수집 실행

수집과 필터를 병행하려면 아래 스크립트를 사용한다.

```powershell
bash scripts/run_async_pipeline.sh
```

기본값은 설정 파일의 모든 쿼리, 각 쿼리 1페이지부터 10페이지, page size 100, stage limit 1000이다.

실행 전 흐름만 확인하려면:

```powershell
$env:DRY_RUN="1"
$env:RUN_ID="dryrun-check"
bash scripts/run_async_pipeline.sh
Remove-Item Env:\DRY_RUN
Remove-Item Env:\RUN_ID
```

주요 조절값:

```powershell
$env:QUERY_GROUP=""
$env:QUERY_KEY=""
$env:START_PAGE="1"
$env:MAX_PAGES_PER_QUERY="10"
$env:STAGE_LIMIT="1000"
bash scripts/run_async_pipeline.sh
```

특정 쿼리만 수집하려면 `QUERY_GROUP`과 `QUERY_KEY`를 지정한다. 여러 페이지를 이어서 수집하려면 `MAX_PAGES_PER_QUERY`를 늘린다.

## 지원 언어 제한

현재 설정은 아래 범위로 제한한다.

```text
JCE/JCA        Java
Bouncy Castle Java, C#
wolfSSL       C
OpenSSL       C
```

이 범위 밖의 언어로 임의 확장하지 않는다.

## 출력물

batch별 주요 출력:

```text
reports/batches/{batch_id}/query_pages.jsonl
reports/batches/{batch_id}/raw_search_items.jsonl
reports/batches/{batch_id}/filter_f0_path_quality.jsonl
reports/batches/{batch_id}/filter_f1_static_candidate.jsonl
reports/batches/{batch_id}/filter_d0_diff_evidence.jsonl
reports/batches/{batch_id}/filter_f2_migration_classifier.jsonl
reports/batches/{batch_id}/filter_summary.json
reports/batches/{batch_id}/export_candidates.jsonl
reports/batches/{batch_id}/non_exported_candidates.jsonl
```

누적 export:

```text
data/exports/migration_candidates.jsonl
```

수동 검토 viewer:

```text
view/index.html
view/app.js
view/styles.css
view/viewer_data.json
```

`view/index.html`은 정적 파일로 열 수 있도록 viewer dataset을 HTML 내부에도 포함한다.

## 검토 기준

각 필터 report row는 row 하나만 보고 pass/drop/label 근거 위치를 추적할 수 있어야 한다.

특히 export row의 `review_evidence`에서 아래 필드를 확인한다.

```text
signal
signal_type
source_field
context
raw_path
patch_hunk_header
patch_line_no
new_file_line
old_file_line
```

기본 export label은 아래 세 가지다.

```text
hybrid_migration
partial_migration
full_migration
```

`pqc_addition_only`와 `dropped`는 기본 export에서 제외된다.

## Export 후보 원격 검증

`runner/verify_exports.py`는 누적 export를 고정된 snapshot으로 만들고, 후보별 GitHub 저장소 정보, 해당 commit의 변경 파일, primary file의 부모/현재 버전을 가져온다. 검토자는 이 원문과 기존 `review_evidence`를 직접 읽고 `decisions.json`에 후보별 판정과 근거를 작성한다. 키워드로 판정을 자동 생성하지 않는다.

```powershell
python runner/verify_exports.py prepare --run-id review-20260909
python runner/verify_exports.py fetch --run-id review-20260909
python runner/verify_exports.py show --run-id review-20260909 --start 1 --end 10 --mode primary
# 모든 후보의 decisions.json 작성 후 실행
python runner/verify_exports.py validate --run-id review-20260909
python runner/verify_exports.py persist --run-id review-20260909
```

`fetch`는 `GITHUB_TOKEN`을 사용하고, 같은 run에서 이미 가져온 원문은 재사용한다. 다른 export나 새 원격 조회에는 새 run id를 사용한다. `validate`와 `persist`는 모든 후보의 판정 존재 여부, snapshot hash, 원문에 인용 근거가 실제 존재하는지 검사한다.

기존 `data/collector.sqlite`에 아래 테이블을 추가하며 원래 수집 테이블은 수정하지 않는다. 같은 run id로 재저장하면 해당 검증 결과만 교체하므로 중복되지 않는다.

- `migration_verification_runs`: 검토 기준, export hash, 실행 요약.
- `migration_candidate_reviews`: 제외/보류를 포함한 전체 판정, 사유, 근거 URL/코드, 원문 dossier 경로/hash. `review_json`에는 source kind와 검토 한계도 포함된다.
- `verified_migration_dataset`: `accepted` 판정만 저장한 데이터셋. 기존 export label과 별도로 재검토한 `migration_type`을 사용한다.

```sql
SELECT repository_full_name, commit_sha, primary_path, migration_type
FROM verified_migration_dataset
WHERE run_id = 'review-20260909';

SELECT verdict, COUNT(*)
FROM migration_candidate_reviews
WHERE run_id = 'review-20260909'
GROUP BY verdict;
```

검토 자료는 `reports/verification/{run_id}/`에 저장한다. `review_report.md`는 전체 판정과 근거, `accepted.jsonl`은 채택 결과, `review_policy.json`은 최종 판정 기준이며, `dossiers/`에는 원격 원문이 있다. 이 자료와 DB는 기존 생성 데이터 정책에 따라 git에서 제외된다.

`review-20260909`에서는 86건을 모두 원격 확인했고 4건 채택, 80건 제외, 2건 보류했다. 기존 암호 사용 흐름에 PQC/하이브리드 경로가 실제 연결된 변경만 채택했다. 기존 PQC 코드의 수정, 단독 신규 구현, 벤치마크와 테스트 fixture 등은 제외했다. 채택에는 실제 before/after가 있는 교육용 TLS 클라이언트 1건이 포함되며 `source_kind`로 구분된다. 이는 정적 소스 검토이며 빌드 성공, 실제 배포 또는 암호학적 안전성 검증을 의미하지 않는다.

## 로그

비동기 pipeline 로그:

```text
temp/async_pipeline/{RUN_ID}/logs/pipeline.log
temp/async_pipeline/{RUN_ID}/logs/*.log
```

실패 목록:

```text
temp/async_pipeline/{RUN_ID}/queues/failed/failures.tsv
```

## 주의

기존 DB에 이전 batch가 남아 있을 수 있다. 특정 smoke나 본수집 실행에서는 `run-f0 --next`보다 스크립트가 생성한 batch id를 명시적으로 따라가는 흐름을 우선 사용한다.

생성 데이터(`data/`, `reports/`, `temp/`, `view/viewer_data.json`)는 기본적으로 git에 올리지 않는다.
