# Financial Statements -- 3-Statement Modeling & ORBI Data Mapping

Core framework for Income Statement, Balance Sheet, Cash Flow Statement modeling.
Maps ORBI's DataKeeper tables to financial statement line items.

---

## 1. Income Statement (P&L)

### Structure

```
Revenue (Gross Sales)
  - Discounts & Returns
= Net Revenue
  - COGS
= Gross Profit                    → GM%
  - Operating Expenses
    - Marketing & Advertising
    - Fulfillment & Shipping
    - Platform Fees
    - Payroll & G&A
    - Seeding / Influencer
= EBITDA                          → EBITDA margin
  - D&A (minimal for DTC)
= EBIT
  - Interest Expense
  - Taxes
= Net Income
```

### ORBI P&L Line-Item Mapping

| Line Item | DataKeeper Source | Notes |
|-----------|------------------|-------|
| Gross Revenue (D2C) | `shopify_orders_daily` SUM(line_price * qty) | Filtered: channel = D2C |
| Gross Revenue (Amazon) | `amazon_sales_daily` SUM(ordered_product_sales) | 3 seller accounts combined |
| Gross Revenue (B2B) | `shopify_orders_daily` WHERE channel = B2B | Faire wholesale |
| Discounts (D2C) | `shopify_orders_daily` SUM(discount_amount) | Promo codes, Kaching bundles |
| Returns | Not in DataKeeper | Manual input or Shopify refunds API |
| COGS | `run_kpi_monthly.py` (685 SKU map) | SKU-level for Shopify; ~15% flat for Amazon |
| Amazon Ads | `amazon_ads_daily` SUM(cost) | Naeiae from Dec 2025; others backfilled |
| Meta Ads | `meta_ads_daily` SUM(spend) | From Aug 2024 |
| Google Ads | `google_ads_daily` SUM(cost_micros/1e6) | From Jan 2024 |
| TikTok Ads | Not in DataKeeper | Manual input; paused 2025 |
| Seeding Cost | `run_kpi_monthly.py` (PayPal + COGS + shipping) | PR/influencer gifting |
| Platform Fees | Calculated: ~3% Shopify, ~15% Amazon | Not stored directly |
| Fulfillment | Not in DataKeeper | WBF invoices, manual input |
| Payroll & G&A | Not in DataKeeper | Manual input from accounting |

### Revenue Build-Up (Bottom-Up)

```
Revenue = Σ (Units Sold × ASP) by Brand × Channel × Month

Shopify D2C:
  Units = shopify_orders_daily COUNT(line_items) by brand
  ASP = AVG(line_price) by brand/product_type

Amazon:
  Units = amazon_sales_daily SUM(units_ordered) by seller
  ASP = ordered_product_sales / units_ordered

B2B:
  Units = shopify_orders_daily WHERE channel=B2B
  ASP = ~52% of retail (wholesale pricing)
```

### Contribution Margin Waterfall

```
Revenue                           100%
  - COGS                          -30% (GM ~70% for Grosmimi)
= Gross Profit (CM0)              70%
  - Platform Fees                  -3% (D2C) / -15% (Amazon)
= CM1                             67% (D2C) / 55% (Amazon)
  - Shipping / Fulfillment         -8%
= CM2                             59% (D2C) / 47% (Amazon)
  - Marketing (Ads + Seeding)      -15%
= CM3 (Contribution Margin)       44% (D2C) / 32% (Amazon)
```

---

## 2. Balance Sheet

### Structure

```
ASSETS
  Current Assets
    Cash & Equivalents
    Accounts Receivable (Amazon settlements, B2B net terms)
    Inventory (Korea warehouse + WBF + Amazon FBA)
    Prepaid Expenses
  Non-Current Assets
    PP&E (minimal — asset-light DTC)
    Intangible Assets (brand IP, trademarks)

LIABILITIES
  Current Liabilities
    Accounts Payable (Korean suppliers)
    Accrued Expenses
    Short-term Debt / Credit Lines
    Deferred Revenue
  Non-Current Liabilities
    Long-term Debt
    Other

EQUITY
  Common Stock
  Retained Earnings
  Additional Paid-In Capital
```

