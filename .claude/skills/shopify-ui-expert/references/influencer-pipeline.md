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
컨텐츠 감지 ──Poll──>  Posted Detection (6hr) ──────>  Airtable → Posted
  (OrbiTools content_posts)
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
- WJ TEST: `734aqkcOIfiylExL` (2026-03-13 PROD에서 복제)

### Stage 2.5: Fulfillment → Airtable + Guidelines Email

**트리거**: Shopify fulfillment 이벤트 (WJ TEST: webhook, PROD: schedule 30분)
**동작**:
1. Fulfillment 데이터에서 Draft Order ID 추출
2. Creator 이메일로 Airtable 검색 → 크리에이터 주문 여부 확인
3. Airtable Order 레코드 생성 + Creator 업데이트
4. 제품 가이드라인 파일 조회 → 이메일 발송 (첨부 또는 텍스트)
5. Config 시트에서 활성화 여부 확인 (Dashboard/Config 패턴)

**PROD에서 가져온 추가 노드** (2026-03-13):
- `Check Draft Status`, `Get Draft Order`, `Has Order?` — Draft Order 검증
- `Fetch Product Guidelines`, `Poll Sample Shipped` — 가이드라인/발송 폴링
- `Fetch Dashboard (SF)`, `Fetch Today Config (SF)`, `Wait for Config (SF)` — Config 패턴
- `Stop: No Email (SF)`, `Not a Creator Order` — 에러 핸들링

**n8n Workflow IDs**:
- Production: `ufMPgU6cjwuzLM0y` (34 nodes)
- WJ TEST: `UP1OnpNEFN54AOUn` (37 nodes, 머지 완료)

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
2. OrbiTools API (`content_posts` 테이블)에서 username으로 검색
3. 포스트 감지 시 Airtable → "Posted" + OrbiTools PG 업데이트

**데이터 소스 변경 (2026-03-18)**: Syncly D+60 Tracker Sheet → OrbiTools content_posts (PostgreSQL)
- 기존: Google Sheets API (인증 미설정으로 실질 미작동)
- 변경: OrbiTools `GET /api/datakeeper/query/?table=content_posts&username=XXX`
- 인증: OrbiTools Basic Auth (n8n credential ID: `THAQRJczCr1cJN2E`)

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

## Django Gifting API (PostgreSQL 저장)

n8n Gifting 워크플로우에서 Airtable과 **병렬로** PostgreSQL에도 저장하는 파이프라인.

### 엔드포인트
| Method | URL | 용도 |
|--------|-----|------|
| POST | `http://orbitools.orbiters.co.kr/api/onzenna/gifting/save/` | 기프팅 신청 저장 (upsert by email+draft_order) |
| POST | `http://orbitools.orbiters.co.kr/api/onzenna/gifting/update/` | 필드 업데이트 (id 또는 email) |
| GET | `http://orbitools.orbiters.co.kr/api/onzenna/gifting/list/` | 목록 조회 (?email=, ?status=, ?limit=) |

### n8n에서 PG 저장 노드 추가 패턴
```
기존 워크플로우 → [Code: Prepare PG Payload] → [HTTP Request: Save to PostgreSQL]
```

**Prepare PG Payload** (Code 노드):
```javascript
// optional chaining (?.) 사용 금지 — n8n Code 노드 호환성
var formData = $('Webhook').first().json.body || $('Webhook').first().json;
var personal = formData.personal_info || {};
var baby = formData.baby_info || {};
var addr = formData.shipping_address || {};
return [{json: {
  email: formData.email,
  full_name: personal.full_name || formData.firstName + ' ' + formData.lastName,
  // ... 필드 매핑
}}];
```

**Save to PostgreSQL** (HTTP Request 노드):
- Method: POST
- URL: `http://orbitools.orbiters.co.kr/api/onzenna/gifting/save/`
- Body: `{{ $json }}` (JSON)
- 인증 없음 (내부 VPC)

### 현재 상태
- Django 모델/뷰/URL: EC2에 배포 완료, curl 201 확인됨
- n8n PG 노드: 테스트 중 제거됨 → n8n webhook 복구 후 재추가 필요

## 트러블슈팅

### n8n 서버 장애 패턴

