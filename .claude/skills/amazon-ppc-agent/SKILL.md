---
name: amazon-ppc-agent
description: "Expert Amazon PPC campaign analysis, optimization, and execution agent. Use when analyzing Amazon Ads performance, diagnosing campaign issues, reviewing PPC daily reports, making bid/budget recommendations, executing bid/budget changes, harvesting keywords, or optimizing ROAS/ACOS. Covers Sponsored Products, Sponsored Brands, and Sponsored Display across multiple seller profiles."
---

# Amazon PPC Analysis, Optimization & Execution Skill

## When to Use This Skill

Use this skill when you need to:
- **Analyze** daily/weekly/monthly Amazon Ads performance data
- **Diagnose** campaign-level issues (high ACOS, low ROAS, wasted spend)
- **Execute** bid and budget adjustments via Amazon Ads API (multi-brand)
- **Harvest** keywords from search term reports
- **Propose** changes with confidence tiers (No-Brainer / Strong / Moderate)
- **Forecast** budget depletion and seasonal adjustments
- **Query** performance data using natural language patterns
- Compare performance across brands and time periods

## Skill Capabilities

### Layer 1: Analysis (Read-Only)
- Daily health check and anomaly detection
- Three-period comparison (yesterday / 7d / 30d)
- Brand-level and campaign-level breakdown
- Wasted spend audit
- Search term profitability analysis
- Cross-platform correlation (Amazon Ads + Shopify + Meta)

### Layer 2: Recommendations (Proposal)
- Bid adjustments per ROAS Decision Framework
- Budget reallocation across campaigns/brands
- Keyword harvesting (profitable search terms -> exact match)
- Negative keyword additions (unprofitable search terms)
- Seasonal budget recommendations (Prime Day, BFCM, Q4)
- **Confidence-tiered proposals**: No-Brainer / Strong Recommend / Moderate

### Layer 3: Execution (Write - Approval Required)
- `--propose`: Generate and email change proposals (per brand, separate emails)
- `--execute`: Apply only human-approved changes via API
- Change logging to Google Sheets
- Email confirmation trail

## Project Context

### Multi-Brand Architecture

The executor supports **3 US seller profiles**, each with independent config:

| Brand Key  | Seller Name     | Brand Display | Daily Budget | Max Campaign | Max Bid | Manual ACOS | Auto ACOS |
|------------|-----------------|---------------|-------------|-------------|---------|-------------|-----------|
| `naeiae`   | Fleeters Inc    | Naeiae        | $120        | $50         | $3.00   | 25%         | 35%       |
| `grosmimi` | GROSMIMI USA    | Grosmimi      | $3,000      | $500        | $5.00   | 20%         | 30%       |
| `chaenmom` | Orbitool        | CHA&MOM       | $150        | $60         | $3.00   | 30%         | 40%       |

**Key config rationale:**
- **Grosmimi** ($3K/day): High-volume brand, 30d ROAS 4.37x. Tight ACOS targets (20/30%) to maintain efficiency at scale. Higher max bid ($5) for competitive baby product keywords.
- **CHA&MOM** ($150/day): Growth phase, 30d ROAS 3.04x trending up to 4.51x 7d. Looser ACOS (30/40%) to allow discovery while still profitable.
- **Naeiae** ($120/day): Stable mid-performer, 30d ROAS 2.61x. Balanced ACOS targets.

### Tools

| Tool | Purpose | Command |
|------|---------|---------|
| `run_amazon_ppc_daily.py` | Daily analysis report (all brands) | `python tools/run_amazon_ppc_daily.py` |
| `amazon_ppc_executor.py` | Bid/budget execution (multi-brand) | `python tools/amazon_ppc_executor.py --propose` |

### Executor Commands

| Command | Description |
|---------|-------------|
| `--propose` | Analyze all 3 brands, send separate email per brand |
| `--propose --brand naeiae` | Single brand only |
| `--propose --brand grosmimi` | Grosmimi only |
| `--propose --brand chaenmom` | CHA&MOM only |
| `--execute --brand naeiae` | Execute approved changes for Naeiae |
| `--execute` | Execute all brands with approved proposals |
| `--check-execute` | Poll Gmail for 'execute' reply, auto-execute per brand |
| `--status` | Show pending proposals for all brands |
| `--cycle` | 6-hour auto-analysis cycle |
| `--skip-keywords` | Campaign-level only (faster) |

