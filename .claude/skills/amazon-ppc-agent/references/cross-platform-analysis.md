# Cross-Platform Analysis for Amazon PPC

## Purpose

Amazon PPC decisions should not be made in isolation. Google Ads, Meta Ads, Shopify DTC, and Amazon organic sales data provide critical context for bid/budget optimization.

## Data Sources & Granularity (DataKeeper)

### Aggregate-Level Data (Cross-Platform Context)

| Channel | Table | Key Fields | Granularity | Brand Filter |
|---------|-------|------------|-------------|--------------|
| Google Ads | `google_ads_daily` | `spend`, `conversion_value`, `clicks`, `impressions` | Daily × Campaign | By campaign name |
| Meta Ads | `meta_ads_daily` | `spend`, `purchase_value`, `purchases`, `reach` | Daily × Ad | By campaign name |
| Amazon Ads | `amazon_ads_daily` | `spend`, `sales`, `clicks`, `impressions` | Daily × Campaign | By profile_id |
| Amazon Sales | `amazon_sales_daily` | `gross_sales`, `net_sales`, `units`, `fees` | Daily × Seller × Brand | By seller_id |
| Shopify DTC | `shopify_orders_daily` | `gross_sales`, `net_sales`, `discounts`, `units` | Daily × Brand × Channel | By brand |
| GA4 | `ga4_daily` | `sessions`, `purchases` | Daily × Channel Grouping | No |
| Klaviyo | `klaviyo_daily` | `revenue`, `opens`, `clicks`, `conversions` | Daily × Source | No |

### Item-Level Data (Product Intelligence)

| Table | Key Fields | Granularity | Use Case |
|-------|------------|-------------|----------|
| `amazon_sales_sku_daily` | `asin`, `sku`, `product_name`, `units`, `ordered_product_sales`, `fees`, `net_sales` | Daily × ASIN × Seller | ASIN-level revenue, per-product ROAS, margin analysis |
| `shopify_orders_sku_daily` | `variant_id`, `sku`, `product_title`, `gross_sales`, `discounts`, `net_sales`, `units` | Daily × SKU × Brand × Channel | SKU-level revenue, discount analysis, cross-channel price comparison |
| `amazon_campaigns` | `campaign_id`, `name`, `status`, `budget`, `bid_strategy`, `campaign_type` | Campaign metadata (snapshot) | Campaign structure mapping |
| `meta_campaigns` | `campaign_id`, `name`, `objective`, `status`, `brand`, `campaign_type` | Campaign metadata (snapshot) | Cross-platform campaign structure |

### How Item-Level Data Informs PPC Decisions

```
ASIN-Level Revenue (amazon_sales_sku_daily)
  → Identify best-selling ASINs → allocate ad budget proportionally
  → Calculate per-ASIN full-cost margin → set max sustainable ACOS
  → Track ASIN revenue trends → detect declining products before ad waste

SKU-Level Shopify (shopify_orders_sku_daily)
  → Compare D2C vs Amazon pricing for same product → arbitrage detection
  → Identify influencer-driven products (PR channel SKUs) → boost Amazon ads
  → Track discount patterns → avoid cannibalizing full-price sales

Golmani Full-Cost Margin Framework:
  → AVG_COGS per brand: Grosmimi $8.41, Naeiae $5.35, CHA&MOM $7.53
  → FBA Fulfillment per unit: Grosmimi $5.39, Naeiae $3.50, CHA&MOM $4.25
  → Export costs (Korea→US): $0.50/unit (ocean freight + customs)
  → Return rate: 5% of revenue (FBA returns + refund processing)
  → Amazon cost waterfall per ASIN:
      Revenue
      - COGS (product cost per unit)
      - Referral Fee (15% of revenue, from amazon_sales_sku_daily.fees)
      - FBA Fulfillment (per unit, varies by size/weight)
      - Export Cost ($0.50/unit)
      - Return Cost (5% of revenue)
      = Contribution Margin (CM)
  → Max Sustainable ACOS = CM / Revenue
  → If campaign ACOS > Max Sustainable ACOS → product is losing money on ads
```

## Cross-Platform Decision Rules

### Rule 1: Multi-Channel ROAS Comparison

```
IF amazon_roas DROPS but google_roas + meta_roas STABLE:
    -> Amazon-specific issue (listing suppression, competitor undercut, BSR drop)
    -> Focus: Check listing quality, pricing, inventory
    -> Do NOT panic-cut Amazon budget

IF ALL channels drop simultaneously:
    -> Market/seasonal issue (post-holiday, tariff, macro)
    -> Focus: Reduce all channel budgets proportionally
    -> Wait for recovery signals before re-scaling

IF amazon_roas STABLE but google_roas DROPS:
    -> Google-specific issue (Quality Score, bid landscape)
    -> Amazon may benefit from budget reallocation FROM Google
```

### Rule 2: Budget Allocation Across Platforms

```
Total Ad Budget = Amazon Ads + Google Ads + Meta Ads

Optimal Split (baby products category):
    Amazon: 50-60% (highest purchase intent)
    Google: 20-30% (Shopping + Search, brand defense)
    Meta:   15-20% (awareness, retargeting)

Reallocation triggers:
    IF channel_roas > 1.5x avg_roas for 14d -> increase by 20%
    IF channel_roas < 0.5x avg_roas for 14d -> decrease by 20%
    Never reallocate more than 30% of any channel in single move
```

