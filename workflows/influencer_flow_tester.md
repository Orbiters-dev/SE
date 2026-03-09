# Influencer Flow E2E Tester — Workflow SOP

## 역할

n8n 기반 인플루언서 협업 파이프라인 전체를 자율주행 스타일로 E2E 테스트한다.
매 스텝마다 request/response를 flight recorder에 기록하고, HTML 리포트를 생성한다.

---

## 3개 플로우

### Flow 1: Influencer Gifting Application (gifting)
```
POST n8n webhook → wait 8s → Airtable 확인 → Shopify 고객 → 메타필드 → PostgreSQL
```

### Flow 2: Creator Profile Signup (creator)
```
POST n8n webhook → wait 10s → Airtable 확인 → Shopify 메타필드(onzenna_creator) → PostgreSQL
```

### Flow 3: Sample Request (sample)
```
POST n8n webhook → wait 10s → Shopify 고객 → Draft Order(100% 할인) → Airtable 업데이트
```

---

## 명령어

```bash
# 환경변수 체크
python tools/test_influencer_flow.py --status

# 전체 3개 플로우 실행
python tools/test_influencer_flow.py --run

# 특정 플로우만
python tools/test_influencer_flow.py --run --flow gifting
python tools/test_influencer_flow.py --run --flow creator
python tools/test_influencer_flow.py --run --flow sample

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
- Step 3에서 `airtable_record_id` 캡처 → Step 5 cleanup에서 사용
- Step 4에서 `shopify_customer_id` 캡처 → Step 5 metafield 조회에서 사용

### Test Email Safety
- 패턴: `flow_test_{timestamp}_{rand4}@test.orbiters.co.kr`
- Cleanup 시 이 패턴만 삭제 (실제 데이터 보호)
- PostgreSQL은 DELETE 엔드포인트 미존재 → 수동 정리 필요

---

## 필요 환경변수

```
N8N_INFLUENCER_WEBHOOK
N8N_CREATOR_AIRTABLE_WEBHOOK
N8N_GIFTING2_WEBHOOK
AIRTABLE_API_KEY
AIRTABLE_INBOUND_BASE_ID (appT2gLRR0PqMFgII)
AIRTABLE_INBOUND_TABLE_ID (tbloYjIEr5OtEppT0)
SHOPIFY_SHOP
SHOPIFY_ACCESS_TOKEN
ORBITOOLS_URL
ORBITOOLS_USER
ORBITOOLS_PASS
```

---

## 트러블슈팅

### n8n 비동기 타이밍 이슈
- 증상: webhook POST는 200이지만 Airtable/Shopify에 데이터 없음
- 원인: n8n 처리 시간 부족
- 해결: `--wait-multiplier 2.0`으로 대기 시간 늘리기

### Shopify rate limit
- 증상: 429 에러
- 해결: 스텝 간 0.5초 딜레이 자동 적용됨

### Airtable 필드명 불일치
- 증상: FAIL at verify_airtable, expect_fields 불일치
- 확인: n8n Set node의 필드명이 Airtable 실제 필드명과 일치하는지 체크
