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
- E2E 테스트 작성 및 실행 (`tools/shopify_tester.py`)
- Shopify 메타필드 정의/동기화

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

| Tool | Purpose | Command |
|------|---------|---------|
| `deploy_core_signup_page.py` | 코어 사인업 페이지 배포 | `python tools/deploy_core_signup_page.py` |
| `deploy_loyalty_survey_page.py` | 로열티 설문 페이지 배포 | `python tools/deploy_loyalty_survey_page.py` |
| `deploy_creator_profile_page.py` | 크리에이터 프로필 페이지 배포 | `python tools/deploy_creator_profile_page.py` |
| `deploy_influencer_page.py` | 인플루언서 기프팅 페이지 배포 | `python tools/deploy_influencer_page.py` |
| `deploy_chaenmom_gifting_page.py` | 차앤맘 기프팅 페이지 배포 | `python tools/deploy_chaenmom_gifting_page.py` |
| `shopify_tester.py` | E2E 테스트 러너 | `python tools/shopify_tester.py --run` |
| `setup_survey_metafields.py` | 메타필드 정의 등록 | `python tools/setup_survey_metafields.py` |
| `shopify_oauth.py` | OAuth 토큰 관리 | `python tools/shopify_oauth.py` |
| `shopify_bulk_import.py` | 기존 데이터 벌크 임포트 | `python tools/shopify_bulk_import.py` |

## Known Issues & Patterns

| 이슈 | 해결 패턴 |
|------|----------|
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
| `SHOPIFY_SHOP` | 스토어 도메인 (mytoddie.myshopify.com) |
| `SHOPIFY_ACCESS_TOKEN` | Admin API 토큰 |
| `N8N_API_KEY` | n8n API 접근 |
| `N8N_BASE_URL` | n8n 인스턴스 URL |
| `N8N_CORE_SIGNUP_WEBHOOK` | 코어 사인업 웹훅 URL |
| `N8N_INFLUENCER_WEBHOOK` | 인플루언서 웹훅 URL |
| `AIRTABLE_API_KEY` | Airtable PAT |
| `AIRTABLE_CUSTOMERS_BASE_ID` | Airtable 고객 베이스 ID |
| `POSTGRES_HOST` / `USER` / `PASSWORD` / `DB` | PostgreSQL 접속 |

Python 경로: `/c/Users/user/AppData/Local/Programs/Python/Python314/python.exe`
