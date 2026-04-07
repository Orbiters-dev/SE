---
name: social-enricher
description: "Creator + Content Pool builder with Apify post-level metric enrichment. Use when: building US content full export from Syncly sheets, enriching post metrics (views/likes/comments) via Apify, extracting filtered creator pools with content grouping, or any task involving '소셜 enricher', 'content full', 'creator pool', 'post metrics'. Triggers: 소셜enricher, social enricher, content full, creator pool, content pool, 포스트 메트릭, post metrics, Apify enrich"
---

# Social Enricher — Creator & Content Pool Builder

## When to Use This Skill

- "소셜 enricher" / "social enricher"
- "US content full 뽑아줘" / "크리에이터 풀 만들어줘"
- "포스트별 뷰수 채워줘" / "Apify로 메트릭 긁어줘"
- "Content Pool 엑셀 업데이트"
- Syncly 시트에서 필터링된 크리에이터+콘텐츠 export

## Architecture

```
Syncly Google Sheet (9K creators + 34K content)
    │
    ▼
build_us_content_full.py
├── [1] Load cached tabs (data_crawler cache)
├── [2] Blacklist removal (32 users)
├── [3] Filter: views >= 2K OR likes >= 30
├── [4] JOIN creators ↔ content by username
├── [5a] Apify enrichment (--enrich)
│     ├── IG posts → apify/instagram-scraper
│     └── TikTok posts → clockworks/free-tiktok-scraper
│     └── Cache: .tmp/data_crawler/enrich_cache.json
└── [6] Write Excel (3 sheets)
      ├── Creator Pool (username, email, followers, bio...)
      ├── Content Pool (post_url, post_views, post_likes, transcript...)
      └── Flat View (creator + content joined)
```

## Commands

```bash
# Basic export (no Apify, uses cached metrics if available)
python tools/build_us_content_full.py

# Dry run — see counts without writing
python tools/build_us_content_full.py --dry-run

# With Apify enrichment (fetches per-post views/likes/comments)
python tools/build_us_content_full.py --enrich

# Custom thresholds
python tools/build_us_content_full.py --min-views 5000 --min-likes 50

# Full pipeline: enrich + custom thresholds
python tools/build_us_content_full.py --enrich --min-views 5000 --min-likes 50
```

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

## PG Schema Mapping

| Excel Sheet | PG Table | Key Columns |
|-------------|----------|-------------|
| Creator Pool | creator_pool | username, email, platform, followers, bio_text |
| Content Pool | content_pool | username (FK), post_url, post_views, post_likes, post_comments, transcript |

## Notes

- `--enrich` costs Apify credits. ~12K URLs in 50-URL chunks = ~240 API calls
- Enrichment cache persists — second run only scrapes new/missing URLs
- Blacklist is from Mgmt_black_list tab + Blacklist column in Creators_updated
- Filter is OR logic: views >= 2000 OR likes >= 30 (both 30-day aggregate)
- Content grouped per creator: content_num = 1, 2, 3...
