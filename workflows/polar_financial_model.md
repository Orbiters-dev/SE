# Polar Financial Model v3

## Objective
Generate a hierarchical, formula-driven Excel financial model from Polar Analytics data. The model covers Revenue, Ads, Organic, Contribution Margin, Campaign Summary, and Influencer Dashboard with 26 months of monthly data (Jan 2024 — Feb 2026).

## Output
- **File**: `Data Storage/Polar_Financial_Model.xlsx`
- **8 Tabs**: Revenue, Ads, Campaign Vintage, Organic, CM, Model Check, Campaign Summary, Influencer Dashboard

## Data Sources (Polar MCP Queries)

All data stored in `.tmp/polar_data/` as JSON files:

| File | Query | Dimensions | Metrics |
|------|-------|------------|---------|
| `q1_channel_brand_product.json` | Blended revenue (3D) | custom_5005 (Channel), custom_5036 (Brand), custom_5037 (Product) | blended_gross_sales, blended_discounts, blended_total_orders, blended_total_sales |
| `q2_shopify_brand.json` | Shopify costs | custom_5036 (Brand) | total_sales, orders, cost_of_products_custom, transaction_fees, CM1, CM2, gross_sales, discounts |
| `q3_amazon_brand.json` | Amazon costs | custom_5036 (Brand) | total_sales, orders, fees, COGS, gross_sales, promo_discounts, net_sales |
| `q5_amazon_ads_campaign.json` | Amazon Ads | campaign | cost, attributed_sales, clicks, impressions |
| `q6_facebook_ads_campaign.json` | Facebook Ads | campaign | spend, purchases_conversion_value, clicks, impressions |
| `q7_google_ads_campaign.json` | Google Ads | campaign | cost, conversion_value, clicks, impressions |
| `q8_tiktok_ads_campaign.json` | TikTok Ads | campaign | spend, purchases_conversion_value, clicks, impressions |

### Additional Data Sources (Optional, from fetch scripts)

| File | Source | Script | Purpose |
|------|--------|--------|---------|
| `q9_meta_campaign_ids.json` | Meta Graph API | `tools/fetch_meta_campaign_ids.py` | Campaign name→ID mapping for direct Meta Ads Manager links |
| `q10_influencer_orders.json` | Shopify Orders API | `tools/fetch_influencer_orders.py` | PR-tagged orders with fulfillment data |
| `q11_paypal_transactions.json` | PayPal Transaction API | `tools/fetch_paypal_transactions.py` | Payment data for paid/non-paid influencer classification |

## Layout Format (90 columns per tab)

Each metric section contains 3 horizontal blocks:

```
DATA BLOCK                          | % OF TOTAL      | YOY GROWTH
Col A:  Section label               |                 |
Col B:  Channel / TOTAL (level 0-1) |                 |
Col C:  Brand (level 2)             |                 |
Col D:  Product (level 3)           |                 |
Col E-AC: Monthly (Jan 2024-Jan 26) | Same months     | Same months
Col AD: Feb 2026 (Full-month)*      | Feb Full %      | Feb Full YoY
Col AE: Feb 18 2026 (partial)**     | Feb 18 %        | Feb 18 YoY
Col AF: YTD 2026                    | YTD %           | YTD YoY
[gap col]                           | [gap col]       |
```

*Full-month = actual × 28/18 extrapolation (PARTIAL_DAY=18, FULL_DAYS=28)
**Feb 18 2026 = actual partial-month data through Feb 18

