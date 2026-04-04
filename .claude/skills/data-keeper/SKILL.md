---
name: data-keeper
description: "Centralized data collection gateway for all advertising and sales metrics. Use when running daily data collection, checking data freshness, querying cached metrics, diagnosing missing data, managing the unified data pipeline, deploying the datakeeper Django app to EC2, backfilling historical data, or troubleshooting API/credential issues. Covers Amazon Ads, Amazon Sales (3 sellers), Meta Ads, Google Ads, GA4, Klaviyo, and Shopify. Also trigger when someone mentions 'data freshness', 'collection status', 'gk_ tables', 'orbitools API', 'datakeeper', or asks about advertising data availability."
---

# Data Keeper - Unified Data Gateway

## When to Use This Skill

- Run daily data collection (all channels or specific ones)
- Check data freshness and collection status
- Query cached advertising/sales data
- Diagnose missing or stale data
- Deploy or update the datakeeper Django app on EC2
- Manage GitHub Actions automation
- Backfill historical data from Polar
- Troubleshoot credential or API issues

## Architecture

```
PST 0:00 / 12:00 (2x daily)
        |
   GitHub Actions (.github/workflows/data_keeper.yml)
   OR local: python tools/data_keeper.py
        |
   7 Channel Collectors (sequential)
        |
   +---------+---------+
   v         v         v
 Cache    PostgreSQL   Log
 (.tmp/   (orbitools   (stdout)
 datakeeper/) API)
        |
        v
  data_keeper_client.py (reader)
        |
   +---------+---------+---------+
   v         v         v         v
 PPC      Meta       Financial  Weekly
 Daily    Daily      Model      Notion
```

## Infrastructure (from Notion Handover)

### EC2 Instances

| Instance | Purpose |
|----------|---------|
| **orbiters_2** | MVP (`export_calculator`) + Dashboard services |
| **orbiters_db** | PostgreSQL database server |
| **orbiters-n8n-server** | n8n automation (n8n.orbiters.co.kr) |

### orbiters_2 Details

- **Django project root**: `/home/ubuntu/export_calculator/`
- **Django settings**: `export_calculator.settings.production`
- **Log file**: `/home/ubuntu/export_calculator/logs/production.log`
- **systemd service**: `export_calculator`
- **Restart**: `sudo systemctl restart export_calculator`
- **HTTPS**: certbot managed
- **Domain**: orbiters.co.kr (Route53 + Gabia)
- **orbitools URL**: `https://orbitools.orbiters.co.kr`
- **WARNING**: API keys are hardcoded in EC2 — should migrate to env vars
- **WARNING**: Amazon data collection key rotation every 6 months

### AWS Account

- **Console**: orbiters11@gmail.com
- **LWA (Login With Amazon)**: official@fleeters.us

## GitHub Repos

| Repo | Type | Purpose |
|------|------|---------|
| `Orbiters-dev/WJ-Test1` | Private | **This project** — WAT framework, data_keeper, tools |
| `Orbiters11-dev/MVP` | Private | export_calculator Django project (EC2 server code) |
| `Orbiters11-dev/dashboard` | Private | Dashboard + ad data collectors |
| `Orbiters11-dev/app_proxy` | Private | Shopify-WordPress proxy (App Runner) |

### CI/CD Workflows (WJ-Test1)

| File | Purpose | Schedule |
|------|---------|----------|
| `.github/workflows/data_keeper.yml` | 7-channel data collection | PST 0:00 / 12:00 |
| `.github/workflows/deploy_ec2.yml` | Deploy Django app to EC2 | Manual dispatch |

## Credential Management

Loaded via `tools/env_loader.py`:
1. `~/.wat_secrets` (user home, NOT on NAS — takes precedence)
2. `.env` (project root, fallback)

### Required Credentials by Channel

