# ORBI Business Context

Single source of truth for ORBI-specific business data used across all 골만이 sub-skills.

---

## Entity Structure

| Entity | Full Name | Jurisdiction | Role | Address |
|--------|-----------|-------------|------|---------|
| ORBI | Orbiters Co., Ltd. | Seoul, Korea | Parent / Exporter | Unit 509, 25, Ttukseom-ro 1-gil, Seongdong-gu, Seoul 04778 |
| LFU | LittlefingerUSA Inc. | Korea | Exporter / Importer | 3, Godeung-ro, Sujeong-gu, Seongnam-si, Gyeonggi-do |
| FLT | Fleeters Inc. | Wyoming, USA | US Importer | 30 N Gould St. Ste 32663, Sheridan, WY 82801 |
| WBF | Walk by Faith | California, USA | 3PL / Final Consignee | 5900 Katella Ave, BLDG C, STE 100, Cypress, CA 90630 |

**Flow:** ORBI (Korea, manufacturing) -> LFU (export) -> FLT (US import) -> WBF (fulfillment) -> End customer

---

## Brands (10)

| Brand | Category | Key Products | Avg Sell Price | Avg COGS | GM% est. |
|-------|----------|-------------|---------------|----------|----------|
| Grosmimi | Baby cups/bottles | PPSU Straw Cup, Stainless Cup, Flip Top | $28 | $8.41 | ~70% |
| Naeiae | Baby snacks | Rice crackers (떡뻥) 5-pack sets | $18 | $5.35 | ~70% |
| CHA&MOM | Skincare | Baby lotion, body wash | $32 | $7.53 | ~76% |
| Alpremio | Nursing | Feeding seat, breast pump accessories | $38 | $12.57 | ~67% |
| Onzenna | Beauty/skincare | House brand (DTC storefront name) | $22 | $5.35 | ~76% |
| Comme Moi | Baby carrier | Baby carriers, wraps | $299 | ~$135 | ~55% |
| BabyRabbit | Baby apparel | Baby clothing sets | $29 | ~$12 | ~59% |
| Bamboobebe | Baby tableware | Bamboo plates, bowls, utensils | $47 | ~$25 | ~47% |
| Hattung | Educational | Educational toys | $123 | ~$46 | ~63% |
| Beemymagic | Baby care | Diaper bags, accessories | $23 | ~$7 | ~70% |

**Revenue share:** Grosmimi ~60%, Naeiae ~15%, Others ~25% (approximate)

---

## Sales Channels (5)

| Channel | Platform | Fee Structure | Data Source |
|---------|----------|--------------|-------------|
| Onzenna (D2C) | Shopify (zezebaebae.com) | Shopify fees ~2.9% + $0.30 | `shopify_orders_daily` |
| Amazon | FBA + FBM (3 seller accounts) | Referral 15% + FBA fees | `amazon_sales_daily`, `amazon_ads_daily` |
| TargetPlus | Target marketplace | Commission ~15% | Manual tracking |
| TikTokShop | TikTok Shop | Commission + ad attribution | Not in DataKeeper yet |
| B2B | Faire, wholesale | ~48% "discount" vs retail (wholesale pricing) | `shopify_orders_daily` (tagged) |

### Channel Classification Rules (shopify_orders_daily)

```
if "faire" in tags              -> B2B
elif "exported to amazon" in tags
  or "amazon status" in tags
  or "rejected by amazon" in tags -> D2C  (FBA MCF logistics, sale is Shopify)
elif "amazon" in tags            -> Amazon
elif "tiktok" in tags            -> TikTok
else                             -> D2C
```

**Important:** "Amazon" in shopify_orders_daily is mostly FBA Multi-Channel Fulfillment (MCF) -- the actual sale happened on Shopify, Amazon is just logistics. True Amazon sales are in `amazon_sales_daily`.

---

## Amazon Seller Accounts

| Seller | Brand | Seller ID | Notes |
|--------|-------|-----------|-------|
| Grosmimi USA | Grosmimi | A3IA0XWP2WCD15 | Largest Amazon presence |
| Fleeters Inc | Naeiae | A2RE0E056TH6H3 | Amazon Ads actively managed |
| Orbitool | CHA&MOM | A3H2CLSAX0BTX6 | Smaller, growing |

