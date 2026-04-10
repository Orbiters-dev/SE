---
name: kpi-monthly
description: "Monthly KPI Excel report generator for ORBI brands. Use this skill when generating, updating, or debugging the monthly KPI report (run_kpi_monthly.py), analyzing discount rates by brand/channel, investigating Amazon discount anomalies, checking ad spend trends, seeding cost analysis, COGS analysis, or explaining any KPI tab structure. Also trigger when the user mentions 'KPI 리포트', 'v14', 'KPI_할인율', 'KPI_광고비', 'KPI_시딩비용', 'KPI_Amazon할인_상세', 'COGS 분석', 'COGS 업데이트', 'Executive Summary', 'D2C KPI', 'seeding cost', 'influencer cost', 'wide format', '매출 리포트', discount rate investigation, or asks why a specific month's numbers look unusual."
---

# KPI Monthly Report

## What This Skill Does

Generates and maintains `kpis_model_YYYY-MM-DD_vN.xlsx` — a multi-tab Excel KPI report covering discount rates, ad spend, seeding costs, and Amazon discount details across all ORBI brands.

**Run it:**
```bash
python tools/run_kpi_monthly.py
```

**Output:** `kpis_model_<date>_v<N>.xlsx` (increments version automatically, loads previous version as base)

**Current version:** v31 (2026-03-14 기준)

---

## Tab Structure

| Tab | Format | Description |
|-----|--------|-------------|
| `KPI_할인율` | Long (date rows) | Discount rate by brand × channel × day |
| `KPI_광고비` | **Wide** (months as columns) | Ad spend by platform + Amazon brand breakdown |
| `KPI_시딩비용` | **Wide** (months as columns) | Influencer seeding cost (PayPal + COGS + shipping) |
| `KPI_Amazon할인_상세` | Long + wide summary | Daily Amazon channel discount detail |
| Executive Summary | Existing sheet | **rows 14/15/16 COGS 업데이트** (D2C Grosmimi/CHA&MOM/Naeiae) |
| D2C KPI Summary | Appended section | **월별 D2C gross/net/discount/ad spend/seeding 추가 섹션** |

### Executive Summary COGS 업데이트

`update_legacy_cogs(wb, cogs_monthly)` 가 기존 Executive Summary 시트에서:
- Row 14: Grosmimi COGS
- Row 15: CHA&MOM COGS
- Row 16: Naeiae COGS

를 월별 컬럼에 맞춰 채워넣음. `_find_partial_month_col(ws, year, month)` 로 헤더 행에서 월 컬럼 위치를 찾아 정확히 삽입.

### D2C KPI Summary 섹션

`add_summary_d2c_section(wb, d2c_monthly, seeding_rows, adspend_rows)` 가 기존 시트에 새 섹션을 append:

| 행 | 내용 |
|----|------|
| Gross Revenue | D2C 채널 총 매출 |
| Discount | D2C 할인 금액 |
| Net Revenue | 순매출 (Gross - Discount) |
| Discount Rate | 할인율 % |
| Ad Spend | 플랫폼별 광고비 합산 |
| Seeding Cost | 인플루언서 시딩비용 |

- `_parse_wide_total(rows)` 로 wide-format TOTAL 행에서 `{month: value}` 딕셔너리 추출
- `_scan_legacy_*_rows()` helpers: 기존 시트에서 레거시 데이터 행 스캔 후 재활용

### Wide Format Conventions

Wide tabs (KPI_광고비, KPI_시딩비용) use:
- Column A = label (platform/item name)
- Columns B+ = one per month (e.g., "Jan 2024", "Feb 2024", ...)
- Last column = "YTD" (current year total)
- Indented rows (`"  Brand"`) = sub-items
- `TOTAL` row = grand total (dark yellow background)
- `n.m` cells = data not collected for that period (dark grey `#595959` fill, white text)

---

## Data Sources

| Data | Source | Notes |
|------|--------|-------|
| Discount rates | `shopify_orders_daily` (PG) | See channel classification caveat below |
| Amazon Ads spend | `amazon_ads_daily` (PG) | Naeiae only from Dec 2025 (API limit) |
| Meta Ads spend | `meta_ads_daily` (PG) | From Aug 2024 |
| Google Ads spend | `google_ads_daily` (PG) | From Jan 2024 |
| Seeding costs | Polar JSON (`no_polar/`) + PayPal export | PR orders from Shopify |
| COGS | SKU map from `tools/no_polar/` | 685+ SKUs |

All PG data via `DataKeeper(prefer_cache=False)`.

---

## Channel Classification — Fixed 2026-03-08

### What "Amazon Channel" Actually Is (Historical Context)

Prior to 2026-03-08, `shopify_orders_daily` classified ALL amazon-tagged orders as channel="Amazon", which inflated discount rates. **This has been fixed in `data_keeper.py`.**

**Root cause that was fixed:**
1. **FBA Multi-Channel Fulfillment (MCF)** — Shopify DTC sales where Amazon handles shipping (WebBee app). Tags: `"Amazon Status - Complete, Exported To Amazon by WebBee App"` or `"Rejected by Amazon - WebBee app"`. **The actual sale is on Shopify** — Amazon is logistics only. Discounts = Shopify promo codes (influencer codes, Kaching Bundle deals).
2. **Faire wholesale orders** — B2B orders via Faire tagged `"Faire, NON-TRANS-FBA, Rejected by Amazon"` — wholesale pricing at ~48% "discount" vs retail.