### Brand Aliases

| Alias | Maps to |
|-------|---------|
| `naeiae`, `fleeters` | `naeiae` |
| `grosmimi`, `gros` | `grosmimi` |
| `chaenmom`, `orbitool`, `cha&mom`, `chamom` | `chaenmom` |

### Daily Report Tool
- API: Amazon Ads Reporting v3 (async: submit -> poll 15s intervals -> download GZIP)
- Analysis: Claude API (claude-sonnet-4-6) with PPC expert system prompt
- Output: HTML email + `.tmp/ppc_report_YYYYMMDD.html` + `.tmp/ppc_payload_YYYYMMDD.json`

### Executor Tool
- Target: All 3 brands (configurable via `--brand`)
- Approval: Nothing executes without explicit `"approved": true`
- Budget caps: Per-brand (see table above)
- Logging: Google Sheets change log + email trail
- Output: `.tmp/ppc_proposal_{brand_key}_YYYYMMDD.json` + `.tmp/ppc_executed_YYYYMMDD.json`

### Credentials (.env)

| Variable | Purpose |
|----------|---------|
| `AMZ_ADS_CLIENT_ID` | Ads API LWA Client ID |
| `AMZ_ADS_CLIENT_SECRET` | Ads API LWA Client Secret |
| `AMZ_ADS_REFRESH_TOKEN` | Ads API refresh token |
| `AMZ_SP_REFRESH_TOKEN` | SP-API refresh token |
| `AMZ_SP_LWA_CLIENT_ID` | SP-API LWA Client ID |
| `AMZ_SP_LWA_CLIENT_SECRET` | SP-API LWA Client Secret |
| `ANTHROPIC_API_KEY` | Claude analysis |
| `PPC_REPORT_RECIPIENT` | Email recipient |

Python path: `/c/Users/user/AppData/Local/Programs/Python/Python314/python.exe`

> Note: Ads API uses a **separate LWA app** from SP-API (different Client ID/Secret pair).

### Data Flow

```
1. Daily Analysis (all brands):
   DataKeeper (amazon_ads_daily PG) -> run_amazon_ppc_daily.py
     -> Claude analysis (claude-sonnet-4-6) -> .tmp/ppc_report_YYYYMMDD.html -> Gmail
   NOTE: run_amazon_ppc_daily.py uses DataKeeper as PRIMARY source (not API).
         Field mapping: DK.spend -> cost, DK.sales -> sales14d, DK.campaign_id -> campaignId

2. Proposal & Execution (per brand):
   DataKeeper -> .tmp/ppc_proposal_{brand}_YYYYMMDD.json -> Human approval
     -> API execution -> .tmp/ppc_executed_YYYYMMDD.json -> Google Sheets changelog

3. Auto-Execute (Gmail polling):
   Every 2h: check Gmail for 'execute'/'approve'/'go'/'yes' reply per brand
     -> approve all -> execute -> log -> email confirmation
```

### amazon_ads_daily Schema (DataKeeper)

| Field | Type | Notes |
|-------|------|-------|
| `date` | str YYYY-MM-DD | Data date |
| `brand` | str | Grosmimi / Naeiae / CHA&MOM |
| `campaign_id` | str | Campaign identifier |
| `campaign_name` | str | Campaign display name |
| `ad_type` | str | SP / SB / SD |
| `spend` | float | **Ad cost** -- use as `cost` in analysis |
| `sales` | float | Ad-attributed sales (14d window) |
| `purchases` | int | Ad-attributed conversions |
| `clicks` | int | Total clicks |
| `impressions` | int | Total impressions |

**CRITICAL**: DataKeeper field is `spend`, NOT `cost`. When querying:
```python
dk = DataKeeper()
rows = dk.get('amazon_ads_daily', days=30)
cost = float(row.get('spend', 0))   # spend, not cost
sales = float(row.get('sales', 0))
```

### Cross-Platform Data Sources (MUST leverage)

