# Mistakes Memory — ORBI WAT Framework

에이전트별 실수 기록. PreToolUse/PostToolUse hook이 자동으로 읽고 씁니다.

---

## Core (모든 에이전트 공통)

### M-001: cp949 UnicodeEncodeError
- **에이전트**: Core
- **날짜**: 2026-03-18
- **상황**: Python print()에 이모지/em dash 포함 시 Windows 터미널 cp949 인코딩 크래시
- **에러**: `UnicodeEncodeError: 'charmap' codec can't encode character`
- **수정**: `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 스크립트 상단에 추가
- **예방**: 모든 Python 스크립트에서 non-ASCII 출력 있으면 reconfigure 먼저

### M-002: bash 인라인 Python 따옴표 중첩
- **에이전트**: Core
- **날짜**: 2026-03-19
- **상황**: `python -c "..."` 안에 작은따옴표/큰따옴표 혼재 시 bash 파싱 실패
- **에러**: `unexpected EOF while looking for matching quote`
- **수정**: `python << 'PYEOF' ... PYEOF` heredoc 사용 또는 `.tmp/script.py` 파일로 저장 후 실행
- **예방**: 10줄 이상 Python은 무조건 파일로 저장

### M-003: curl SSL revocation check 실패
- **에이전트**: Core
- **날짜**: 2026-03-18
- **상황**: Windows에서 `curl https://...` 호출 시 SSL 인증서 revocation check 실패
- **에러**: `SSL: certificate subject name does not match` 또는 `schannel: next InitializeSecurityContext`
- **수정**: `curl -sk` (silent + insecure) 사용
- **예방**: Windows 환경 curl은 항상 `-sk`

### M-004: 스크립트 경로 하드코딩 — 멀티 컴터 브레이크
- **에이전트**: Core
- **날짜**: 2026-03-21
- **상황**: mistake_recorder.py, mistake_checker.py, _check_rag.py 등에 `C:\Users\wjcho\Desktop\WJ Test1` 절대경로 박혀있음. 랩탑에서 실행 시 FileNotFoundError
- **에러**: `FileNotFoundError: C:\Users\wjcho\Desktop\WJ Test1\.tmp\...`
- **수정**: `os.path.dirname(os.path.abspath(__file__))` 기준 상대경로로 변경
- **예방**: 절대경로 하드코딩 금지. 항상 `__file__` 또는 env var 기준으로 경로 설정

### M-005: 공유 파일을 ~/.claude/ 에 저장 — 멀티 컴터 미공유
- **에이전트**: Core
- **날짜**: 2026-03-21
- **상황**: mistakes.md를 `~/.claude/projects/.../memory/` 에 저장했더니 SynologyDrive로 싱크 안 됨. 데스크탑/랩탑 각각 따로 존재
- **에러**: 데이터 분리 — 각 컴터에서 쌓인 오답노트가 공유 안 됨
- **수정**: 공유 파일은 프로젝트 폴더(SynologyDrive) 안 `memory/` 에 저장. `~/.claude/` 는 로컬 전용
- **예방**: 팀/멀티컴터 공유 필요한 파일은 반드시 SynologyDrive 프로젝트 내부에 저장

### M-006: hooks 미등록 — 오답노트 시스템 무용지물
- **에이전트**: Core
- **날짜**: 2026-03-21
- **상황**: mistake_checker.py(PreToolUse), mistake_recorder.py(PostToolUse) 스크립트가 있었지만 `.claude/settings.json` hooks에 등록 안 됨
- **에러**: hooks 섹션에 error_logger.py만 있고 나머지 없음
- **수정**: settings.json PreToolUse + PostToolUse에 각각 추가
- **예방**: 새 hook 스크립트 만들면 반드시 settings.json에 즉시 등록. 등록 여부 테스트까지 확인