**Current channel logic (fixed):**
```python
if "faire" in tags:              → B2B
elif "exported to amazon" in tags or "amazon status" in tags or "rejected by amazon" in tags:
                                  → D2C  (FBA MCF, sale is Shopify)
elif "amazon" in tags:            → Amazon
```

**Actual Amazon Marketplace data** lives in `amazon_sales_daily` (SP-API) — no line-item detail, no discount breakdown.

**Historical data note:** Pre-fix data in PG (before 2026-03-08 recollection) may show inflated Amazon channel metrics. Re-run `data_keeper.py --channel shopify` to refresh if needed.

---

## Amazon Discount Calculation

For orders classified as channel="Amazon":

```
ref_price = amazon_prices.get(variant_id, sell_price)
ref_price = max(ref_price, sell_price)  # floor: no negative discounts
gross    += ref_price × qty
discount += (ref_price - sell_price) × qty + line_disc
net      += sell_price × qty - line_disc
```

Where:
- `ref_price` = current Shopify `price` field (NOT `compare_at_price`)
- `sell_price` = line item price from Shopify order (what Amazon/WebBee recorded)
- `line_disc` = coupon discount on the line item

**For D2C channel:** `ref_price` = `compare_at_price ?? price` (captures Shopify sale pricing)

### Grosmimi Price History

Grosmimi raised retail prices in March 2025. Use old prices for pre-increase orders:

```python
GROSMIMI_PRICE_CUTOFF = "2025-03-01"
GROSMIMI_OLD_PRICES = { variant_id: old_retail_price, ... }  # in data_keeper.py

if brand == "Grosmimi" and date < GROSMIMI_PRICE_CUTOFF:
    ref_price = GROSMIMI_OLD_PRICES.get(vid, amazon_prices.get(vid, sell_price))
else:
    ref_price = amazon_prices.get(vid, sell_price)
```

**Without this**: pre-March 2025 orders would show 0% discount (Amazon was priced above old Shopify reference, so floor kicks in).

### Price Snapshot Timing

`amazon_prices` is fetched from Shopify's current product catalog each run. If Shopify raised prices since a historical order was placed, the stored discount for that period will reflect the NEW price as reference — potentially inflating historical discount percentages. This is an inherent limitation of using a price snapshot.

**Example:** Grosmimi SS Straw Cup raised from $43→$46.80. Jan 2026 orders stored when data_keeper ran in Jan showed the gap vs the then-current Shopify price. Once Amazon updated to $46.80, the gap closed going forward.

---

## n.m (No Measurement) Sentinel

When a platform has no data for a given period (not $0 spend, but genuinely uncollected):

- Data rows: use string `"n.m"` as the cell value
- `write_wide_tab()` renders it: dark grey fill (`#595959`), white text, centered, 8pt font
- Related cells in the same column also get `n.m`

**Data availability windows:**
- Amazon Ads: Dec 2025 onward (Naeiae), earlier for others via backfill
- Meta Ads: Aug 2024 onward
- Google Ads: Jan 2024 onward

---

## Debugging Common Issues

### "IndexError: list index out of range" in add_summary_d2c_section
Old code tried to read `adspend_rows` as month-indexed rows. After switching to wide format, this breaks. The fix uses `_parse_wide_total()` to find the TOTAL row and extract values by header column index.

### High Amazon Discount Rate in a Specific Month
Check in order:
1. **Faire orders?** Query Shopify for Amazon-tagged orders with `"Faire"` in tags. These use wholesale pricing (48% "discount" vs retail ref).
2. **Shopify promo codes?** Look for discount_codes in order data. FBA MCF orders carry whatever Shopify code the customer used.
3. **Price raise timing?** If a product was repriced recently, old orders stored with old prices may show larger gaps when displayed with current reference prices.
4. **Real Amazon deal?** Check Amazon Seller Central for active coupons/lightning deals that period.

### Version Increment
Script auto-detects latest `kpis_model_*_vN.xlsx` and saves as `vN+1`. Always loads previous version to preserve existing tabs not managed by the script.

---

## Key Functions in run_kpi_monthly.py

| Function | Purpose |
|----------|---------|
| `write_wide_tab(wb, tab, rows)` | Writes wide-format tab with n.m styling |
| `write_tab(wb, tab, rows)` | Writes long-format tab |
| `analyze_ad_spend(date_from, date_to)` | Returns wide-format ad spend rows by platform + Amazon brand |
| `analyze_seeding_cost(date_from, date_to)` | Returns wide-format seeding cost rows |
| `add_amazon_discount_tab(wb, through_date)` | Builds KPI_Amazon할인_상세 from shopify_orders_daily |
| `add_summary_d2c_section(wb, d2c_monthly, seeding_rows, adspend_rows)` | Appends D2C KPI Summary section to existing sheet |
| `_parse_wide_total(rows)` | Helper: extracts {month: value} from wide-format TOTAL row |

---

## File Locations

```
tools/run_kpi_monthly.py         # Main script
tools/data_keeper_client.py      # DataKeeper(prefer_cache=False) for fresh PG data
tools/no_polar/                  # Polar JSON files (seeding, COGS, historical)
.tmp/kpi_debug_*.json            # Debug dumps (when enabled)
kpis_model_YYYY-MM-DD_vN.xlsx   # Output (project root)
```


---

## 보고 규칙 (전 에이전트 공통)

세은에게 보고할 때: **표 + 설명 2-3줄**로 끝낸다. 장황한 과정 설명 금지. 결과만 간단명료하게.
