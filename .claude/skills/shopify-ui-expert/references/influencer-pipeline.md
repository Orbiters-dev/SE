# Influencer Collaboration Pipeline (Pathlight) Reference

인플루언서 협업의 전체 수명주기를 n8n 워크플로우 체인으로 자동화하는 파이프라인.

## Status Flow

```
Not Started → Draft Ready → Sent → Replied → Needs Review
→ Accepted → Sample Sent → Sample Shipped → Sample Delivered → Posted
                          → Sample Error
→ Declined
```

## 전체 아키텍처

```
[UI Layer]                    [n8n Orchestration]              [Storage]

인플루언서 폼 제출 ──POST──>  Gifting Webhook ──────────>  Airtable (Needs Review)
  (/pages/influencer-gifting)    │                              │
                                 ├──> Shopify Customer 조회/생성  │
                                 ├──> IG 프로필 스크래핑           │
                                 └──> Slack 알림                  │
                                                                  │
수락 후 샘플 요청 ──POST──>  Gifting2 Webhook ──────────>  Airtable 업데이트
  (/pages/influencer-gifting2)   │                              │
                                 └──> Draft Order 생성 (100%)    │
                                                                  │
관리자 배송 확인 ──Airtable──>  Sample Sent Poll (5min) ──>  Draft Order Complete
  (Status → Sample Sent)         │                              │
                                 └──> Airtable → Sample Shipped  │
                                                                  │
Shopify 배송 완료 ──Poll──>  Delivered Detection (30min) ──>  Airtable → Sample Delivered
  (Fulfillment delivered)                                        │
                                                                  │
Syncly 컨텐츠 감지 ──Poll──>  Posted Detection (6hr) ──────>  Airtable → Posted
  (D+60 Tracker 매칭)
```

## 워크플로우 상세

### Stage 1: Gifting Application (Webhook)

**트리거**: 인플루언서 폼 제출 → n8n webhook POST
**동작**:
1. Shopify 고객 이메일 검색 → 없으면 신규 고객 생성
2. Instagram 프로필 스크래핑 (팔로워 수, 프로필 이미지)
3. Airtable 레코드 생성 (Outreach Status = "Needs Review")
4. Slack 알림 발송

**Payload 예시** (폼 → webhook):
```json
{
  "email": "creator@example.com",
  "firstName": "Jane",
  "lastName": "Doe",
  "instagramHandle": "@janecreator",
  "selectedProducts": ["Product A Variant ID", "Product B Variant ID"],
  "shippingAddress": {
    "address1": "123 Main St",
    "city": "Los Angeles",
    "province": "CA",
    "zip": "90001",
    "country": "US",
    "phone": "3105551234"
  }
}
```

**n8n Workflow IDs**:
- Production: `F0sv8RsCS1v56Gkw`
- WJ TEST: `4q5NCzMb3nMGYqL4`

### Stage 2: Sample Request (Webhook)

**트리거**: 수락된 크리에이터가 Gifting2 폼에서 제품 선택 후 제출
**동작**:
1. Shopify Draft Order 생성 (100% 할인 적용)
2. Airtable 업데이트 (Draft Order ID 기록)
3. 확인 이메일 발송

**n8n Workflow IDs**:
- Production: `KqICsN9F1mPwnAQ9`

### Stage 3: Sample Sent → Complete (Polling, 5분)

**트리거**: Airtable Outreach Status = "Sample Sent" (관리자가 수동으로 변경)
**동작**:
1. Airtable에서 "Sample Sent" 레코드 조회 (maxRecords=10)
2. 레코드의 Draft Order ID로 Shopify Draft Order Complete API 호출
3. 성공 시 Airtable Outreach Status → "Sample Shipped"
4. 실패 시 Outreach Status → "Sample Error"

**중요**: Code 노드에 `fetch()` 사용 불가 — 반드시 HTTP Request 노드로 API 호출

**노드 구성 (fetch-free 패턴)**:
```
Schedule (5min) → HTTP Request (Airtable GET, AT cred)
→ Code (데이터 변환만) → Code (URL 준비)
→ HTTP Request (Shopify PUT, Shopify cred)
→ Code (결과 판단) → HTTP Request (Airtable PATCH, AT cred)
```

**n8n Workflow IDs**:
- Production: `m89xU9RUbPgnkBy8`
- WJ TEST: `Vd5NiKMwdLT7b9wa`

### Stage 4: Shipped → Delivered Detection (Polling, 30분)

**트리거**: Airtable Outreach Status = "Sample Shipped"
**동작**:
1. Airtable에서 "Sample Shipped" 레코드 + Draft Order ID 조회
2. Shopify Draft Order API → order_id 추출
3. Shopify Order Fulfillment API → delivery_status 확인
4. `delivered` 감지 시 Airtable → "Sample Delivered"

**n8n Workflow IDs**:
- WJ TEST: `2vsXyHtjo79hnFoD`

### Stage 5: Delivered → Posted Detection (Polling, 6시간)

**트리거**: Airtable Outreach Status = "Sample Delivered"
**동작**:
1. Airtable에서 "Sample Delivered" 레코드 + IG 핸들 조회
2. Syncly D+60 Tracker Google Sheet에서 핸들로 검색
3. 포스트 감지 시 Airtable → "Posted"

**n8n Workflow IDs**:
- WJ TEST: `82t55jurzbY3iUM4`

