# Data Pipeline Reference

UI에서 수집한 유저 데이터가 최종 저장소에 도달하는 전체 파이프라인 문서.

## 전체 아키텍처

```
[Data Sources]                [Orchestration]         [Storage]

Checkout Extension ─metafield─>                     Order Metafield
                                                        │
Thank-You Extension ─POST──>                            │
                              n8n Orchestrator ────> PostgreSQL (Source of Truth)
Liquid Pages ─fetch()──>          │                     │
                                  ├──────────────> Airtable (팀 운영)
Shopify Webhooks ──────────>      ├──────────────> Slack 알림
  (orders/create,                 ├──────────────> Email 확인
   customers/create)              └──────────────> Shopify Customer Metafield
                                                    (Admin API)
```

## 데이터 흐름별 상세

### Flow A: 체크아웃 설문 (Checkout Extension)
```
고객 체크아웃 → Checkout.jsx useApplyMetafieldsChange
→ Order Metafield (onzenna_survey/*)
→ Shopify Webhook (orders/create) → n8n
→ n8n: Extract metafields from order
→ PostgreSQL: UPSERT customers + customer_metrics
→ Airtable: Update customer record
→ Shopify Admin API: Customer Metafield write (sync from order to customer)
```

### Flow B: 크리에이터 폼 (Thank-You Extension)
```
감사 페이지 → ThankYou.jsx fetch(webhookUrl, POST)
→ n8n Webhook: /webhook/onzenna-creator-survey
→ n8n: Validate + transform payload
→ PostgreSQL: INSERT creator_submissions
→ Airtable: Create creator record
→ Slack: #creators 채널 알림
→ Email: 크리에이터 환영 이메일
```

### Flow C: 인플루언서 기프팅 (Liquid Page)
```
/pages/influencer-gifting → JS fetch(N8N_INFLUENCER_WEBHOOK, POST)
→ n8n Webhook: /webhook/influencer-gifting
→ n8n: Create Shopify Draft Order (selected products + variants)
→ n8n: Create Airtable record (influencer DB)
→ Slack: #influencer-ops 알림
→ Email: 인플루언서 확인 + 콘텐츠 가이드라인
```

### Flow D: 고객 동기화 (Webhook 기반)
```
Shopify Webhook (customers/create, customers/update)
→ n8n: Transform customer data
→ PostgreSQL: UPSERT customers + addresses
→ Daily enrichment: RFM 세그먼트 + 패턴 태그 계산
→ Daily Airtable sync: PostgreSQL → Airtable (active customers)
```

## PostgreSQL 스키마

### customers 테이블
```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,           -- Shopify customer ID
    email VARCHAR(255),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(50),
    tags TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    orders_count INT DEFAULT 0,
    total_spent DECIMAL(10,2) DEFAULT 0,
    synced_at TIMESTAMP DEFAULT NOW()
);
```

### orders 테이블
```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,           -- Shopify order ID
    customer_id BIGINT REFERENCES customers(id),
    order_number INT,
    total_price DECIMAL(10,2),
    financial_status VARCHAR(50),
    fulfillment_status VARCHAR(50),
    created_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT NOW()
);
```

### customer_metrics 테이블 (일일 enrichment)
```sql
CREATE TABLE customer_metrics (
    customer_id BIGINT PRIMARY KEY REFERENCES customers(id),
    ltv DECIMAL(10,2),                -- Lifetime Value
    aov DECIMAL(10,2),                -- Average Order Value
    purchase_count INT,
    first_purchase_at TIMESTAMP,
    last_purchase_at TIMESTAMP,
    rfm_recency INT,                  -- 1-5
    rfm_frequency INT,                -- 1-5
    rfm_monetary INT,                 -- 1-5
    rfm_segment VARCHAR(50),          -- Champions, Loyal, At Risk, etc.
    pattern_tags TEXT[],              -- repeat_buyer, high_aov, vip, etc.
    top_product VARCHAR(255),
    calculated_at TIMESTAMP DEFAULT NOW()
);
```