| Channel | Env Vars | In GitHub Secrets? |
|---------|----------|-------------------|
| Amazon Ads | `AMZ_ADS_CLIENT_ID`, `AMZ_ADS_CLIENT_SECRET`, `AMZ_ADS_REFRESH_TOKEN` | Yes |
| Amazon Sales (Grosmimi) | `AMZ_SP_GROSMIMI_CLIENT_ID`, `AMZ_SP_GROSMIMI_CLIENT_SECRET`, `AMZ_SP_REFRESH_TOKEN_GROSMIMI` | Partial |
| Amazon Sales (Fleeters) | `AMZ_SP_CLIENT_ID`, `AMZ_SP_CLIENT_SECRET`, `AMZ_SP_REFRESH_TOKEN_FLEETERS` | Partial |
| Amazon Sales (Orbitool) | `AMZ_SP_CLIENT_ID`, `AMZ_SP_CLIENT_SECRET`, `AMZ_SP_REFRESH_TOKEN_ORBITOOL` | Partial |
| Meta Ads | `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID` | Yes |
| Google Ads | `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID/SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Yes |
| GA4 | `GA4_CLIENT_ID`, `GA4_CLIENT_SECRET`, `GA4_REFRESH_TOKEN`, `GA4_PROPERTY_ID` | **Missing** |
| Klaviyo | `KLAVIYO_API_KEY` | **Missing** |
| Shopify | `SHOPIFY_SHOP`, `SHOPIFY_ACCESS_TOKEN` | Yes |
| Orbitools PG | `ORBITOOLS_USER`, `ORBITOOLS_PASS` | **Missing** |
| EC2 Deploy | `EC2_SSH_KEY`, `EC2_HOST`, `EC2_USER` | **Missing** |

## Data Sources (9 Channels)

| Channel | Table | API | Lookback | Accounts |
|---------|-------|-----|----------|----------|
| Amazon Ads | `amazon_ads_daily` | Reporting v3 (async) | 35d | 3 profiles |
| Amazon Sales | `amazon_sales_daily` | SP-API flat-file | 35d | 3 sellers |
| Meta Ads | `meta_ads_daily` | Graph API v18 insights | 35d | 1 ad account |
| Google Ads | `google_ads_daily` | search_stream | 35d | MCC + sub-accounts |
| GA4 | `ga4_daily` | Analytics Data API | 35d | 1 property |
| Klaviyo | `klaviyo_daily` | REST API (Campaigns + **Flows**) | 35d | 1 account |
| Shopify | `shopify_orders_daily` | Admin REST API | 35d | 1 shop |
| GSC | `gsc_daily` | Search Console API v1 | 35d | 3 sites (onzenna/grosmimi/naeiae) |
| Keyword Volume | `dataforseo_keywords` | **Google Ads Keyword Planner** (NOT DataForSEO) | weekly | DATAFORSEO_KEYWORDS dict |

### Keyword Volume (dataforseo_keywords) — Important Notes

- **실제 소스**: Google Ads Keyword Planner API (`GenerateKeywordHistoricalMetrics`) — DataForSEO 유료 API 대체
- **저장 테이블명**은 `dataforseo_keywords`이지만 데이터는 Google Ads에서 수집
- **추적 키워드**: 브랜드별 정의 (`DATAFORSEO_KEYWORDS` dict in `data_keeper.py`)
  - Onzenna: onzenna, onzenna sunscreen, tinted sunscreen 등 6개
  - Naeiae: pop rice snack, baby rice crackers, 떡뻥 등 10개
  - Grosmimi: grosmimi, baby teether, silicone baby teether 등 6개
  - CHA&MOM: cha and mom, korean baby food 등 4개
- **컬럼**: `keyword`, `brand`, `avg_monthly_searches`, `competition`, `low_top_of_page_bid_micros`, `high_top_of_page_bid_micros`, `date`
- **사용처**: `amazon_ppc_executor.py` (Amazon CPC vs Google CPC 비교), `run_communicator.py` (SEO Insights 섹션)
- **키워드 추가**: `data_keeper.py` `DATAFORSEO_KEYWORDS` dict 수정 후 `--channel dataforseo` 재실행

### Amazon SP-API Sellers

| Seller | Brand | Seller ID |
|--------|-------|-----------|
| Grosmimi USA | Grosmimi | A3IA0XWP2WCD15 |
| Fleeters Inc | Naeiae | A2RE0E056TH6H3 |
| Orbitool | CHA&MOM | A3H2CLSAX0BTX6 |

## Commands

### Collect
```bash
python tools/data_keeper.py                    # All channels
python tools/data_keeper.py --channel meta     # Specific channel
python tools/data_keeper.py --skip-pg          # Local cache only
python tools/data_keeper.py --days 60          # Custom lookback
python tools/data_keeper.py --status           # Show status
```

### GitHub Actions
```bash
# Collect all
gh workflow run data_keeper.yml -R Orbiters-dev/WJ-Test1