### Rule 3: Google Ads CPC as Amazon Bid Ceiling Signal

```
Google Search CPC for same keywords provides a market price signal:
    IF google_cpc for "baby straw cup" = $2.50
    AND amazon_cpc for same product keywords = $1.80
    -> Amazon is underpriced relative to market, room to increase bid

    IF google_cpc DROPS 30%+ week-over-week
    -> Market competition cooling, may see Amazon CPC follow
    -> Hold Amazon bids steady, don't chase

Google Shopping ROAS provides conversion quality benchmark:
    IF google_shopping_roas > amazon_sp_roas for same products
    -> Check Amazon listing quality (main image, A+ content, reviews)
    -> Amazon should convert at least as well as Google Shopping
```

### Rule 4: Meta Awareness -> Amazon Demand Lag

```
Meta spend increase -> 7-14 day lag -> Amazon organic search increase
    Track: meta_spend_7d vs amazon_organic_sales_next_7d

IF meta spend UP 50%+ AND amazon branded search UP 30%+:
    -> Meta awareness driving Amazon demand
    -> Increase Amazon brand defense bids (protect from competitors)
    -> Increase Amazon auto campaign budgets (capture new queries)

IF meta spend CUT and Amazon organic drops 2 weeks later:
    -> Confirms halo effect
    -> Don't cut meta without understanding Amazon impact
```

### Rule 5: Organic vs Ad Sales Ratio

```
FROM amazon_sales_daily (total) vs amazon_ads_daily (ad-attributed):
    ad_sales_ratio = ad_attributed_sales / total_marketplace_sales

Healthy ranges:
    < 20%: Very organic-heavy, ads may be under-invested
    20-40%: Balanced
    40-60%: Ad-dependent, watch for diminishing returns
    > 60%: Over-reliance on ads, focus on organic growth (reviews, SEO)

IF ad_sales_ratio INCREASING month-over-month:
    -> Organic declining, investigate: reviews dropping? competitor gaining?
    -> May need to invest in listing optimization before increasing ad budget
```

### Rule 6: Shopify DTC Price Sensitivity Signal

```
Shopify has full pricing transparency:
    IF shopify_aov DROPS 10%+ while volume steady:
        -> Customers price-shopping, market becoming price-sensitive
        -> Amazon bid strategy: emphasize value/bundling keywords
        -> Reduce bids on premium-positioned keywords

    IF shopify_conversion_rate DROPS but traffic stable:
        -> Product page or pricing issue
        -> Check if same happening on Amazon (conversion rate in ad reports)
```

## Implementation in Executor

### `fetch_cross_platform_context(brand_key, days=30)`
1. Queries DataKeeper for all 6 channels (7d + 30d windows)
2. Computes ROAS/CPC/CTR per channel
3. Generates actionable insights list
4. Builds HTML "Cross-Platform Context" section in proposal email

### `fetch_sku_level_context(brand_key, days=14)`
1. Queries `amazon_sales_sku_daily` and `shopify_orders_sku_daily`
2. Aggregates by ASIN/SKU: units, revenue, ASP, estimated COGS, margin
3. Computes max sustainable ACOS per ASIN using Golmani margin framework
4. Identifies thin-margin products, revenue concentration risks
5. Builds HTML "Product-Level Intelligence" section in proposal email

### Data Freshness Rule
**IMPORTANT:** Before running proposals, executor MUST verify DataKeeper has fresh data. If any channel returns empty, run `data_keeper.py` collection first — never send proposals with [NO DATA] sections.

Cross-platform and product-level data are **context** — they inform but do not override the ROAS Decision Framework thresholds for Amazon PPC actions.

## Google Ads Campaign Types (Reference)

Understanding Google Ads structure helps interpret the data:

| Type | Description | ROAS Benchmark | Relevance to Amazon |
|------|-------------|----------------|---------------------|
| Search | Keyword-based text ads | >= 4.0x | Direct overlap: same keywords, CPC comparison |
| Shopping | Product feed, image+price | >= 3.0x | Same products, conversion comparison |
| PMax | AI-optimized all inventory | >= 4.0x | Mixed signal (includes Display, YouTube) |
| Branded | Brand name defense | High (5-10x) | Amazon brand defense correlation |

## Google Ads Bidding Strategy Context

From `bidding-strategies.md`:
- `< 15 conv/30d`: Maximize Clicks (cold start)
- `15-29 conv`: Maximize Conversions
- `30+ conv`: Target CPA (1.1-1.2x historical)
- `50+ conv + values`: Target ROAS
- Brand protection: Target Impression Share (95-100%)

These stages affect Google Ads CPC stability — a Google campaign in learning phase produces noisy CPC data that shouldn't be used as Amazon bid reference.

## Seasonal Cross-Platform Patterns

| Season | Google Effect | Amazon Effect | Action |
|--------|-------------|---------------|--------|
| Prime Day (Jul) | CPC stable/slight up | CPC spikes 50-100% | Increase Amazon budget 2-3x, hold Google |
| BFCM (Nov) | CPC spikes 30-50% | CPC spikes 50-150% | Increase both, Amazon priority |
| Back to School (Aug-Sep) | CPC slight up | CPC moderate up | Baby products: mild impact |
| Q1 Reset (Jan) | CPC drops 20-30% | CPC drops 15-20% | Good testing period for both |
| Tax Season (Feb-Apr) | CPC stable | CPC stable | Normal operations |
