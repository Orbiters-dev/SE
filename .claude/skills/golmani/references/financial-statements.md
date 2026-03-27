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

### CRITICAL: P&L Revenue = GROSS (정가 기준)

P&L은 반드시 **Gross Revenue (정가 × 수량)** 에서 시작한다. 할인은 별도 MKT 비용 라인으로 차감.
이유: 정가 대비 실제 할인 규모를 파악하고, COGS%가 정확히 계산되려면 분모가 gross여야 함.
Net revenue를 분모로 쓰면 COGS%가 뻥튀기됨 (예: gross 기준 34% → net 기준 40%).

```
Revenue = Shopify gross_sales + Amazon gross_sales (ordered_product_sales)
  NOT net_sales. net_sales는 참고용.
```

### ORBI P&L Line-Item Mapping

| Line Item | DataKeeper Source | Field | Notes |
|-----------|------------------|-------|-------|
| Gross Revenue (D2C) | `shopify_orders_daily` | `gross_sales` | channel != PR, != Amazon |
| Gross Revenue (Amazon) | `amazon_sales_daily` | `gross_sales` | 3 seller accounts. `net_sales`는 할인 후 |
| Gross Revenue (B2B) | `shopify_orders_daily` | `gross_sales` | channel = B2B (Faire) |
| Discounts (D2C) | `shopify_orders_daily` | `discounts` | Promo codes, Kaching bundles |
| Discounts (Amazon) | `amazon_sales_daily` | `gross_sales - net_sales` | 쿠폰/프로모 ~15% |
| Returns | Not in DataKeeper | | Manual input or Shopify refunds API |
| COGS | 685-SKU NAS map | `COGS by SKU.xlsx` | Landed cost = FOB × 1.15 |
| Amazon Ads | `amazon_ads_daily` | `spend` | DK Dec 2025+; Jan-Nov backfill from Polar Excel |
| Meta Ads | `meta_ads_daily` | `spend` | From Aug 2024 |
| Google Ads | `google_ads_daily` | `spend` | From Jan 2024 |
| TikTok Ads | Not in DataKeeper | | Manual input; paused 2025 |
| Influencer (PAID) | `q11_paypal_transactions.json` | outbound (amt < 0) | PayPal payments to creators |
| Influencer (NON-PAID) | `q10_influencer_orders.json` | COGS + $10/unit ship | PR tagged Shopify orders |
| Platform Fees | Calculated | ~3% Shopify, ~15% Amazon | Not stored directly |
| Fulfillment | `amazon_sales_sku_daily` | `fba_fee_total` | FBA fee from SP-API report |
| Payroll & G&A | Not in DataKeeper | | Manual input from accounting |

### Consistency Rule: Financial Dashboard ↔ KPI Report

`generate_fin_data.py` 수정 시 반드시 `run_kpi_monthly.py`와 일관성 확인:
- `analyze_discounts()` — 할인 계산 로직
- `analyze_seeding_cost()` — 인플루언서 비용 (PayPal + COGS + Shipping)
- Amazon Ads backfill — Polar Excel "IR 매출분석" row 119
- FY 합계 — 반드시 1월부터 12월 전체 포함 (--months 파라미터 확인)

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

**IMPORTANT:** DataKeeper returns `list[dict]`, NOT DataFrames. Use `.get()` method (NOT `.fetch()`).