### M-007: Anthropic API 키 비활성화 시 n8n 하드코딩 키 미교체
- **에이전트**: Core
- **날짜**: 2026-03-22
- **상황**: Anthropic Console에서 키 비활성화 시도. n8n 워크플로우 5개에 API 키가 credential이 아닌 httpRequest 헤더/코드에 직접 하드코딩
- **에러**: `Couldn't connect with these settings` + DM Auto Reply 워크플로우 Claude API 호출 실패
- **수정**: n8n API로 88개 전체 워크플로우 스캔 → 삭제된 키 사용처 발견 → 전수 교체
- **예방**: (1) API 키 비활성화 전 반드시 n8n 전체 워크플로우 스캔 (2) httpRequest 노드에 키 하드코딩 금지 → credential 참조로 통일

### M-008: 존재하지 않는 함수 호출 — 배포 전 테스트 미실행
- **에이전트**: Core
- **날짜**: 2026-03-22
- **상황**: `--verify` CLI 옵션 추가 후 `_ensure_auth()` 호출했으나 해당 함수가 존재하지 않음
- **에러**: `NameError: name '_ensure_auth' is not defined`
- **수정**: `_ensure_auth()` 호출 제거 (인증은 API 호출 시 `get_access_token()`이 자동 처리)
- **예방**: 새 코드 추가 후 반드시 로컬에서 1회 실행 테스트. push 전 최소 import 테스트

---

## Google API (Sheets / Gemini)