### Formula Rules
- **Parent node totals**: `=SUM(child1, child2, ...)` with explicit cell refs (non-contiguous)
- **AOV**: `=IF(orders_cell=0, 0, gross_cell/orders_cell)`
- **Discount Rate**: `=IF(gross_cell=0, 0, disc_cell/gross_cell)`
- **ROAS**: `=IF(spend_cell=0, 0, revenue_cell/spend_cell)`
- **Diff metrics** (Gross Profit, CM): `=a_cell - b_cell`
- **Feb Full-month**: `=Feb18_cell * 28/18`
- **YTD data**: `=SUM(Jan_2026, Feb_Full-month)` (uses extrapolated full month)
- **YTD ratios**: `=IF(ytd_den=0, 0, ytd_num/ytd_den)`
- **% of Total**: `=IF(TOTAL_cell=0, 0, item_cell/TOTAL_cell)`
- **YoY Growth**: `=IF(ABS(prior_year)=0, 0, (current-prior)/ABS(prior))`
- **YTD YoY (ratio)**: computes prior-year YTD ratio from underlying numerator/denominator sections

### Display Rules
- **Zeros**: displayed as "-" (comma style format with dash for zero)
- **Borders**: only TOTAL rows have top/bottom borders; all other rows borderless
- **Sorting**: all hierarchy levels sorted by YTD Net Sales descending; "Other" always last

## Tab Details

### Tab 1: Revenue
Three sub-sections on one sheet:
- **1A**: Channel × Brand × Product (full 3-level hierarchy)
- **1B**: Brand × Product (2-level, aggregated across channels)
- **1C**: Product Category (flat, 1-level)

Each sub-section has 6 metric blocks: Gross Sales, Discounts, # of Orders, AOV, Discount Rate, Net Sales.

**B2B Wholesale Override (Feb 2026):** The $7,302 B2B Wholesale entry is automatically split into 5 Grosmimi products: Beige 10oz, Beige 6oz, Charcoal 6oz, Straw (2110), White 10oz — with their actual quantities and unit prices.

### Tab 2: Ads
Four sub-sections:
- **2A**: Ad Platform × Campaign Type × Brand
- **2B**: Landing Channel × Brand
- **2C**: Brand × Campaign Type
- **2D**: Campaign Type (flat)

Metrics: Ad Spend, Ad Revenue, Clicks, ROAS, CPC.

**Running Campaigns:** A standalone section at the bottom shows the count of campaigns with Spend > $0 per month.

### Tab 3: Campaign Vintage
Platform × Brand × Vintage Month × Campaign [Type] (4-level hierarchy). Shows campaign cohort analysis by first month of spend.

**Meta Ads Manager Links:** Facebook Ads campaign names in column E are hyperlinked to Meta Ads Manager for direct editing (requires q9_meta_campaign_ids.json).

### Tab 4: Organic
Channel × Brand hierarchy. Metrics: Total Revenue, Ad Revenue, Organic Revenue (=Total-Ad), Organic %.

### Tab 5: CM (Contribution Margin)
Channel × Brand hierarchy. Metrics: Net Sales, COGS, Gross Profit, Channel Fees, CM Before Ads, Ad Spend, CM After Ads.

COGS source: Shopify costs → non-Amazon channels, Amazon costs → Amazon channel.

### Tab 6: Model Check
Validation reference for verifying totals match across sub-sections.

### Tab 7: Summary
Multi-period dashboard with 4 sections, each showing 3 time windows (90d / 30d / 14d):

**Section 1 — Campaign Performance Rankings:**
- Top 5 / Worst 5 CVR Campaigns by ROAS (min $50 spend per window)
- Top 5 / Worst 5 Traffic Campaigns by CPC (lowest CPC = best)

**Section 2 — Ad Spend Summary:**
- Channel > Brand hierarchy (Spend, Revenue, ROAS, Clicks, CPC)
- Brand > Channel hierarchy (same metrics)

**Section 3 — Revenue Summary:**
- Channel > Brand hierarchy (Gross Sales, Discounts, Orders, AOV, Disc Rate, Net Sales)

**Section 4 — Organic Revenue Summary:**
- Channel > Brand hierarchy (Total Rev, Ad Rev, Organic Rev, Organic %)

