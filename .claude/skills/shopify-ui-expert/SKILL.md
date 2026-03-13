---
name: shopify-ui-expert
description: "Shopify UI 개발 전문가. Checkout UI Extensions(React), Liquid 테마 페이지, Polaris Admin 앱, Hydrogen/Remix 스토어프론트 개발과 폼 데이터 → n8n → PostgreSQL → Airtable → Shopify Metafields 데이터 파이프라인, E2E 테스트를 담당한다. Shopify UI, 체크아웃 확장, Liquid 페이지, 메타필드, 데이터 흐름, 폼 개발, 테마 배포, n8n 웹훅, 유저 데이터 저장, 스토어프론트, Polaris 관련 작업에 반드시 사용할 것. 새 페이지/폼 개발, 기존 UI 수정, 데이터 플로우 설계, E2E 테스트 작성 모두 이 스킬의 영역이다."
---

# Shopify UI 개발 전문가

4개 UI 도메인(Checkout Extension, Liquid 테마, Polaris Admin, Hydrogen/Remix)과 공유 데이터 파이프라인을 통합 관리하는 스킬이다. UI에서 수집한 유저 데이터가 최종 저장소까지 도달하는 전체 흐름을 책임진다.

## When to Use This Skill

- Checkout UI Extension (React JSX) 생성/수정
- Liquid 테마 페이지 생성/배포 (`tools/deploy_*.py`)
- Polaris 기반 Shopify Admin 앱 개발
- Hydrogen/Remix 헤드리스 스토어프론트 개발
- 폼 데이터 → n8n webhook → PostgreSQL → Airtable → Metafield 파이프라인 설계/디버깅
- E2E 테스트 작성 및 실행 (`tools/shopify_tester.py`, `tools/test_influencer_flow.py`)
- Shopify 메타필드 정의/동기화
- 인플루언서 협업 파이프라인 (Gifting → Sample → Delivery → Posted) 관리
- n8n 워크플로우 생성/수정/디버깅

## Architecture

```
[UI Layer]                              [Data Pipeline]

Checkout UI Extension ──metafield──>    Shopify Order Metafields
  (React, @shopify/ui-extensions-react)     │
  onzenna-survey-app/extensions/            │ Shopify Webhook
                                            ▼
Thank-You Extension ──POST──>           n8n Orchestrator
  (React, purchase.thank-you.*)             │
                                     ┌──────┼──────┬──────┐
Liquid Pages ──fetch()──>            │      │      │      │
  (deploy_*.py, Theme Asset API)   Postgres Airtable Slack Email
                                     │
Admin App ──GraphQL──>            Shopify Metafields (via n8n)
  (Polaris, App Bridge)

Hydrogen/Remix ──Storefront API──>
  (headless, SSR)

Influencer Pipeline ──n8n polling──>
  (Airtable status → Shopify Draft Order → Fulfillment → Syncly)
```

## Domain 1: Checkout UI Extensions

React 컴포넌트 기반. `@shopify/ui-extensions-react/checkout` 패키지 사용.

**위치:** `onzenna-survey-app/extensions/`
- `onzenna-checkout-survey/` — 체크아웃 설문 (Q4~Q7)
- `onzenna-thankyou-survey/` — 감사 페이지 크리에이터 폼 + 로열티 CTA

**핵심 패턴:**
- 컴포넌트: BlockStack, InlineStack, Heading, Text, Select, TextField, Checkbox, Button, Banner, Link, Divider
- 훅: `useApplyMetafieldsChange` (메타필드 쓰기), `useMetafield` (읽기), `useCustomer`, `useOrder`, `useSettings`
- 데이터 쓰기: `applyMetafieldsChange({ type: "updateMetafield", namespace, key, valueType, value })`
- 설정: `shopify.extension.toml`에서 api_version, targeting, capabilities, metafields 선언
- 배포: `shopify app dev` (프리뷰) / `shopify app deploy` (프로덕션)