| 증상 | 원인 | 해결 |
|------|------|------|
| **webhook POST → 200 + 빈 body** | JS Task Runner "Offer expired" — task offer를 시간 내 수락 못함 | `docker compose down && docker compose up -d` 클린 재시작 |
| **webhook POST → HTTP 000** | Caddy `ERR_ERL_UNEXPECTED_X_FORWARDED_FOR` — trust proxy 미설정 | `.env`에 `N8N_PROXY_HOPS=1` 추가 후 재시작 |
| **docker logs 에러 flood** | Task Runner가 크래시/오버로드 | 클린 재시작. 재발 시 n8n 버전 고정 (`n8nio/n8n:1.76.1` 등) |
| **EC2에서 curl HTTP 000** | EC2 → 자기 도메인 루프백 불가 | `curl -sk https://127.0.0.1/ -H "Host: n8n.orbiters.co.kr"` 또는 외부 PC에서 테스트 |

### n8n 서버 진단 순서
```bash
# 1. 컨테이너 상태 확인
docker ps

# 2. n8n 로그 확인 (크래시, 에러 패턴)
docker logs n8n-n8n-1 --tail 50

# 3. Caddy 로그 확인 (프록시 에러)
docker logs n8n-caddy-1 --tail 20

# 4. .env 확인 (잘못된 환경변수)
cat /home/ubuntu/n8n/.env

# 5. 클린 재시작
cd /home/ubuntu/n8n && docker compose down && docker compose up -d

# 6. webhook 테스트 (외부에서)
curl -s -w "\nHTTP %{http_code}" -X POST https://n8n.orbiters.co.kr/webhook/influencer-gifting \
  -H "Content-Type: application/json" -d '{"email":"test@test.com"}'
```

### 기존 이슈

| 증상 | 원인 | 해결 |
|------|------|------|
| webhook POST 시 500 에러 | n8n webhook 시스템 장애 | n8n 서버 재시작 (SSH) |
| "fetch is not defined" | Code 노드에서 API 호출 시도 | HTTP Request 노드로 리팩토링 |
| Draft Order Complete 실패 | .wat_secrets 토큰에 draft_orders scope 없음 | n8n Shopify 크레덴셜 사용 (ID: `rIJuzuN1C5ieE7dr`) |
| Airtable 422 에러 | select 필드에 존재하지 않는 옵션 | `typecast: true`로 임시 레코드 생성 → 옵션 추가 → 삭제 |
| Sample Sent 워크플로우 무동작 | Draft Order ID 필드가 비어있음 | Airtable 레코드에 Draft Order ID 먼저 기입 |
| Delivered Detection 미동작 | WJ TEST에만 구현됨 | Production 워크플로우는 미생성 상태 |
| Posted Detection 미동작 | (해결됨) 기존 Syncly Sheet 인증 미설정 → OrbiTools API로 전환 완료 (2026-03-18) |
| n8n API PUT 400 | `name` 필드 누락 | payload에 `"name": wf.get("name")` 포함 필수 |
| n8n API POST 400 `active is read-only` | `active` 필드 포함 | POST 시 `active` 필드 제거 |
| Windows curl SSL 실패 | `CRYPT_E_NO_REVOCATION_CHECK` | `curl -sk` 사용 |
| Python subprocess cp949 에러 | 한글/특수문자 워크플로우 이름 | 파일로 출력 후 `rb` + `decode('utf-8')` |

## n8n API 워크플로우 마이그레이션 패턴

### 신규 복제 (PROD → WJ TEST)
```python
payload = {
    'name': '[WJ TEST] ' + src['name'],
    'nodes': src['nodes'],
    'connections': src['connections'],
    'settings': src.get('settings', {})
}
# active 필드 절대 포함 금지 (read-only)
# Airtable base 교체: appNPVxj4gUJl9v15 → appT2gLRR0PqMFgII
```

### 노드 머지 (PROD 노드 → 기존 WJ TEST에 추가)
```python
# 1. PROD-only 노드 식별 (Sticky Note 제외)
prod_only = prod_node_names - wj_node_names

# 2. 새 노드 위치 오프셋 (+800px, 겹침 방지)
# 3. 커넥션 머지 (PROD-only 소스/타겟 연결 추가)
# 4. Airtable base 교체
# 5. PUT 업데이트 (name 필수!)
```

### 핵심 규칙
- POST: `active` 필드 포함 → 400 에러
- PUT: `name` 필드 누락 → 400 에러
- Windows: `curl -sk` 필수 (SSL revocation check 실패)
- Airtable: `appNPVxj4gUJl9v15` (PROD) → `appT2gLRR0PqMFgII` (WJ TEST)
