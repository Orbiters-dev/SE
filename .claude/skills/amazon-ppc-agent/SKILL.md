---
name: amazon-ppc-agent
description: "Expert Amazon PPC campaign analysis, optimization, and execution agent. Use when analyzing Amazon Ads performance, diagnosing campaign issues, reviewing PPC daily reports, making bid/budget recommendations, executing bid/budget changes, harvesting keywords, or optimizing ROAS/ACOS. Covers Sponsored Products, Sponsored Brands, and Sponsored Display across multiple seller profiles."
---

# Amazon PPC Analysis, Optimization & Execution Skill

## When to Use This Skill

Use this skill when you need to:
- **Analyze** daily/weekly/monthly Amazon Ads performance data
- **Diagnose** campaign-level issues (high ACOS, low ROAS, wasted spend)
- **Execute** bid and budget adjustments via Amazon Ads API
- **Harvest** keywords from search term reports
- **Forecast** budget depletion and seasonal adjustments
- **Query** performance data using natural language patterns
- Analyze the daily PPC HTML report (`tools/run_amazon_ppc_daily.py` output)
- Compare performance across brands and time periods

## Skill Capabilities

### Layer 1: Analysis (Read-Only)
- Daily health check and anomaly detection
- Three-period comparison (yesterday / 7d / 30d)
- Brand-level and campaign-level breakdown
- Wasted spend audit
- Search term profitability analysis

### Layer 2: Recommendations (Proposal)
- Bid adjustments per ROAS Decision Framework
- Budget reallocation across campaigns/brands
- Keyword harvesting (profitable search terms -> exact match)
- Negative keyword additions (unprofitable search terms)
- Seasonal budget recommendations (Prime Day, BFCM, Q4)

### Layer 3: Execution (Write - Approval Required)
- `--propose`: Generate and email change proposals
- `--execute`: Apply only human-approved changes via API
- Change logging to Google Sheets
- Email confirmation trail

## Project Context

### Managed Brands & Profiles

| Profile Name    | Brand     | Notes |
|-----------------|-----------|-------|
| Orbitool        | CHA&MOM   | Primary brand, improving trend |
| GROSMIMI USA    | Grosmimi  | Established brand |
| Fleeters Inc    | Naeiae    | Executor target. API timeout on campaign list (20s limit) |

### Tools

| Tool | Purpose | Command |
|------|---------|---------|
| `run_amazon_ppc_daily.py` | Daily analysis report | `python tools/run_amazon_ppc_daily.py --dry-run` |
| `amazon_ppc_executor.py` | Bid/budget execution | `python tools/amazon_ppc_executor.py --propose` |

### Daily Report Tool
- API: Amazon Ads Reporting v3 (async: submit -> poll 15s intervals -> download GZIP)
- Analysis: Claude API (claude-sonnet-4-6) with PPC expert system prompt
- Output: HTML email + `.tmp/ppc_report_YYYYMMDD.html` + `.tmp/ppc_payload_YYYYMMDD.json`

### Executor Tool
- Target: Fleeters Inc (Naeiae) only
- Approval: Nothing executes without explicit `"approved": true`
- Budget caps: $120/day total, $50/campaign max, $3 bid max
- Logging: Google Sheets change log + email trail
- Output: `.tmp/ppc_proposal_YYYYMMDD.json` + `.tmp/ppc_executed_YYYYMMDD.json`

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
1. Daily Analysis:
   Ads API (Reporting v3 async) → .tmp/ppc_payload_YYYYMMDD.json
     → Claude analysis (claude-sonnet-4-6) → .tmp/ppc_report_YYYYMMDD.html → Gmail

2. Execution (Fleeters Inc only):
   Payload → .tmp/ppc_proposal_YYYYMMDD.json → Human approval
     → API execution → .tmp/ppc_executed_YYYYMMDD.json → Google Sheets changelog

3. Content Tracking (separate pipeline):
   fetch_syncly_export.py → CSV → sync_syncly_to_sheets.py → Google Sheets D+60 Tracker