### Tab 8: Influencer Dashboard
Only generated if q10_influencer_orders.json exists. Sections:
- **A. Monthly Shipped Count:** Total PR-tagged shipped orders per month
- **B. Monthly Shipped by Product:** 3-level hierarchy (Brand → Category → Product)
  - Columns: A(indicator) | B(Brand) | C(Category, collapse) | D(Product, collapse) | E+(monthly data)
  - Colors: TOTAL=MBLUE > Brand=LGRAY > Category=LLGRAY > Product=no fill
  - Category and Product rows collapsed by default (Excel row groups)
- **C. Paid vs Non-paid Split:**
  - PR + TikTok tagged → always Non-paid
  - PR only → matched against PayPal + Bill Pay transactions → Paid or Non-paid
- **D. PayPal / Bill Pay Influencer Payments:** Paid count + amount sent per month

#### Manual Bill Pay Overrides
Influencers paid via QuickBooks Bill Pay (not PayPal) — add to `MANUAL_INF_PAYMENTS` constant in [polar_financial_model.py](../tools/polar_financial_model.py):
| Name | Date | Amount |
|------|------|--------|
| Emily Krausz | 2026-01-05 | $4,500 |
| Emily Krausz | 2025-10-14 | $1,000 |
| Kathlyn Marie Sanga Flores | 2025-12-05 | $275 |
| Ehwa Lindsay | 2025-11-07 | $300 |
| Ehwa Lindsay | 2025-07-22 | $100 |
| Ehwa Lindsay | 2025-07-17 | $100 |
| Jessica Lim | 2025-01-21 | $500 |

## Pre-requisite: Fetch Scripts

Before running the model, optionally run these scripts to populate additional data:

```bash
# Meta campaign IDs (for direct links in Campaign Vintage tab)
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" -X utf8 tools/fetch_meta_campaign_ids.py

# Shopify PR orders (for Influencer Dashboard) — fetches from Jan 2024, full history
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" -X utf8 tools/fetch_influencer_orders.py

# PayPal transactions (for Paid/Non-paid classification)
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" -X utf8 tools/fetch_paypal_transactions.py
```

## How to Run

```bash
"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe" -X utf8 tools/polar_financial_model.py
```

## How to Refresh Data

1. Run Polar MCP queries (conversation_id needed) for each Q1-Q8
2. Save results to `.tmp/polar_data/` JSON files
3. (Optional) Run fetch scripts for q9, q10, q11
4. Run the script

## Environment Variables

Required in `.env`:
- `META_ACCESS_TOKEN` — Meta Graph API token (for fetch_meta_campaign_ids.py)
- `META_AD_ACCOUNT_ID` — Meta ad account ID (act_XXXXX)
- `SHOPIFY_SHOP` — Shopify store domain
- `SHOPIFY_ACCESS_TOKEN` — Shopify admin API token
- `PAYPAL_CLIENT_ID` — PayPal Business API client ID
- `PAYPAL_SECRET` — PayPal Business API secret

## Key Constants
- **BRANDS**: Grosmimi, Alpremio, Comme Moi, BabyRabbit, Naeiae, Bamboobebe, Hattung, CHA&MOM, Beemymagic, Nature Love Mere
- **Channel Map**: D2C→Onzenna, Target+→TargetPlus, Amazon variants→Amazon, PR→PR (net=0)
- **Product Categories**: 18 categories classified by keyword matching on product variant names
- **Campaign Types**: Amazon (SP/SB/SD), Facebook (CVR/Traffic/Other), Google (CVR), TikTok (CVR/Traffic/Other)

## Known Limitations
- Facebook Ads connector was "building" during data pull — FB data may be incomplete
- TikTok Ads: minimal spend ($6.8K total), mostly 2025 data
- PR channel: Net Sales forced to 0 (samples, not revenue)
- COGS only available for Shopify and Amazon channels
- PayPal name matching for Paid/Non-paid is case-insensitive but exact — fuzzy matching not implemented
- Meta campaign links require Meta access token to be valid (may expire)