## n8n 크레덴셜

| ID | 이름 | 타입 | 용도 |
|----|------|------|------|
| `rIJuzuN1C5ieE7dr` | Shopify Admin API (Gifting) | httpHeaderAuth | mytoddie.myshopify.com Draft Order 관리 |
| `59gWUPbiysH2lxd8` | Airtable PAT (WJ Test) | httpHeaderAuth | Airtable HTTP Request 인증 (WJ TEST 환경) |

## Airtable 구조

### Outreach Status 필드 옵션
```
Not Started, Draft Ready, Sent, Replied, Needs Review,
Accepted, Declined, Sample Sent, Sample Shipped, Sample Error,
Sample Delivered, Posted
```

### 주요 필드
| 필드 | 타입 | 용도 |
|------|------|------|
| Email | email | 인플루언서 이메일 |
| Username | text | IG 핸들 |
| Name | text | 이름 |
| Outreach Status | single select | 파이프라인 상태 |
| Draft Order ID | text | Shopify Draft Order ID |
| Last Contact At | date | 마지막 상태 변경일 |

### 베이스/테이블 ID

| 환경 | Base ID | Table ID |
|------|---------|----------|
| Production (William) | `appNPVxj4gUJl9v15` | `tblv2Jw3ZAtAMhiYY` |
| WJ TEST | `appT2gLRR0PqMFgII` | `tbl7zJ1MscP852p9N` |
| Inbound (공통) | `appT2gLRR0PqMFgII` | `tbloYjIEr5OtEppT0` |

## 두 개의 Shopify 스토어

| 속성 | mytoddie.myshopify.com | toddie-4080.myshopify.com |
|------|----------------------|--------------------------|
| 접근 방법 | n8n 크레덴셜 (ID: `rIJuzuN1C5ieE7dr`) | `.wat_secrets` SHOPIFY_ACCESS_TOKEN |
| 스코프 | draft_orders, orders 등 (전체) | read_products, write_products 등 (제한적) |
| 용도 | Draft Order 생성/완료, 주문 관리 | 제품 정보 조회, 페이지 배포 |

## n8n Code 노드 제약사항

**`fetch()` 사용 불가** — n8n의 sandboxed Code 노드 환경에는 `fetch`, `axios`, `node-fetch` 없음.

### 올바른 패턴 (HTTP Request 노드 사용):
```
Code 노드 (URL/body 준비) → HTTP Request 노드 (실제 API 호출) → Code 노드 (응답 처리)
```

### 잘못된 패턴 (실행 시 에러):
```javascript
// ERROR: "fetch is not defined [line 6] ReferenceError"
const resp = await fetch('https://api.airtable.com/v0/...', {
  headers: { 'Authorization': 'Bearer ...' }
});
```

### Code 노드에서 할 수 있는 것:
- 데이터 변환/매핑
- 조건 분기 (`return []`으로 흐름 중단 가능)
- URL/payload 문자열 조립
- `$input`, `$('Node Name')` 으로 이전 노드 데이터 참조

## E2E 테스트

`tools/test_influencer_flow.py` — 3개 플로우를 순차 실행하는 자율주행 테스터.

### CLI
```bash
python tools/test_influencer_flow.py --status         # 환경변수 체크
python tools/test_influencer_flow.py --dry-run         # API 호출 없이 미리보기
python tools/test_influencer_flow.py --run             # 전체 3개 플로우
python tools/test_influencer_flow.py --run --flow gifting  # 특정 플로우만
python tools/test_influencer_flow.py --run --no-cleanup    # 데이터 보존
python tools/test_influencer_flow.py --results         # 마지막 결과 보기
```

### Flight Recorder
매 스텝마다 request/response 전체 기록:
```json
{
  "step_id": "verify_airtable",
  "duration_ms": 892,
  "request": { "url": "...", "body": "..." },
  "response": { "status": 200, "body": {} },
  "captures": { "airtable_record_id": "recABC123" },
  "assertions": [{ "field": "Status", "expected": "New", "actual": "New", "pass": true }],
  "status": "PASS"
}
```

### 테스트 이메일 패턴
`flow_test_{timestamp}_{rand4}@test.orbiters.co.kr`

Cleanup 시 반드시 `@test.orbiters.co.kr` 패턴 매칭 확인 후 삭제.

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| webhook POST 시 500 에러 | n8n webhook 시스템 장애 | n8n 서버 재시작 (SSH) |
| "fetch is not defined" | Code 노드에서 API 호출 시도 | HTTP Request 노드로 리팩토링 |
| Draft Order Complete 실패 | .wat_secrets 토큰에 draft_orders scope 없음 | n8n Shopify 크레덴셜 사용 (ID: `rIJuzuN1C5ieE7dr`) |
| Airtable 422 에러 | select 필드에 존재하지 않는 옵션 | `typecast: true`로 임시 레코드 생성 → 옵션 추가 → 삭제 |
| Sample Sent 워크플로우 무동작 | Draft Order ID 필드가 비어있음 | Airtable 레코드에 Draft Order ID 먼저 기입 |
| Delivered Detection 미동작 | WJ TEST에만 구현됨 | Production 워크플로우는 미생성 상태 |
| Posted Detection 미동작 | Syncly D+60 시트에 데이터 없음 | Syncly 크롤링 정상 동작 확인 필요 |
