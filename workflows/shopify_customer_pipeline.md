# Shopify Customer Data Pipeline

## Overview

Shopify 고객/주문 데이터를 PostgreSQL에 실시간 동기화하고, 팀 운영용 Airtable에 노출하는 파이프라인.

```
Shopify ──webhook──> n8n ──> PostgreSQL (전체 저장)
                                 │
                                 ├──> n8n (daily) ──> Airtable (팀 운영, 10명)
                                 │
                                 └──> 커뮤니티 앱 API (향후)
```

## Architecture

### Data Flow

| Layer | Tool | Role |
|---|---|---|
| Source | Shopify Admin API | 고객/주문 원본 데이터 |
| Orchestrator | n8n | Webhook 수신, 데이터 변환, DB 적재 |
| Storage | EC2 PostgreSQL | 전체 데이터 저장 (Source of Truth) |
| Operations | Airtable | 팀 운영 인터페이스 (필터/태깅/메모) |
| Analytics | PostgreSQL queries | LTV, RFM, 소비패턴 자동 계산 |

### PostgreSQL Tables

| Table | Purpose |
|---|---|
| `customers` | Shopify 고객 기본정보 |
| `addresses` | 배송지 (지역 분석) |
| `orders` | 주문 이력 |
| `line_items` | 주문별 상품 상세 |
| `customer_metrics` | LTV, RFM, 소비패턴 (enrichment) |
| `sync_log` | 동기화 이력 |

### n8n Workflows

| Workflow | Trigger | Action |
|---|---|---|
| Customer Sync | Shopify webhook (customer create/update) | Upsert to PostgreSQL |
| Order Sync | Shopify webhook (order create/update) | Upsert order + line items + metrics |
| Customer Enrichment | Daily 10:00 KST | Calculate RFM, patterns, top product |
| Airtable Sync | Daily 09:00 KST | Sync active customers to Airtable |

---

## Setup Guide (순서대로 실행)

### Prerequisites

- EC2 PostgreSQL 접속 가능
- n8n에 PostgreSQL credential 등록됨
- `~/.wat_secrets`에 필요한 키 설정됨

### Step 1: PostgreSQL 스키마 생성

```bash
# EC2에서 실행
psql -h <host> -U <user> -d <db> -f tools/shopify_db_schema.sql
```

### Step 2: n8n Customer Sync 워크플로우 생성

```bash
python tools/setup_n8n_customer_sync.py --dry-run   # 미리보기
python tools/setup_n8n_customer_sync.py              # 실행
```

### Step 3: n8n Order Sync 워크플로우 생성

```bash
python tools/setup_n8n_order_sync.py --dry-run
python tools/setup_n8n_order_sync.py
```

### Step 4: Shopify Webhook 등록

```bash
python tools/setup_shopify_webhooks.py --dry-run     # 미리보기
python tools/setup_shopify_webhooks.py               # 등록
python tools/setup_shopify_webhooks.py --list         # 확인
```

### Step 5: 기존 데이터 Bulk Import

```bash
python tools/shopify_bulk_import.py --dry-run         # 건수 확인
python tools/shopify_bulk_import.py --limit 10        # 10건 테스트
python tools/shopify_bulk_import.py                   # 전체 임포트
```

### Step 6: Customer Enrichment 워크플로우 생성

```bash
python tools/setup_n8n_customer_enrichment.py --dry-run
python tools/setup_n8n_customer_enrichment.py
```

### Step 7: Airtable 세팅 + Sync

```bash
# 1. Airtable base 생성
python tools/setup_airtable_customers.py --dry-run
python tools/setup_airtable_customers.py

# 2. ~/.wat_secrets에 추가:
#    AIRTABLE_CUSTOMERS_BASE_ID=appXXXXX
#    AIRTABLE_CUSTOMERS_TABLE_ID=tblXXXXX

# 3. n8n sync 워크플로우 생성
python tools/setup_n8n_airtable_sync.py --dry-run
python tools/setup_n8n_airtable_sync.py
```

---

## Customer Metrics (Enrichment)

### RFM Segments

| Segment | Description | R | F | M |
|---|---|---|---|---|
| Champions | 최근 자주 많이 구매 | 4-5 | 4-5 | 4-5 |
| Loyal | 자주 구매하는 충성 고객 | - | 4-5 | 3+ |
| Potential Loyalist | 최근 구매, 빈도 중간 | 4-5 | 2-3 | - |
| Recent | 최근 첫 구매 | 4-5 | 1 | - |
| Promising | 비교적 최근, 빈도 낮음 | 3+ | 1-2 | - |
| Need Attention | 중간 수준 전반 | 2-3 | 2+ | - |
| At Risk | 과거 자주 구매했으나 이탈 중 | 1-2 | 3+ | - |
| Hibernating | 오래전 구매, 빈도 낮음 | 1-2 | 1-2 | 2+ |
| Lost | 모든 지표 낮음 | 1-2 | 1-2 | 1 |

### Pattern Tags

| Tag | Condition |
|---|---|
| `repeat_buyer` | 3회 이상 구매 |
| `one_time` | 1회만 구매 |
| `high_aov` | 평균 객단가 $100+ |
| `low_aov` | 평균 객단가 $30 미만 |
| `frequent` | 월 1회 이상 구매 |
| `active_30d` | 최근 30일 내 구매 |
| `dormant_180d` | 180일 이상 미구매 |
| `vip` | LTV $500+ |

---

## Troubleshooting

### Webhook not firing

```bash
# Shopify webhook 목록 확인
python tools/setup_shopify_webhooks.py --list

# 재등록
python tools/setup_shopify_webhooks.py --clean
python tools/setup_shopify_webhooks.py
```

### n8n workflow not active

```bash
# n8n UI에서 직접 확인: https://n8n.orbiters.co.kr
# 또는 해당 setup 스크립트 재실행 (idempotent)
```

### Bulk import failed midway

```bash
# 재실행해도 안전 (UPSERT 사용)
python tools/shopify_bulk_import.py
```

---

## Environment Variables

```
# ~/.wat_secrets에 필요한 키
SHOPIFY_SHOP=toddie-4080.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_...
N8N_API_KEY=...
N8N_BASE_URL=https://n8n.orbiters.co.kr
AIRTABLE_API_KEY=pat...
AIRTABLE_CUSTOMERS_BASE_ID=app...    # setup_airtable_customers.py 실행 후 추가
AIRTABLE_CUSTOMERS_TABLE_ID=tbl...   # setup_airtable_customers.py 실행 후 추가
```

---

## Future: Community App Integration

커뮤니티 앱은 PostgreSQL에 직접 연결:
- Django ORM 또는 REST API로 customer 데이터 조회
- 기존 Django Auth와 연동
- customer_metrics 활용해 앱 내 세그먼트/혜택 차등 적용
