# KPI Data Taxonomy -- Classification, Computation & Quality Rules

Authoritative reference for how ORBI data is classified, computed, and validated.
All metric formulas trace back to `tools/data_keeper.py` and `tools/run_kpi_monthly.py`.

---

## 1. DataKeeper Table Schemas

### `shopify_orders_daily` (Primary Revenue Source)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str (YYYY-MM-DD) | Order date |
| `brand` | str | Detected brand (Grosmimi, Naeiae, CHA&MOM, Onzenna, Alpremio, Unknown) |
| `channel` | str | Classified channel (D2C, Amazon, B2B, TikTok, PR, Unknown) |
| `gross_sales` | float | Reference price x qty (before discounts) |
| `discounts` | float | Total discount amount (ref_price - sell_price + coupons) |
| `net_sales` | float | Actual revenue received (sell_price x qty - coupons) |
| `orders` | int | Order count |
| `units` | int | Unit count |
| `refunds` | float | Refund amount |

**Identity:** `gross_sales - discounts = net_sales` (always holds)

### `shopify_orders_sku_daily` (Shopify Line-Item Level — Most Granular)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str (YYYY-MM-DD) | Order date |
| `brand` | str | Line-item brand (more precise than order-level detection) |
| `channel` | str | Same classification as shopify_orders_daily |
| `variant_id` | str | Shopify variant ID |
| `sku` | str | Seller SKU |
| `product_title` | str | Product name from Shopify |
| `gross_sales` | float | Reference price × qty |
| `discounts` | float | Discount amount |
| `net_sales` | float | Actual revenue |
| `units` | int | Units sold |

**Unique key:** `(date, brand, channel, variant_id)`
**Source:** Collected as side effect of collect_shopify() — same API call, no extra cost.
**Use for:** SKU-level revenue analysis, COGS mapping, product-level discount analysis.

---

### `amazon_sales_daily` (Amazon Marketplace via SP-API)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | Sales date |
| `seller_id` | str | Amazon Seller Central ID |
| `brand` | str | Mapped from seller profile |
| `channel` | str | "Amazon" or "Target+" |
| `gross_sales` | float | Ordered product sales |
| `net_sales` | float | Net after Amazon adjustments |
| `orders` | int | Order count |
| `units` | int | Unit count |
| `fees` | float | Amazon referral/FBA fees |
| `refunds` | float | Refund amount |

**Seller -> Brand Map:**
- `GROSMIMI USA` (A3IA0XWP2WCD15) -> Grosmimi
- `Fleeters Inc` (A2RE0E056TH6H3) -> Naeiae
- `Orbitool` (A3H2CLSAX0BTX6) -> CHA&MOM

### `amazon_sales_sku_daily` (Amazon ASIN/SKU Level — Most Granular)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | Sales date |
| `seller_id` | str | Amazon Seller Central ID |
| `brand` | str | From seller profile map |
| `channel` | str | "Amazon" or "Target+" |
| `asin` | str | Amazon Standard Identification Number |
| `sku` | str | Seller SKU |
| `product_name` | str | Product name from flat file |
| `units` | int | Units ordered |
| `ordered_product_sales` | float | Revenue before fees |
| `fees` | float | Estimated Amazon fees (~15%) |
| `net_sales` | float | Revenue after fees |

**Unique key:** `(date, seller_id, channel, asin, sku)`
**Source:** Collected as side effect of collect_amazon_sales() — same SP-API report, no extra polling.
**Use for:** ASIN-level revenue, best-seller ranking, product mix analysis, SKU-level ROAS.

---

### `amazon_ads_daily` (Amazon Advertising API)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | Report date |
| `profile_id` | str | Advertising profile |
| `brand` | str | From profile map |
| `campaign_id` | str | Campaign ID |
| `campaign_name` | str | Campaign name |
| `ad_type` | str | SP (Products), SB (Brands), SD (Display) |
| `impressions` | int | Impression count |
| `clicks` | int | Click count |
| `spend` | float | Ad cost (USD) |
| `sales` | float | Attributed revenue |
| `purchases` | int | Attributed conversions |

**Data start:** Dec 2025 (Naeiae/Fleeters). Others backfilled earlier.