| Source | DataKeeper Table | Key Fields | How to Use |
|--------|-----------------|------------|------------|
| Amazon Ads | `amazon_ads_daily` | `spend`, `sales`, `clicks`, `impressions` | Primary PPC data |
| Amazon Sales | `amazon_sales_daily` | `ordered_product_sales`, `units_ordered` | Total revenue, organic vs ad ratio |
| Google Ads | `google_ads_daily` | `spend`, `conversions_value`, `clicks`, `impressions` | CPC benchmark, ROAS comparison, budget allocation |
| Meta Ads | `meta_ads_daily` | `spend`, `purchase_value`, `purchases` | Awareness -> demand lag, multi-channel ROAS |
| Shopify DTC | `shopify_orders_daily` | `total_price`, orders | Cross-channel conversion, AOV trends |
| GA4 | `ga4_daily` | `sessions`, `conversions` | Landing page quality signal |
| Keyword Volume | `dataforseo_keywords` | `keyword`, `avg_monthly_searches`, `low_top_of_page_bid_micros`, `high_top_of_page_bid_micros` | Google market CPC vs Amazon bid comparison |
| GSC | `gsc_daily` | `query`, `clicks`, `impressions`, `position` | Organic search demand signals |
| Syncly D+60 | External sheet | Views, likes, comments | Content-driven demand correlation |

**dataforseo_keywords 활용 패턴:**
- `fetch_dataforseo_keywords(brand_key)` — 브랜드별 키워드 볼륨 + Google CPC 조회 (Data Keeper → PG)
- Amazon bid vs Google `high_top_of_page_bid_micros/1e6` 비교 → bid ceiling 판단
- 소스는 **Google Ads Keyword Planner** (DataForSEO 아님) — Data Keeper `--channel dataforseo`로 수집

### Cross-Platform Decision Rules (Automated in Executor)

Every proposal email now includes a **Cross-Platform Context** section with Google Ads, Meta, Shopify, and Amazon Sales data. This is fetched via `fetch_cross_platform_context()`.

**Rule 1: Multi-Channel ROAS Comparison**
- Amazon ROAS drops, Google/Meta stable -> Amazon-specific issue (listing, competitor)
- All channels drop -> market/seasonal (reduce proportionally)
- Amazon stable, Google drops -> potential budget reallocation opportunity

**Rule 2: Google Ads CPC as Bid Ceiling Signal**
- Google Search CPC for same keywords = market price signal
- If Google CPC > Amazon CPC -> room to increase Amazon bids
- If Google CPC dropping -> market cooling, hold Amazon bids

**Rule 3: Meta Awareness -> Amazon Demand Lag (7-14 days)**
- Meta spend increase -> 7-14 day lag -> Amazon organic search increase
- Track: meta_spend_7d vs amazon_organic_sales_next_7d
- If meta spend UP and Amazon branded search UP -> increase Amazon brand defense

**Rule 4: Organic vs Ad Sales Ratio**
- < 20% ad ratio: Under-invested in ads
- 20-40%: Balanced
- 40-60%: Ad-dependent, watch diminishing returns
- > 60%: Over-reliance, focus organic growth

**Rule 5: Budget Allocation Across Platforms**
- Optimal split (baby products): Amazon 50-60%, Google 20-30%, Meta 15-20%
- Reallocation: channel ROAS > 1.5x avg for 14d -> increase 20%
- Never reallocate > 30% of any channel in single move

**Full reference:** `references/cross-platform-analysis.md`

### Known Issues & Fixes

| Issue | Fix |
|-------|-----|
| Python output buffered in background | Use `-u` flag for unbuffered output |
| Fleeters Inc hangs on campaign list | `timeout=20` set to fail fast |
| Reporting v3 only ~60-90 days history | 400 error for older dates; use SP-API for historical |
| Campaign list returns LIST directly | Not wrapped in `{"campaigns": {...}}` -- check `isinstance(data, dict)` |
| Emoji in print() crashes on Windows | cp949 UnicodeEncodeError -- use ASCII text only |
| Attribution lag | Report data has 2-3 day lag (14-day attribution window) |
| Grosmimi campaign list API timeout | Many campaigns, may need pagination patience |

---

## Proposal Confidence Tiers

Every proposal MUST be categorized into one of these tiers:

