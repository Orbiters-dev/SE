# Mistakes Memory — ORBI WAT Framework

에이전트별 실수 기록. PreToolUse/PostToolUse hook이 자동으로 읽고 씁니다.

---

## Core (모든 에이전트 공통)

### M-001: cp949 인코딩 에러
- **에이전트**: Core (모든 에이전트 공통)
- **날짜**: 2026-03-20
- **상황**: Python 스크립트에서 한글 출력 시 발생
- **에러**: `UnicodeEncodeError: 'charmap' codec can't encode character`
- **수정**: 스크립트 상단에 `import sys; sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 추가
- **예방**: 새 .py 파일 작성 시 항상 첫 줄에 reconfigure 추가

### M-002: 따옴표 중첩 에러 (python -c)
- **에이전트**: Core (모든 에이전트 공통)
- **날짜**: 2026-03-20
- **상황**: Bash에서 `python -c "..."` 안에 따옴표 포함 코드 실행 시 발생
- **에러**: `unexpected EOF while looking for matching`
- **수정**: `.tmp/script.py` 파일로 저장 후 `python .tmp/script.py` 로 실행
- **예방**: python -c 는 한 줄 이상이거나 따옴표 포함 시 절대 사용 금지

### M-003: curl SSL revocation 실패
- **에이전트**: Core (모든 에이전트 공통)
- **날짜**: 2026-03-20
- **상황**: Windows에서 curl로 HTTPS 요청 시 SSL revocation check 실패
- **에러**: `SSL: certificate subject name does not match` 또는 `schannel: next InitializeSecurityContext`
- **수정**: curl 명령에 `-sk` 플래그 추가
- **예방**: Windows curl 명령은 항상 `-sk` 포함

### M-012: 스크립트 경로 하드코딩 — 멀티 컴터 브레이크
- **에이전트**: Core (모든 에이전트 공통)
- **날짜**: 2026-03-21
- **상황**: mistake_recorder.py, mistake_checker.py, _check_rag.py 등에 `C:\Users\wjcho\Desktop\WJ Test1` 절대경로 박혀있음. 랩탑에서 실행 시 FileNotFoundError
- **에러**: `FileNotFoundError: C:\Users\wjcho\Desktop\WJ Test1\.tmp\...`
- **수정**: `os.path.dirname(os.path.abspath(__file__))` 기준 상대경로로 변경
- **예방**: 절대경로 하드코딩 금지. 항상 `__file__` 또는 env var 기준으로 경로 설정

### M-013: 공유 파일을 ~/.claude/ 에 저장 — 멀티 컴터 미공유
- **에이전트**: Core (모든 에이전트 공통)
- **날짜**: 2026-03-21
- **상황**: mistakes.md를 `~/.claude/projects/.../memory/` 에 저장했더니 SynologyDrive로 싱크 안 됨. 데스크탑/랩탑 각각 따로 존재
- **에러**: 데이터 분리 — 각 컴터에서 쌓인 오답노트가 공유 안 됨
- **수정**: 공유 파일은 프로젝트 폴더(SynologyDrive) 안 `memory/` 에 저장. `~/.claude/` 는 로컬 전용
- **예방**: 팀/멀티컴터 공유 필요한 파일은 반드시 SynologyDrive 프로젝트 내부에 저장

### M-014: hooks 미등록 — 오답노트 시스템 무용지물
- **에이전트**: Core (모든 에이전트 공통)
- **날짜**: 2026-03-21
- **상황**: mistake_checker.py(PreToolUse), mistake_recorder.py(PostToolUse) 스크립트가 있었지만 `.claude/settings.json` hooks에 등록 안 됨. 에러 나도 아무것도 안 기록됨
- **에러**: hooks 섹션에 error_logger.py만 있고 나머지 없음
- **수정**: settings.json PreToolUse + PostToolUse에 각각 추가
- **예방**: 새 hook 스크립트 만들면 반드시 settings.json에 즉시 등록. 등록 여부 테스트까지 확인

---

## Google API

### M-004: Google Sheets range 포맷 에러
- **에이전트**: Google API
- **날짜**: 2026-03-20
- **상황**: Sheets API range에 공백 포함 탭 이름 사용 시 발생
- **에러**: `Unable to parse range: Tab Name!A1:Z50`
- **수정**: 탭 이름을 작은따옴표로 감싸기 `"'Tab Name'!A1:Z50"` 형식
- **예방**: 탭 이름에 공백/특수문자 있으면 무조건 작은따옴표 감싸기

### M-005: 임베딩 모델 404 에러
- **에이전트**: Google API
- **날짜**: 2026-03-20
- **상황**: 구버전 임베딩 모델명 사용 시 발생
- **에러**: `text-embedding-004: 404 not found`
- **수정**: 모델명을 `gemini-embedding-001` 로 변경
- **예방**: text-embedding-004 사용 금지 → gemini-embedding-001 사용

### M-006: google.generativeai deprecated
- **에이전트**: Google API
- **날짜**: 2026-03-20
- **상황**: 구버전 genai SDK import 사용 시 발생
- **에러**: `ImportError: cannot import name 'generativeai' from 'google'`
- **수정**: `import google.generativeai` → `from google import genai` 로 변경
- **예방**: google.generativeai import는 모두 from google import genai 로 교체

---

## n8n 매니저

### M-009: n8n POST active 필드 에러
- **에이전트**: n8n 매니저
- **날짜**: 2026-03-20
- **상황**: n8n 워크플로우 POST 시 active 필드 포함하면 read-only 에러
- **에러**: `"active" is read-only and cannot be set`
- **수정**: POST body에서 `active` 필드 제거
- **예방**: n8n POST/PUT 시 active 필드는 절대 포함 금지

### M-010: n8n JSON cp949 인코딩
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
- **대체**: PROD 폴더 워크플로우 직접 사용. WJ TEST 환경은 `toddie-4080.myshopify.com` + AT base `appT2gLRR0PqMFgII`
- **주의**: clone_n8n_to_test.py 등 WJ인플 TEST 타깃 스크립트 실행 금지. PROD 워크플로우만 수정할 것

---

## 아마존 퍼포마

### M-015: Amazon Ads API — search term report date 컬럼 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: timeUnit=SUMMARY로 search term report 요청 시 date 컬럼 포함하면 에러
- **에러**: `date column not available with timeUnit=SUMMARY`
- **수정**: columns 목록에서 `"date"` 제거
- **예방**: SUMMARY 리포트는 date 컬럼 사용 불가. 날짜 범위는 요청 파라미터로만 지정

### M-016: Amazon Ads API — keyword report groupBy 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: keyword report 요청 시 groupBy에 "keyword" 또는 "keywordId" 넣으면 에러
- **에러**: `Invalid groupBy value`
- **수정**: `groupBy: ["adGroup"]` 으로 변경. keywordBid 컬럼도 제거 (reporting metric 아님)
- **예방**: keyword report groupBy는 반드시 `["adGroup"]`

### M-017: Amazon Ads API — campaignId/adGroupId int 전송 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: API 실행 시 campaignId/adGroupId를 int로 전송하면 400 에러
- **에러**: `"NUMBER_VALUE can not be converted to a String"`
- **수정**: `str(campaign_id)` 로 변환 후 전송
- **예방**: Amazon Ads API ID 필드는 항상 string 타입으로 변환 후 전송

### M-018: Amazon Ads API — targets PUT wrapper 누락
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: ASIN target 입찰가 수정 시 body에 targetingClauses wrapper 없으면 에러
- **에러**: `Invalid request body`
- **수정**: `{"targetingClauses": [{...}]}` 형태로 감싸기
- **예방**: SP targets PUT은 반드시 targetingClauses 배열 wrapper 필요

### M-019: Amazon Ads API — targets list state filter 대소문자
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: targets list 요청 시 state filter 소문자로 보내면 필터 무시됨
- **에러**: 빈 결과 또는 모든 상태 반환
- **수정**: `"ENABLED"` (대문자) 로 변경
- **예방**: Amazon Ads API state filter는 항상 대문자 (ENABLED, PAUSED, ARCHIVED)

### M-020: Amazon SP-API — Grosmimi 전용 LWA 앱 혼용 오류
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-08
- **상황**: Grosmimi refresh token이 자체 LWA 앱(`6525b887...`)으로 발급됐으나 shared client로 교환 시도
- **에러**: `ACI prefix 'amzn1.swa.' did not match` 또는 400 Bad Request
- **수정**: Grosmimi는 shared client(`03dbca9c...`) + Grosmimi 원래 refresh token 조합 사용
- **예방**: SP-API refresh token은 발급한 LWA 앱과 client_id가 반드시 매칭되어야 함

---

## 파이프라이너

### M-011: 서버 연결 거부
- **에이전트**: 파이프라이너
- **날짜**: 2026-03-20
- **상황**: `python tools/dual_test_runner.py --dual` 실행 중
- **에러**: `ConnectionRefusedError: [Errno 111] Connection refused`
- **수정**: 서버 상태 확인: `curl -sk https://orbitools.orbiters.co.kr/healthz`
- **예방**: E2E 테스트 전 서버 healthz 체크 선행