### ORBI-Specific Balance Sheet Notes

| Item | ORBI Context |
|------|-------------|
| Inventory | **Largest asset**. 60-90 day lead time from Korea. Multiple locations: Korea warehouse, in-transit (sea), WBF (CA), Amazon FBA warehouses. Model as 4-6x turns. |
| Accounts Receivable | Amazon: 14-day settlement cycle. Faire B2B: net 30-60. Shopify: 2-day payout. |
| PP&E | Near zero. No factory, no warehouse (3PL). Office equipment only. |
| Intangible Assets | Brand distribution rights. Grosmimi exclusivity in US market. |
| AP | Korean suppliers: net 30-60 in KRW. FX exposure on payables. |
| Debt | Not in DataKeeper. Manual input required. |

**Data gap:** Balance sheet data is NOT in DataKeeper. All BS items require manual input from ORBI's accounting team.

---

## 3. Cash Flow Statement

### Structure

```
OPERATING ACTIVITIES
  Net Income
  + D&A
  +/- Changes in Working Capital
    - Increase in AR
    - Increase in Inventory
    + Increase in AP
  = Cash from Operations (CFO)

INVESTING ACTIVITIES
  - CapEx (minimal)
  - Brand acquisition costs
  = Cash from Investing (CFI)

FINANCING ACTIVITIES
  + Debt proceeds
  - Debt repayment
  + Equity issuance
  - Dividends / distributions
  = Cash from Financing (CFF)

NET CHANGE IN CASH = CFO + CFI + CFF
```

### ORBI Cash Flow Drivers

| Driver | Impact | Magnitude |
|--------|--------|-----------|
| Inventory purchases | Cash outflow, lumpy (container shipments) | $50-200K per container |
| Amazon settlements | Cash inflow, 14-day lag | ~40% of revenue |
| Ad spend | Cash outflow, continuous | ~$100K/month |
| Seasonal inventory build | Q3 build for BFCM | 2-3x normal months |
| FX settlements | KRW payables, timing mismatch | Depends on KRW/USD |

---

## 4. Key Metrics & KPIs

### Unit Economics

| Metric | Formula | ORBI Benchmark |
|--------|---------|----------------|
| CAC | Total Ad Spend / New Customers | $25-50 (D2C), $15-30 (Amazon) |
| LTV | AOV × Purchase Frequency × Customer Lifespan | $80-150 (D2C) |
| LTV:CAC | LTV / CAC | Target: >3:1 |
| Payback Period | CAC / (AOV × GM%) | Target: <6 months |
| AOV | Net Revenue / Orders | $35-45 (D2C), $25-35 (Amazon) |
| MER | Total Ad Spend / Total Revenue | Target: <20% |
| ROAS | Revenue / Ad Spend | Target: >5x (blended) |
| ACOS | Ad Spend / Revenue (Amazon) | Target: <20% |

### DataKeeper Queries for KPIs

```python
from data_keeper_client import DataKeeper
dk = DataKeeper(prefer_cache=False)

# Monthly Revenue by Brand (D2C)
shopify = dk.fetch("shopify_orders_daily")
monthly_rev = shopify.groupby([shopify['date'].dt.to_period('M'), 'brand'])['net_sales'].sum()

# Amazon Revenue by Seller
amazon = dk.fetch("amazon_sales_daily")
amz_rev = amazon.groupby([amazon['date'].dt.to_period('M'), 'seller_name'])['ordered_product_sales'].sum()

# Total Ad Spend by Platform
meta = dk.fetch("meta_ads_daily")
google = dk.fetch("google_ads_daily")
amz_ads = dk.fetch("amazon_ads_daily")

meta_spend = meta.groupby(meta['date_start'].dt.to_period('M'))['spend'].sum()
google_spend = google.groupby(google['date'].dt.to_period('M'))['cost_micros'].sum() / 1e6
amz_spend = amz_ads.groupby(amz_ads['date'].dt.to_period('M'))['cost'].sum()
```