### Tier 1: No-Brainer (Must-Do)
**Green badge. Execute immediately.**
- ROAS < 1.0 with $50+ spend -> **pause** (literally losing money)
- Search terms with $100+ spend, 0 sales -> **negate** (pure waste)
- Keywords with ACOS > 200% sustained 14d+ -> **pause or negate**
- Budget exhausted before noon on ROAS > 4.0 campaigns -> **increase budget**

### Tier 2: Strong Recommend
**Orange badge. High confidence, should act within 24h.**
- ROAS 1.0-1.5 campaigns -> **reduce bid 30%** (bleeding cash)
- Profitable search terms (ACOS < target, 3+ sales) -> **harvest to exact match**
- Yesterday ROAS drops 40%+ vs 7d avg -> **emergency bid reduction**
- Campaign ACOS > 2x target for 14d+ -> **reduce bid or restructure**

### Tier 3: Moderate Recommendation
**Yellow badge. Good practice, review within 48h.**
- ROAS 1.5-2.0 -> **reduce bid 15%** (below breakeven zone)
- ROAS 3.0-5.0 -> **consider budget increase** if budget utilization > 80%
- Keyword bid adjustments within 20% range
- Auto campaign search terms to harvest (lower confidence, smaller volume)

### Tier 4: Monitor Only
**Gray badge. No action needed, informational.**
- ROAS 2.0-3.0 (healthy range)
- New campaigns < 7 days old (insufficient data)
- Seasonal fluctuations within normal bounds

---

## ROAS Decision Framework (MANDATORY)

These thresholds are hardcoded in the executor:

| 7-Day ROAS | Action | Bid Change | Budget Change | Priority | Tier |
|------------|--------|------------|---------------|----------|------|
| < 1.0      | **pause** | - | - | urgent | No-Brainer |
| 1.0 ~ 1.5  | reduce_bid | -30% | - | urgent | Strong |
| 1.5 ~ 2.0  | reduce_bid | -15% | - | high | Moderate |
| 2.0 ~ 3.0  | monitor | - | - | medium | Monitor |
| 3.0 ~ 5.0  | increase_budget | - | +20% | medium | Moderate |
| > 5.0      | increase_budget | +10% | +30% | high | Strong |

**Drop rule:** Yesterday ROAS drops 30%+ vs 7-day average -> reduce_bid -20% additional.

### ROAS Color Coding
- Green (good): ROAS >= 3.0
- Orange (warning): ROAS 2.0 ~ 3.0
- Red (danger): ROAS < 2.0

### ACOS Thresholds (per brand)
| Brand | Green | Orange | Red |
|-------|-------|--------|-----|
| Grosmimi | < 15% | 15-20% | > 20% |
| Naeiae | < 20% | 20-25% | > 25% |
| CHA&MOM | < 25% | 25-30% | > 30% |

---

## Bid Adjustment Presets

Fine-grained bid rules per campaign type:

### Manual Campaigns (Exact/Phrase)
```
desired_acos: per brand config (20-30%)
increase_by: 0.20         # +20% for high performers
decrease_by: 0.20         # -20% for underperformers
max_bid: per brand ($3-5)
min_bid: $0.10
high_acos: desired + 5%   # Above this = aggressive cut
mid_acos: desired          # Between mid and high = moderate cut
click_limit: 10            # Below this = insufficient data
impression_limit: 200
step_up: $0.05             # Incremental bid bump for low-impression keywords
```

### Auto Campaigns (Discovery)
```
desired_acos: per brand config (30-40%)
max_bid: $2.00-3.00
min_bid: $0.05
click_limit: 15            # Higher threshold (noisier data)
impression_limit: 300
```

### Bid Decision Matrix

| Condition | Action | Amount | Tier |
|-----------|--------|--------|------|
| ACOS < mid_acos AND clicks >= limit | Increase bid | +increase_by | Moderate |
| ACOS between mid and high | Hold | No change | Monitor |
| ACOS > high_acos AND clicks >= limit | Decrease bid | -decrease_by | Strong |
| Clicks >= limit AND sales = 0 | Decrease bid | -30% | No-Brainer |
| Impressions < limit AND clicks < 3 | Step up bid | +step_up | Moderate |
| Impressions = 0 for 7d | Pause keyword | - | No-Brainer |

