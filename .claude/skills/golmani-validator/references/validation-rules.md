# Validation Rules Reference

## Schema Rules (L1)

All schemas defined in `tools/kpi_schemas.py` using Pandera.

### Common Patterns
- `date`: str matching `YYYY-MM-DD` pattern, never null
- `brand`: str, nullable (Unknown allowed)
- `channel`: str, nullable
- Monetary fields (`gross_sales`, `net_sales`, `spend`): float, coerced, nullable
- Count fields (`orders`, `units`, `impressions`, `clicks`): float (coerced from int), >= 0
- `discounts`: float, can be negative (refund adjustments)

### Table-Specific
- `shopify_orders_daily`: Revenue identity enforced via L2
- `amazon_ads_daily`: `ad_type` in [SP, SB, SD]
- `meta_ads_daily`: `purchase_value` can be null
- `google_ads_daily`: `spend` already divided by 1e6

---

## Identity Rules (L2)

Only `shopify_orders_daily`:
```
|gross_sales - discounts - net_sales| < $0.02
```

---

## Coverage Rules (L3)

### Expected Brands
Grosmimi, Naeiae, CHA&MOM, Onzenna, Alpremio

### Expected Shopify Channels
D2C, Amazon, B2B

### Expected Amazon Brands
Grosmimi (GROSMIMI USA), Naeiae (Fleeters Inc), CHA&MOM (Orbitool)

---

## Through-Date Rules (L4)

```
through_date = MIN(max_date across main tables) capped at yesterday PST
Main tables: shopify_orders_daily, amazon_ads_daily, meta_ads_daily, google_ads_daily
Gap > 2 days = WARN
```

---

## Cross-Table Rules (L5)

1. **Amazon Reconciliation**: Shopify Amazon net_sales should NOT exceed SP-API net_sales by >10%
2. **Discount Rate Sanity**: Any row with discount_rate > 50% gets flagged (except PR channel = OK)

---

## Anomaly Rules (L6)

### MoM Thresholds
- Spike: >50% MoM increase
- Dip: >30% MoM decrease

### Seasonal Exceptions
| Month | Event | Allowed Spike |
|-------|-------|---------------|
| Jul | Prime Day | up to 50% |
| Nov | BFCM | up to 100% |
| Dec | Holiday tail | normal dip OK |
| Jan | Post-holiday | up to 50% dip OK |

### Ad Spend Ranges (Monthly)
| Platform | Min | Max |
|----------|-----|-----|
| Amazon Ads | $30K | $150K |
| Meta Ads | $5K | $60K |
| Google Ads | $3K | $30K |

---

## Data Availability (n.m Windows)

| Source | Available From |
|--------|---------------|
| Shopify Orders | 2024-01 |
| Amazon Sales | 2024-01 |
| Amazon Ads | 2025-12 |
| Meta Ads | 2024-08 |
| Google Ads | 2024-01 |
| GA4 | 2024-01 |
| Klaviyo | 2024-01 |