---

## 앱스터

### M-021: nginx CORS — if + add_header 조합 브레이크
- **에이전트**: 앱스터
- **날짜**: 2026-03-20
- **상황**: nginx config에서 if 블록 안에 add_header 쓰면 CORS 헤더가 간헐적으로 누락
- **에러**: OPTIONS preflight 204 반환하지만 헤더 없음
- **수정**: `@cors_preflight` named location 사용으로 교체
- **예방**: nginx에서 if + add_header 조합 사용 금지. named location 패턴 사용

### M-022: Django CORS — Base settings에 MIDDLEWARE 추가해야 함
- **에이전트**: 앱스터
- **날짜**: 2026-03-20
- **상황**: production.py에만 CORS 미들웨어 추가했더니 base settings에서 MIDDLEWARE 상속받아 충돌
- **에러**: `CORS headers not set` 또는 middleware 순서 충돌
- **수정**: `base.py`의 MIDDLEWARE에 corsheaders 추가 (production.py 아님)
- **예방**: Django settings 상속 구조 확인. 공통 설정은 반드시 base.py에

### M-023: EC2 배포 — onzenna 디렉토리 클린 없이 배포 시 캐시 충돌
- **에이전트**: 앱스터
- **날짜**: 2026-03-20
- **상황**: 재배포 시 __pycache__ 남아있으면 모듈 임포트 충돌
- **에러**: 구버전 .pyc 파일로 인한 ImportError 또는 예상치 못한 동작
- **수정**: 배포 전 `find . -name '__pycache__' -exec rm -rf {} +` 실행
- **예방**: deploy_onzenna.py에 클린 스텝 포함