---

## Search Term Optimization Flow

### Keyword Harvesting (Profitable Terms)
```
IF search_term.acos < desired_acos
AND search_term.clicks >= click_limit
AND search_term.sales >= 1
THEN (Tier: Strong Recommend):
  1. Add to exact match campaign with bid = search_term.cpc * 1.1
  2. Add as negative exact in source auto/broad campaign (prevent cannibalization)
  3. Log action to changelog
```

### Negative Keyword Addition (Unprofitable Terms)
```
IF search_term.spend > 3x target_cpa AND sales = 0
THEN (Tier: No-Brainer):
  1. Add as negative exact in campaign
  2. Priority: urgent

IF search_term.acos > 2x desired_acos AND clicks >= click_limit
THEN (Tier: Strong Recommend):
  1. Add as negative exact in campaign
  2. OR reduce bid to min_bid
  3. Priority: high
```

---

## Budget Forecasting & Seasonal Rules

### Daily Budget Depletion Check
```
IF campaign.daily_spend_rate > budget * 0.8 by noon
THEN: Flag "budget depleting"
ACTION: +20% budget if ROAS > 3.0 (Tier: Strong)

IF budget fully spent before 6PM
THEN: Flag "budget exhausted"
ACTION: +30% if ROAS > 2.5, else redistribute (Tier: No-Brainer if ROAS > 4.0)
```

### Seasonal Budget Multipliers
| Event | Dates | Budget Multiplier | Notes |
|-------|-------|-------------------|-------|
| Prime Day | July (TBD) | 2.0x - 3.0x | Ramp 5 days before |
| Back to School | Aug 1-Sep 15 | 1.3x | Gradual ramp |
| BFCM | Nov 20-Dec 2 | 2.5x - 4.0x | Highest competition |
| Holiday Season | Dec 1-24 | 1.5x - 2.0x | Sustained increase |
| Q1 Reset | Jan 1-31 | 0.7x - 0.8x | Lower CPMs, good for testing |

### Budget Reallocation Logic
```
70% -> Proven performers (ROAS > 3.0 sustained 14d+)
20% -> Growth candidates (ROAS 2.0-3.0, showing upward trend)
10% -> Testing (new campaigns, keyword expansion, new match types)
```

---

## Analysis Structure

### Three-Period Comparison (Required)
Every analysis must compare three time windows:
1. **Yesterday (yd)** - most recent single-day snapshot
2. **7-day average (7d)** - short-term trend
3. **30-day average (30d)** - baseline performance

### Anomaly Detection
Flag when any of these occur:
- Yesterday spend > 7-day average by 50%+
- Yesterday ROAS drops 30%+ vs 7-day average
- Zero sales campaigns with ongoing spend (7-day window)
- CTR drops below 0.3%
- ACOS spikes 50%+ vs 7-day average
- Single keyword consuming >40% of campaign budget
- **Cross-brand anomaly**: one brand craters while others stable -> brand-specific issue

### Report JSON Structure
```json
{
  "yesterday": "YYYY-MM-DD",
  "summary": {
    "yesterday": { "spend": 0, "sales": 0, "roas": 0, "acos": 0, "cpc": 0, "cvr": 0 },
    "7d": { "..." : "..." },
    "30d": { "..." : "..." }
  },
  "brand_breakdown": [
    { "brand": "...", "spend_7d": 0, "sales_7d": 0, "roas_7d": 0, "roas_7d_vs_30d_pct": 0 }
  ],
  "by_brand_campaigns": {
    "BrandName": [
      { "campaign": "...", "spend_yd": 0, "roas_yd": 0, "spend_7d": 0, "roas_7d": 0 }
    ]
  },
  "campaigns_7d": { "top5": [], "bottom5": [], "zero_sales": [] },
  "anomalies_detected": []
}
```

---

## Natural Language Query Guide

### Performance Analysis Queries