```python
from data_keeper_client import DataKeeper
from collections import defaultdict

dk = DataKeeper(prefer_cache=False)

# Monthly Revenue by Brand (all channels)
rows = dk.get("shopify_orders_daily", days=365)
monthly = defaultdict(lambda: {"gross": 0.0, "net": 0.0, "disc": 0.0, "units": 0, "orders": 0})
for r in rows:
    month = r["date"][:7]  # "2026-01"
    brand = r.get("brand", "Unknown")
    channel = r.get("channel", "Unknown")
    if channel == "PR":
        continue  # PR excluded from revenue
    monthly[(month, brand)]["net"] += float(r.get("net_sales", 0) or 0)
    monthly[(month, brand)]["gross"] += float(r.get("gross_sales", 0) or 0)

# Amazon Marketplace Revenue (SP-API -- separate from Shopify)
amz_rows = dk.get("amazon_sales_daily", days=365)
for r in amz_rows:
    month = r["date"][:7]
    brand = r.get("brand", "Unknown")
    # Note: This is TRUE Amazon sales, not Shopify Amazon channel

# Ad Spend by Platform
meta_rows = dk.get("meta_ads_daily", days=90)
google_rows = dk.get("google_ads_daily", days=90)
amz_ads_rows = dk.get("amazon_ads_daily", days=90)

meta_spend = defaultdict(float)
for r in meta_rows:
    meta_spend[r["date"][:7]] += float(r.get("spend", 0) or 0)
# Same pattern for google (field: "spend") and amazon_ads (field: "spend")
```

### Data Classification Rules

See `references/kpi-data-taxonomy.md` for complete decision trees:
- **Channel classification**: Shopify order tags -> D2C/Amazon/B2B/TikTok/PR
- **Brand classification**: Line item title+vendor (Shopify), campaign name (ads)
- **Discount computation**: ref_price methodology varies by channel
- **n.m periods**: Data not yet collected -> dark grey sentinel
- **Through-date**: Consistent cutoff across all KPI tabs

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

| Source | Coverage | File | Notes |
|--------|----------|------|-------|
| **NAS SKU COGS map** | 685 SKUs (all brands) | `Z:\...\COGS by SKU.xlsx` | **Landed cost = FOB × 1.15** |
| Ex Price file | Grosmimi FOB prices | `REFERENCE/2025_Ex Price_Grosmimi_*.xlsx` | Barcode col 23 for 1:1 매칭 |
| Product Variant map | SKU → Brand mapping | `Z:\...\Product Variant by SKU.xlsx` | 694 SKUs |
| DataKeeper SKU | Amazon SKU daily | `amazon_sales_sku_daily` | units, gross, fees, fba_fee |

### CRITICAL: COGS 비교 시 SKU/바코드 1:1 매칭 필수

COGS 정확도 검증 시 카테고리 평균 비교 금지. 반드시 바코드(88코드) 단위로 1:1 매칭.

```
NAS SKU: MB8809466582561 → barcode 8809466582561
Ex Price: barcode column (col 23) = 8809466582561 → FOB $6.60
NAS COGS $7.59 = FOB $6.60 × 1.15 ✓ (정확히 일치)
```

카테고리 평균으로 비교하면 Cup 종류별 가격차이 ($6.20~$8.90)가 뭉개져서 오판함.
Amazon SKU 중 `2c-`, `ic-`, `3o-` 등 FBA 자체코드는 바코드 없음 → ASIN으로 매칭.

### Volume-Weighted COGS (2026-03 기준)

| Brand | VW Avg COGS | SKU Count | Match Rate |
|-------|-------------|-----------|------------|
| Grosmimi | $8.50 | 422 | 99.9% |
| Naeiae | $9.69 | 5 | 100% |
| CHA&MOM | $7.65 | 11 | 100% |
| Alpremio | $11.79 | 6 | 100% |

### Margin Analysis by Brand (Gross Revenue 기준)

| Brand | COGS/Gross | GM% | Key Driver |
|-------|-----------|-----|-----------|
| Grosmimi | 34-36% | 64-66% | PPSU cups $7-10, Stainless $10-15 |
| Naeiae | 37-38% | 62-63% | Snack products, higher per-unit cost |
| CHA&MOM | 33-34% | 66-67% | Skincare $6-8/unit |
| Alpremio | 31% | 69% | Higher ASP offsets COGS |

NOTE: Amazon channel COGS% appears higher (~40%) when calculated against net_sales.
This is because Amazon discounts ~15% reduce the denominator. Against gross_sales, COGS% is 34%.

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