### `meta_ads_daily` (Meta Marketing API)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | Report date |
| `ad_id` | str | Ad ID |
| `ad_name` | str | Ad name |
| `campaign_id` | str | Campaign ID |
| `campaign_name` | str | Campaign name |
| `adset_id` | str | Ad Set ID |
| `adset_name` | str | Ad Set name |
| `brand` | str | Detected from campaign_name + landing_url |
| `campaign_type` | str | Prospecting, Retargeting, etc. |
| `objective` | str | Campaign objective |
| `impressions` | int | Impressions |
| `clicks` | int | Link clicks |
| `spend` | float | Amount spent (USD) |
| `reach` | int | Unique reach |
| `frequency` | float | Avg frequency |
| `purchases` | int | Conversions (purchases) |
| `purchase_value` | float | Conversion value |
| `landing_url` | str | Destination URL |

**Data start:** Aug 2024.

### `google_ads_daily` (Google Ads API)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | Report date |
| `customer_id` | str | Google Ads account |
| `campaign_id` | str | Campaign ID |
| `campaign_name` | str | Campaign name |
| `brand` | str | Detected from campaign_name |
| `campaign_type` | str | Search, PMax, Shopping, etc. |
| `impressions` | int | Impressions |
| `clicks` | int | Clicks |
| `spend` | float | Cost (USD, already divided by 1e6) |
| `conversions` | float | Conversion count |
| `conversion_value` | float | Revenue attributed |

**Data start:** Jan 2024.

### `ga4_daily` (Google Analytics 4)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | Session date |
| `channel_grouping` | str | GA4 default channel grouping |
| `sessions` | int | Session count |
| `purchases` | int | E-commerce purchases |

### `klaviyo_daily` (Klaviyo API)

| Field | Type | Description |
|-------|------|-------------|
| `date` | str | Date |
| `source_type` | str | "campaign" or "flow" |
| `source_name` | str | Campaign/flow name |
| `source_id` | str | Klaviyo ID |
| `sends` | int | Emails sent |
| `opens` | int | Opens |
| `clicks` | int | Clicks |
| `conversions` | int | Placed orders |
| `revenue` | float | Attributed revenue |

---

## 2. Channel Classification (Decision Tree)

Source: `data_keeper.py:collect_shopify()` lines 1233-1253.

Classification is applied **at order level** based on Shopify order tags and source.

```
Order tags (lowercased, comma-split)
  |
  +-- "faire" in tags?
  |     YES -> B2B (Faire wholesale)
  |
  +-- "exported to amazon" in tags?
  |   or "amazon status" in tags?
  |   or "rejected by amazon" in tags?
  |     YES -> D2C (FBA MCF: Shopify sale, Amazon logistics only)
  |
  +-- "amazon" in tags or "amazon" in source?
  |     YES -> Amazon (Amazon channel orders via Shopify integration)
  |
  +-- "tiktok" in tags or "tiktok" in source?
  |     YES -> TikTok
  |
  +-- "b2b" or "wholesale" in tags?
  |     YES -> B2B
  |
  +-- "pr" or "sample" or "supporter" in tags?
  |     YES -> PR (excluded from revenue KPIs, goes to seeding cost)
  |
  +-- else
        -> D2C (default: Onzenna/zezebaebae.com direct)
```

### Critical Distinction: Amazon Channel vs FBA MCF

| Scenario | Shopify Tags | Classification | Why |
|----------|-------------|----------------|-----|
| Customer buys on Shopify, fulfilled via Amazon FBA | "Exported To Amazon by WebBee App" | **D2C** | The SALE is on Shopify; Amazon is just the warehouse |
| Customer buys on Shopify, Amazon rejects fulfillment | "Rejected by Amazon - WebBee app" | **D2C** | Still a Shopify sale |
| Amazon channel orders pushed to Shopify | "amazon" (generic) | **Amazon** | True Amazon channel sale |
| True Amazon Marketplace purchases | NOT in Shopify at all | Use `amazon_sales_daily` | SP-API data, separate table |

### Channel Display Mapping

| DB channel | KPI Display | D2C Aggregate? |
|------------|-------------|----------------|
| `D2C` | ONZ | Yes |
| `Amazon` | Amazon | Yes |
| `TikTok` | TikTok | Yes |
| `B2B` | B2B | No |
| `PR` | (excluded) | No |
| `Unknown` | Unknown | No |

**"D2C" in KPI reports = ONZ + Amazon + TikTok** (i.e., all consumer-facing channels).

---

## 3. Brand Classification

### Shopify Orders (`_detect_shopify_brand()`)

Detects from `line_items[].title` + `line_items[].vendor` (lowercased):

| Keyword Match | Brand |
|---------------|-------|
| "grosmimi" | Grosmimi |
| "cha&mom", "chamom", "orbitool" | CHA&MOM |
| "naeiae" | Naeiae |
| "onzenna" | Onzenna |
| "alpremio" | Alpremio |
| (no match) | Unknown |

