# Polar Dashboard Builder

## Objective
Generate a comprehensive analytics dashboard (`Data Storage/Polar_Dashboard.xlsx`) from Polar Analytics MCP data. The dashboard contains 6 tabs covering sales, ad spend, organic vs paid, margins, product breakdown, and data status.

## Prerequisites
- Polar Analytics MCP connection active (via claude.ai Connectors OAuth)
- Python with `openpyxl` installed
- `.tmp/polar_data/` directory exists

## Workflow Steps

### Step 1: Initialize Polar MCP
Call `get_context` to get a fresh `conversation_id`. Note connector statuses.

### Step 2: Get Metrics & Dimensions
Call `get_metrics` and `list_dimensions` for each connector to confirm metric keys and available breakdowns.

### Step 3: Run 8 Polar Queries

| # | Metrics | Dimensions | Granularity |
|---|---------|------------|-------------|
| Q1 | blended_total_sales, blended_total_orders, blended_gross_sales, blended_discounts, blended_net_sales | custom_5036 (Brand), custom_5005 (Channel) | month |
| Q2 | shopify total_sales, AOV, orders, discounts, COGS, txn_fees, net_sales, gross_sales, CM1, CM2 | custom_5036 (Brand) | month |
| Q3 | amazon total_sales, orders, AOV, fees, COGS, gross_sales, promo_discounts, net_sales | custom_5036 (Brand) | month |
| Q4 | blended_total_sales, blended_total_orders | custom_5037 (Product Variant) | month |
| Q5 | amazonads cost, attributed_sales, clicks, impressions | campaign | month |
| Q6 | facebookads spend, purchases_conversion_value, clicks, impressions | campaign | month |
| Q7 | googleads cost, conversion_value, clicks, impressions | campaign | month |
| Q8 | tiktokads spend, purchases_conversion_value, clicks, impressions | campaign | month |

Date range: First day of analysis period to current date.

### Step 4: Save Query Results to JSON
Save each query result to `.tmp/polar_data/q{N}_{name}.json` using the save scripts:
- `.tmp/polar_data/save_q1_q4.py` — Sales data (Q1-Q4)
- `.tmp/polar_data/save_q5_q8.py` — Ads data (Q5-Q8)

JSON format: `{"tableData": [...], "totalData": [...]}`

### Step 5: Run Dashboard Builder
```bash
python tools/polar_dashboard_builder.py
```

Output: `Data Storage/Polar_Dashboard.xlsx` with 6 tabs.

## Dashboard Tabs

### Tab 1: Sales_Monthly
- A. Blended Sales by Brand (11 brands)
- B. Sales by Sales Channel x Brand (10 channels)
- C. Orders by Sales Channel x Brand
- D. AOV (Shopify + Amazon)
- E. Discounts (Shopify + Amazon)

### Tab 2: AdSpend_Monthly
- A. Ad Spend by Platform x Brand (campaign name parsing)
- B. Ad Spend by Landing Channel x Brand
- C. Ad Sales (Attributed) by Platform x Brand
- D. ROAS by Platform x Brand
- E. CPC by Platform

### Tab 3: Organic_Monthly
- A. Total Sales by Channel Group
- B. Ad-Attributed Sales by Channel Group
- C. Organic Sales (Total - Ad)
- D. Organic % by Channel Group

### Tab 4: Margin_Monthly
- A. Revenue (Shopify + Amazon Net Sales)
- B. COGS (Shopify GSheet + Amazon)
- C. Channel Fees (Amazon + Shopify)
- D. CM1, CM2 (Polar computed)
- E. Ad Spend by Brand
- F. Manual Input skeleton (yellow cells for tariffs, shipping, fulfillment, influencers)

### Tab 5: Product_Monthly
- A. Sales by Product Variant (sorted by Jan sales)
- B. Orders by Product Variant

### Tab 6: Data_Status
- Connector status
- Known data gaps
- Manual input requirements
- Future modules (TBD)

## Campaign Name Parsing Rules

Ad spend brand breakdown is derived from campaign names:

**Amazon Ads**: Default = Grosmimi. Keywords: `cha&mom` -> CHA&MOM, `naeiae` -> Naeiae, `alpremio` -> Alpremio, `comme` -> Comme Moi.

**Facebook Ads**: Keywords checked in priority order:
- Brand codes: `| gm |` / `_gm_` -> Grosmimi, `| cm |` / `_cm_` -> CHA&MOM
- Product names: `tumbler`/`stainless`/`sls` -> Grosmimi
- Brand names: `alpremio`, `naeiae`, `cha&mom`, `love&care` -> mapped directly
- Landing: `amz_traffic` -> Amazon, `shopify` -> Shopify, `target` -> Target+

**Google Ads**: All `onzenna` campaigns -> Grosmimi, Shopify landing.

**TikTok Ads**: Currently $0.

## Known Limitations
1. FB Ads connector may be in "building" state -> incomplete data
2. Campaign name parsing is ~90% accurate -> some misclassification
3. "ETC" and "B2B wholesale" brands excluded from standard tables (~$8K)
4. Organic = Total - Ad-attributed (approximate if attribution is incomplete)
5. Feb data is partial (through most recent sync date)

## Updating the Dashboard
To refresh with new data:
1. Re-run all 8 Polar queries (Step 3) with updated date range
2. Update the save scripts with new data
3. Re-run `python tools/polar_dashboard_builder.py`

## Future Enhancements
- Weekly granularity tabs (add after monthly validation)
- Inventory tracking module
- Search volume integration (Helium10 / Google Ads)
- Content pipeline (Airtable)