---

## 이메일 지니

### M-024: Gmail RAG — 인덱스 미동기화 (2일 이상 경과)
- **에이전트**: 이메일 지니
- **날짜**: 2026-03-21
- **상황**: 마지막 동기화 2026-03-18 이후 신규 이메일 인덱싱 안 됨
- **에러**: 최근 이메일 RAG 검색 시 누락
- **수정**: `python tools/gmail_rag.py --sync` 실행
- **예방**: GitHub Actions 또는 Task Scheduler로 매일 자동 동기화 설정 필요

---

## CI 팀장 (크롤러 포함)

(아직 추가 기록 없음)

---

## 커뮤니케이터

(아직 추가 기록 없음)

---

## 골만이

(아직 추가 기록 없음)

---

## Template

새 실수 추가 시 아래 형식 사용:

### M-025: PPC 대시보드 — GitHub Pages 정적 파일 캐시로 인한 데이터 미갱신 착각
- **에이전트**: 아마존퍼포마
- **날짜**: 2026-03-22
- **상황**: KST 08:00에 대시보드 확인했는데 07:30 Pipeline 결과가 안 보임. Pipeline + Dashboard Action 둘 다 success였음
- **에러**: 브라우저 캐시로 인해 이전 data.js가 표시됨. 실제로는 정상 업데이트 완료 상태
- **수정**: Ctrl+Shift+R (하드 리프레시)로 해결
- **예방**: GitHub Pages는 정적 파일 → 브라우저 캐시 이슈 불가피. PG+웹서버(orbitools) 기반으로 전환하면 항상 최신 데이터 제공 가능. 단기: data.js에 `?v=timestamp` 캐시 버스터 추가 검토. 장기: orbitools Django에 PPC dashboard API endpoint 추가하여 실시간 데이터 제공