### M-009: Sheets API range 포맷 에러
- **에이전트**: Google API
- **날짜**: 2026-03-19
- **상황**: `Creator FAQ!A1:Z50` → `!` 앞에 자동으로 `\` 이스케이프 붙어서 API 400 에러
- **에러**: `Unable to parse range: Creator FAQ\!A1:Z50`
- **수정**: `"'Creator FAQ'!A1:Z50"` — 탭 이름을 작은따옴표로 감싸고, heredoc에서 실행
- **예방**: 탭 이름에 공백 있으면 반드시 작은따옴표. bash -c 대신 heredoc 또는 파일 실행

### M-010: Gemini embedding model 이름 오류
- **에이전트**: Google API
- **날짜**: 2026-03-18
- **상황**: `text-embedding-004` 모델 호출 → 404 Not Found
- **수정**: `gemini-embedding-001` 사용 (3072-dim)
- **예방**: Gemini 임베딩은 `gemini-embedding-001`만 사용

### M-011: google.generativeai deprecated
- **에이전트**: Google API
- **날짜**: 2026-03-18
- **상황**: `import google.generativeai as genai` → 구 SDK, API 호출 방식 다름
- **수정**: `from google import genai` (google-genai 패키지)
- **예방**: `pip install google-genai`, import는 `from google import genai`

### M-012: Pinecone 차원 불일치
- **에이전트**: 이메일 지니
- **날짜**: 2026-03-18
- **상황**: 768-dim 인덱스 생성 (Voyage AI용) → Gemini는 3072-dim
- **수정**: 기존 `multimodal-embeddings` 인덱스 (3072-dim) 사용, namespace `gmail-rag`
- **예방**: 임베딩 모델 차원 먼저 확인 후 인덱스 생성/선택

---

## n8n 매니저

### M-013: n8n POST active 필드 에러
- **에이전트**: n8n 매니저
- **날짜**: 2026-03-20
- **상황**: n8n 워크플로우 POST 시 active 필드 포함하면 read-only 에러
- **에러**: `"active" is read-only and cannot be set`
- **수정**: POST body에서 `active` 필드 제거
- **예방**: n8n POST/PUT 시 active 필드는 절대 포함 금지

### M-014: n8n JSON cp949 인코딩
- **에이전트**: n8n 매니저
- **날짜**: 2026-03-20
- **상황**: Windows에서 curl로 n8n API JSON 전송 시 한글 깨짐
- **에러**: JSON 파싱 오류 또는 한글 깨짐
- **수정**: Python으로 파일 저장(`rb` 모드 + `decode('utf-8')`) 후 curl에 파일 전달
- **예방**: n8n JSON은 파일로 저장 후 `curl --data-binary @file.json` 방식 사용

### ⚠️ DEPRECATED: n8n "WJ인플 TEST" 폴더 사용 중단
- **에이전트**: n8n 매니저
- **날짜**: 2026-03-21
- **결정**: `WJ인플 TEST` 폴더(태그: `wj-test-1`) 내 워크플로우 — **앞으로 사용 안 함**
- **이유**: PROD → WJ TEST 마이그레이션 완료 (2026-03-13). 파이프라인 PROD로 전환됨
- **대체**: PROD 폴더 워크플로우 직접 사용

---

## 이메일 지니 (Gmail RAG)

### M-015: 토큰 스코프 불일치
- **에이전트**: 이메일 지니
- **날짜**: 2026-03-18
- **상황**: zezebaebae 토큰이 `gmail.send` 스코프만 갖고 있어서 `gmail.readonly` 호출 실패
- **에러**: `Insufficient Permission: Request had insufficient authentication scopes`
- **수정**: `gmail.readonly` + `gmail.send` 스코프로 재인증
- **예방**: 토큰 생성 시 필요한 모든 스코프를 미리 포함

### M-016: OAuth 브라우저 팝업 타임아웃
- **에이전트**: 이메일 지니
- **날짜**: 2026-03-18
- **상황**: Claude Code bash 도구 내에서 OAuth 인증 → 브라우저 팝업 → 타임아웃
- **수정**: VS Code 터미널에서 직접 실행하도록 유저에게 안내
- **예방**: OAuth 인증이 필요한 작업은 유저에게 터미널 직접 실행 요청

### M-017: 불필요한 대량 인덱싱
- **에이전트**: 이메일 지니
- **날짜**: 2026-03-18
- **상황**: orbiters11@gmail.com 27K 이메일 인덱싱 시작 → 유저가 "읽을 필요 없음"
- **수정**: 인덱싱 중단, ACCOUNTS에서 제거
- **예방**: 대량 작업 전 유저에게 범위 확인. 계정별 필터(backfill_query) 먼저 설정

### M-018: zezebaebae 전체 인덱싱 (33K)
- **에이전트**: 이메일 지니
- **날짜**: 2026-03-18
- **상황**: zezebaebae 전체 33K 이메일 인덱싱 → 유저가 "collab 키워드만"
- **수정**: `backfill_query: "collab OR collaboration"` 추가 → 755개로 축소
- **예방**: 계정별 필터 조건을 유저에게 먼저 확인

### M-019: Gmail RAG — 인덱스 미동기화 (2일 이상 경과)
- **에이전트**: 이메일 지니
- **날짜**: 2026-03-21
- **상황**: 마지막 동기화 2026-03-18 이후 신규 이메일 인덱싱 안 됨
- **에러**: 최근 이메일 RAG 검색 시 누락
- **수정**: `python tools/gmail_rag.py --sync` 실행
- **예방**: GitHub Actions 또는 Task Scheduler로 매일 자동 동기화 설정 필요

---

## 데이터 키퍼

### M-020: PG upsert는 stale rows를 삭제하지 않음
- **에이전트**: 데이터 키퍼
- **날짜**: 2026-03-19
- **상황**: data_keeper.py Shopify 채널 분류 로직 변경 (FBA MCF: Amazon → D2C). 새 코드로 재수집했지만 PG의 기존 `channel=Amazon` rows는 삭제되지 않음 → 매출 이중 계산
- **에러**: Grosmimi Jan 2026 매출: PG daily $203K (실제 $107K) — $95K 이중 계산
- **수정**: generate_fin_data.py에서 Shopify `channel=Amazon` 스킵
- **예방**: PG upsert ≠ full replace. 분류 로직 변경 후 반드시 stale data 정리 필요

---

## 아마존 퍼포마

### M-021: Amazon Ads API — search term report date 컬럼 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: timeUnit=SUMMARY로 search term report 요청 시 date 컬럼 포함하면 에러
- **에러**: `date column not available with timeUnit=SUMMARY`
- **수정**: columns 목록에서 `"date"` 제거
- **예방**: SUMMARY 리포트는 date 컬럼 사용 불가

### M-022: Amazon Ads API — keyword report groupBy 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: keyword report 요청 시 groupBy에 "keyword" 또는 "keywordId" 넣으면 에러
- **에러**: `Invalid groupBy value`
- **수정**: `groupBy: ["adGroup"]` 으로 변경
- **예방**: keyword report groupBy는 반드시 `["adGroup"]`

### M-023: Amazon Ads API — campaignId/adGroupId int 전송 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: API 실행 시 campaignId/adGroupId를 int로 전송하면 400 에러
- **에러**: `"NUMBER_VALUE can not be converted to a String"`
- **수정**: `str(campaign_id)` 로 변환 후 전송
- **예방**: Amazon Ads API ID 필드는 항상 string 타입으로 변환

### M-024: Amazon Ads API — targets PUT wrapper 누락
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: ASIN target 입찰가 수정 시 body에 targetingClauses wrapper 없으면 에러
- **에러**: `Invalid request body`
- **수정**: `{"targetingClauses": [{...}]}` 형태로 감싸기
- **예방**: SP targets PUT은 반드시 targetingClauses 배열 wrapper 필요

### M-025: Amazon Ads API — targets list state filter 대소문자
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: targets list 요청 시 state filter 소문자로 보내면 필터 무시됨
- **에러**: 빈 결과 또는 모든 상태 반환
- **수정**: `"ENABLED"` (대문자) 로 변경
- **예방**: Amazon Ads API state filter는 항상 대문자 (ENABLED, PAUSED, ARCHIVED)

### M-026: Amazon SP-API — Grosmimi 전용 LWA 앱 혼용 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: Grosmimi refresh token이 자체 LWA 앱으로 발급됐으나 shared client로 교환 시도
- **에러**: `ACI prefix 'amzn1.swa.' did not match` 또는 400 Bad Request
- **수정**: Grosmimi는 shared client + Grosmimi 원래 refresh token 조합 사용
- **예방**: SP-API refresh token은 발급한 LWA 앱과 client_id가 반드시 매칭

### M-027: Amazon Ads API — add_keyword HTTP 200이지만 개별 keyword 거부 (팬텀 실행)
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-22
- **상황**: 떡뻥(한국어) 키워드를 US 마켓에 harvest 실행. API HTTP 200 반환하지만 실제 미등록
- **에러**: response body 내 개별 keyword `code` 필드가 `SUCCESS`가 아님 (자동 거부)
- **수정**: `add_keyword()`, `add_negative_keyword()`에 응답 body 개별 keyword `code` 필드 검증 추가
- **예방**: Amazon Ads API bulk 요청은 HTTP status와 개별 item status가 별개. 항상 body의 각 item `code` 검증

### M-028: PPC executor — GitHub Actions에서 harvest dedup 무효화
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-22
- **상황**: 떡뻥 키워드가 execute됐는데도 매일 다시 proposal에 등장
- **에러**: `_load_executed_history()`가 `.tmp/` 만 스캔. GitHub Actions는 매번 fresh checkout → dedup 히스토리 0
- **수정**: `exec_log.json` (git-committed persistent log)도 dedup 소스로 추가
- **예방**: Actions에서 돌아가는 로직은 로컬 파일(.tmp/) 의존 금지. git-committed 또는 DB에서 히스토리 로드

### M-029: GitHub Actions data.js 이전 날짜 소실
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-19
- **상황**: Dashboard Execute dispatch → Actions에서 새 proposal만 → 이전 날짜/브랜드 전부 소실
- **에러**: data.js가 새 proposal 1건만 포함, 기존 누적 데이터 모두 삭제
- **수정**: `_load_existing_data_js()` 함수 추가. 기존 data.js를 먼저 읽어 old dates 보존
- **예방**: GitHub Actions `.tmp/`는 ephemeral. 누적 데이터는 반드시 기존 output에서 merge

### M-030: campaignName 기반 brand detection 오분류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-19
- **상황**: `campaignName`에 "grosmimi" 포함 여부로 브랜드 판별. 이름에 브랜드명 미포함 → 전부 naeiae로 오분류
- **에러**: exec_log.json에 grosmimi 28건이 naeiae에 잘못 기록
- **수정**: executed item에 `brand_key` 필드 추가, campaignName은 fallback으로만
- **예방**: 브랜드 판별은 항상 명시적 brand_key 사용

### M-031: GitHub PAT fine-grained → org repo dispatch 403
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-19
- **상황**: PPC Dashboard에서 workflow dispatch에 fine-grained PAT → org repo 403 Forbidden
- **에러**: `403 Forbidden` — fine-grained PAT은 org repo workflow dispatch 미지원
- **수정**: Classic PAT(repo+workflow scope) + PIN 인증(0812)으로 PAT 숨김
- **예방**: GitHub org repo workflow dispatch = Classic PAT 필수. PAT을 프론트엔드에 노출 금지

### M-032: exec_log 업데이트가 generate_dashboard_data.py에 의존
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-19
- **상황**: Executor 실행 후 exec_log.json이 즉시 업데이트 안 되고 별도 스크립트 실행 시에만 기록
- **수정**: Executor가 직접 exec_log.json 업데이트. merge-with-dedup 처리
- **예방**: 실행 결과는 실행 직후 즉시 영속 저장. 후속 스크립트에 의존하면 타이밍 gap 발생

### M-033: exec_log 03-08 중복 레코드 9건
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-19
- **상황**: exec_log.json에 동일 campaignId 레코드가 9건 중복. dedup 로직 없이 append만
- **수정**: dedup 로직 추가 (campaignId + date 기준). 중복 9건 제거
- **예방**: append 방식 로그는 반드시 dedup 로직 포함

### M-034: PPC summary_7d zeroed defaults에서 계산
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-19
- **상황**: summary_7d를 zeroed default 값에서 계산 → 7일 요약이 전부 0
- **수정**: campaign-level 데이터에서 직접 7일 합산 계산
- **예방**: summary/aggregate 값은 반드시 원본 데이터에서 계산. default 초기값에서 계산하면 항상 0

### M-035: PPC 대시보드 — GitHub Pages 정적 파일 캐시
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-22
- **상황**: KST 08:00에 대시보드 확인했는데 07:30 Pipeline 결과가 안 보임. 실제로는 정상 업데이트
- **에러**: 브라우저 캐시로 인해 이전 data.js 표시
- **수정**: Ctrl+Shift+R 하드 리프레시
- **예방**: GitHub Pages 정적 파일 → 캐시 이슈 불가피. data.js에 `?v=timestamp` 캐시 버스터 검토

---

## 골만이 / Financial Dashboard

### M-036: Financial Dashboard waterfall Meta 광고비 누락
- **에이전트**: 골만이
- **날짜**: 2026-03-19
- **상황**: `generate_fin_data.py` waterfall에서 `"Meta Ads"` 키 참조. 실제 키는 `"Meta CVR"` + `"Meta Traffic"`
- **에러**: 월 ~$27K 광고비 누락 → CM 과대계상. 월 ~$37K 매출이 Organic으로 잘못 분류
- **수정**: `"Meta Ads"` → `"Meta CVR", "Meta Traffic"` 교체
- **예방**: ad_monthly 딕셔너리 키와 참조 키 일치 확인. 플랫폼 세분화 시 모든 하위 키 포함

### M-037: KPI Shopify Amazon 채널 → Amazon MP로 잘못 분류
- **에이전트**: 골만이
- **날짜**: 2026-03-19
- **상황**: Shopify `channel="Amazon"`은 FBA MCF (DTC 주문 + Amazon 물류). KPI에서 "Amazon"으로 패스스루 → SP-API Amazon과 합산
- **에러**: FBA MCF 매출이 Amazon MP에 귀속. Dec 2025+ 월 $12K-$109K 잘못 분류
- **수정**: `CHANNEL_MAP`의 `"Amazon": "Onzenna"` 매핑
- **예방**: Shopify channel="Amazon" = FBA MCF (DTC 귀속). 진짜 Amazon = SP-API 전용

### M-038: COGS 계산 방식 오류 — variable cost vs product cost
- **에이전트**: 골만이
- **날짜**: 2026-03-19
- **상황**: COGS를 `Revenue - CM before Ads` (all variable costs, ~67%)로 계산. 실제 COGS는 제품 원가만 (~38%)
- **에러**: Gross Margin 33% (실제 60-64%) — COGS에 물류비/수수료 등 비원가 항목 포함
- **수정**: COGS = units * AVG_COGS (제품 원가만)
- **예방**: COGS = 제품 원가(product cost)만. GM ~60%가 정상 (유아용품 DTC)

### M-039: Polar Excel 빈 탭 참조
- **에이전트**: 골만이
- **날짜**: 2026-03-19
- **상황**: Polar Excel "폴라 희망" 탭 참조 → 비어있음. 실제 데이터는 "IR 매출분석" 탭
- **에러**: Amazon Ads 연간 광고비 $0 표시 (실제 $657K)
- **수정**: `tab_name = "IR 매출분석"` 으로 변경
- **예방**: 빈 결과 나오면 탭 목록 먼저 출력해서 올바른 소스인지 검증

### M-040: Grosmimi sub-rows 불필요하게 추가
- **에이전트**: 골만이
- **날짜**: 2026-03-19
- **상황**: Brand Performance에 Grosmimi 제품별 breakdown 추가 → 유저가 원하지 않음
- **수정**: sub-row 코드 전체 삭제. 브랜드 레벨만 유지
- **예방**: 세분화 레벨은 유저에게 먼저 확인. 불필요한 복잡성 → 삭제 비용 발생

### M-041: SKU 데이터 "없다"고 섣부른 결론
- **에이전트**: 골만이
- **날짜**: 2026-03-19
- **상황**: 제품별 breakdown에 gap → "PG에 SKU 데이터 없음"이라 결론. 실제로는 stale Amazon 채널 rows가 원인
- **수정**: Shopify Amazon 채널 필터링으로 gap 0.4%까지 감소
- **예방**: 데이터 "없음" 결론 전에 stale data, 분류 변경, 이중 계산 먼저 검토. 유저의 직관 존중

---

## 파이프라이너

### M-042: Airtable base 혼동 — PROD vs WJ TEST 방향 전환 3번
- **에이전트**: 파이프라이너
- **날짜**: 2026-03-19
- **상황**: 유저 "이거말하느거맞지?" → WJ TEST로 변경 → "PROD로 돌리는거 아니냐" → 다시 PROD 복원
- **에러**: WJ TEST 필드명이 PROD와 다름 → 422 에러
- **수정**: PROD base로 복원. Pathlight = PROD base (`app3Vnmh7hLAVsevE`)
- **예방**: 유저 질문이 확인인지 지시인지 구분. base 변경 전 필드명 호환성 먼저 확인

### M-043: 기존 워크플로우 존재 확인 안 하고 "없다" 단언
- **에이전트**: 파이프라이너
- **날짜**: 2026-03-19
- **상황**: 유저 "reminder 워크플로우 있지?" → "없음"이라 답변. 실제로 Stage 8 워크플로우 이미 active
- **에러**: 유저 "야이거확인 이미잇음", "정신차려라"
- **수정**: n8n API로 전체 워크플로우 검색 → v1/v2 두 개 발견
- **예방**: "없다"고 답하기 전에 반드시 확인: n8n API 검색, SKILL.md 재확인. 확인 없이 "없음" 단언 금지

### M-044: 서버 연결 거부
- **에이전트**: 파이프라이너
- **날짜**: 2026-03-20
- **상황**: `python tools/dual_test_runner.py --dual` 실행 중
- **에러**: `ConnectionRefusedError: [Errno 111] Connection refused`
- **수정**: 서버 상태 확인: `curl -sk https://orbitools.orbiters.co.kr/healthz`
- **예방**: E2E 테스트 전 서버 healthz 체크 선행