### sync_log 테이블
```sql
CREATE TABLE sync_log (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50),            -- customer_sync, order_sync, enrichment
    records_processed INT,
    status VARCHAR(20),               -- success, partial, failed
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

## RFM 세그먼트 정의

| 세그먼트 | R | F | M | 설명 |
|---------|---|---|---|------|
| Champions | 4-5 | 4-5 | 4-5 | 최근+자주+고액 구매 |
| Loyal | * | 4-5 | 3+ | 자주 구매 |
| Potential Loyalist | 4-5 | 2-3 | * | 최근 구매 시작 |
| Recent | 4-5 | 1 | * | 신규 구매 |
| Need Attention | 2-3 | 2+ | * | 구매 감소 추세 |
| At Risk | 1-2 | 3+ | * | 이전 단골, 이탈 위험 |
| Hibernating | 1-2 | 1-2 | 2+ | 장기 휴면 |
| Lost | 1-2 | 1-2 | 1 | 이탈 |

## 패턴 태그

```
repeat_buyer    — 3회 이상 구매
one_time        — 1회 구매
high_aov        — AOV $100+
low_aov         — AOV $30 미만
frequent        — 월 1회 이상 구매
active_30d      — 최근 30일 내 구매
dormant_180d    — 180일+ 미구매
vip             — LTV $500+
```

## 메타필드 인벤토리

### onzenna_survey 네임스페이스
| Key | Type | Source | 설명 |
|-----|------|--------|------|
| `journey_stage` | string | Checkout Extension | 육아 단계 |
| `baby_birth_month` | string | Checkout Extension | YYYY-MM 형식 |
| `has_other_children` | string | Checkout Extension | "true"/"false" |
| `other_children_detail` | string | Checkout Extension | 자유 텍스트 |
| `is_creator` | string | Checkout Extension | "true"/"false" |
| `signup_completed_at` | string | Checkout Extension | ISO 8601 타임스탬프 |

### onzenna_creator 네임스페이스
| Key | Type | Source | 설명 |
|-----|------|--------|------|
| `creator_completed_at` | string | Thank-You Extension | ISO 8601 타임스탬프 |
| `primary_platform` | string | n8n sync | 주요 SNS 플랫폼 |
| `primary_handle` | string | n8n sync | SNS 핸들 |
| `following_size` | string | n8n sync | 팔로워 규모 범위 |

## n8n 워크플로우 도구 인벤토리

| Python 도구 | n8n 워크플로우 | 트리거 |
|------------|--------------|--------|
| `setup_n8n_core_signup.py` | Core Signup → Metafield | Webhook |
| `setup_n8n_airtable_to_shopify_metafields.py` | Airtable → Metafield Sync | Daily cron |
| `setup_shopify_webhooks.py` | Webhook 등록 | 수동 실행 |
| `shopify_bulk_import.py` | 기존 데이터 벌크 임포트 | 수동 실행 |

## Webhook URL 카탈로그

| 환경변수 | URL 패턴 | 용도 |
|---------|---------|------|
| `N8N_CORE_SIGNUP_WEBHOOK` | `/webhook/onzenna-core-signup` | 코어 사인업 |
| `N8N_INFLUENCER_WEBHOOK` | `/webhook/influencer-gifting` | 인플루언서 기프팅 |
| `N8N_METAFIELD_WEBHOOK` | `/webhook/onzenna-save-metafields` | 메타필드 직접 저장 |

Base URL: `https://n8n.orbiters.co.kr`

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 폼 제출 후 Airtable에 안 들어옴 | n8n 워크플로우 비활성 | n8n UI에서 워크플로우 활성화 확인 |
| 메타필드 값이 null | toml에 메타필드 미선언 | `shopify.extension.toml`에 `[[extensions.metafields]]` 추가 |
| 중복 레코드 | UPSERT 조건 누락 | PostgreSQL ON CONFLICT 절 확인 |
| webhook 타임아웃 | n8n 응답 지연 | n8n 워크플로우 최적화, 비동기 처리 전환 |
| 벌크 임포트 실패 | API rate limit | 요청 간 0.5초 sleep 추가 |
