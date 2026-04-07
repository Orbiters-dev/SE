---
name: social-enricher
description: "Creator + Content Pool builder with Apify post-level metric enrichment (11 data points). Use when: building US content full export from Syncly sheets, enriching post metrics via Apify, filtering by engagement rate/platform/language/theme, syncing to PostgreSQL, or any task involving 'social enricher', 'content full', 'creator pool', 'post metrics'. Triggers: social enricher, content full, creator pool, content pool, post metrics, Apify enrich, PG sync, engagement rate filter"
---

# Social Enricher — Creator & Content Pool Builder

## When to Use This Skill

- "social enricher" / "enricher"
- "US content full export" / "creator pool"
- "post metrics" / "Apify enrich"
- "engagement rate filter" / "ER 3% over"
- "PG sync" / "PostgreSQL push"
- "platform instagram only" / "language en filter"
- Syncly sheet filtered creator+content export

## Architecture

```
Syncly Google Sheet (9K creators + 34K content)
    |
    v
build_us_content_full.py
+-- [1] Load cached tabs (data_crawler cache)
+-- [2] Blacklist removal (32 users)
+-- [3] Filter: views >= 2K OR likes >= 30
|       + Advanced: --min-er, --min-followers, --max-followers
|       + Advanced: --platform, --language
+-- [4] JOIN creators <-> content by username
|       + Content filters: --theme, --since
+-- [5a] Apify enrichment (--enrich) -> 11 data points
|       +-- IG posts -> apify/instagram-scraper
|       +-- TikTok posts -> clockworks/free-tiktok-scraper
|       +-- Cache: .tmp/data_crawler/enrich_cache.json
+-- [6] Write Excel (3 sheets)
|       +-- Creator Pool (username, email, followers, ER, bio...)
|       +-- Content Pool (post_url, views, likes, comments, ER, hashtags, media_type...)
|       +-- Flat View (creator + content joined)
+-- [7] PG Sync (--pg-sync)
        +-- gk_content_posts (posts)
        +-- gk_content_metrics_daily (daily snapshots)
```

## Data Points (11 per post via Apify)

| # | Field | IG Source | TikTok Source |
|---|-------|----------|---------------|
| 1 | views | videoViewCount | playCount |
| 2 | likes | likesCount | diggCount |
| 3 | comments | commentsCount | commentCount |
| 4 | caption | caption | text |
| 5 | hashtags | hashtags[].name | hashtags[].name |
| 6 | post_date | timestamp | createTimeISO |
| 7 | engagement_rate | (likes+comments)/views | same |
| 8 | media_type | type | "Video" |
| 9 | shortcode | shortCode | id |
| 10 | owner_followers | ownerFollowersCount | authorMeta.fans |
| 11 | thumbnail_url | displayUrl | videoMeta.coverUrl |

## Commands

```bash
# Basic export (uses cached metrics if available)
python tools/build_us_content_full.py

# Dry run
python tools/build_us_content_full.py --dry-run

# With Apify enrichment (fetches 11 data points per post)
python tools/build_us_content_full.py --enrich

# Custom thresholds
python tools/build_us_content_full.py --min-views 5000 --min-likes 50

# Engagement rate filter (3% minimum)
python tools/build_us_content_full.py --min-er 0.03

# Platform + language filter
python tools/build_us_content_full.py --platform instagram --language en

# Follower range
python tools/build_us_content_full.py --min-followers 1000 --max-followers 500000

# Theme + date filter
python tools/build_us_content_full.py --theme "baby,family" --since 2025-01-01

# Full pipeline: enrich + filters + PG sync
python tools/build_us_content_full.py --enrich --min-er 0.03 --pg-sync

# PG sync only (no Apify, uses cache)
python tools/build_us_content_full.py --pg-sync
```

## Filter Reference

### Creator-Level Filters
| Flag | Type | Default | Example |
|------|------|---------|---------|
| `--min-views` | int | 2000 | `--min-views 5000` |
| `--min-likes` | int | 30 | `--min-likes 50` |
| `--min-er` | float | 0 | `--min-er 0.03` (3%) |
| `--min-followers` | int | 0 | `--min-followers 1000` |
| `--max-followers` | int | 0 (no limit) | `--max-followers 500000` |
| `--platform` | str | all | `--platform instagram` |
| `--language` | str | all | `--language en` |

### Content-Level Filters
| Flag | Type | Default | Example |
|------|------|---------|---------|
| `--theme` | str | all | `--theme "baby,family"` |
| `--since` | str | all | `--since 2025-01-01` |

### ER Calculation
- Creator-level: `(likes_30d + comments_30d) / views_30d`
- Post-level: `(post_likes + post_comments) / post_views`

## Prerequisites

Cache must exist first. If not, run:
```bash
python tools/data_crawler.py --source "sheet:1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o" --sheet-name "Creators_updated" --dry-run
python tools/data_crawler.py --source "sheet:1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o" --sheet-name "Output_updated" --dry-run
python tools/data_crawler.py --source "sheet:1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o" --sheet-name "Mgmt_black_list" --dry-run
```

## Output

- Excel: `SYNCLY/US_Content_Full_YYYY-MM-DD.xlsx`
- Enrich cache: `.tmp/data_crawler/enrich_cache.json` (persists across runs)
- PG tables: `gk_content_posts`, `gk_content_metrics_daily`

## PG Schema Mapping

| Excel Sheet | PG Table | Key Columns |
|-------------|----------|-------------|
| Creator Pool | gk_content_posts | username, followers, bio_text, views_30d, likes_30d |
| Content Pool | gk_content_posts | post_id (shortcode), url, caption, hashtags, post_date |
| Metrics | gk_content_metrics_daily | post_id, date, views, likes, comments |

## Notes

- `--enrich` costs Apify credits. ~12K URLs in 50-URL chunks = ~240 API calls
- Enrichment cache persists — second run only scrapes new/missing URLs
- Existing 3-field cache is backward compatible (new fields default to empty)
- Blacklist from Mgmt_black_list tab + Blacklist column in Creators_updated
- Base filter is OR logic: views >= 2000 OR likes >= 30 (30-day aggregate)
- Advanced filters applied after base filter (AND logic)
- Content grouped per creator: content_num = 1, 2, 3...
- `--pg-sync` uses orbitools API (push_content_to_pg.py)