### M-026: Anthropic API 키 비활성화 시 n8n 하드코딩 키 미교체
- **에이전트**: Core (모든 에이전트 공통)
- **날짜**: 2026-03-22
- **상황**: Anthropic Console에서 `rogh` + `WJ_CLAUDE_NEW` 키 비활성화 시도. n8n 워크플로우 5개에 API 키가 credential이 아닌 httpRequest 헤더/코드에 직접 하드코딩되어 있었음. credential(`Orbiters Anthropic`) 교체만으로는 이 워크플로우들이 깨짐
- **에러**: `Couldn't connect with these settings` (n8n credential) + DM Auto Reply 워크플로우 Claude API 호출 실패
- **수정**: n8n API로 88개 전체 워크플로우 스캔 → 삭제된 키(`NiyjTsV...WITwAA`) 사용처 3개 + code 노드 1개 발견 → `WJ_CLAUDE_NEW`로 전수 교체
- **예방**: (1) API 키 비활성화 전 반드시 n8n 전체 워크플로우 스캔 실행 (2) httpRequest 노드에 키 하드코딩 금지 → credential 참조로 통일 (3) 키 교체 체크리스트: GitHub Secrets + n8n credentials + n8n httpRequest headers + n8n code nodes

### M-027: Amazon Ads API — add_keyword HTTP 200이지만 개별 keyword 거부 (팬텀 실행)
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-22
- **상황**: 떡뻥(한국어) 키워드를 US 마켓에 harvest 실행. API HTTP 200 반환. exec_log에 "OK" 기록. 하지만 실제 Amazon에 키워드 미등록
- **에러**: API는 HTTP 200 반환하지만 response body 내 개별 keyword `code` 필드가 `SUCCESS`가 아님 (자동 거부). `add_keyword()`가 `resp.raise_for_status()`만 체크하고 body 미검증
- **수정**: `add_keyword()`, `add_negative_keyword()`에 응답 body의 개별 keyword `code` 필드 검증 추가. `SUCCESS` 아니면 RuntimeError raise
- **예방**: Amazon Ads API bulk 요청은 HTTP status와 개별 item status가 별개. 항상 response body의 각 item `code` 필드를 검증할 것

### M-028: PPC executor — GitHub Actions에서 harvest dedup 무효화 (반복 제안)
- **에이전트**: 아마존 퍼포마
- **날짜**: 2026-03-22
- **상황**: 떡뻥 키워드가 execute됐는데도 매일 다시 proposal에 등장. exec_log에 5건이나 "OK" 기록
- **에러**: `_load_executed_history()`가 `.tmp/ppc_proposal_*.json`만 스캔. GitHub Actions는 매번 fresh checkout → `.tmp/` 비어있음 → dedup 히스토리 0 → 이미 실행된 키워드 재제안
- **수정**: `exec_log.json` (git에 커밋된 persistent log)도 dedup 소스로 추가
- **예방**: Actions에서 돌아가는 로직은 로컬 파일(.tmp/) 의존 금지. git-committed 파일 또는 API/DB에서 히스토리 로드

### M-XXX: 에러 제목
- **에이전트**: 에이전트명
- **날짜**: YYYY-MM-DD
- **상황**: 어떤 상황에서 발생했는지
- **에러**: `실제 에러 메시지`
- **수정**: 어떻게 고쳤는지
- **예방**: 다음에 어떻게 예방할지