**메타필드 네임스페이스:**
| Namespace | Key | 설명 |
|-----------|-----|------|
| `onzenna_survey` | `journey_stage` | 육아 단계 |
| `onzenna_survey` | `baby_birth_month` | 아기 생년월 (YYYY-MM) |
| `onzenna_survey` | `has_other_children` | 다른 자녀 유무 |
| `onzenna_survey` | `is_creator` | 크리에이터 여부 |
| `onzenna_survey` | `signup_completed_at` | 설문 완료 시각 |
| `onzenna_creator` | `creator_completed_at` | 크리에이터 폼 완료 시각 |

상세 패턴은 `references/ui-extensions.md` 참조.

## Domain 2: Liquid Theme Pages

Python 스크립트가 Liquid 섹션 + JSON 템플릿을 Shopify Theme Asset API로 업로드하고, 페이지를 생성/업데이트한다.

**기존 배포 스크립트:**
| 스크립트 | 페이지 | 상태 |
|---------|--------|------|
| `deploy_core_signup_page.py` | /pages/core-signup | 운영 |
| `deploy_loyalty_survey_page.py` | /pages/loyalty-survey | 운영 |
| `deploy_creator_profile_page.py` | /pages/creator-profile | 운영 |
| `deploy_creator_sample_form_page.py` | /pages/creator-sample | 운영 |
| `deploy_influencer_page.py` | /pages/influencer-gifting | 운영 |
| `deploy_influencer_gifting2_page.py` | /pages/influencer-gifting2 | 운영 |
| `deploy_chaenmom_gifting_page.py` | /pages/chaenmom-gifting | 운영 |

**핵심 패턴:**
- API: `PUT /themes/{id}/assets.json` (Theme Asset)
- 활성 테마 감지: `GET /themes.json` → `role == "main"`
- OS 2.0 JSON 템플릿: `templates/page.{handle}.json`
- CSS 스코핑: 페이지별 고유 접두사 (`ck-`, `igf-`, `cs-`)
- JS 웹훅 연동: `fetch(WEBHOOK_URL, { method: "POST", ... })`
- CLI 옵션: `--dry-run`, `--unpublish`, `--rollback`

**새 페이지 개발 시:** 가장 유사한 기존 deploy 스크립트를 복사하여 시작한다.

상세 패턴은 `references/liquid-themes.md` 참조.

## Domain 3: Polaris Admin App

Shopify Admin에 임베딩되는 React 앱. 내부 대시보드, 설정 패널, 커스텀 워크플로우에 사용.

**기술 스택:**
- `@shopify/polaris` — UI 컴포넌트 (Page, Card, Layout, DataTable, ResourceList 등)
- `@shopify/app-bridge-react` — Admin 임베딩
- Shopify Admin REST/GraphQL API (인증된 세션)
- OAuth: `tools/shopify_oauth.py` 기존 패턴 재사용

**현재 상태:** 설계 단계. 기존 구현 없음.

상세 패턴은 `references/polaris-admin.md` 참조.

## Domain 4: Hydrogen/Remix Storefront

헤드리스 커스텀 스토어프론트. Remix 기반 SSR.

**기술 스택:**
- Remix + Hydrogen SDK
- Shopify Storefront API (GraphQL)
- Customer Account API
- `loader`/`action` 패턴으로 데이터 페칭
- 배포: Oxygen (Shopify-hosted) 또는 Vercel/Fly.io

**현재 상태:** 계획 단계. 기존 구현 없음.

상세 패턴은 `references/hydrogen-remix.md` 참조.

## Domain 5: Influencer Collaboration Pipeline (Pathlight)

인플루언서 협업의 전체 수명주기를 n8n 워크플로우 체인으로 자동화한다.

### Status Flow (Airtable Outreach Status)

```
Not Started → Draft Ready → Sent → Replied → Needs Review
→ Accepted → Sample Sent → Sample Shipped → Sample Delivered → Posted
                          → Sample Error
→ Declined
```

### 워크플로우 체인