---

## Data Sources (DataKeeper PostgreSQL)

| Table | Content | Frequency | From |
|-------|---------|-----------|------|
| `shopify_orders_daily` | Orders by brand/channel/day | 2x daily | 2024-01 |
| `amazon_sales_daily` | Amazon marketplace sales (3 sellers) | 2x daily | 2024-01 |
| `amazon_ads_daily` | Amazon Ads campaign metrics | 2x daily | 2025-12 (Naeiae) |
| `amazon_campaigns` | Campaign metadata | 2x daily | 2025-12 |
| `meta_ads_daily` | Meta Ads ad-level insights | 2x daily | 2024-08 |
| `google_ads_daily` | Google Ads campaign metrics | 2x daily | 2024-01 |
| `ga4_daily` | GA4 sessions & purchases | 2x daily | 2024-01 |
| `klaviyo_daily` | Email campaign/flow metrics | 2x daily | 2024-01 |
| `gsc_daily` | Google Search Console | 2x daily | 2024-01 |

**Access:** `from data_keeper_client import DataKeeper; dk = DataKeeper(prefer_cache=False); df = dk.fetch("table_name")`

---

## Historical Price Events

### Grosmimi Price Increase (March 2025)

| Product | Before 2025-03-01 | After 2025-03-01 |
|---------|-------------------|-------------------|
| PPSU Baby Bottle 10oz | $18.60 | $19.60 |
| Stainless Straw Cup 10oz | $33.80 | $36.80 |
| PPSU Straw Cup 10oz | $22.80 | $25.80 |

Code reference: `GROSMIMI_PRICE_CUTOFF = "2025-03-01"` in `data_keeper.py`

---

## Advertising Platforms

| Platform | Brands | Monthly Spend (recent) | Data Available From |
|----------|--------|----------------------|---------------------|
| Amazon Ads | Naeiae (primary), Grosmimi, CHA&MOM | ~$80K/mo (2026) | Dec 2025 |
| Meta Ads | All brands | ~$25K/mo | Aug 2024 |
| Google Ads | All brands | ~$12K/mo | Jan 2024 |
| TikTok Ads | Limited | ~$2K/mo (2025, paused as of 2026-03) | Not in DataKeeper — manual input required for any TikTok spend in financial models |

---

## Product Categories

PPSU Straw Cup, Flip Top Cup, Stainless Cup, Tumbler, Baby Bottle, Bundles,
Replacement Parts, Accessories, Skincare, Food & Snacks, Baby Carrier,
Apparel, Tableware, Educational Toys, Baby Care, Bamboo Products, Wholesale, Other

---

## Promo Calendar (Recurring)

| Event | Typical Timing | Impact |
|-------|---------------|--------|
| New Year Sale | Jan 1-7 | Medium |
| Valentine's Day | Feb 10-14 | Low |
| Easter | Mar-Apr (varies) | Low |
| Memorial Day | Late May | Medium |
| 4th of July | Jun 28 - Jul 4 | Medium |
| Amazon Prime Day | Jul (2 days) | High (Amazon) |
| Back to School | Aug | Low |
| Labor Day | Early Sep | Medium |
| Black Friday / Cyber Monday | Late Nov | Very High |
| Holiday Season | Dec | High |
| Lunar New Year | Jan-Feb (varies) | Medium (Korean customers) |

---

## Key Financial Notes for Modeling

1. **COGS is fragmented:** SKU-level COGS available for 685 SKUs (Shopify), Amazon uses ~15% flat estimate, manual inputs supplement
2. **Balance sheet data not in DataKeeper:** Assets, liabilities, equity require manual input from user
3. **Channel fees vary:** Shopify ~3%, Amazon 15%+ referral + FBA, B2B wholesale at ~48% off retail
4. **Seasonality:** BFCM = biggest month (Nov), Prime Day = Amazon spike (Jul), Jan = post-holiday dip
5. **FX exposure:** Products manufactured in Korea (KRW), sold in US (USD). No FX hedging.
6. **Multi-brand portfolio premium:** Shared fulfillment (WBF), shared marketing team, shared tech stack = synergy value
