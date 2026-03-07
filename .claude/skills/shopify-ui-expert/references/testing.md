# E2E Testing Reference

`tools/shopify_tester.py`를 사용한 전체 데이터 체인 E2E 테스트 방법론.

## 테스트 도구

| 명령 | 설명 |
|------|------|
| `python tools/shopify_tester.py --status` | 큐 상태 확인 |
| `python tools/shopify_tester.py --push --spec '{...}'` | 테스트 스펙 추가 |
| `python tools/shopify_tester.py --run` | pending 테스트 실행 |
| `python tools/shopify_tester.py --results` | 결과 조회 |

결과 파일: `.tmp/test_results.json`
테스트 큐: `.tmp/test_queue.json`
Python 경로: `/c/Users/user/AppData/Local/Programs/Python/Python314/python.exe`

## 테스트 스펙 구조

```json
{
  "name": "테스트 이름",
  "description": "테스트 설명",
  "steps": [
    {
      "type": "http_post",
      "url": "https://n8n.orbiters.co.kr/webhook/onzenna-core-signup",
      "body": {
        "form_type": "core_signup",
        "email": "tester_20260307_1@test.com",
        "journey_stage": "new_mom_0_12m",
        "baby_birth_month": "2025-08"
      },
      "expect_status": 200
    },
    {
      "type": "wait",
      "seconds": 3
    },
    {
      "type": "verify_postgres",
      "query": "SELECT * FROM customers WHERE email = 'tester_20260307_1@test.com'",
      "expect": { "min_rows": 1 }
    },
    {
      "type": "verify_airtable",
      "base_id": "appXXX",
      "table_id": "tblXXX",
      "filter": "{email} = 'tester_20260307_1@test.com'",
      "expect": { "min_records": 1 }
    },
    {
      "type": "verify_shopify",
      "endpoint": "/customers/search.json?query=email:tester_20260307_1@test.com",
      "expect_metafield": {
        "namespace": "onzenna_survey",
        "key": "journey_stage",
        "value": "new_mom_0_12m"
      }
    }
  ]
}
```

## Step Types 상세

### http_post
폼 제출을 시뮬레이션. n8n webhook에 JSON POST.

```json
{
  "type": "http_post",
  "url": "https://n8n.orbiters.co.kr/webhook/...",
  "body": { /* 폼 데이터 */ },
  "headers": { "Content-Type": "application/json" },
  "expect_status": 200
}
```

### http_get
페이지 렌더링 또는 API 응답 확인.

```json
{
  "type": "http_get",
  "url": "https://mytoddie.myshopify.com/pages/core-signup",
  "expect_status": 200,
  "expect_contains": "Tell Us About You"
}
```

### verify_postgres
PostgreSQL 쿼리 실행 후 결과 검증.

```json
{
  "type": "verify_postgres",
  "query": "SELECT journey_stage FROM customers WHERE email = $1",
  "params": ["tester@test.com"],
  "expect": {
    "min_rows": 1,
    "column_values": { "journey_stage": "pregnant" }
  }
}
```

### verify_airtable
Airtable 레코드 필터 검색 후 존재 확인.

```json
{
  "type": "verify_airtable",
  "base_id": "appXXX",
  "table_id": "tblXXX",
  "filter": "{email} = 'tester@test.com'",
  "expect": { "min_records": 1 }
}
```

### verify_shopify
Shopify Admin API 호출 후 메타필드 등 검증.

```json
{
  "type": "verify_shopify",
  "endpoint": "/customers/search.json?query=email:tester@test.com",
  "expect_metafield": {
    "namespace": "onzenna_survey",
    "key": "journey_stage",
    "value": "new_mom_0_12m"
  }
}
```

### wait
비동기 처리 대기. n8n 워크플로우 완료까지 보통 2~5초.

```json
{
  "type": "wait",
  "seconds": 3
}
```

## FAIL 분석 프레임워크

테스트 실패 시 데이터 체인의 어느 레이어에서 깨졌는지 순차적으로 확인:

```
1. 폼 제출 (http_post)     → FAIL: webhook URL 오류, payload 형식 오류
2. n8n 수신                → FAIL: n8n 워크플로우 비활성, webhook URL 변경됨
3. n8n 처리                → FAIL: 워크플로우 노드 에러, 데이터 변환 실패
4. PostgreSQL 저장          → FAIL: DB 연결 실패, 스키마 불일치, UPSERT 충돌
5. Airtable 동기화          → FAIL: API key 만료, 필드명 불일치
6. Shopify 메타필드 동기화   → FAIL: Admin API 토큰 만료, 메타필드 정의 누락
```

각 단계별로 verify step을 넣어서 정확히 어디서 실패했는지 파악한다.

## 테스트 이메일 관리

테스트용 이메일 형식: `tester_{YYYYMMDD}_{n}@test.com`

예: `tester_20260307_1@test.com`, `tester_20260307_2@test.com`

테스트 후 클린업:
- PostgreSQL: `DELETE FROM customers WHERE email LIKE 'tester_%@test.com'`
- Airtable: 필터로 테스트 레코드 삭제
- Shopify: Admin API로 테스트 고객 삭제 (선택)

## E2E 테스트 시나리오 템플릿

### 1. 코어 사인업 전체 플로우
```
http_post (core-signup webhook) → wait 3s
→ verify_postgres (customers 테이블)
→ verify_airtable (고객 레코드)
→ verify_shopify (customer metafield)
```

### 2. 크리에이터 폼 플로우
```
http_post (creator-survey webhook) → wait 3s
→ verify_postgres (creator_submissions)
→ verify_airtable (creators 테이블)
```

### 3. 인플루언서 기프팅 플로우
```
http_post (influencer-gifting webhook) → wait 5s
→ verify_shopify (draft order 생성)
→ verify_airtable (influencer 레코드)
```

### 4. 페이지 렌더링 확인
```
http_get (/pages/core-signup) → expect_status 200, expect_contains "Tell Us About You"
http_get (/pages/loyalty-survey) → expect_status 200
http_get (/pages/influencer-gifting) → expect_status 200
```

## 테스트 작성 원칙

1. **항상 전체 체인을 검증한다** — 폼 제출만 확인하면 데이터가 실제로 저장되었는지 알 수 없다
2. **각 단계마다 verify를 넣는다** — 실패 지점을 정확히 식별하기 위해
3. **적절한 wait를 넣는다** — n8n 비동기 처리 시간 고려 (보통 2~5초)
4. **테스트 데이터는 식별 가능하게** — `tester_` 접두사로 클린업 용이하게
5. **반복 실행 가능하게** — 이전 테스트 데이터가 있어도 UPSERT로 처리되도록