```

### Known Issues & Fixes

| Issue | Fix |
|-------|-----|
| Python output buffered in background | Use `-u` flag for unbuffered output |
| Fleeters Inc hangs on campaign list | `timeout=20` set to fail fast |
| Reporting v3 only ~60-90 days history | 400 error for older dates; use SP-API for historical |
| Campaign list returns LIST directly | Not wrapped in `{"campaigns": {...}}` — check `isinstance(data, dict)` |
| Wrong payload key | `payload['summary']['30d']` not `payload['summary']['total_30d']` |
| Emoji in print() crashes on Windows | cp949 UnicodeEncodeError — use ASCII text only |
| Attribution lag | Report data has 2-3 day lag (14-day attribution window) |

### Dayparting Analysis

Amazon Ads does not provide hourly performance data natively.
- Use **budget depletion time** as a proxy for traffic distribution
- If budget exhausted before 6PM → traffic is front-loaded, consider budget increase
- For true dayparting, use Amazon DSP or third-party tools (Perpetua, Pacvue)

### Cross-Platform Context

- This brand also runs **Meta Ads** (see `meta-ads-agent` skill)
- Combined ROAS tracked in the financial model (`tools/no_polar/`)
- **Shopify** is the primary DTC storefront
- Amazon sales data: `tools/no_polar/fetch_amazon_sales_monthly.py` (Q3)
- Amazon ads monthly: `tools/no_polar/fetch_amazon_ads_monthly.py` (Q5)

---

## ROAS Decision Framework (MANDATORY)

These thresholds are hardcoded in the daily report system prompt and executor:

| 7-Day ROAS | Action | Bid Change | Budget Change | Priority |
|------------|--------|------------|---------------|----------|
| < 1.0      | **pause** | - | - | urgent |
| 1.0 ~ 1.5  | reduce_bid | -30% | - | urgent |
| 1.5 ~ 2.0  | reduce_bid | -15% | - | high |
| 2.0 ~ 3.0  | monitor | - | - | medium |
| 3.0 ~ 5.0  | increase_budget | - | +20% | medium |
| > 5.0      | increase_budget | +10% | +30% | high |

**Drop rule:** Yesterday ROAS drops 30%+ vs 7-day average -> reduce_bid -20% additional.

### ROAS Color Coding
- Green (good): ROAS >= 3.0
- Orange (warning): ROAS 2.0 ~ 3.0
- Red (danger): ROAS < 2.0

### ACOS Thresholds
- Green: ACOS < 15%
- Orange: ACOS 15% ~ 25%
- Red: ACOS > 25%

---

## Bid Adjustment Presets

Fine-grained bid rules per campaign type (inspired by production presets):

### Manual Campaigns (Exact/Phrase)
```
desired_acos: 0.25        # 25% target
increase_by: 0.20         # +20% for high performers
decrease_by: 0.20         # -20% for underperformers
max_bid: $3.00
min_bid: $0.10
high_acos: 0.30           # Above this = aggressive cut
mid_acos: 0.25            # Between mid and high = moderate cut
click_limit: 10           # Below this = insufficient data
impression_limit: 200     # Below this = insufficient data
step_up: $0.05            # Incremental bid bump for low-impression keywords
```

### Auto Campaigns (Discovery)
```
desired_acos: 0.35        # Looser target for discovery
max_bid: $2.00
min_bid: $0.05
click_limit: 15           # Higher threshold (noisier data)
impression_limit: 300
```

### Bid Decision Matrix

| Condition | Action | Amount |
|-----------|--------|--------|
| ACOS < mid_acos AND clicks >= click_limit | Increase bid | +increase_by (max: max_bid) |
| ACOS between mid_acos and high_acos | Hold | No change |
| ACOS > high_acos AND clicks >= click_limit | Decrease bid | -decrease_by (min: min_bid) |
| Clicks >= click_limit AND sales = 0 | Decrease bid | -30% (min: min_bid) |
| Impressions < impression_limit AND clicks < 3 | Step up bid | +step_up (max: max_bid) |
| Impressions = 0 for 7d | Pause keyword | - |

---

## Search Term Optimization Flow

### Keyword Harvesting (Profitable Terms)
```
IF search_term.acos < desired_acos
AND search_term.clicks >= click_limit
AND search_term.sales >= 1
THEN:
  1. Add to exact match campaign with bid = search_term.cpc * 1.1
  2. Add as negative exact in source auto/broad campaign (prevent cannibalization)
  3. Log action to changelog
```

### Negative Keyword Addition (Unprofitable Terms)
```
IF search_term.spend > 3x target_cpa AND sales = 0
THEN:
  1. Add as negative exact in campaign
  2. Priority: urgent

IF search_term.acos > 2x desired_acos AND clicks >= click_limit
THEN:
  1. Add as negative exact in campaign
  2. OR reduce bid to min_bid
  3. Priority: high
```

### Search Term Query Patterns

When analyzing search terms, use these natural language patterns:

```
"For the last 14 days, which search terms have spend > $10 but zero sales?
Include campaign name, ad group, search term, match type, cost, impressions, clicks."

"Show top 20 search terms by sales in the last 14 days.
Include ACOS, cost, clicks, impressions, and source campaign."

"Which search terms have ACOS < 15% and 3+ sales in the last 30 days?
These are keyword harvesting candidates."

"Show search terms with 20+ clicks but 0 sales in the last 7 days.
These are negative keyword candidates."
```

---

## Budget Forecasting & Seasonal Rules

### Daily Budget Depletion Check
```
IF campaign.daily_spend_rate > campaign.daily_budget * 0.8 by noon
THEN: Flag "budget depleting" - campaign may miss afternoon/evening traffic
ACTION: Consider +20% budget if ROAS > 3.0

