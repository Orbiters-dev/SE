---
name: data-keeper
description: "Centralized data collection gateway for all advertising and sales metrics. Use when running daily data collection, checking data freshness, querying cached metrics, diagnosing missing data, or managing the unified data pipeline. Covers Amazon Ads, Amazon Sales, Meta Ads, Google Ads, GA4, Klaviyo, and Shopify."
---

# Data Keeper - Unified Data Gateway

## When to Use This Skill

Use this skill when you need to:
- Run daily data collection (all channels or specific ones)
- Check data freshness and collection status
- Query cached advertising/sales data
- Diagnose missing or stale data
- Understand the data pipeline architecture

## Architecture

```
PST 0:00 / 12:00 (2x daily)
        |
        v
  data_keeper.py (collector)
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

## Data Sources (7 Channels)

| Channel | Table | API | Lookback |
|---------|-------|-----|----------|
| Amazon Ads | `amazon_ads_daily` | Reporting v3 (async) | 35d |
| Amazon Sales | `amazon_sales_daily` | SP-API flat-file | 35d |
| Meta Ads | `meta_ads_daily` | Graph API v18 insights | 35d |
| Google Ads | `google_ads_daily` | search_stream | 35d |
| GA4 | `ga4_daily` | Analytics Data API | 35d |
| Klaviyo | `klaviyo_daily` | REST API | 35d |
| Shopify | `shopify_orders_daily` | Admin REST API | 35d |

## Commands

### Collect All
```bash
python tools/data_keeper.py
```

### Collect Specific Channel
```bash
python tools/data_keeper.py --channel amazon_ads
python tools/data_keeper.py --channel meta
python tools/data_keeper.py --channel shopify
```

### Check Status
```bash
python tools/data_keeper.py --status
```

### Local Only (skip PostgreSQL)
```bash
python tools/data_keeper.py --skip-pg
```

### Custom Lookback
```bash
python tools/data_keeper.py --days 60
```

## Client Library (for Consumer Tools)

```python
from data_keeper_client import DataKeeper

dk = DataKeeper()

# Get last 30 days of Amazon Ads data
rows = dk.get("amazon_ads_daily", days=30)

# Filter by brand
rows = dk.get("amazon_ads_daily", days=30, brand="CHA&MOM")

# Date range query
rows = dk.get("meta_ads_daily", date_from="2026-02-01", date_to="2026-03-06")

# Check freshness (within 14 hours = 2x/day schedule)
if dk.is_fresh("amazon_ads_daily"):
    rows = dk.get("amazon_ads_daily", days=30)
else:
    print("Cache stale - run data_keeper.py first")
```

## PostgreSQL Tables

All tables use `gk_` prefix. Upsert on unique keys.

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
| `gk_klaviyo_daily` | (date, source_type, source_id) |

## Orbitools API Endpoints

- `POST /api/datakeeper/save/` - Bulk upsert rows
- `GET /api/datakeeper/query/?table=...&date_from=...&brand=...` - Query rows
- `GET /api/datakeeper/tables/` - List tables with row counts
- `GET /api/datakeeper/status/` - Latest collection timestamps

## Brand Detection

All channels use consistent brand detection:
- **Grosmimi**: campaign/product name contains "grosmimi"
- **CHA&MOM**: contains "cha&mom", "chamom", "orbitool"
- **Naeiae**: contains "naeiae", "fleeters"
- **Onzenna**: contains "onzenna", "zezebaebae"
- **Alpremio**: contains "alpremio"

## Consumer Migration Guide

Before (direct API):
```python
# OLD: Each tool fetches its own data
resp = requests.get("https://graph.facebook.com/...")
```

After (Data Keeper):
```python
# NEW: Read from cached/PG data
from data_keeper_client import DataKeeper
dk = DataKeeper()
rows = dk.get("meta_ads_daily", days=30)
```

## Cron Schedule (PST)

```
# PST 0:00 - Full daily collection (yesterday's complete data)
0 8 * * * cd /path/to/project && python tools/data_keeper.py

# PST 12:00 - Midday refresh (intraday monitoring)
0 20 * * * cd /path/to/project && python tools/data_keeper.py
```

Note: Cron uses UTC. PST 0:00 = UTC 8:00, PST 12:00 = UTC 20:00.

## Files

- `tools/data_keeper.py` - Main collector (7 channel collectors)
- `tools/data_keeper_client.py` - Client library for consumers
- `datakeeper/models.py` - Django models (9 tables)
- `datakeeper/views.py` - API endpoints (save, query, tables, status)
- `datakeeper/urls.py` - URL routing
- `.tmp/datakeeper/*.json` - Local cache files