| 단계 | n8n 워크플로우 | 트리거 | 동작 |
|------|---------------|--------|------|
| 0. AI 아웃리치 | Draft Generation (schedule) | 30분 폴링 | Airtable "Not Started" → Claude AI 초안 생성 → "Draft Ready" |
| 0.5 승인 발송 | Approval Send (schedule) | 5분 폴링 | "Approved" → Gmail 발송 → "Sent" |
| 1. 답장 처리 | Reply Handler (schedule) | 5분 폴링 | Gmail 답장 감지 → 분류(LT/HT) → AI 답장 초안 → "Replied" |
| 2. 신청 접수 | Gifting (webhook) | 폼 제출 | Shopify 고객 생성/조회 → Airtable 레코드 생성 (Needs Review) |
| 3. 수락 → 샘플 요청 | Gifting2 (webhook) | 크리에이터 폼 제출 | Draft Order 생성 (100% 할인) → Airtable + PG 업데이트 |
| 4. 샘플 발송 처리 | Fulfillment (schedule/webhook) | 폴링/이벤트 | Shopify fulfillment → Airtable "Sample Shipped" + 가이드라인 이메일 |
| 5. 샘플 발송 완료 | Sample Sent → Complete (polling) | 5분 간격 | Airtable "Sample Sent" → Draft Order Complete → "Sample Shipped" |
| 6. 배송 완료 | Shipped → Delivered (polling) | 30분 간격 | Shopify delivery 감지 → "Sample Delivered" |
| 7. 컨텐츠 게시 | Delivered → Posted (polling) | 6시간 간격 | Syncly D+60 시트 매칭 → "Posted" |

### n8n 워크플로우 ID 목록

**Production (17 workflows):**
| ID | 이름 | 노드 | 상태 |
|----|------|------|------|
| `fwwOeLiDLSnR77E1` | Draft Generation | 42 | Active |
| `jf9uxkPww2xeCr82` | Approval Send | 16 | Active |
| `K99grtW9iWq8V79f` | Reply Handler | 46 | Active |
| `F0sv8RsCS1v56Gkw` | Gifting (Influencer Application) | - | Active |
| `KqICsN9F1mPwnAQ9` | Gifting2 (Sample Request → Draft Order) | 14 | Inactive |
| `ufMPgU6cjwuzLM0y` | Shopify Fulfillment → Airtable | 34 | Active |
| `m89xU9RUbPgnkBy8` | Sample Sent → Complete Draft Order | - | Active |
| `FzBJVEOTvr6qJPAL` | Syncly: Daily Content Metrics Sync | 5 | Active |

**WJ TEST (18 workflows, 2026-03-13 마이그레이션 완료):**
| ID | 이름 | 노드 | 상태 | 비고 |
|----|------|------|------|------|
| `0q9uJUYTpDhQFMfz` | Draft Generation | 49 | Active | PROD +9 머지 |
| `mmkBpmvhzbgmSayh` | Approval Send | 16 | Active | PROD +4 머지 |
| `nVtYmhU0InRqRn4K` | Reply Handler | 50 | Active | PROD +7 머지 (HT Reply) |
| `4q5NCzMb3nMGYqL4` | Gifting | 12 | Active | |
| `734aqkcOIfiylExL` | **Gifting2 → Draft Order** | 14 | **Inactive** | **검증 후 활성화 필요** |
| `UP1OnpNEFN54AOUn` | Fulfillment → Airtable | 37 | Active | PROD +12 머지 |
| `Vd5NiKMwdLT7b9wa` | Sample Sent → Complete | 7 | Active | |
| `2vsXyHtjo79hnFoD` | Shipped → Delivered | 11 | Active | |
| `82t55jurzbY3iUM4` | Delivered → Posted | 8 | Active | |
| `FT70hFR6qI0mVc2T` | **Syncly Metrics Sync** | 5 | **Inactive** | **검증 후 활성화 필요** |
| `wyttsPSZJlWLgy86` | Customer Lookup | 5 | Active | |
| `zKmOX0tEWi6EBT9h` | Content Tracking | 23 | Active | |
| `6BNQRz57oCtdROlH` | Syncly Data Processing | 64 | Active | |
| `CEWr3kQlDg07310Y` | Full Pipeline (monolith) | 68 | Inactive | archive |
| `YCZuTAsHK2Ja6kIs` | AI Outreach (archive) | 61 | Inactive | archive |
| `5BG7Qe7HtsbD4iP0` | Docusign Contracting | 14 | Inactive | |
| `k08R16VJIuSPdi6T` | ManyChat Automation | 13 | Inactive | |
| `fJd4tZkBmmB2bdHJ` | Fulfillment (archive) | 26 | Inactive | archive |