IF campaign.daily_budget fully spent before 6PM
THEN: Flag "budget exhausted"
ACTION: Increase budget +30% if ROAS > 2.5, else redistribute from low-ROAS campaigns
```

### Seasonal Budget Multipliers
| Event | Dates | Budget Multiplier | Notes |
|-------|-------|-------------------|-------|
| Prime Day | July (TBD) | 2.0x - 3.0x | Ramp 5 days before, peak on event days |
| Back to School | Aug 1-Sep 15 | 1.3x | Gradual ramp |
| Halloween | Oct 15-31 | 1.2x | Category dependent |
| BFCM | Nov 20-Dec 2 | 2.5x - 4.0x | Highest competition. Ramp 7 days before |
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

### Report JSON Structure
```
{
  "yesterday": "YYYY-MM-DD",
  "summary": {
    "yesterday": { spend, sales, roas, acos, impressions, clicks },
    "7d": { ... },
    "30d": { ... }
  },
  "brand_breakdown": [
    { brand, spend_7d, sales_7d, roas_7d, spend_30d, sales_30d, roas_30d, ... }
  ],
  "by_brand_campaigns": {
    "BrandName": [
      { name, spend_yd, roas_yd, spend_7d, roas_7d, spend_30d, roas_30d, ... }
    ]
  },
  "campaigns_7d": {
    "top": [...],
    "worst": [...],
    "zero_sales": [...]
  },
  "anomalies_detected": [...]
}
```

---

## Natural Language Query Guide

### Performance Analysis Queries

| What You Want | How to Ask |
|---------------|-----------|
| Overall health | "Show overall ROAS, ACOS, spend, sales for 7d and 30d across all brands" |
| Brand comparison | "Compare CHA&MOM vs Grosmimi ROAS and spend trend over last 30 days" |
| Top campaigns | "Which 10 campaigns have the highest ROAS in the last 14 days? Include spend and sales" |
| Wasted spend | "Show campaigns with 7d spend > $50 and zero sales" |
| Budget check | "Which campaigns are spending >80% of daily budget before noon?" |
| Trend detection | "Show daily ROAS trend for last 30 days - is it improving or declining?" |
| Keyword analysis | "Top 20 keywords by sales in last 14d with ACOS, CPC, and impressions" |

### Execution Queries

| What You Want | How to Ask |
|---------------|-----------|
| Generate proposals | "Run --propose for Fleeters Inc and email the proposal" |
| Check pending | "What proposals are pending approval?" |
| Execute approved | "Execute all approved changes from today's proposal" |
| View changelog | "Show last 7 days of executed changes from the changelog" |

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

### Known Quirks
- Campaign list API returns a LIST directly (not wrapped in `{"campaigns": {...}}`)
- Reporting v3 only returns ~60-90 days of history (400 error for older dates)
- Report data has 2-3 day attribution lag
- `Fleeters Inc` profile hangs on campaign list -> 20s timeout set to fail fast
- Use `-u` flag for unbuffered Python output when running in background
- Ads API uses separate LWA app from SP-API (different Client ID/Secret)

### Key Metrics (14-day Attribution)
Amazon Ads uses 14-day attribution windows:
- `sales14d` - Sales attributed to ad click within 14 days
- `purchases14d` - Orders attributed within 14 days
- ACOS = (ad spend / ad sales) x 100 (lower = better)
- ROAS = ad sales / ad spend (higher = better, inverse of ACOS)

---

## Optimization Workflows

### Daily Health Check
1. Run `python tools/run_amazon_ppc_daily.py --dry-run`
2. Review `.tmp/ppc_payload_YYYYMMDD.json` for raw data
3. Check overall ROAS vs brand-level breakdown
4. Flag zero-sales campaigns for immediate action
5. Apply ROAS Decision Framework for bid/budget changes

### Wasted Spend Audit
1. Identify campaigns with 7d spend > $50 and zero sales
2. Check keyword-level data for high-spend, no-conversion terms
3. Recommend: pause, negative keyword, or bid reduction per ROAS bands

### Keyword Harvesting Cycle (Weekly)
1. Pull search term report for last 14 days
2. Filter profitable terms: ACOS < desired_acos, sales >= 1, clicks >= click_limit
3. Add to exact match campaign, negate in source campaign
4. Pull unprofitable terms: spend > 3x CPA, sales = 0
5. Add as negative exact keywords

### Brand Comparison
1. Compare ROAS across CHA&MOM, Grosmimi, Naeiae
2. Identify which brand is improving vs declining
3. Recommend budget reallocation across brands

### Execution Cycle (Fleeters Inc)
1. `python tools/amazon_ppc_executor.py --propose` - Generate proposals
2. Review email / `.tmp/ppc_proposal_YYYYMMDD.json`
3. Approve items: set `"approved": true`
4. `python tools/amazon_ppc_executor.py --execute` - Apply changes
5. Verify in changelog and confirmation email

## Reference Documents

See `references/` directory for:
- `amazon-execution-rules.md` - Bid presets, search term rules, API execution details
- `amazon-query-patterns.md` - Natural language query examples and scoping guide
- `benchmarks.md` - Industry benchmarks and scoring
- `bidding-strategies.md` - Bid optimization strategies (cross-platform)
- `budget-allocation.md` - Budget distribution best practices
- `conversion-tracking.md` - Attribution and tracking setup
- `scoring-system.md` - Performance scoring methodology
