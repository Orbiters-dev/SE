---
name: reference-dk-read-orbitools-mcp
description: orbitools-code-edit MCP datakeeper READ — 읽을 수 있는 6개 테이블 + 필터 제약
metadata:
  type: reference
---

# orbitools MCP datakeeper READ (code:read:datakeeper)

`mcp__orbitools-code-edit__dk_list_tables / dk_table_schema / dk_query_table` — allowlist 비-PII scalar만.

**읽을 수 있는 6개 (2026-07-01 실측):**
| domain | table |
|---|---|
| content | content_metrics_daily, content_posts |
| finance | amazon_sales_daily, shopify_orders_daily |
| seo | amazon_keepa_bsr_daily, gsc_daily |

**⚠️ meta_ads_daily / meta_campaigns / rakuten_ads_daily 는 READ 범위에 없음** → 메타·RPP 데이터는 이 MCP로 못 가져옴 (Graph API / RMS 별도).

**content_posts**: `id`(=CT-id, 광고명 토큰7 조인키), username, post_date, platform, brand(소문자 `grosmimi`), url, content_type, source, followers, *_30d, engagement_rate, hashtags, product_types(대체로 빈값), region.
- 필터는 `post_date/platform/brand/source/content_type/region`만 — **id/username/url 필터 없음** → 특정 크리에이터·CT코드 역조회는 brand+region 통째로 받아 스캔. grosmimi region 분포: jp 140 / "" 190 / us 340.

CT-id 조인 검증: 현재 JP 광고 15/16이 content_posts.id와 정확매칭. → [[reference-adname-framework-v1]]