### PROD → WJ TEST 차이점

| 항목 | PROD | WJ TEST |
|------|------|---------|
| Airtable Base | `appNPVxj4gUJl9v15` | `appT2gLRR0PqMFgII` |
| 트리거 방식 | scheduleTrigger (폴링) | webhook (실시간) + schedule |
| Config 패턴 | Fetch Dashboard + Fetch Today Config + Wait for Config | Read Config Sheet (Google Sheets) |
| Shopify 스토어 | mytoddie.myshopify.com | toddie-4080.myshopify.com |
| PostgreSQL | 없음 | Django API 연동 (orbitools.orbiters.co.kr) |
| 테스트 인프라 | 없음 | Inject Test Record, Is Dry Run?, Manual Trigger |

### PROD에서 가져온 핵심 로직 (2026-03-13)

- **Dashboard/Config 패턴**: `Fetch Dashboard` + `Fetch Today Config` + `Wait for Config` + `Is Active?` (중앙 Config 시트에서 on/off 제어)
- **에러 핸들링**: `Stop: No Email`, `Stop: Missing Email`, `Update Creator: Error`
- **HT Reply 시스템** (Reply Handler): Claude AI로 High Touch 답변 초안 생성 + 가이드라인 참조
- **Product Detection** (Draft Gen): 컨텐츠 트랜스크립트에서 제품 자동 감지
- **System Prompts**: Google Sheets에서 LT/HT/RH 시스템 프롬프트 동적 로딩
- **Fulfillment 확장**: Draft status check, product guidelines fetch, sample shipped polling, guideline email 발송

### n8n 크레덴셜

| ID | 이름 | 용도 |
|----|------|------|
| `rIJuzuN1C5ieE7dr` | Shopify Admin API (Gifting) | mytoddie.myshopify.com Draft Order 관리 |
| `59gWUPbiysH2lxd8` | Airtable PAT (WJ Test) | Airtable HTTP Request 인증 |

### Airtable 베이스

| 환경 | Base ID | Table ID | 용도 |
|------|---------|----------|------|
| Production (William) | `appNPVxj4gUJl9v15` | `tblv2Jw3ZAtAMhiYY` | Outbound CRM |
| WJ TEST | `appT2gLRR0PqMFgII` | `tbl7zJ1MscP852p9N` | 테스트 환경 |
| Inbound | `appT2gLRR0PqMFgII` | `tbloYjIEr5OtEppT0` | 인플루언서 인바운드 |

### 중요 제약사항

1. **n8n Code 노드에 `fetch()` 없음** — API 호출은 반드시 HTTP Request 노드 사용
2. **두 개의 Shopify 스토어**: `mytoddie.myshopify.com` (n8n 크레덴셜, Draft Order 권한 있음) vs `toddie-4080.myshopify.com` (.wat_secrets 토큰, product scope만)
3. **n8n webhook 안정성** — 간헐적 system-wide 장애 발생 가능, 서버 재시작 필요

상세는 `references/influencer-pipeline.md` 참조.

## Data Pipeline

UI에서 수집한 데이터가 최종 저장소에 도달하는 경로.

### 데이터 흐름 패턴

**패턴 A — Checkout Extension (메타필드 직접 쓰기):**
```
체크아웃 폼 → useApplyMetafieldsChange → Order Metafield
→ Shopify Webhook (orders/create) → n8n → PostgreSQL + Airtable
→ n8n (sync) → Customer Metafield (via Admin API)
```

**패턴 B — Thank-You / Liquid 페이지 (webhook POST):**
```
폼 submit → fetch(n8n_webhook_url) → n8n
→ PostgreSQL (upsert) + Airtable (create/update)
→ Shopify Customer Metafield (via Admin API)
→ Slack 알림 / Email 확인
```

### PostgreSQL 스키마 (핵심 테이블)

| 테이블 | 용도 |
|--------|------|
| `customers` | Shopify 고객 기본 정보 |
| `addresses` | 배송 주소 (지역 분석) |
| `orders` | 주문 이력 |
| `line_items` | 제품별 주문 데이터 |
| `customer_metrics` | LTV, RFM, 소비 패턴 (일일 enrichment) |
| `sync_log` | 동기화 감사 추적 |

