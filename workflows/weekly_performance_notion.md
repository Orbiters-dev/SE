# Workflow: Weekly Performance Report (Polar -> Notion)

## Objective

Pull weekly performance data from Polar Analytics (via MCP), calculate KPMs and OKR metrics, and create a Notion page replicating the Performance Team Weekly Report template.

**Auto-fills**: OKR table (ROAS, CAC, Email Open Rate) + Key Performance Metrics bullets (Ad Spend, Revenue, ROAS, CPA, Conversion Rate, Email CTR).

**Scope**: All ads EXCEPT Grosmimi Amazon PPC. Meta/Google/TikTok all included.

---

## Prerequisites

### .env Required Keys

```
NOTION_API_TOKEN=ntn_xxx
```

Optional override:
```
WEEKLY_REPORT_NOTION_DB_ID=2fb86c6dc04680988f1fe3a5803eb4f0
```

### Polar Data Files

JSON files must exist in `.tmp/weekly_polar_data/` before running the script. These are generated via Claude + Polar MCP tools (see Phase A below).

---

## Two-Phase Flow

### Phase A: Polar Data Collection (Claude MCP)

Run these 7 queries in Claude using Polar MCP tools. Save results to `.tmp/weekly_polar_data/`.

| File | Query | Key Metrics | Notes |
|------|-------|-------------|-------|
| `wk_meta_ads_weekly.json` | Facebook Ads by campaign | spend, purchases_conversion_value, clicks, impressions | weekly granularity |
| `wk_google_ads_weekly.json` | Google Ads by campaign | cost, conversion_value, clicks, impressions | weekly granularity |
| `wk_tiktok_ads_weekly.json` | TikTok Ads by campaign | spend, purchases_conversion_value, clicks, impressions | weekly granularity |
| `wk_amazon_ads_weekly.json` | Amazon Ads by campaign | cost, attributed_sales, clicks, impressions | Script filters Grosmimi |
| `wk_shopify_weekly.json` | Shopify D2C | gross_sales, total_sales, total_orders | No campaign dimension |
| `wk_ga4_weekly.json` | GA4 | sessions, ecommerce_purchases | No campaign dimension |
| `wk_klaviyo_weekly.json` | Klaviyo | open_rate, click_rate, sends, revenue | No campaign dimension |

**Query Parameters**:
- `dateRangeFrom`: 3 weeks before target week Monday (e.g., 2026-02-02 for W08)
- `dateRangeTo`: Target week Sunday (e.g., 2026-02-22 for W08)
- `granularity`: `week`
- Ads queries: include `campaign` dimension (for brand classification)

### Phase B: Script Execution

```bash
python tools/weekly_performance_notion.py --week 2026-W08
```

---

## How to Run

### Step 1: Discover (Check Data + Notion DB)

```bash
python tools/weekly_performance_notion.py --discover
```

Shows:
- Which JSON data files exist and their date ranges
- Notion database connection and properties

### Step 2: Dry Run (Verify Numbers)

```bash
python tools/weekly_performance_notion.py --week 2026-W08 --dry-run
```

Prints all calculated metrics without creating a Notion page. Use this to verify numbers before creating the actual page.

### Step 3: Create Notion Page

```bash
python tools/weekly_performance_notion.py --week 2026-W08
```

Creates the page in Notion with:
- Page properties: Title, Report Date, Team, Member
- 5-section template with auto-filled numbers in Section 2
- Placeholder text in Sections 1, 3, 4, 5 (filled manually)

---

## Metric Definitions

| Metric | Formula | Source |
|--------|---------|--------|
| Total Ad Spend | meta.spend + google.cost + tiktok.spend + amazon_filtered.cost | All ad platforms |
| Revenue Generated | shopify.total_sales | Shopify |
| Overall ROAS | (meta.conv_value + google.conv_value + tiktok.conv_value + amazon.attributed_sales) / Total Ad Spend | Ad platforms |
| CPA | Total Ad Spend / shopify.total_orders | Ad platforms + Shopify |
| Conversion Rate | ga4.ecommerce_purchases / ga4.sessions x 100 | GA4 |
| Email Open Rate | klaviyo.campaign_unique_open_rate x 100 | Klaviyo |
| Email CTR | klaviyo.campaign_unique_click_rate_excl_bot x 100 | Klaviyo |

**Amazon Filtering**: Campaigns are classified by keywords (`cha&mom` -> CHA&MOM, `naeiae` -> Naeiae, etc.). Default = Grosmimi. Only non-Grosmimi campaigns are included.

---

## OKR Targets

Defined as `OKR_TARGETS` constant at the top of the script. Update quarterly.

```python
OKR_TARGETS = {
    "roas": 3.0,
    "cac": 25.00,
    "email_open_rate": 50.0,
}
```

**Status Logic**:
- On Track (green): >= 100% of target
- At Risk (yellow): >= 80% of target
- Behind (red): < 80% of target

CAC uses inverse logic (lower is better).

---

## Notion Page Structure

| Section | Content | Auto-filled? |
|---------|---------|:---:|
| Header | Team, Week, Member | Yes |
| 1. Focus Areas | Primary focus, campaigns, time allocation | No (placeholder) |
| 2. Results (OKRs) | OKR table + KPM bullets | **Yes** |
| 3. Issues | Challenges, blockers, resource needs | No (placeholder) |
| 4. Problem Solving | Solutions, learnings, best practices | No (placeholder) |
| 5. Next Week | Planned tasks, KR focus, support needed | No (placeholder) |

---

## Troubleshooting

- **Missing data file**: Run Phase A Polar MCP queries again
- **Notion 401**: Check `NOTION_API_TOKEN` in `.env`
- **Notion 404**: Ensure the integration is connected to the database
- **Week format error**: Use ISO format `YYYY-Wnn` (e.g., `2026-W08`)
- **Zero values**: Check if the platform had data for that week (e.g., TikTok may have no spend)
