---
name: deep-crawler
description: >
  Deep Crawler — Apify-based profile + recent posts scraper for IG/TikTok creators.
  Discovers latest content from a list of handles, exports to Excel, optionally syncs to PG.
triggers:
  - 딥크롤러
  - deep crawler
  - 프로필 크롤링
  - 최근 포스트 긁어
  - 핸들로 검색
  - profile crawl
---

# Deep Crawler

Apify를 통해 크리에이터 핸들 목록에서 프로필 정보 + 최근 포스트를 긁어오는 도구.

## Architecture

```
Input (handles)
  |
  +-- --handles "a,b,c"        (comma-separated)
  +-- --handles-file file.txt  (one per line)
  +-- --from-syncly            (Syncly Creators_updated cache)
  |
  v
Cache Check (.tmp/deep_crawler/profile_cache.json)
  |  24h TTL per username
  v
Apify Scrape (batches of 20, 5s cooldown)
  |
  +-- IG: apify/instagram-profile-scraper
  +-- TT: clockworks/free-tiktok-scraper
  |
  v
Extract & Filter
  |  --max-posts, --min-post-views, --min-post-er
  v
Output
  +-- Excel (.tmp/deep_crawler/output/deep_crawl_YYYY-MM-DD.xlsx)
  +-- --pg-sync -> push_content_to_pg (content_posts + metrics)
  +-- --dry-run -> print summary only
```

## Commands

```bash
# Basic — comma handles
python tools/deep_crawler.py --handles "user1,user2,user3"

# From file
python tools/deep_crawler.py --handles-file creators.txt

# From Syncly cache (with min views filter)
python tools/deep_crawler.py --from-syncly --min-views 5000

# Filters
python tools/deep_crawler.py --handles "user1" --max-posts 10 --min-post-views 1000 --min-post-er 0.03

# Platform-specific
python tools/deep_crawler.py --handles "user1" --platform instagram
python tools/deep_crawler.py --handles "user1" --platform tiktok

# Dry run (no output file)
python tools/deep_crawler.py --handles "user1" --dry-run

# Custom output filename
python tools/deep_crawler.py --handles "user1" --output "my_report.xlsx"

# With PG sync
python tools/deep_crawler.py --handles "user1,user2" --pg-sync
```

## Output Paths

| Item | Path |
|------|------|
| Excel output | `.tmp/deep_crawler/output/deep_crawl_YYYY-MM-DD.xlsx` |
| Profile cache | `.tmp/deep_crawler/profile_cache.json` |
| Syncly cache (input) | `.tmp/data_crawler/cache/cache_..._Creators_updated.json` |

## Excel Sheets

- **Profiles** — one row per creator: username, platform, followers, following, bio, post_count, is_verified, crawled_posts_count
- **Posts** — one row per post: username, post_url, post_id, views, likes, comments, caption, hashtags, post_date, media_type, engagement_rate, thumbnail_url, platform

## Notes

- Cache TTL is 24 hours. Cached profiles skip Apify calls entirely.
- Apify batches are 20 handles per chunk with 5-second cooldown between chunks.
- `--pg-sync` maps to `push_content_to_pg.push_posts()` and `push_metrics()` using `source="deep_crawler"`, `region="us"`.
- `--from-syncly` reads column index 3 (Username) and optionally filters by column index 21 (views_30d).
- Requires `APIFY_TOKEN` in environment (loaded via `env_loader`).
- Dependencies: `apify-client`, `openpyxl`, `requests` (for PG sync).