---

## CI 팀장 (크롤러 포함)

### M-045: 브랜드 분류 — 주문 기반이 캡션 무시하고 강제 적용
- **에이전트**: CI 팀장
- **날짜**: 2026-03-19
- **상황**: `enrich_posts_from_orders()`에서 알파벳순 첫 브랜드를 모든 포스트에 강제 적용
- **영향**: 675건 중 72건 오분류 (10.7%)
- **수정**: 캡션/해시태그 브랜드 감지를 우선 적용, 캡션에 없을 때만 주문 폴백
- **예방**: 포스트별 컨텐츠(캡션/해시태그)가 항상 주문 데이터보다 우선

### M-046: Onzenna를 브랜드로 분류 — umbrella storefront ≠ brand
- **에이전트**: CI 팀장
- **날짜**: 2026-03-19
- **상황**: `_BRAND_REGEX`에 "Onzenna"가 브랜드로 등록 → 174건이 "Onzenna"로 잘못 분류
- **수정**: Onzenna 제거. `_PRODUCT_BRAND_REGEX` 2단계 폴백 추가 (straw cup→Grosmimi 등). 174건 재분류
- **예방**: Onzenna = 스토어프론트, NOT a brand. 브랜드 regex 추가 시 실제 제품 브랜드인지 확인