# Specific channel
gh workflow run data_keeper.yml -R Orbiters-dev/WJ-Test1 -f channel=amazon_ads

# Deploy to EC2
gh workflow run deploy_ec2.yml -R Orbiters-dev/WJ-Test1 -f app=datakeeper
```

## Client Library

```python
from data_keeper_client import DataKeeper
dk = DataKeeper()
rows = dk.get("amazon_ads_daily", days=30)
rows = dk.get("amazon_ads_daily", days=30, brand="CHA&MOM")
rows = dk.get("meta_ads_daily", date_from="2026-02-01", date_to="2026-03-06")
dk.is_fresh("amazon_ads_daily")  # True if within 14 hours
```

## PostgreSQL Tables

All on orbitools EC2, `gk_` prefix, upsert on unique keys.

| Table | Unique Key |
|-------|-----------|
| `gk_shopify_orders_daily` | (date, brand, channel) |
| `gk_amazon_sales_daily` | (date, seller_id, channel) |
| `gk_amazon_ads_daily` | (date, campaign_id) |
| `gk_amazon_campaigns` | (campaign_id) |
| `gk_meta_ads_daily` | (date, ad_id) |
| `gk_meta_campaigns` | (campaign_id) |
| `gk_google_ads_daily` | (date, campaign_id) |
| `gk_ga4_daily` | (date, channel_grouping) |
| `gk_klaviyo_daily` | (date, source_type, source_id) — source_type: "campaign" \| "flow" |
| `gk_gsc_daily` | (date, site_url, query) |
| `gk_dataforseo_keywords` | (date, keyword, brand) |

## Orbitools API

Base: `https://orbitools.orbiters.co.kr/api/datakeeper`
Auth: HTTP Basic (`ORBITOOLS_USER` / `ORBITOOLS_PASS`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/save/` | Bulk upsert rows (max 500/chunk) |
| GET | `/query/?table=...&date_from=...&brand=...` | Query with filters |
| GET | `/tables/` | List tables with row counts |
| GET | `/status/` | Latest collection timestamps |

## EC2 Deployment

### Via GitHub Actions (recommended)
```bash
gh workflow run deploy_ec2.yml -R Orbiters-dev/WJ-Test1 -f app=datakeeper
```
Required secrets: `EC2_SSH_KEY`, `EC2_HOST`, `EC2_USER`, `ORBITOOLS_USER`, `ORBITOOLS_PASS`

### What deploy does
1. SCP `datakeeper/` to EC2 `/home/ubuntu/export_calculator/datakeeper/`
2. Add to `INSTALLED_APPS` in `export_calculator.settings.production`
3. Add URL route `api/datakeeper/`
4. `makemigrations` + `migrate` → creates 9 `gk_*` tables
5. `sudo systemctl restart export_calculator`
6. Verify API responds

### Via deploy script (Instance Connect)
```bash
python tools/deploy_datakeeper.py  # Generates copy-paste commands
```

## Backfill (Polar History)

```bash
python tools/data_keeper_backfill.py --dry-run      # Preview
python tools/data_keeper_backfill.py                  # Push all
python tools/data_keeper_backfill.py --source q5      # Amazon Ads only
```

| Source | Polar File | Target Table |
|--------|-----------|--------------|
| q1 | `q1_channel_brand_product.json` | shopify_orders_daily |
| q3 | `q3_amazon_brand.json` | amazon_sales_daily |
| q5 | `q5_amazon_ads_campaign.json` | amazon_ads_daily |
| q6 | `q6_facebook_ads_campaign.json` | meta_ads_daily |
| q7 | `q7_google_ads_campaign.json` | google_ads_daily |
| q13b | `q13b_ga4_by_channel_daily.json` | ga4_daily |
| q13e | `q13e_klaviyo_campaigns_daily.json` | klaviyo_daily |

## Brand Detection

| Brand | Keywords |
|-------|----------|
| Grosmimi | grosmimi, grosm |
| CHA&MOM | cha&mom, chamom, cha_mom, chaandmom, orbitool |
| Naeiae | naeiae, fleeters |
| Onzenna | onzenna, zezebaebae |
| Alpremio | alpremio |

## ⚠️ Known Issues & Design Decisions

### Shopify Channel Classification (FIXED 2026-03-08)

`shopify_orders_daily` previously used `"amazon" in tags` to classify all amazon-tagged orders as channel="Amazon". **This has been fixed.**

**What was wrong:**
1. **FBA Multi-Channel Fulfillment (MCF)** — Shopify DTC sales where Amazon handles fulfillment (WebBee app). Tags: `"Amazon Status - Complete, Exported To Amazon by WebBee App"` or `"Rejected by Amazon - WebBee app"`. These are **DTC sales**, not Amazon marketplace sales. The "discount" shown was from Shopify promo codes (influencer codes, Kaching Bundle deals), NOT Amazon pricing.
2. **Faire wholesale orders** — B2B orders via Faire tagged `"Faire, NON-TRANS-FBA, Rejected by Amazon"` — wholesale/B2B, not consumer sales.

**Current logic (fixed in `data_keeper.py`):**
```python
if "faire" in tags:
    channel = "B2B"
elif "exported to amazon" in tags or "amazon status" in tags or "rejected by amazon" in tags:
    channel = "D2C"   # FBA MCF: sale is on Shopify, Amazon is logistics only
elif "amazon" in tags or "amazon" in source:
    channel = "Amazon"
```

**Impact of fix**: Jan 2026 Grosmimi "Amazon channel" orders reduced from ~1,500 to ~0 (all reclassified to D2C/B2B). Previous inflated Amazon discount rates (e.g., 10.8% Jan 2026) were caused by Shopify promo codes (LAUREN10OFF, Kaching Bundles) being attributed to "Amazon channel".

**Actual Amazon Marketplace data** is in `amazon_sales_daily` (from SP-API flat files) — no line-item detail, no discount breakdown.

### Amazon Discount Calculation — Price Reference

For `channel="Amazon"` orders in `shopify_orders_daily`:
```
discount = (ref_price - sell_price) × qty + line_disc
gross    = ref_price × qty
```

Where:
- `ref_price` = current Shopify `price` field (NOT `compare_at_price`)
- `sell_price` = order line item price (what Amazon/WebBee recorded)
- `line_disc` = coupon/promo discount on the line item

**For D2C channel**: `ref_price` = `compare_at_price ?? price` (captures Shopify sale events)

**Price snapshot timing**: `amazon_prices` is built fresh each run using CURRENT Shopify prices. For the 35-day lookback window, historical orders use today's prices as reference. If prices changed within that window, calculated discounts may not reflect what was actually charged.

### Grosmimi Price History

Grosmimi raised retail prices in March 2025. Pre-increase prices are stored in `GROSMIMI_PRICE_CUTOFF` and `GROSMIMI_OLD_PRICES` in `data_keeper.py`:

```python
GROSMIMI_PRICE_CUTOFF = "2025-03-01"
GROSMIMI_OLD_PRICES = { variant_id: old_retail_price, ... }
```

Logic:
- Before `2025-03-01`: use `GROSMIMI_OLD_PRICES.get(vid)` as ref_price
- After: use current `amazon_prices`
- Floor: `ref_price = max(ref_price, sell_price)` — prevents negative discount when Amazon was premium-priced above Shopify reference

### Amazon Ads Data Availability

- Amazon Ads API v3 only retains ~60-90 days of history
- Naeiae (Fleeters Inc) Amazon Ads only exists from **Dec 2025 onward** in PG
- Pre-Dec 2025 Amazon Ads data for Naeiae: not available (hard API constraint)

## Troubleshooting

### Token Expired
- **Meta**: `META_ACCESS_TOKEN` expires ~60 days. Regenerate at Meta Business Suite.
- **Amazon Ads**: Refresh token is long-lived but key rotation every 6 months (next: 2026-04-28).
- **Google Ads**: Refresh token long-lived. Re-auth via OAuth playground if needed.

### API Returns 404
- `datakeeper` app not deployed. Run deploy workflow or `deploy_datakeeper.py`.
- Verify: `curl -u USER:PASS https://orbitools.orbiters.co.kr/api/datakeeper/tables/`

### Collection Hangs on Amazon Ads
- Async reports with 15s polling, up to 10min per report. 3 profiles x weekly chunks = normal 10-30min.

### No Data for a Channel
1. Check credential: `python -c "from tools.env_loader import load_env; load_env(); import os; print(os.getenv('KEY'))"`
2. Single channel test: `python tools/data_keeper.py --channel meta --skip-pg`
3. Check cache: `.tmp/datakeeper/*.json`

### PG Push Fails
- Verify API: `curl https://orbitools.orbiters.co.kr/api/datakeeper/status/`
- Data still cached locally even if PG fails.

## Files

| File | Purpose |
|------|---------|
| `tools/data_keeper.py` | Main collector (7 channels) |
| `tools/data_keeper_client.py` | Client library for consumers |
| `tools/data_keeper_backfill.py` | Polar history → PostgreSQL |
| `tools/deploy_datakeeper.py` | EC2 deploy command generator |
| `tools/env_loader.py` | Credential loader (~/.wat_secrets + .env) |
| `datakeeper/models.py` | Django models (9 tables) |
| `datakeeper/views.py` | API endpoints |
| `datakeeper/urls.py` | URL routing |
| `.github/workflows/data_keeper.yml` | Automated collection (2x daily) |
| `.github/workflows/deploy_ec2.yml` | EC2 deployment |
| `.tmp/datakeeper/*.json` | Local cache files |

## Ops Checklist (→ `_ops-framework/OPS_FRAMEWORK.md`)

### EVALUATE (단일 채널 건강체크)
- 마지막 수집 시각 (freshness) — core 14h, campaigns/GSC 25h threshold
- Row count 이상 여부 (이전 대비 급감/급증)
- API 응답 코드 확인 (401=토큰만료, 404=엔드포인트변경, 429=rate limit)
- 출력: PASS / NEEDS_FIXES / BLOCKED

### AUDIT (9채널 크로스체크)
- 9채널 freshness 동시 비교 (전체 stale 여부)
- PG 데이터 vs .tmp 캐시 일치 여부
- Shared export (`Shared/datakeeper/latest/`) 최신성
- manifest.json 타임스탬프 vs 실제 파일 일치

### FIX (수집 장애 복구)
1. 장애 채널 식별 (orbitools API 조회)
2. Credential reload (토큰 갱신)
3. Single-channel test (`--channel {name} --days 1`)
4. 성공 시 전체 수집 재실행
5. 실패 지속 시 .tmp 캐시 fallback 활성화

### IMPACT (채널 중단 downstream 영향)
| 채널 | downstream 영향 |
|------|----------------|
| amazon_ads_daily | PPC Agent 분석 불가, KPI 광고비 누락 |
| amazon_sales_daily | KPI 매출 누락 (3 seller) |
| meta_ads_daily | Meta Agent 분석 불가 |
| google_ads_daily | Google 광고비 누락 |
| ga4_daily | 트래픽/전환 분석 불가 |
| klaviyo_daily | 이메일 마케팅 분석 불가 |
| shopify_orders_daily | D2C 매출/할인율 산출 불가 |