### Meta Ads (`_detect_meta_brand()`)

Detects from `campaign_name` + `landing_url` (lowercased):

| Keyword Match | Brand |
|---------------|-------|
| "grosmimi", "grosm" | Grosmimi |
| "cha&mom", "chaandmom", "chamom", "cha_mom", "orbitool" | CHA&MOM |
| "naeiae", "fleeters" | Naeiae |
| "onzenna", "zezebaebae" | Onzenna |
| "alpremio" | Alpremio |
| (no match) | Unknown |

### Google Ads (`_detect_google_brand()`)

Same as Meta but uses `campaign_name` only.

### Amazon Ads (Profile Map)

Direct mapping from advertising profile name:

| Profile Name | Brand |
|-------------|-------|
| GROSMIMI USA | Grosmimi |
| Fleeters Inc | Naeiae |
| Orbitool | CHA&MOM |

---

## 4. Metric Computation Formulas

### Revenue Metrics

```
Gross Sales = SUM(reference_price * qty)
  - D2C: reference_price = compare_at_price ?? sell_price (Shopify MSRP)
  - Amazon: reference_price = shopify_base_price (not compare_at)
            Grosmimi pre-2025-03: GROSMIMI_OLD_PRICES[variant_id]

Discounts = Gross Sales - Net Sales

Net Sales = SUM(sell_price * qty - coupon_discount)

Discount Rate = Discounts / Gross Sales
```

### COGS & Margin

```
AVG_COGS = {
    Grosmimi: $8.41, Naeiae: $5.35, CHA&MOM: $7.53,
    Onzenna: $5.35, Alpremio: $12.57, Unknown: $8.00
}

COGS est. = Units * AVG_COGS[brand]

GM ($) = Net Sales - COGS est.
GM (%) = GM ($) / Net Sales

Note: If units=0 (backfill data), estimate: units = gross_sales / AVG_PRICE[brand]
AVG_PRICE = {
    Grosmimi: $28.0, Naeiae: $18.0, CHA&MOM: $32.0,
    Onzenna: $22.0, Alpremio: $38.0, Unknown: $25.0
}
```

### Ad Spend Aggregation

```
Amazon Ads Spend = SUM(amazon_ads_daily.spend) -- by brand from profile map
Meta Ads Spend   = SUM(meta_ads_daily.spend)   -- by brand from campaign name
Google Ads Spend = SUM(google_ads_daily.spend)  -- by brand from campaign name
Total Ad Spend   = Amazon + Meta + Google + TikTok (manual)
```

### Seeding Cost

```
PayPal Payments = SUM(q11_paypal_transactions where type=influencer)
Sample COGS     = SUM(PR channel orders: units * cogs_per_sku from "COGS by SKU.xlsx")
Shipping        = PR units * $10/unit (estimate)
Total Seeding   = PayPal + Sample COGS + Shipping
```

### Marketing Efficiency

```
MER  = Total Ad Spend / Total Net Revenue                    -- Target: <20%
ROAS = Revenue / Ad Spend                                     -- Target: >5x blended
ACOS = Ad Spend / Revenue (Amazon only)                       -- Target: <20%
CAC  = Total Ad Spend / New Customers                         -- D2C: $25-50, Amazon: $15-30
LTV  = AOV * Purchase Frequency * Avg Customer Lifespan       -- D2C: $80-150
AOV  = Net Revenue / Orders                                   -- D2C: $35-45, Amazon: $25-35
```

### Executive Summary Derived Metrics

```
Net Revenue    = total_monthly[m]["net"]
Gross Sales    = total_monthly[m]["gross"]
Discounts      = total_monthly[m]["disc"]
Discount Rate  = disc / gross
Total Orders   = total_monthly[m]["orders"]
AOV            = net / orders
COGS           = total_monthly[m]["cogs"]  (= SUM(units * avg_cogs by brand))
Gross Profit   = net - cogs
Gross Margin % = gross_profit / net
```

### MKT SPEND Waterfall (Executive Summary)

```
MKT SPEND = Ad Spend + Seeding Cost + Channel Discounts

Ad Spend breakdown (from KPI_ad_spend tab):
  - Amazon Ads (TOTAL row)
  - Meta Ads (TOTAL row)
  - Google Ads (TOTAL row)
  - TikTok Ads (if available)

Seeding (from KPI_seeding tab):
  - TOTAL row

Discounts by Channel (from KPI_discount tab):
  - ONZ Discounts
  - Amazon Discounts
  - B2B Discounts
  - TikTok Discounts

Grand Total = SUM(all above)

Note: Executive Summary uses Excel FORMULAS linking to other tabs, NOT hardcoded values.
```