### n8n 워크플로우 도구

| 도구 | 용도 |
|------|------|
| `setup_n8n_core_signup.py` | 코어 사인업 → 메타필드 |
| `setup_n8n_airtable_to_shopify_metafields.py` | Airtable → Shopify 메타필드 동기화 |
| `setup_shopify_webhooks.py` | Shopify 웹훅 등록 |
| `shopify_bulk_import.py` | 기존 데이터 벌크 임포트 |

상세는 `references/data-pipeline.md` 참조.

## Testing

`tools/shopify_tester.py`를 사용한 E2E 테스트.

### 테스트 플로우
1. 테스트 스펙 작성 (JSON) → `shopify_tester.py --push --spec '...'`
2. 실행: `shopify_tester.py --run`
3. 결과 확인: `shopify_tester.py --results`

### 테스트 Step Types
| Type | 설명 |
|------|------|
| `http_post` | 폼 제출 시뮬레이션 |
| `http_get` | 페이지/API 응답 확인 |
| `verify_airtable` | Airtable 레코드 확인 |
| `verify_postgres` | PostgreSQL 쿼리 검증 |
| `verify_shopify` | Shopify 메타필드/주문 확인 |
| `wait` | 비동기 처리 대기 |

### FAIL 분석 프레임워크
데이터 체인에서 어느 레이어가 깨졌는지 식별:
`폼 제출` → `webhook 수신` → `n8n 처리` → `DB 저장` → `메타필드 동기화`

상세는 `references/testing.md` 참조.

## Tools Inventory

### Page Deployment (deploy_*.py)

| Tool | 페이지 |
|------|--------|
| `deploy_core_signup_page.py` | /pages/core-signup (Part 1) |
| `deploy_loyalty_survey_page.py` | /pages/loyalty-survey (Part 3) |
| `deploy_creator_profile_page.py` | /pages/creator-profile (Part 2) |
| `deploy_creator_sample_form_page.py` | /pages/creator-sample |
| `deploy_influencer_page.py` | /pages/influencer-gifting |
| `deploy_influencer_gifting2_page.py` | /pages/influencer-gifting2 |
| `deploy_chaenmom_gifting_page.py` | /pages/chaenmom-gifting |

### n8n Workflow Setup (setup_n8n_*.py)

| Tool | 용도 |
|------|------|
| `setup_n8n_core_signup.py` | Core Signup → PG + Airtable + Shopify (PG-first) |
| `setup_n8n_loyalty_survey.py` | Loyalty Survey → Discount Code + Metafields |
| `setup_n8n_creator_to_airtable.py` | Creator Signup → PG + Airtable + IG Scrape |
| `setup_n8n_gifting2_order.py` | Gifting2 → Shopify Draft Order + Airtable |
| `setup_n8n_sample_request_order.py` | Sample Request → Draft Order (100% discount) |
| `setup_n8n_metafield_sync.py` | Form survey data → Shopify customer metafields |
| `setup_n8n_airtable_to_shopify_metafields.py` | Airtable → Shopify metafield sync (5min poll) |
| `setup_n8n_airtable_to_postgres.py` | Airtable → PostgreSQL sync (5min poll) |
| `setup_n8n_airtable_sync.py` | PostgreSQL → Airtable daily customer sync |
| `setup_n8n_customer_sync.py` | Shopify Customer Webhook → PostgreSQL |
| `setup_n8n_order_sync.py` | Shopify Order Webhook → PostgreSQL |
| `setup_n8n_customer_enrichment.py` | Daily RFM + LTV + AOV calculation |
| `setup_n8n_accepted_email.py` | Accepted creators → Send sample form email |
| `setup_n8n_syncly_daily.py` | Syncly Daily Content Metrics Sync |
| `setup_n8n_signup_overview.py` | Tag + overview workflow with flow diagram |

### Shopify Integration

| Tool | 용도 |
|------|------|
| `shopify_tester.py` | E2E 테스트 러너 (customer journey) |
| `shopify_bulk_import.py` | 기존 데이터 벌크 임포트 to PG |
| `shopify_oauth.py` | OAuth 토큰 발급 (local callback server) |
| `setup_survey_metafields.py` | 메타필드 정의 등록 |

