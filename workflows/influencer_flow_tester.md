# Influencer Flow E2E Tester — Workflow SOP

## 역할

n8n 기반 인플루언서 협업 파이프라인 전체를 자율주행 스타일로 E2E 테스트한다.
매 스텝마다 request/response를 flight recorder에 기록하고, HTML 리포트를 생성한다.

> **[2026-03-21] AT 제거 완료**: Airtable은 n8n 워크플로우와 테스트 양쪽에서 모두 제거됨.
> 검증 타겟: PostgreSQL (orbitools API) + Shopify.

---

## 3개 플로우

### Flow 1: Influencer Gifting Application (gifting)
```
POST /webhook/influencer-gifting (브랜드별 payload)
  ↓ wait 12s
verify_postgres  /api/onzenna/gifting/list/?email={test_email}
  → fields: email, ig_handle, brand, draft_order_id
verify_shopify   Shopify Customer exists
verify_shopify   Draft Order exists (draft_order_id from PG)
  → state = open, 100% discount
[cleanup] cancel Draft Order + delete Shopify customer
```

4개 브랜드를 `--brand` 파라미터로 선택 (grosmimi / chamom / naeiae / ht / all).
기본값: `naeiae`.

### Flow 2: Creator Profile (creator)
```
POST /webhook/onzenna-creator-to-airtable (webhook명은 레거시, 실제 n8n 워크플로우는 AT 없이 PG 저장)
  ↓ wait 10s
verify_postgres  /api/onzenna/pipeline/creators/?email={test_email}
  → fields: email, ig_handle, pipeline_status
[cleanup] PG DELETE (405 시 WARN)
```

### Flow 3: Sample Sent — PG 상태 전환 (sample)
```
[setup] POST /api/onzenna/pipeline/creators/ → Accepted 상태 레코드 생성
PUT    /api/onzenna/pipeline/creators/{id}/  → pipeline_status = "Sample Sent"
  ↓ wait 3s
verify_postgres  GET /api/onzenna/pipeline/creators/?email={test_email}
  → pipeline_status == "Sample Sent"
NOTE: n8n 5분 폴러가 이 상태 감지 → Draft Order 완성 (실시간 검증 불가, PG까지만)
[cleanup] DELETE /api/onzenna/pipeline/creators/{id}/ (또는 WARN if 405)
```

---

## 명령어

```bash
# 환경변수 체크 (AIRTABLE_API_KEY 불필요)
python tools/test_influencer_flow.py --status

# 전체 3개 플로우 실행
python tools/test_influencer_flow.py --run

# 특정 플로우만
python tools/test_influencer_flow.py --run --flow gifting
python tools/test_influencer_flow.py --run --flow creator
python tools/test_influencer_flow.py --run --flow sample

# 브랜드 선택 (gifting 플로우)
python tools/test_influencer_flow.py --run --flow gifting --brand grosmimi
python tools/test_influencer_flow.py --run --flow gifting --brand all

# API 호출 없이 미리보기
python tools/test_influencer_flow.py --dry-run

# 데이터 보존 (cleanup 건너뜀)
python tools/test_influencer_flow.py --run --no-cleanup

# 느린 환경용 (대기 시간 1.5배)
python tools/test_influencer_flow.py --run --wait-multiplier 1.5

# 마지막 결과 보기
python tools/test_influencer_flow.py --results
```

---

## 출력 파일

| 파일 | 설명 |
|------|------|
| `.tmp/influencer_flow_log.json` | Flight recorder 원본 (모든 request/response) |
| `.tmp/influencer_flow_report.html` | 시각적 HTML 리포트 (접이식) |

---

## 핵심 개념

### Flight Recorder
매 스텝마다 기록:
- request (method, url, body)
- response (status, body)
- assertions (check, expected, actual, pass/fail)
- captures (변수 캡처 결과)
- duration_ms

### State Passing
스텝 간 `capture` 필드로 값 전달:
- Flow 1: `verify_postgres`에서 `pg_draft_order_id` 캡처 → Shopify Draft Order 조회에 사용
- Flow 3: `setup_creator_pg`에서 `pg_creator_id` 캡처 → PUT/DELETE URL에 사용

### Test Email Safety
- 패턴: `flow_test_{timestamp}_{rand4}@test.orbiters.co.kr`
- Cleanup 시 이 패턴만 삭제 (실제 데이터 보호)

---

## 필요 환경변수

```
N8N_API_KEY
N8N_BASE_URL
SHOPIFY_SHOP
SHOPIFY_ACCESS_TOKEN
ORBITOOLS_URL
ORBITOOLS_USER
ORBITOOLS_PASS
N8N_CREATOR_AIRTABLE_WEBHOOK  (레거시 이름, Flow 2에서 사용)
N8N_INFLUENCER_WEBHOOK        (Flow 1)
```

*`AIRTABLE_API_KEY` 불필요 — AT 완전 제거됨.*

---

## 트러블슈팅

### n8n 비동기 타이밍 이슈
- 증상: webhook POST는 200이지만 PG에 데이터 없음
- 원인: n8n 처리 시간 부족
- 해결: `--wait-multiplier 2.0`으로 대기 시간 늘리기

### Shopify rate limit
- 증상: 429 에러
- 해결: 스텝 간 0.5초 딜레이 자동 적용됨

### PG 필드명 불일치
- 증상: FAIL at verify_postgres, expect_fields 불일치
- 확인: n8n Set node가 orbitools API에 저장하는 필드명 확인

### Flow 3 PUT 404
- 증상: PUT /api/onzenna/pipeline/creators/{id}/ → 404
- 원인: setup_creator_pg 스텝이 FAIL → pg_creator_id 미캡처
- 확인: orbitools API에 POST /api/onzenna/pipeline/creators/ 엔드포인트 존재 여부