---

## 5. Grosmimi Price History

### Price Cutoff: 2025-03-01

| Product | Before 2025-03-01 | After 2025-03-01 |
|---------|-------------------|-------------------|
| PPSU Baby Bottle 10oz | $18.60 | $19.60 |
| PPSU Baby Bottle 6oz | $17.40 | $18.40 |
| PPSU Straw Cup 10oz (6M+) | $21.90 | $24.90 |
| Stainless Steel Straw Cup 10oz | $33.80 | $36.80 |
| (22+ variant IDs in GROSMIMI_OLD_PRICES) | | |

**Rule:** For Amazon channel orders with brand=Grosmimi and date < "2025-03-01", use `GROSMIMI_OLD_PRICES[variant_id]` as reference price. After cutoff, use current Shopify prices.

**Location:** `tools/data_keeper.py` lines 56-120.

---

## 6. Data Availability Windows (n.m Rules)

"n.m" = data not collected for this period. Displayed as dark grey cell (#595959) with white text.

| Data Source | Available From | n.m Before |
|-------------|----------------|------------|
| Shopify Orders | 2024-01 | Pre-Jan 2024 |
| Amazon Sales (SP-API) | 2024-01 | Pre-Jan 2024 |
| Amazon Ads | 2025-12 (Naeiae); varies by brand | Pre-Dec 2025 |
| Meta Ads | 2024-08 | Pre-Aug 2024 |
| Google Ads | 2024-01 | Pre-Jan 2024 |
| GA4 | 2024-01 | Pre-Jan 2024 |
| Klaviyo | 2024-01 | Pre-Jan 2024 |
| TikTok Ads | Not in DataKeeper | Always n.m |

### Through-Date Consistency

`compute_through_date()` ensures all tabs use the same cutoff date:

```
through_date = MIN(latest_date across main tables) capped at yesterday PST

Main tables checked: shopify_orders_daily, amazon_ads_daily, meta_ads_daily, google_ads_daily
```

Any data after `through_date` is excluded from all computations.

---

## 7. KPI Tab Architecture

### `KPI_discount` (Wide Format via `write_tab()`)

Dimensions: Brand x Channel x Metric x Month

Metric Sections (in order):
1. GROSS SALES ($)
2. NET SALES ($)
3. DISCOUNTS ($)
4. DISCOUNT RATE (%)
5. UNITS
6. AVG LIST PRICE ($/unit)
7. COGS est. ($)
8. GM ($)
9. GM %

Each section: brand rows + TOTAL row + channel sub-sections. PR channel excluded.

### `KPI_ad_spend` (Wide Format via `write_wide_tab()`)

Structure:
```
Amazon Ads                    (section header)
  Grosmimi                    (indented brand rows)
  Naeiae
  CHA&MOM
  TOTAL Amazon Ads            (sub-total, yellow)
Meta Ads
  TOTAL Meta Ads
Google Ads
  TOTAL Google Ads
TOTAL                         (grand total, dark blue)
```

### `KPI_seeding` (Wide Format via `write_wide_tab()`)

Structure:
```
PayPal Payments
Sample COGS
Shipping (est.)
TOTAL                         (grand total)
Units
```

### `KPI_Amazon_discount_detail` (Brand-level Amazon Shopify Orders)

Only Shopify orders with channel="Amazon" (NOT FBA MCF D2C).
Per brand: Gross Sales, Discounts, Net Sales, Disc Rate, Units.

### `KPI_Amazon_MP_discount` (True Amazon Marketplace Discounts)

Uses `amazon_sales_daily` (SP-API) vs Shopify D2C ASP as reference.
Metrics: Amazon Gross Sales, Amazon Units, Amazon ASP, Reference ASP, Implied Discount ($), Implied Disc Rate (%).

### `Executive Summary` (Updated In-Place)

Row mapping via label search:
```
Row Labels -> DataKeeper Mapping:
  "Net Revenue"      <- total_monthly[m]["net"]
  "Gross Sales"      <- total_monthly[m]["gross"]
  "Discounts"        <- total_monthly[m]["disc"]
  "Discount Rate"    <- disc / gross (as %)
  "Total Orders"     <- total_monthly[m]["orders"]
  "AOV (Net/Orders)" <- net / orders
  "COGS"             <- total_monthly[m]["cogs"]
  "Gross Profit"     <- net - cogs
  "Gross Margin %"   <- (net - cogs) / net
```

MKT SPEND section appended below with Excel formulas linking to other tabs.

### `Summary` (D2C KPI Block Appended)

D2C = ONZ + Amazon + TikTok channels combined.
Metrics: D2C Gross Sales, D2C Net Sales, D2C Discount, D2C Discount Rate, Ad Spend, Seeding Cost.

---

## 8. Data Quality Checks

### Cross-Table Consistency

| Check | Rule | Action on Fail |
|-------|------|----------------|
| Revenue identity | `gross - disc = net` for every row | Data corruption; investigate collector |
| Through-date alignment | All tabs use same through_date | Re-run with `compute_through_date()` |
| Brand coverage | All brands in BRAND_ORDER appear | Check brand detection keywords |
| Channel coverage | All channels in CHANNEL_ORDER appear | Check tag classification logic |
| n.m vs zero | Pre-data-start periods show "n.m", not 0 | Check DATA_START constants |
| YTD consistency | YTD column = SUM of monthly columns for current year | Formula error in write_wide_tab |

### Amazon Data Reconciliation

| Check | Rule |
|-------|------|
| Amazon in Shopify vs SP-API | `shopify_orders_daily` channel=Amazon should be small; bulk should be in `amazon_sales_daily` |
| FBA MCF misclassification | Orders with "exported to amazon" tag MUST be D2C, NOT Amazon |
| Amazon discount sanity | Discount rate should be 0-50%; >50% indicates ref_price issue |
| Grosmimi price history | Orders before 2025-03-01 must use GROSMIMI_OLD_PRICES |

### Ad Spend Sanity

| Check | Range | Flag If |
|-------|-------|---------|
| Amazon Ads monthly | $50K-$120K | < $30K or > $150K |
| Meta Ads monthly | $15K-$40K | < $5K or > $60K |
| Google Ads monthly | $8K-$20K | < $3K or > $30K |
| Total MER | 10%-25% | > 30% or < 5% |

### Period-over-Period Analysis

```
MoM growth = (current_month - prev_month) / prev_month
YoY growth = (current_month - same_month_last_year) / same_month_last_year

Anomaly flags:
  - MoM > 50% or < -30%: Investigate (seasonal? promo? data gap?)
  - YoY > 100% or < -50%: Validate data completeness
  - BFCM exception: Nov MoM spike ~50-100% is normal
  - Prime Day exception: Jul Amazon spike ~30-50% is normal
```

---

## 9. DataKeeper Client API

### Correct Usage (`.get()` not `.fetch()`)

```python
from data_keeper_client import DataKeeper

dk = DataKeeper(prefer_cache=True)   # Use local cache (fast, may be stale)
dk = DataKeeper(prefer_cache=False)  # Query API (slow, fresh data)

# Basic queries
rows = dk.get("shopify_orders_daily", days=30)
rows = dk.get("amazon_ads_daily", date_from="2026-01-01", date_to="2026-02-28")
rows = dk.get("meta_ads_daily", brand="Grosmimi")
rows = dk.get("shopify_orders_daily", channel="D2C")

# Status
dk.status()          # -> dict of all tables with row counts, date ranges, timestamps
dk.is_fresh("shopify_orders_daily")  # -> bool (within 14h)
dk.last_updated("shopify_orders_daily")  # -> ISO timestamp str

# Returns: list[dict] -- NOT a DataFrame. Manual aggregation required.
```

### Valid Tables

```python
VALID_TABLES = [
    "shopify_orders_daily", "amazon_sales_daily", "amazon_ads_daily",
    "amazon_campaigns", "meta_ads_daily", "meta_campaigns",
    "google_ads_daily", "ga4_daily", "klaviyo_daily",
    "gsc_daily", "dataforseo_keywords",
]
```

### Aggregation Pattern (Python, not pandas)

```python
from collections import defaultdict

rows = dk.get("shopify_orders_daily", days=90)
monthly = defaultdict(lambda: {"gross": 0.0, "net": 0.0, "disc": 0.0, "units": 0, "orders": 0})

for r in rows:
    month = r["date"][:7]  # "2026-01"
    brand = r.get("brand", "Unknown")
    channel = r.get("channel", "Unknown")
    key = (month, brand, channel)
    monthly[key]["gross"] += float(r.get("gross_sales", 0) or 0)
    monthly[key]["net"]   += float(r.get("net_sales", 0) or 0)
    monthly[key]["disc"]  += float(r.get("discounts", 0) or 0)
    monthly[key]["units"] += int(r.get("units", 0) or 0)
    monthly[key]["orders"] += int(r.get("orders", 0) or 0)
```