### Projection Methods

| Method | When to Use | Inputs |
|--------|-------------|--------|
| Growth rate | Stable business, no major changes | Historical CAGR, seasonality index |
| Bottom-up | New product launch, channel expansion | Units × ASP × channel mix |
| Cohort-based | LTV analysis, retention modeling | Monthly cohort data |
| Driver-based | Scenario planning | Traffic × CVR × AOV |

### Seasonality Index (ORBI Historical)

| Month | Index | Notes |
|-------|-------|-------|
| Jan | 0.75 | Post-holiday dip |
| Feb | 0.80 | Valentine's small lift |
| Mar | 0.85 | Easter varies |
| Apr | 0.90 | Spring recovery |
| May | 0.95 | Memorial Day |
| Jun | 1.00 | Baseline |
| Jul | 1.10 | Prime Day spike (Amazon) |
| Aug | 0.95 | Back to school |
| Sep | 1.00 | Labor Day |
| Oct | 1.05 | Pre-holiday build |
| Nov | 1.50 | BFCM |
| Dec | 1.15 | Holiday season |

---

## 5. COGS Deep Dive

### SKU-Level COGS Structure

```
Unit COGS = FOB Price (Korea) + Shipping to US + Customs Duty + Inland Freight

For LFU → FLT flow:
  Ex Price (from Ex Price file) × 1.05 = LFU→FLT transfer price
  COGS to FLT = transfer price + shipping + duty

For ORBI → FLT flow:
  Direct export price + shipping + duty
```

### COGS Data Sources

| Source | Coverage | File |
|--------|----------|------|
| SKU COGS map | 685 Shopify SKUs | `tools/no_polar/` JSON files |
| Ex Price file | Grosmimi FOB prices | `REFERENCE/2025_Ex Price_Grosmimi_*.xlsx` |
| Amazon COGS | Flat ~15% estimate | Manual assumption |
| Shipping per unit | ~$2-5 depending on weight | WBF rate card |

### Margin Analysis by Brand

| Brand | GM% | Key Driver |
|-------|-----|-----------|
| Grosmimi | ~70% | High ASP cups, low unit COGS |
| Naeiae | ~70% | Food products, small packaging |
| CHA&MOM | ~76% | Skincare, high markup |
| Alpremio | ~67% | Nursing accessories |
| Comme Moi | ~55% | Carriers, higher material cost |
| Bamboobebe | ~47% | Bamboo tableware, heavier |

---

## 6. Model Building Conventions (openpyxl)

### Tab Structure for 3-Statement Model

```
Tab 1: Assumptions (all blue inputs here)
Tab 2: Income Statement (monthly + annual)
Tab 3: Balance Sheet (quarterly or annual)
Tab 4: Cash Flow Statement (derived from IS + BS)
Tab 5: Supporting Schedules (D&A, debt, working capital)
Tab 6: Valuation (DCF, multiples — links to IS/BS/CF)
Tab 7: Sensitivity (data tables)
```

### Formula Conventions

```python
# Always use Excel formulas, never hardcode
ws['B5'] = '=B3-B4'                    # Net Revenue = Gross - Discounts
ws['B8'] = '=B5-B6'                    # Gross Profit = Net Rev - COGS
ws['B8'].number_format = '#,##0'       # Thousands format
ws['B8'].font = Font(color="000000")   # Black = formula

# Input cells
ws['B3'].font = Font(color="0000FF")   # Blue = input
ws['B3'].number_format = '#,##0'

# Cross-sheet references
ws['B10'] = "='Income Statement'!B15"  # Green = cross-sheet link
ws['B10'].font = Font(color="008000")
```

### Conditional Formatting Patterns

```python
# Negative numbers in red parentheses
ws['B5'].number_format = '#,##0;(#,##0);"-"'

# Percentage format
ws['B12'].number_format = '0.0%'

# Growth rate with color
# Use conditional formatting rules for red/green
```