### Influencer Pipeline

| Tool | 용도 |
|------|------|
| `test_influencer_flow.py` | E2E flow tester (Pathlight pipeline) |
| `process_influencer_order.py` | 폼 제출 → Shopify customer + draft order |
| `influencer_customer_lookup.py` | Shopify 고객 검색 (n8n Execute Command용) |
| `fetch_influencer_orders.py` | 인플루언서 주문 조회 (PR/supporter/sample) |
| `check_influencer_hashtag.py` | IG 해시태그 포스팅 확인 (Meta Graph API) |
| `create_typeform_influencer.py` | Typeform 기프팅 폼 생성 |
| `sync_influencer_notion.py` | Google Sheets → Notion DB 동기화 |

### Airtable Setup

| Tool | 용도 |
|------|------|
| `setup_airtable_customers.py` | Shopify Customers 베이스 생성 |
| `setup_airtable_inbound.py` | Inbound from ONZ 베이스 생성 |
| `setup_airtable_customers_table.py` | Onzenna Customers 마스터 테이블 |

## n8n Server Infrastructure

### EC2 인스턴스
| 항목 | 값 |
|------|-----|
| 인스턴스 | `orbiters-n8n-server` (`i-0ddaa6796683e8043`) |
| Private IP | `172.31.47.225` |
| Docker Compose | `/home/ubuntu/n8n/docker-compose.yml` |
| 컨테이너 | `n8n-n8n-1` (n8n) + `n8n-caddy-1` (Caddy reverse proxy) |
| 도메인 | `https://n8n.orbiters.co.kr` (Caddy SSL) |
| n8n 포트 | 5678 (Docker 내부, 호스트에 미노출) |
| 환경변수 | `/home/ubuntu/n8n/.env` |

### Docker Compose 구조
```yaml
services:
  n8n:
    image: n8nio/n8n:latest    # 주의: latest는 불안정할 수 있음
    environment:
      - DB_TYPE, DB_POSTGRESDB_*, N8N_HOST, N8N_PROTOCOL, N8N_PORT
      - WEBHOOK_URL, N8N_ENCRYPTION_KEY
      - N8N_PROXY_HOPS=1       # Caddy 프록시 필수 설정
      - TZ=America/Los_Angeles
    volumes:
      - ./n8n_data:/home/node/.n8n
  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - ./caddy_data:/data, ./caddy_data:/config
```

### 서버 관리 명령어
```bash
# SSH 접속
ssh ubuntu@<n8n-ec2-ip>  # 또는 AWS Session Manager

# 기본 조작
cd /home/ubuntu/n8n
docker compose down && docker compose up -d   # 클린 재시작
docker logs n8n-n8n-1 --tail 50               # n8n 로그
docker logs n8n-caddy-1 --tail 20             # Caddy 로그
docker ps                                      # 컨테이너 상태

# .env 수정
echo "KEY=VALUE" >> .env                       # 환경변수 추가
sed -i '/KEY/d' .env                           # 환경변수 제거
cat .env                                       # 현재 설정 확인
```

### n8n API 프로그래밍 패턴
```bash
# 워크플로우 조회
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_BASE_URL/api/v1/workflows/$WF_ID"

# 워크플로우 업데이트 (PUT) — 반드시 name 필드 포함!
curl -s -X PUT -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  "$N8N_BASE_URL/api/v1/workflows/$WF_ID" \
  -d '{"name":"workflow name","nodes":[...],"connections":{...}}'

# 활성화/비활성화
curl -s -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows/$WF_ID/activate"
```
**주의**: PUT 시 `name` 필드 누락하면 400 에러 ("must have required property 'name'")

## Django Gifting API (onzenna app)

### EC2 배포 위치
- 서버: `orbiters_2` EC2 (`orbitools.orbiters.co.kr`)
- 경로: `/home/ubuntu/export_calculator/onzenna/`
- 서비스: `sudo systemctl restart export_calculator`

