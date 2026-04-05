# Amazon Campaign → Product Group Classification

Used by `generate_fin_data.py` (`CAT_CAMP_KEYWORDS`) to split Amazon Ads and Meta Traffic campaigns into product groups for the Hero Products dashboard tab.

## Classification Logic

Campaign name is normalized (lowercase, `|_-` → space) then checked against keywords in order. **First match wins.**

## Keyword Map

| Product Group | Keywords | Notes |
|---------------|----------|-------|
| PPSU Straw Cup | `ppsu straw`, `ppsu strawcup`, `ppsu manual`, `ppsu auto`, `stage2`, `stage 2` | Includes SP_ppsu_manual ($174K spend) and SP_ppsu_auto ($1.7K) |
| Stainless Straw Cup | `stainless straw`, `stainless strawcup`, `steel straw`, `stainlessstrawcup`, `fliptop`, `flip top`, `flip_top` | |
| PPSU Tumbler | `ppsu tumbler`, `knotted` | |
| Stainless Tumbler | `stainless tumbler`, `steel tumbler`, `vacuum`, `vacumm` | |
| PPSU Baby Bottle | `ppsu bottle`, `baby bottle`, `ppsu baby`, `stage1`, `stage 1`, `stage_1` | |
| Replacements | `replacement` | Ad-only group (no influencer content). SP_Replacements_defensive ($3.3K spend, 34x ROAS) |
| Rice Puff | `rice puff`, `rice snack`, `rice pop`, `naeiae rice` | |
| Moisturizer | `moisturizer`, `lotion` | |
| Body Wash | `body wash`, `wash` | |
| Alpremio | `alpremio` | |
| Baby Cream | `baby cream`, `cream` | |

## Brand-Level Fallbacks

| Brand | Default Group | Reason |
|-------|---------------|--------|
| Naeiae | Rice Puff | Single product brand |
| Alpremio | Alpremio | Single product brand |

## General / Brand-Wide Campaigns (NOT classified into product groups)

These campaigns are intentionally excluded from category-level view. They appear only in brand-level toggle.

| Campaign | Brand | 90d Spend | Reason |
|----------|-------|-----------|--------|
| SBV_brand | Grosmimi | $3,393 | Sponsored Brand Video — brand awareness, not product-specific |
| SB-manual | Grosmimi | $2,606 | Sponsored Brand — brand awareness |
| SD_AudienceTargeting | Grosmimi | $338 | Sponsored Display — audience retargeting, cross-product |
| SP_all_auto | Grosmimi | $72 | Auto campaign covering all products |
| CHA&MOM_Competitor Targeting | CHA&MOM | $1,363 | Competitor targeting — brand-level strategy |

## Meta Traffic Campaigns

Same keyword classification is applied to Meta Ads campaigns with `traffic`/`amz`/`amazon` in the name or landing URL.

| Campaign | Product Group |
|----------|---------------|
| AMZ_Traffic_Dental Mom_Stainless_StrawCup_* | Stainless Straw Cup |
| AMZ_Traffic_Grosmimi_* | (unclassified → brand-level) |
| AMZ_Traffic_Naeiae_* | Rice Puff (brand fallback) |
| Target_Traffic_CHA&MOM_* | (unclassified → brand-level) |
| Target_Traffic_Alpremio_* | Alpremio (brand fallback) |

## Attribution Campaign Matching

Amazon Attribution campaigns are matched to Meta Traffic campaigns by fuzzy name overlap (token matching). See `_match_attribution_reverse()` in `generate_fin_data.py`.

| Attribution Campaign | Matched Product Group | Attribution Sales (60D) |
|----------------------|----------------------|------------------------|
| AMZ_Traffic_Dental Mom_Stainless_StrawCup_20260107 | Stainless Straw Cup | $1,217 |
| AMZ \| Traffic \| Amazon Spring Sale \| 0325-0331 | (generic — brand-level) | $8,838 |
| AMZ_Traffic_Dental Mom & Livfuselli | (generic — brand-level) | $5,136 |

## Updating This Classification

When new campaigns are created:
1. Check if campaign name contains any existing keyword
2. If not, ask the marketer which product group it belongs to
3. Add keywords to `CAT_CAMP_KEYWORDS` in `generate_fin_data.py`
4. Update this reference doc
5. Regenerate `fin_data.js`

Last updated: 2026-04-05