### M-047: PG 행 수 표시 — API limit=1이 total count로 오인
- **에이전트**: CI 팀장
- **날짜**: 2026-03-19
- **상황**: `pg_table_count()`가 `limit=1`로 API 호출 → `count` 필드를 전체 행 수로 표시
- **에러**: content_posts 675행 → 1로 표시
- **수정**: `DataKeeper` 클라이언트로 전체 조회 후 `len()`
- **예방**: API `count` = 반환된 행 수 (not total). 전체 행 수가 필요하면 limit 없이 조회

---

## 앱스터

### M-048: nginx CORS — if + add_header 조합 브레이크
- **에이전트**: 앱스터
- **날짜**: 2026-03-20
- **상황**: nginx config에서 if 블록 안에 add_header → CORS 헤더 간헐적 누락
- **에러**: OPTIONS preflight 204 반환하지만 헤더 없음
- **수정**: `@cors_preflight` named location 사용으로 교체
- **예방**: nginx에서 if + add_header 조합 사용 금지. named location 패턴 사용

### M-049: Django CORS — Base settings에 MIDDLEWARE 추가해야 함
- **에이전트**: 앱스터
- **날짜**: 2026-03-20
- **상황**: production.py에만 CORS 미들웨어 추가 → base settings에서 MIDDLEWARE 상속 충돌
- **수정**: `base.py`의 MIDDLEWARE에 corsheaders 추가 (production.py 아님)
- **예방**: Django settings 상속 구조 확인. 공통 설정은 반드시 base.py에

### M-050: EC2 배포 — onzenna 디렉토리 클린 없이 배포 시 캐시 충돌
- **에이전트**: 앱스터
- **날짜**: 2026-03-20
- **상황**: 재배포 시 __pycache__ 남아있으면 모듈 임포트 충돌
- **에러**: 구버전 .pyc 파일로 인한 ImportError
- **수정**: 배포 전 `find . -name '__pycache__' -exec rm -rf {} +` 실행
- **예방**: deploy_onzenna.py에 클린 스텝 포함

---

## 커뮤니케이터

(아직 기록된 실수 없음 — 발생 시 추가)

---

## KPI 리포트

(아직 기록된 실수 없음 — 발생 시 추가)

---

## 자료 찾기

(아직 기록된 실수 없음 — 발생 시 추가)

---

## Template

새 실수 추가 시 아래 형식 사용:

### M-0XX: 에러 제목
- **에이전트**: 에이전트명
- **날짜**: YYYY-MM-DD
- **상황**: 어떤 상황에서 발생했는지
- **에러**: `실제 에러 메시지`
- **수정**: 어떻게 고쳤는지
- **예방**: 다음에 어떻게 예방할지