### API 엔드포인트
| Method | URL | 용도 |
|--------|-----|------|
| POST | `/api/onzenna/gifting/save/` | 기프팅 신청 저장 (upsert) |
| POST | `/api/onzenna/gifting/update/` | 필드 업데이트 |
| GET | `/api/onzenna/gifting/list/` | 목록 조회 (?email=, ?status=) |
| GET | `/api/onzenna/tables/` | 전체 테이블 row count |

### EC2 배포 방법
`tools/deploy_onzenna.py`로 배포 명령 생성 → `.tmp/ec2_deploy_commands.txt`
또는 직접 cat heredoc으로 views.py/urls.py/admin.py 덮어쓰기 + `sudo systemctl restart export_calculator`

## Known Issues & Patterns

| 이슈 | 해결 패턴 |
|------|----------|
| **n8n Code 노드에 `fetch()` 없음** | API 호출은 반드시 HTTP Request 노드 사용. Code 노드는 데이터 변환만 |
| **두 개의 Shopify 스토어** | `mytoddie.myshopify.com` (n8n 크레덴셜, draft_orders 권한) vs `toddie-4080.myshopify.com` (.wat_secrets, product scope만) |
| **n8n Task Runner "Offer expired"** | JS Task Runner가 task offer를 시간 내 수락 못함 → 클린 재시작(`docker compose down && up`)으로 해결. 재발 시 n8n 버전 고정 검토 |
| **Caddy `ERR_ERL_UNEXPECTED_X_FORWARDED_FOR`** | Caddy가 X-Forwarded-For 헤더를 보내지만 n8n Express가 trust proxy 미설정 → `.env`에 `N8N_PROXY_HOPS=1` 추가 |
| **EC2에서 외부 도메인 curl HTTP 000** | EC2 → 자기 도메인(n8n.orbiters.co.kr) curl 시 연결 실패. `curl -sk https://127.0.0.1/ -H "Host: n8n.orbiters.co.kr"` 또는 외부에서 테스트 |
| **n8n API PUT 400 에러** | 워크플로우 업데이트 시 `name` 필드 필수. 누락하면 "must have required property 'name'" |
| **n8n webhook 간헐적 장애** | 전체 webhook 실행 실패 시 `docker compose down && docker compose up -d` (단순 restart로 부족할 수 있음) |
| **Airtable select 옵션 추가** | API로 직접 추가 불가 → `typecast: true`로 임시 레코드 생성 후 삭제 |
| Python f-string에서 Liquid `{{` 충돌 | `{{{{` 또는 별도 변수로 분리 |
| CSS 클래스 테마 충돌 | 페이지별 고유 접두사 사용 (`ck-`, `igf-`, `cs-`) |
| 체크아웃에서 customer metafield 직접 쓰기 불가 | `useApplyMetafieldsChange`는 order metafield에 기록 → n8n이 customer metafield로 동기화 |
| 모바일 반응형 깨짐 | `@media(max-width:768px)` + flex-direction: column |
| 페이지 간 데이터 전달 | sessionStorage로 핸드오프 |
| US 전화번호/ZIP 검증 | 클라이언트 JS: 10자리 전화, 5자리 ZIP |
| Windows Python 인코딩 | 스크립트 시작부에 `sys.stdout.reconfigure(encoding="utf-8")` |

## Credentials (.env / ~/.wat_secrets)

| Variable | Purpose |
|----------|---------|
| `SHOPIFY_SHOP` | 스토어 도메인 (toddie-4080.myshopify.com — product scope만) |
| `SHOPIFY_ACCESS_TOKEN` | Admin API 토큰 (product scope만, draft_orders 없음) |
| `N8N_API_KEY` | n8n API 접근 |
| `N8N_BASE_URL` | n8n 인스턴스 URL |
| `N8N_CORE_SIGNUP_WEBHOOK` | 코어 사인업 웹훅 URL |
| `N8N_INFLUENCER_WEBHOOK` | 인플루언서 웹훅 URL |
| `AIRTABLE_API_KEY` | Airtable PAT |
| `AIRTABLE_CUSTOMERS_BASE_ID` | Airtable 고객 베이스 ID |
| `POSTGRES_HOST` / `USER` / `PASSWORD` / `DB` | PostgreSQL 접속 |

Python 경로: `/c/Users/wjcho/AppData/Local/Programs/Python/Python312/python.exe`