| What You Want | How to Ask |
|---------------|-----------|
| Overall health | "Show overall ROAS, ACOS, spend, sales for 7d and 30d across all brands" |
| Brand comparison | "Compare CHA&MOM vs Grosmimi ROAS and spend trend over last 30 days" |
| Top campaigns | "Which 10 campaigns have the highest ROAS in the last 14 days?" |
| Wasted spend | "Show campaigns with 7d spend > $50 and zero sales" |
| Budget check | "Which campaigns are spending >80% of daily budget before noon?" |
| Trend detection | "Show daily ROAS trend for last 30 days - improving or declining?" |
| Keyword analysis | "Top 20 keywords by sales in last 14d with ACOS, CPC, and impressions" |
| Cross-platform | "Compare Amazon ROAS vs Meta ROAS for Grosmimi this month" |

### Execution Queries

| What You Want | How to Ask |
|---------------|-----------|
| Generate proposals | "Run --propose for all brands" or "--propose --brand grosmimi" |
| Check pending | "What proposals are pending approval?" |
| Execute approved | "Execute all approved changes for Naeiae" |
| View changelog | "Show last 7 days of executed changes from the changelog" |
| Single brand | "Run PPC analysis for CHA&MOM only" |

---

## Amazon Ads API Notes

### Reporting v3 Async Flow
1. Submit report request -> get `reportId`
2. Poll status every 15s (600s deadline)
3. Download GZIP result on completion
4. Parse campaign-level daily metrics

### Campaign Management API
- `PUT /sp/campaigns` - Update campaign state/budget
- `PUT /sp/keywords` - Update keyword bid/state
- `POST /sp/negativeKeywords` - Add negative keywords
- `POST /sp/keywords` - Add new keywords
- `PUT /sp/targets` - Update ASIN target bids (requires `targetingClauses` wrapper)
- `POST /sp/targets/list` - List ASIN targets (state filter: `ENABLED` uppercase only)

### Known Quirks
- Campaign list API returns a LIST directly (not wrapped in object)
- Reporting v3 only returns ~60-90 days of history
- Report data has 2-3 day attribution lag
- campaignId/adGroupId/targetId must be **string** in API calls (not int)
- Use `-u` flag for unbuffered Python output
- Ads API uses separate LWA app from SP-API

### Key Metrics (14-day Attribution)
- `sales14d` - Sales attributed to ad click within 14 days
- `purchases14d` - Orders attributed within 14 days
- ACOS = (ad spend / ad sales) x 100 (lower = better)
- ROAS = ad sales / ad spend (higher = better, inverse of ACOS)

---

## Optimization Workflows

### Daily Health Check
1. Run `python tools/run_amazon_ppc_daily.py`
2. Review `.tmp/ppc_payload_YYYYMMDD.json` for raw data
3. Check overall ROAS vs brand-level breakdown
4. Flag zero-sales campaigns for immediate action
5. Apply ROAS Decision Framework for bid/budget changes

### Multi-Brand Propose Cycle
1. `python tools/amazon_ppc_executor.py --propose` (all 3 brands)
2. Receive 3 separate emails (Naeiae, Grosmimi, CHA&MOM)
3. Reply "execute" to any email to approve that brand's changes
4. Auto-execute workflow checks every 2 hours

### Keyword Harvesting Cycle (Weekly)
1. Pull search term report for last 14 days
2. Filter profitable terms: ACOS < desired_acos, sales >= 1, clicks >= 10
3. Add to exact match campaign, negate in source campaign
4. Pull unprofitable terms: spend > 3x CPA, sales = 0
5. Add as negative exact keywords

### Brand Comparison & Reallocation
1. Compare ROAS across CHA&MOM, Grosmimi, Naeiae
2. Identify which brand is improving vs declining
3. Check cross-platform (Meta, Google) for context
4. Recommend budget reallocation across brands

## Reference Documents

See `references/` directory for:
- `amazon-execution-rules.md` - Bid presets, search term rules, API execution details
- `amazon-query-patterns.md` - Natural language query examples and scoping guide
- `benchmarks.md` - Industry benchmarks and scoring
- `bidding-strategies.md` - Multi-platform bid optimization (Google, Meta, LinkedIn, TikTok, Microsoft)
- `budget-allocation.md` - Budget distribution best practices
- `conversion-tracking.md` - Attribution and tracking setup
- `scoring-system.md` - Performance scoring methodology
- `cross-platform-analysis.md` - **Google Ads + Meta + Shopify cross-platform decision rules, seasonal patterns, budget allocation formulas**
