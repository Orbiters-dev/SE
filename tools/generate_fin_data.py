"""Generate fin_data.js for Financial KPIs dashboard tab.

Pulls data from DataKeeper (Shopify, Amazon, Meta, Google, GA4) and computes:
  - Revenue by brand, channel, month
  - Ad spend by platform
  - Ad-attributed vs organic revenue
  - Top search queries
  - GA4 traffic sources
  - Marketing spend waterfall -> Contribution Margin

Usage:
    python tools/generate_fin_data.py
    python tools/generate_fin_data.py --months 9    # last 9 months (default)
    python tools/generate_fin_data.py --push         # git push after generation

Part of 골만이 Squad pipeline.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

from env_loader import load_env
load_env()

from data_keeper_client import DataKeeper

OUTPUT = ROOT / "docs" / "financial-dashboard" / "fin_data.js"
PST = timezone(timedelta(hours=-8))

# Brand / channel config (reuse from run_kpi_monthly)
BRAND_ORDER = ["Grosmimi", "Naeiae", "CHA&MOM", "Alpremio", "Other"]
BRAND_COLORS = {
    "Grosmimi": "#8b5cf6", "Naeiae": "#eab308", "CHA&MOM": "#0ea5e9",
    "Alpremio": "#f97316", "Other": "#94a3b8",
}
CHANNEL_COLORS = {
    "Onzenna D2C": "#6366f1", "Amazon MP": "#f59e0b", "Amazon FBA MCF": "#fb923c",
    "TikTok Shop": "#ec4899", "Target+": "#ef4444", "B2B": "#10b981", "Other": "#94a3b8",
}
AD_COLORS = {
    "Amazon Ads": "#f59e0b", "Meta CVR": "#3b82f6", "Meta Traffic": "#93c5fd",
    "Google Ads": "#10b981",
}
AVG_COGS = {
    "Grosmimi": 8.41, "Naeiae": 5.35, "CHA&MOM": 7.53,
    "Onzenna": 5.35, "Alpremio": 12.57,
}
AVG_PRICE = {
    "Grosmimi": 28.0, "Naeiae": 18.0, "CHA&MOM": 32.0,
    "Onzenna": 22.0, "Alpremio": 38.0,
}

# n.m. (not measured) — data not yet collected for these periods.
# Use None in JSON arrays; HTML renders as "n.m." in dark grey.
# Rule: 0 means genuinely zero activity; None means no data source.
_NM_RULES = {
    "amazon_ads":   lambda m: False,  # backfill covers all months now
    "fba_fulfill":  lambda m: True,   # FBA fee report not yet running
    "sku_cogs":     lambda m: m < "2025-10",  # SKU daily starts Oct 2025
}

# NAS paths for SKU-level COGS (Option B from run_kpi_monthly.py)
_NAS_COGS_DIR = Path(r"Z:\Orbiters\ORBI CLAUDE_0223\ORBITERS CLAUDE\ORBITERS CLAUDE\Shared\NoPolar KPIs\Data config sheet")

# Amazon Ads backfill: Polar Excel "IR 매출분석" row 119 (Jan-Nov 2025, DK starts Dec 2025)
_AMZ_ADS_BACKFILL = {
    "2025-01": 47847, "2025-02": 38004, "2025-03": 40882, "2025-04": 46141,
    "2025-05": 45848, "2025-06": 56294, "2025-07": 82121, "2025-08": 67267,
    "2025-09": 55637, "2025-10": 59565, "2025-11": 65391,
}

# Influencer costs: PAID (PayPal) + NON-PAID (Sample COGS + Shipping $10/unit)
# Source: q11_paypal_transactions.json + q10_influencer_orders.json + COGS by SKU.xlsx
_INFLUENCER_COST = {
    "2025-01": 3311, "2025-02": 5282, "2025-03": 2811, "2025-04": 3225,
    "2025-05": 3184, "2025-06": 2875, "2025-07": 5045, "2025-08": 19121,
    "2025-09": 10271, "2025-10": 23233, "2025-11": 4420, "2025-12": 2156,
    "2026-01": 8235, "2026-02": 11911, "2026-03": 7290,
}


def load_sku_cogs_map():
    """Load SKU -> COGS from NAS Excel. Returns {sku_lower: cost}."""
    try:
        import openpyxl
        p = _NAS_COGS_DIR / "COGS by SKU.xlsx"
        if not p.exists():
            return {}
        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
        rows = list(wb.active.iter_rows(values_only=True))
        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        sku_col = next((i for i, h in enumerate(headers) if "sku" in h), None)
        cost_col = next((i for i, h in enumerate(headers) if "cost" in h and "type" not in h), None)
        if sku_col is None or cost_col is None:
            wb.close()
            return {}
        out = {}
        for row in rows[1:]:
            sku = str(row[sku_col] or "").strip().lower()
            try:
                cost = float(row[cost_col] or 0)
            except (TypeError, ValueError):
                continue
            if sku and cost > 0:
                out[sku] = cost
        wb.close()
        return out
    except Exception as e:
        print(f"  [WARN] SKU COGS load failed: {e}")
        return {}


def build_sku_cogs_monthly(amazon_sku_rows, shopify_sku_rows, cogs_map, through, brand_order):
    """Compute per-brand per-month COGS from SKU-level data.

    Returns:
        amz_cogs[brand][month] = total COGS (float)
        shop_cogs[brand][month] = total COGS (float)  -- Shopify D2C only (excl PR/Amazon)
        shop_cogs_by_channel[channel][brand][month] = total COGS (float)
    """
    SKIP_CH = {"PR", "Amazon"}
    amz_cogs = defaultdict(lambda: defaultdict(float))
    shop_cogs = defaultdict(lambda: defaultdict(float))
    shop_cogs_by_channel = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    # Volume-weighted avg COGS per brand (for unmatched SKUs)
    _brand_vw = defaultdict(lambda: {"cost_sum": 0.0, "units": 0})

    # Pass 1: compute brand vw avg from matched amazon SKUs
    for r in amazon_sku_rows:
        sku = str(r.get("sku", "")).strip().lower()
        cost = cogs_map.get(sku)
        if cost:
            b = r.get("brand", "Other")
            u = int(r.get("units", 0) or 0)
            _brand_vw[b]["cost_sum"] += cost * u
            _brand_vw[b]["units"] += u
    for r in shopify_sku_rows:
        sku = str(r.get("sku", "")).strip().lower()
        cost = cogs_map.get(sku)
        if cost:
            b = r.get("brand", "Other")
            u = int(r.get("units", 0) or 0)
            _brand_vw[b]["cost_sum"] += cost * u
            _brand_vw[b]["units"] += u

    brand_vw_avg = {}
    for b, v in _brand_vw.items():
        brand_vw_avg[b] = v["cost_sum"] / v["units"] if v["units"] else AVG_COGS.get(b, 8)

    # Track SKU units per month (for partial-month detection)
    amz_sku_units = defaultdict(int)  # month -> total units from SKU data

    # Pass 2: compute monthly COGS
    for r in amazon_sku_rows:
        d = r.get("date", "")
        if not d or d > through:
            continue
        m = d[:7]
        b = r.get("brand", "Other")
        if b not in brand_order and b != "Other":
            b = "Other"
        u = int(r.get("units", 0) or 0)
        sku = str(r.get("sku", "")).strip().lower()
        cost = cogs_map.get(sku, brand_vw_avg.get(b, AVG_COGS.get(b, 8)))
        amz_cogs[b][m] += u * cost
        amz_sku_units[m] += u

    shop_sku_units = defaultdict(int)
    for r in shopify_sku_rows:
        d = r.get("date", "")
        if not d or d > through:
            continue
        ch = r.get("channel", "")
        if ch in SKIP_CH:
            continue
        m = d[:7]
        b = r.get("brand", "Other")
        if b not in brand_order and b != "Other":
            b = "Other"
        u = int(r.get("units", 0) or 0)
        sku = str(r.get("sku", "")).strip().lower()
        cost = cogs_map.get(sku, brand_vw_avg.get(b, AVG_COGS.get(b, 8)))
        shop_cogs[b][m] += u * cost
        shop_sku_units[m] += u
        # Map channel for channel P&L
        ch_mapped = "Onzenna D2C"
        if ch == "B2B" or ch == "Wholesale":
            ch_mapped = "B2B"
        elif ch == "TikTok":
            ch_mapped = "TikTok"
        shop_cogs_by_channel[ch_mapped][b][m] += u * cost

    return amz_cogs, shop_cogs, shop_cogs_by_channel, brand_vw_avg, amz_sku_units, shop_sku_units


CHANNEL_PNL_COLORS = {
    "Amazon MP": "#f59e0b",
    "Onzenna D2C": "#6366f1",
    "Target+": "#ef4444",
    "B2B": "#10b981",
    "Other": "#94a3b8",
}



def generate():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Financial KPIs data")
    parser.add_argument("--months", type=int, default=14)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    dk = DataKeeper(prefer_cache=False)
    now_pst = datetime.now(PST)
    today = now_pst.date()
    yesterday = (today - timedelta(days=1)).isoformat()

    # Date ranges
    days_back = args.months * 31 + 30  # extra buffer
    d7 = (today - timedelta(days=7)).isoformat()
    d30 = (today - timedelta(days=30)).isoformat()
    mtd_start = today.replace(day=1).isoformat()
    ytd_start = f"{today.year}-01-01"

    import calendar

    print("=== Generating Financial KPIs Data ===")
    print(f"  Today (PST): {today}")

    # ── 1. Load all DataKeeper tables ─────────────────────────────────────────
    print("\n[1/7] Loading DataKeeper tables...")
    shopify = dk.get("shopify_orders_daily", days=days_back)
    amazon_sales = dk.get("amazon_sales_daily", days=days_back)
    amazon_ads = dk.get("amazon_ads_daily", days=days_back)
    meta_ads = dk.get("meta_ads_daily", days=days_back)
    google_ads = dk.get("google_ads_daily", days=days_back)
    ga4 = dk.get("ga4_daily", days=days_back)
    search_terms = dk.get("amazon_ads_search_terms", days=30)
    gsc = dk.get("gsc_daily", days=30)
    brand_analytics = dk.get("amazon_brand_analytics", days=30)
    shopify_sku = dk.get("shopify_orders_sku_daily", date_from="2025-06-01")
    amazon_sku = dk.get("amazon_sales_sku_daily", days=days_back)
    klaviyo = dk.get("klaviyo_daily", days=days_back)
    print(f"  Shopify: {len(shopify)} rows, Amazon Sales: {len(amazon_sales)}")
    print(f"  Amazon Ads: {len(amazon_ads)}, Meta: {len(meta_ads)}, Google: {len(google_ads)}")
    print(f"  GA4: {len(ga4)}, Search Terms: {len(search_terms)}, GSC: {len(gsc)}")
    print(f"  Brand Analytics: {len(brand_analytics)}, Shopify SKU: {len(shopify_sku)}, Amazon SKU: {len(amazon_sku)}")
    print(f"  Klaviyo: {len(klaviyo)}")

    # ── Load SKU-level COGS map ──────────────────────────────────────────────
    sku_cogs_map = load_sku_cogs_map()
    print(f"  SKU COGS map: {len(sku_cogs_map)} SKUs {'(NAS)' if sku_cogs_map else '(fallback to AVG_COGS)'}")

    # ── Compute through-date ─────────────────────────────────────────────────
    def max_date(rows):
        dates = [r.get("date", "") for r in rows if r.get("date")]
        return max(dates) if dates else "0000"

    through = min(max_date(shopify), max_date(amazon_ads), yesterday)
    print(f"  Through-date: {through}")

    # ── Data source freshness metadata ────────────────────────────────────────
    def source_meta(name, rows, label, refresh="2x daily"):
        dates = [r.get("date", "") for r in rows if r.get("date")]
        return {
            "name": name,
            "label": label,
            "rows": len(rows),
            "min_date": min(dates) if dates else "",
            "max_date": max(dates) if dates else "",
            "refresh": refresh,
        }

    data_sources = [
        source_meta("shopify_orders_daily", shopify, "Shopify Orders"),
        source_meta("amazon_sales_daily", amazon_sales, "Amazon Sales (SP-API)"),
        source_meta("amazon_ads_daily", amazon_ads, "Amazon Ads"),
        source_meta("meta_ads_daily", meta_ads, "Meta Ads"),
        source_meta("google_ads_daily", google_ads, "Google Ads"),
        source_meta("ga4_daily", ga4, "GA4 Analytics"),
        source_meta("amazon_ads_search_terms", search_terms, "Amazon Search Terms", "1x daily"),
        source_meta("gsc_daily", gsc, "Google Search Console"),
        source_meta("klaviyo_daily", klaviyo, "Klaviyo Email"),
    ]

    # ── Partial month detection ───────────────────────────────────────────────
    through_date_obj = datetime.strptime(through, "%Y-%m-%d").date()
    current_month = through[:7]  # e.g. "2026-03"
    days_elapsed = through_date_obj.day
    days_in_month = calendar.monthrange(through_date_obj.year, through_date_obj.month)[1]
    is_partial = days_elapsed < days_in_month
    fm_multiplier = round(days_in_month / days_elapsed, 4) if days_elapsed > 0 else 1
    print(f"  Partial month: {current_month} ({days_elapsed}/{days_in_month}d) -> multiplier {fm_multiplier}x")

    partial_month_info = {
        "month": current_month,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "is_partial": is_partial,
        "multiplier": fm_multiplier,
    }

    # ── Helper: date -> ISO week key ────────────────────────────────────────
    def _week_key(date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        iy, iw, _ = dt.isocalendar()
        return f"{iy}-W{iw:02d}"

    # ── 2. Revenue by Brand (Shopify only, PR/Amazon excluded) ─────────────────
    # Amazon channel = stale FBA MCF rows in PG (now reclassified as D2C in current code)
    # True Amazon Marketplace sales come from amazon_sales_daily (SP-API)
    SKIP_CHANNELS = {"PR", "Amazon"}
    print("\n[2/7] Computing revenue by brand...")
    brand_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gross": 0, "net": 0, "disc": 0, "orders": 0, "units": 0
    }))
    # Weekly mirrors
    brand_weekly = defaultdict(lambda: defaultdict(lambda: {
        "gross": 0, "net": 0, "disc": 0, "orders": 0, "units": 0
    }))
    amz_brand_weekly = defaultdict(lambda: defaultdict(lambda: {
        "gross": 0, "net": 0, "orders": 0, "units": 0
    }))
    channel_weekly = defaultdict(lambda: defaultdict(lambda: {"net": 0, "orders": 0}))
    ad_weekly = defaultdict(lambda: defaultdict(lambda: {
        "spend": 0, "sales": 0, "impressions": 0, "clicks": 0
    }))
    brand_ad_weekly = defaultdict(lambda: defaultdict(lambda: {"spend": 0, "sales": 0}))

    for r in shopify:
        d = r.get("date", "")
        if not d or d > through:
            continue
        if r.get("channel") in SKIP_CHANNELS:
            continue
        month = d[:7]
        brand = r.get("brand") or "Other"
        if brand not in BRAND_ORDER:
            brand = "Other"
        brand_monthly[brand][month]["gross"] += float(r.get("gross_sales") or 0)
        brand_monthly[brand][month]["net"] += float(r.get("net_sales") or 0)
        brand_monthly[brand][month]["disc"] += float(r.get("discounts") or 0)
        brand_monthly[brand][month]["orders"] += int(r.get("orders") or 0)
        brand_monthly[brand][month]["units"] += int(r.get("units") or 0)
        wk = _week_key(d)
        brand_weekly[brand][wk]["gross"] += float(r.get("gross_sales") or 0)
        brand_weekly[brand][wk]["net"] += float(r.get("net_sales") or 0)
        brand_weekly[brand][wk]["disc"] += float(r.get("discounts") or 0)
        brand_weekly[brand][wk]["orders"] += int(r.get("orders") or 0)
        brand_weekly[brand][wk]["units"] += int(r.get("units") or 0)

    # Amazon SP-API revenue by brand
    amz_brand_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gross": 0, "net": 0, "orders": 0, "units": 0
    }))
    for r in amazon_sales:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        brand = r.get("brand") or "Other"
        if brand not in BRAND_ORDER:
            brand = "Other"
        amz_brand_monthly[brand][month]["gross"] += float(r.get("gross_sales") or r.get("ordered_product_sales") or 0)
        amz_brand_monthly[brand][month]["net"] += float(r.get("net_sales") or 0)
        amz_brand_monthly[brand][month]["orders"] += int(r.get("orders") or 0)
        amz_brand_monthly[brand][month]["units"] += int(r.get("units") or 0)
        wk = _week_key(d)
        amz_brand_weekly[brand][wk]["gross"] += float(r.get("gross_sales") or r.get("ordered_product_sales") or 0)
        amz_brand_weekly[brand][wk]["net"] += float(r.get("net_sales") or 0)
        amz_brand_weekly[brand][wk]["orders"] += int(r.get("orders") or 0)
        amz_brand_weekly[brand][wk]["units"] += int(r.get("units") or 0)

    # ── 3. Revenue by Channel (Shopify channels + Amazon MP) ──────────────────
    print("\n[3/7] Computing revenue by channel...")
    channel_monthly = defaultdict(lambda: defaultdict(lambda: {"net": 0, "orders": 0}))

    CHANNEL_MAP = {
        "D2C": "Onzenna D2C",
        "Amazon": "Amazon FBA MCF",
        "TikTok": "TikTok Shop",
        "B2B": "B2B",
        "Target+": "Target+",
    }

    for r in shopify:
        d = r.get("date", "")
        if not d or d > through:
            continue
        if r.get("channel") in SKIP_CHANNELS:
            continue
        month = d[:7]
        raw_ch = r.get("channel") or "Other"
        ch = CHANNEL_MAP.get(raw_ch, "Other")
        channel_monthly[ch][month]["net"] += float(r.get("net_sales") or 0)
        channel_monthly[ch][month]["orders"] += int(r.get("orders") or 0)
        wk = _week_key(d)
        channel_weekly[ch][wk]["net"] += float(r.get("net_sales") or 0)
        channel_weekly[ch][wk]["orders"] += int(r.get("orders") or 0)

    # Amazon Marketplace (SP-API)
    for r in amazon_sales:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        channel_monthly["Amazon MP"][month]["net"] += float(r.get("net_sales") or 0)
        channel_monthly["Amazon MP"][month]["orders"] += int(r.get("orders") or 0)
        wk = _week_key(d)
        channel_weekly["Amazon MP"][wk]["net"] += float(r.get("net_sales") or 0)
        channel_weekly["Amazon MP"][wk]["orders"] += int(r.get("orders") or 0)

    # ── 4. Ad Spend by Platform ───────────────────────────────────────────────
    print("\n[4/7] Computing ad spend by platform...")
    ad_monthly = defaultdict(lambda: defaultdict(lambda: {
        "spend": 0, "sales": 0, "impressions": 0, "clicks": 0
    }))

    for r in amazon_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        ad_monthly["Amazon Ads"][month]["spend"] += float(r.get("spend") or 0)
        ad_monthly["Amazon Ads"][month]["sales"] += float(r.get("sales") or 0)
        ad_monthly["Amazon Ads"][month]["impressions"] += int(r.get("impressions") or 0)
        ad_monthly["Amazon Ads"][month]["clicks"] += int(r.get("clicks") or 0)
        wk = _week_key(d)
        ad_weekly["Amazon Ads"][wk]["spend"] += float(r.get("spend") or 0)
        ad_weekly["Amazon Ads"][wk]["sales"] += float(r.get("sales") or 0)
        ad_weekly["Amazon Ads"][wk]["impressions"] += int(r.get("impressions") or 0)
        ad_weekly["Amazon Ads"][wk]["clicks"] += int(r.get("clicks") or 0)

    for r in meta_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        # Classify by landing destination: Amazon-landing = Traffic, else = CVR
        cname = (r.get("campaign_name") or "").lower()
        landing = (r.get("landing_url") or "").lower()
        is_amz = "amazon" in cname or "amz" in cname or "amazon" in landing
        label = "Meta Traffic" if is_amz else "Meta CVR"
        ad_monthly[label][month]["spend"] += float(r.get("spend") or 0)
        ad_monthly[label][month]["sales"] += float(r.get("purchase_value") or 0)
        ad_monthly[label][month]["impressions"] += int(r.get("impressions") or 0)
        ad_monthly[label][month]["clicks"] += int(r.get("clicks") or 0)
        wk = _week_key(d)
        ad_weekly[label][wk]["spend"] += float(r.get("spend") or 0)
        ad_weekly[label][wk]["sales"] += float(r.get("purchase_value") or 0)
        ad_weekly[label][wk]["impressions"] += int(r.get("impressions") or 0)
        ad_weekly[label][wk]["clicks"] += int(r.get("clicks") or 0)

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        ad_monthly["Google Ads"][month]["spend"] += float(r.get("spend") or 0)
        ad_monthly["Google Ads"][month]["sales"] += float(r.get("conversion_value") or 0)
        ad_monthly["Google Ads"][month]["impressions"] += int(r.get("impressions") or 0)
        ad_monthly["Google Ads"][month]["clicks"] += int(r.get("clicks") or 0)
        wk = _week_key(d)
        ad_weekly["Google Ads"][wk]["spend"] += float(r.get("spend") or 0)
        ad_weekly["Google Ads"][wk]["sales"] += float(r.get("conversion_value") or 0)
        ad_weekly["Google Ads"][wk]["impressions"] += int(r.get("impressions") or 0)
        ad_weekly["Google Ads"][wk]["clicks"] += int(r.get("clicks") or 0)

    # ── Brand-level ad performance ────────────────────────────────────────────
    brand_ad_monthly = defaultdict(lambda: defaultdict(lambda: {"spend": 0, "sales": 0}))

    for r in amazon_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        brand = r.get("brand") or "Other"
        if brand not in BRAND_ORDER:
            brand = "Other"
        brand_ad_monthly[brand][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_monthly[brand][month]["sales"] += float(r.get("sales") or 0)
        wk = _week_key(d)
        brand_ad_weekly[brand][wk]["spend"] += float(r.get("spend") or 0)
        brand_ad_weekly[brand][wk]["sales"] += float(r.get("sales") or 0)

    for r in meta_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        brand = r.get("brand") or "Other"
        if brand not in BRAND_ORDER:
            brand = "Other"
        brand_ad_monthly[brand][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_monthly[brand][month]["sales"] += float(r.get("purchase_value") or 0)
        wk = _week_key(d)
        brand_ad_weekly[brand][wk]["spend"] += float(r.get("spend") or 0)
        brand_ad_weekly[brand][wk]["sales"] += float(r.get("purchase_value") or 0)

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        # All Google Ads campaigns are Grosmimi (Mint | prefix)
        brand_ad_monthly["Grosmimi"][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_monthly["Grosmimi"][month]["sales"] += float(r.get("conversion_value") or 0)
        wk = _week_key(d)
        brand_ad_weekly["Grosmimi"][wk]["spend"] += float(r.get("spend") or 0)
        brand_ad_weekly["Grosmimi"][wk]["sales"] += float(r.get("conversion_value") or 0)

    # ── Brand × Platform ad breakdown ─────────────────────────────────────────
    brand_ad_by_platform = defaultdict(lambda: defaultdict(lambda: defaultdict(
        lambda: {"spend": 0, "sales": 0, "impressions": 0, "clicks": 0}
    )))
    brand_ad_by_platform_wk = defaultdict(lambda: defaultdict(lambda: defaultdict(
        lambda: {"spend": 0, "sales": 0, "impressions": 0, "clicks": 0}
    )))

    for r in amazon_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        brand = r.get("brand") or "Other"
        if brand not in BRAND_ORDER:
            brand = "Other"
        month = d[:7]
        wk = _week_key(d)
        brand_ad_by_platform["Amazon Ads"][brand][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_by_platform["Amazon Ads"][brand][month]["sales"] += float(r.get("sales") or 0)
        brand_ad_by_platform["Amazon Ads"][brand][month]["impressions"] += int(r.get("impressions") or 0)
        brand_ad_by_platform["Amazon Ads"][brand][month]["clicks"] += int(r.get("clicks") or 0)
        brand_ad_by_platform_wk["Amazon Ads"][brand][wk]["spend"] += float(r.get("spend") or 0)
        brand_ad_by_platform_wk["Amazon Ads"][brand][wk]["sales"] += float(r.get("sales") or 0)
        brand_ad_by_platform_wk["Amazon Ads"][brand][wk]["impressions"] += int(r.get("impressions") or 0)
        brand_ad_by_platform_wk["Amazon Ads"][brand][wk]["clicks"] += int(r.get("clicks") or 0)

    for r in meta_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        brand = r.get("brand") or "Other"
        if brand not in BRAND_ORDER:
            brand = "Other"
        cname = (r.get("campaign_name") or "").lower()
        landing = (r.get("landing_url") or "").lower()
        is_amz = "amazon" in cname or "amz" in cname or "amazon" in landing
        label = "Meta Traffic" if is_amz else "Meta CVR"
        month = d[:7]
        wk = _week_key(d)
        brand_ad_by_platform[label][brand][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_by_platform[label][brand][month]["sales"] += float(r.get("purchase_value") or 0)
        brand_ad_by_platform[label][brand][month]["impressions"] += int(r.get("impressions") or 0)
        brand_ad_by_platform[label][brand][month]["clicks"] += int(r.get("clicks") or 0)
        brand_ad_by_platform_wk[label][brand][wk]["spend"] += float(r.get("spend") or 0)
        brand_ad_by_platform_wk[label][brand][wk]["sales"] += float(r.get("purchase_value") or 0)
        brand_ad_by_platform_wk[label][brand][wk]["impressions"] += int(r.get("impressions") or 0)
        brand_ad_by_platform_wk[label][brand][wk]["clicks"] += int(r.get("clicks") or 0)

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        brand = r.get("brand") or "Grosmimi"
        if brand not in BRAND_ORDER:
            brand = "Grosmimi"
        month = d[:7]
        wk = _week_key(d)
        brand_ad_by_platform["Google Ads"][brand][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_by_platform["Google Ads"][brand][month]["sales"] += float(r.get("conversion_value") or 0)
        brand_ad_by_platform["Google Ads"][brand][month]["impressions"] += int(r.get("impressions") or 0)
        brand_ad_by_platform["Google Ads"][brand][month]["clicks"] += int(r.get("clicks") or 0)
        brand_ad_by_platform_wk["Google Ads"][brand][wk]["spend"] += float(r.get("spend") or 0)
        brand_ad_by_platform_wk["Google Ads"][brand][wk]["sales"] += float(r.get("conversion_value") or 0)
        brand_ad_by_platform_wk["Google Ads"][brand][wk]["impressions"] += int(r.get("impressions") or 0)
        brand_ad_by_platform_wk["Google Ads"][brand][wk]["clicks"] += int(r.get("clicks") or 0)

    # ── Build month list ──────────────────────────────────────────────────────
    all_months_set = set()
    for d in [brand_monthly, amz_brand_monthly, channel_monthly]:
        for entity in d.values():
            all_months_set |= set(entity.keys())
    for platform in ad_monthly.values():
        all_months_set |= set(platform.keys())

    # Filter to last N months
    cutoff_month = (today - timedelta(days=args.months * 30)).strftime("%Y-%m")
    months = sorted(m for m in all_months_set if m >= cutoff_month)
    ad_start_idx = next((i for i, m in enumerate(months) if m >= "2026-01"), 0)
    ad_months = months[ad_start_idx:]
    print(f"  Months: {months[0]} -> {months[-1]} ({len(months)} months)")
    print(f"  Ad months: {ad_months[0] if ad_months else 'none'} -> {ad_months[-1] if ad_months else 'none'} (from idx {ad_start_idx})")

    # ── 4b. SKU-level COGS by brand/month ────────────────────────────────────
    amz_sku_cogs, shop_sku_cogs, shop_cogs_by_channel, brand_vw_cogs, amz_sku_units_m, shop_sku_units_m = build_sku_cogs_monthly(
        amazon_sku, shopify_sku, sku_cogs_map, through, BRAND_ORDER
    )
    if sku_cogs_map:
        print(f"  SKU COGS built - VW avg: {', '.join(f'{b}=${v:.2f}' for b, v in sorted(brand_vw_cogs.items()) if b in BRAND_ORDER[:4])}")
    else:
        print(f"  SKU COGS: using flat AVG_COGS (NAS unavailable)")

    # ── 5. Compute summary KPIs (7d, 30d, MTD) ───────────────────────────────
    print("\n[5/7] Computing KPI summaries...")

    def compute_period_kpi(date_from, date_to):
        """Compute KPIs for a date range from raw daily data."""
        shopify_rev = 0
        shopify_gross = 0
        shopify_disc = 0
        shopify_orders = 0
        shopify_units = 0
        shopify_cogs = 0

        for r in shopify:
            d = r.get("date", "")
            if not d or d < date_from or d > date_to or r.get("channel") in SKIP_CHANNELS:
                continue
            net = float(r.get("net_sales") or 0)
            gross = float(r.get("gross_sales") or 0)
            disc = float(r.get("discounts") or 0)
            units = int(r.get("units") or 0)
            brand = r.get("brand") or "Other"
            cogs_rate = AVG_COGS.get(brand, 8.0)
            price_rate = AVG_PRICE.get(brand, 25.0)
            if units == 0 and gross > 0:
                units = int(gross / price_rate)
            shopify_rev += net
            shopify_gross += gross
            shopify_disc += disc
            shopify_orders += int(r.get("orders") or 0)
            shopify_units += units
            shopify_cogs += units * cogs_rate

        amz_rev = 0
        amz_orders = 0
        for r in amazon_sales:
            d = r.get("date", "")
            if not d or d < date_from or d > date_to:
                continue
            amz_rev += float(r.get("net_sales") or 0)
            amz_orders += int(r.get("orders") or 0)

        total_rev = shopify_rev + amz_rev
        total_orders = shopify_orders + amz_orders

        # Ad spend
        total_ad_spend = 0
        ad_attributed_sales = 0
        for r in amazon_ads:
            d = r.get("date", "")
            if d and date_from <= d <= date_to:
                total_ad_spend += float(r.get("spend") or 0)
                ad_attributed_sales += float(r.get("sales") or 0)
        for r in meta_ads:
            d = r.get("date", "")
            if d and date_from <= d <= date_to:
                total_ad_spend += float(r.get("spend") or 0)
                ad_attributed_sales += float(r.get("purchase_value") or 0)
        for r in google_ads:
            d = r.get("date", "")
            if d and date_from <= d <= date_to:
                total_ad_spend += float(r.get("spend") or 0)
                ad_attributed_sales += float(r.get("conversion_value") or 0)

        # Amazon COGS estimate (brand-level)
        amz_cogs = 0
        for r in amazon_sales:
            d = r.get("date", "")
            if not d or d < date_from or d > date_to:
                continue
            brand = r.get("brand") or "Other"
            units = int(r.get("units") or 0)
            if units == 0:
                net = float(r.get("net_sales") or 0)
                if net > 0:
                    units = int(net / AVG_PRICE.get(brand, 25))
            amz_cogs += units * AVG_COGS.get(brand, 8)

        total_cogs = shopify_cogs + amz_cogs
        gm = total_rev - total_cogs  # GM = Total Revenue - Total COGS
        total_discounts = abs(shopify_disc)
        mkt_total = total_ad_spend + total_discounts  # + seeding (not available)
        cm = gm - mkt_total  # CM = GM - MKT Total

        return {
            "total_revenue": round(total_rev),
            "shopify_revenue": round(shopify_rev),
            "amazon_revenue": round(amz_rev),
            "total_orders": total_orders,
            "total_ad_spend": round(total_ad_spend),
            "ad_attributed_sales": round(ad_attributed_sales),
            "organic_revenue": round(total_rev - ad_attributed_sales) if total_rev > ad_attributed_sales else 0,
            "gross_margin": round(gm),
            "gm_pct": round(gm / total_rev * 100, 1) if total_rev else 0,
            "contribution_margin": round(cm),
            "cm_pct": round(cm / total_rev * 100, 1) if total_rev else 0,
            "mer": round(total_rev / total_ad_spend, 2) if total_ad_spend else 0,
            "roas": round(ad_attributed_sales / total_ad_spend, 2) if total_ad_spend else 0,
            "discount_rate": round(abs(shopify_disc) / shopify_gross * 100, 1) if shopify_gross else 0,
        }

    summary = {
        "7d": compute_period_kpi(d7, through),
        "30d": compute_period_kpi(d30, through),
        "mtd": compute_period_kpi(mtd_start, through),
    }

    # ── 6. Search Queries & Traffic Sources ───────────────────────────────────
    print("\n[6/7] Computing search queries & traffic sources...")

    # Amazon search terms (top 30 by spend) — with brand
    st_agg = defaultdict(lambda: {"impressions": 0, "clicks": 0, "spend": 0, "sales": 0, "orders": 0, "brands": set()})
    for r in search_terms:
        q = (r.get("query") or r.get("search_term") or "").strip().lower()
        if not q:
            continue
        brand = r.get("brand") or "Other"
        st_agg[q]["impressions"] += int(r.get("impressions") or 0)
        st_agg[q]["clicks"] += int(r.get("clicks") or 0)
        st_agg[q]["spend"] += float(r.get("spend") or r.get("cost") or 0)
        st_agg[q]["sales"] += float(r.get("sales") or r.get("revenue") or 0)
        st_agg[q]["orders"] += int(r.get("orders") or r.get("conversions") or 0)
        st_agg[q]["brands"].add(brand)

    # Also aggregate per-brand for brand sub-tabs
    st_brand_agg = defaultdict(lambda: defaultdict(lambda: {"impressions": 0, "clicks": 0, "spend": 0, "sales": 0, "orders": 0}))
    for r in search_terms:
        q = (r.get("query") or r.get("search_term") or "").strip().lower()
        brand = r.get("brand") or "Other"
        if not q:
            continue
        st_brand_agg[brand][q]["impressions"] += int(r.get("impressions") or 0)
        st_brand_agg[brand][q]["clicks"] += int(r.get("clicks") or 0)
        st_brand_agg[brand][q]["spend"] += float(r.get("spend") or r.get("cost") or 0)
        st_brand_agg[brand][q]["sales"] += float(r.get("sales") or r.get("revenue") or 0)
        st_brand_agg[brand][q]["orders"] += int(r.get("orders") or r.get("conversions") or 0)

    def build_search_data(agg, limit=30):
        top = sorted(agg.items(), key=lambda x: x[1]["spend"], reverse=True)[:limit]
        result = []
        for q, v in top:
            acos = round(v["spend"] / v["sales"] * 100, 1) if v["sales"] else 0
            ctr = round(v["clicks"] / v["impressions"] * 100, 2) if v["impressions"] else 0
            cvr = round(v["orders"] / v["clicks"] * 100, 2) if v["clicks"] else 0
            entry = {
                "query": q,
                "impressions": v["impressions"],
                "clicks": v["clicks"],
                "ctr": ctr,
                "spend": round(v["spend"], 2),
                "sales": round(v["sales"], 2),
                "orders": v["orders"],
                "acos": acos,
                "cvr": cvr,
            }
            if "brands" in v:
                entry["brand"] = ", ".join(sorted(v["brands"]))
            result.append(entry)
        return result

    search_data = build_search_data(st_agg)
    search_by_brand = {}
    for brand, agg in st_brand_agg.items():
        search_by_brand[brand] = build_search_data(agg, 20)

    # GSC queries (top 20 by clicks)
    gsc_agg = defaultdict(lambda: {"impressions": 0, "clicks": 0, "position": []})
    for r in gsc:
        q = (r.get("query") or "").strip().lower()
        if not q:
            continue
        gsc_agg[q]["impressions"] += int(r.get("impressions") or 0)
        gsc_agg[q]["clicks"] += int(r.get("clicks") or 0)
        pos = float(r.get("position") or r.get("avg_position") or 0)
        if pos > 0:
            gsc_agg[q]["position"].append(pos)

    top_gsc = sorted(gsc_agg.items(), key=lambda x: x[1]["clicks"], reverse=True)[:20]
    gsc_data = []
    for q, v in top_gsc:
        avg_pos = round(sum(v["position"]) / len(v["position"]), 1) if v["position"] else 0
        ctr = round(v["clicks"] / v["impressions"] * 100, 2) if v["impressions"] else 0
        gsc_data.append({
            "query": q,
            "impressions": v["impressions"],
            "clicks": v["clicks"],
            "ctr": ctr,
            "position": avg_pos,
        })

    # ── Keyword Rankings (GSC daily position tracking) ────────────────────────
    # Top keywords by clicks, with daily position history for sparklines
    gsc_full = dk.get("gsc_daily", days=90)
    kw_daily = defaultdict(lambda: defaultdict(lambda: {"clicks": 0, "impressions": 0, "position": []}))
    for r in gsc_full:
        q = (r.get("query") or "").strip().lower()
        d = r.get("date", "")
        if not q or not d:
            continue
        kw_daily[q][d]["clicks"] += int(r.get("clicks") or 0)
        kw_daily[q][d]["impressions"] += int(r.get("impressions") or 0)
        pos = float(r.get("position") or 0)
        if pos > 0:
            kw_daily[q][d]["position"].append(pos)

    kw_dates = sorted(set(d for days_data in kw_daily.values() for d in days_data.keys()))

    def build_kw_rankings(kw_daily, kw_dates, cutoff_date, period_label):
        """Build keyword rankings for a specific date range."""
        kw_totals = {}
        for q, days_data in kw_daily.items():
            filtered = {d: dd for d, dd in days_data.items() if d >= cutoff_date}
            if not filtered:
                continue
            total_clicks = sum(dd["clicks"] for dd in filtered.values())
            total_impr = sum(dd["impressions"] for dd in filtered.values())
            all_pos = [p for dd in filtered.values() for p in dd["position"]]
            avg_pos = round(sum(all_pos) / len(all_pos), 1) if all_pos else 0
            kw_totals[q] = {"clicks": total_clicks, "impressions": total_impr, "avg_position": avg_pos}

        top_kw = sorted(kw_totals.items(), key=lambda x: x[1]["clicks"], reverse=True)[:25]
        filtered_dates = sorted(d for d in kw_dates if d >= cutoff_date)

        rankings = []
        for q, totals in top_kw:
            # Weekly average positions for trend
            weekly_positions = []
            for i in range(0, len(filtered_dates), 7):
                week_dates = filtered_dates[i:i+7]
                week_pos = []
                for d in week_dates:
                    dd = kw_daily[q].get(d, {})
                    week_pos.extend(dd.get("position", []))
                if week_pos:
                    weekly_positions.append(round(sum(week_pos) / len(week_pos), 1))
                else:
                    weekly_positions.append(None)
            ctr = round(totals["clicks"] / totals["impressions"] * 100, 2) if totals["impressions"] else 0
            rankings.append({
                "query": q,
                "clicks": totals["clicks"],
                "impressions": totals["impressions"],
                "avg_position": totals["avg_position"],
                "ctr": ctr,
                "weekly_positions": weekly_positions,
            })
        return rankings

    # Build rankings for 7D, 30D, 90D
    cutoff_7d = (today - timedelta(days=7)).isoformat()
    cutoff_30d = (today - timedelta(days=30)).isoformat()
    cutoff_90d = (today - timedelta(days=90)).isoformat()

    keyword_rankings = {
        "7d": build_kw_rankings(kw_daily, kw_dates, cutoff_7d, "7D"),
        "30d": build_kw_rankings(kw_daily, kw_dates, cutoff_30d, "30D"),
        "90d": build_kw_rankings(kw_daily, kw_dates, cutoff_90d, "90D"),
    }

    # Collect all unique keywords across all periods for avg position summary
    all_kw_set = set()
    for period_data in keyword_rankings.values():
        for k in period_data:
            all_kw_set.add(k["query"])

    # Build avg position per keyword per period (for the fixed header)
    kw_positions_summary = []
    for q in sorted(all_kw_set):
        row = {"query": q}
        for period in ["7d", "30d", "90d"]:
            match = next((k for k in keyword_rankings[period] if k["query"] == q), None)
            row["pos_" + period] = match["avg_position"] if match else None
            row["clicks_" + period] = match["clicks"] if match else 0
            row["impressions_" + period] = match["impressions"] if match else 0
        # Sort key: use 90d clicks as primary
        row["_sort"] = row["clicks_90d"]
        kw_positions_summary.append(row)

    kw_positions_summary.sort(key=lambda x: x["_sort"], reverse=True)
    for r in kw_positions_summary:
        del r["_sort"]

    # ── DataForSEO keyword volumes ─────────────────────────────────────────────
    dfseo = dk.get("dataforseo_keywords", days=7)
    # Deduplicate: latest date per keyword
    latest_dfseo = {}
    for r in dfseo:
        kw = r.get("keyword", "")
        d = r.get("date", "")
        if kw and (kw not in latest_dfseo or d > latest_dfseo[kw].get("date", "")):
            latest_dfseo[kw] = r

    keyword_volumes = []
    for kw, r in sorted(latest_dfseo.items(), key=lambda x: int(x[1].get("search_volume") or 0), reverse=True):
        vol = int(r.get("search_volume") or 0)
        # Parse monthly_searches JSON
        monthly_raw = r.get("monthly_searches", "[]")
        if isinstance(monthly_raw, str):
            try:
                monthly_parsed = json.loads(monthly_raw)
            except (json.JSONDecodeError, TypeError):
                monthly_parsed = []
        else:
            monthly_parsed = monthly_raw or []
        # Extract last 6 months of search volume
        monthly_trend = [m.get("monthly_searches", 0) for m in monthly_parsed[-6:]] if monthly_parsed else []
        keyword_volumes.append({
            "keyword": kw,
            "brand": r.get("brand", ""),
            "search_volume": vol,
            "cpc": round(float(r.get("cpc") or 0), 2),
            "competition_index": int(r.get("competition_index") or 0),
            "monthly_trend": monthly_trend,
        })

    # ── Brand Analytics (Amazon) ──────────────────────────────────────────────
    # Group by brand, show top search terms with ranking + click/conversion share
    BABY_CATEGORY_TERMS = {
        "toddler cup", "toddler cups", "sippy cup", "straw cup", "baby cup",
        "baby bottle", "ppsu bottle", "ppsu cup", "ppsu straw",
        "toddler straw cup", "baby straw cup", "sippy cups for toddlers",
        "training cup", "transition cup", "weighted straw cup",
        "baby snack", "baby rice puff", "baby puffs", "toddler snack",
        "baby rice cracker", "baby teething wafer", "organic baby snack",
        "baby wipe", "baby wipes", "water wipes",
    }

    ba_by_brand = defaultdict(list)
    ba_category = []  # Category competitor keywords
    for r in brand_analytics:
        term = (r.get("search_term") or "").strip().lower()
        if not term:
            continue
        entry = {
            "term": term,
            "rank": int(r.get("search_frequency_rank") or 0),
            "asin_rank": int(r.get("asin_rank") or 0),
            "asin_name": (r.get("asin_name") or "")[:80],
            "click_share": round(float(r.get("click_share") or 0) * 100, 2),
            "conv_share": round(float(r.get("conversion_share") or 0) * 100, 2),
            "is_ours": bool(r.get("is_ours")),
        }
        if r.get("is_ours"):
            brand = r.get("brand") or "Other"
            ba_by_brand[brand].append(entry)
        else:
            # Only keep baby-product related category terms
            if any(cat in term for cat in BABY_CATEGORY_TERMS):
                ba_category.append(entry)

    # Deduplicate BA entries per brand (take latest/best per search_term + asin_rank)
    ba_data = {}
    for brand, entries in ba_by_brand.items():
        seen = {}
        for e in entries:
            key = (e["term"], e["asin_rank"])
            if key not in seen or e["click_share"] > seen[key]["click_share"]:
                seen[key] = e
        sorted_entries = sorted(seen.values(), key=lambda x: x["rank"])[:20]
        ba_data[brand] = sorted_entries

    # Category competitors (deduplicated, top 15)
    cat_seen = {}
    for e in ba_category:
        key = (e["term"], e["asin_rank"])
        if key not in cat_seen or e["click_share"] > cat_seen[key]["click_share"]:
            cat_seen[key] = e
    ba_category_top = sorted(cat_seen.values(), key=lambda x: x["rank"])[:15]

    # GA4 traffic sources (top 15 by sessions, last 30d)
    traffic_agg = defaultdict(lambda: {"sessions": 0, "users": 0, "revenue": 0, "conversions": 0})
    for r in ga4:
        d = r.get("date", "")
        if not d or d < d30 or d > through:
            continue
        src = r.get("source") or "direct"
        med = r.get("medium") or "none"
        key = f"{src} / {med}"
        traffic_agg[key]["sessions"] += int(r.get("sessions") or 0)
        traffic_agg[key]["users"] += int(r.get("users") or r.get("active_users") or 0)
        traffic_agg[key]["revenue"] += float(r.get("revenue") or r.get("purchase_revenue") or 0)
        traffic_agg[key]["conversions"] += int(r.get("conversions") or r.get("purchases") or 0)

    top_traffic = sorted(traffic_agg.items(), key=lambda x: x[1]["sessions"], reverse=True)[:15]
    traffic_data = []
    for src, v in top_traffic:
        conv_rate = round(v["conversions"] / v["sessions"] * 100, 2) if v["sessions"] else 0
        traffic_data.append({
            "source": src,
            "sessions": v["sessions"],
            "users": v["users"],
            "revenue": round(v["revenue"], 2),
            "conversions": v["conversions"],
            "conv_rate": conv_rate,
        })

    # ── 7. Build monthly waterfall data ───────────────────────────────────────
    print("\n[7/7] Building monthly waterfall...")

    def monthly_val(data_dict, month, field="net"):
        """Sum field across all entities for a month."""
        total = 0
        for entity_months in data_dict.values():
            v = entity_months.get(month, {})
            total += v.get(field, 0) if isinstance(v, dict) else 0
        return total

    def proj_array(vals):
        """Add full-month projection for partial last month."""
        if is_partial and months and months[-1] == current_month and len(vals) > 0:
            return [round(v * fm_multiplier) if i == len(vals) - 1 else v for i, v in enumerate(vals)]
        return vals[:]

    def proj_for(vals, month_list):
        """Full-month projection for a specific month list."""
        if is_partial and month_list and month_list[-1] == current_month and len(vals) > 0:
            return [round(v * fm_multiplier) if i == len(vals) - 1 else v for i, v in enumerate(vals)]
        return vals[:]

    # Build output arrays
    brand_rev_out = {}
    for brand in BRAND_ORDER:
        vals = []
        for m in months:
            v = brand_monthly.get(brand, {}).get(m, {})
            amz_v = amz_brand_monthly.get(brand, {}).get(m, {})
            vals.append(round(v.get("net", 0) + amz_v.get("net", 0)))
        if any(v > 0 for v in vals):
            brand_rev_out[brand] = {
                "monthly": vals,
                "monthly_proj": proj_array(vals),
                "color": BRAND_COLORS.get(brand, "#94a3b8"),
            }

    channel_rev_out = {}
    for ch in ["Onzenna D2C", "Amazon MP", "Amazon FBA MCF", "TikTok Shop", "Target+", "B2B"]:
        vals = [round(channel_monthly.get(ch, {}).get(m, {}).get("net", 0)) for m in months]
        if any(v > 0 for v in vals):
            channel_rev_out[ch] = {
                "monthly": vals,
                "monthly_proj": proj_array(vals),
                "color": CHANNEL_COLORS.get(ch, "#94a3b8"),
            }

    ad_out = {}
    for platform in ["Amazon Ads", "Meta CVR", "Meta Traffic", "Google Ads"]:
        spend_vals = [round(ad_monthly.get(platform, {}).get(m, {}).get("spend", 0)) for m in months]
        sales_vals = [round(ad_monthly.get(platform, {}).get(m, {}).get("sales", 0)) for m in months]
        impr_vals = [ad_monthly.get(platform, {}).get(m, {}).get("impressions", 0) for m in months]
        click_vals = [ad_monthly.get(platform, {}).get(m, {}).get("clicks", 0) for m in months]
        if any(v > 0 for v in spend_vals):
            ad_out[platform] = {
                "spend": spend_vals,
                "spend_proj": proj_array(spend_vals),
                "sales": sales_vals,
                "sales_proj": proj_array(sales_vals),
                "impressions": impr_vals,
                "clicks": click_vals,
                "color": AD_COLORS.get(platform, "#94a3b8"),
            }

    # ── Ads Landing Channel TROAS ─────────────────────────────────────────
    # Onzenna channel: Google Ads + Meta CVR -> Shopify D2C revenue
    # Amazon channel: Amazon Ads + Meta Traffic -> Amazon MP revenue
    ads_landing = {}
    onz_spend = [0] * len(months)
    amz_spend = [0] * len(months)
    for i, m in enumerate(months):
        for p in ["Google Ads", "Meta CVR"]:
            onz_spend[i] += ad_monthly.get(p, {}).get(m, {}).get("spend", 0)
        for p in ["Amazon Ads", "Meta Traffic"]:
            amz_spend[i] += ad_monthly.get(p, {}).get(m, {}).get("spend", 0)
    onz_rev = [round(channel_monthly.get("Onzenna D2C", {}).get(m, {}).get("net", 0)) for m in months]
    amz_rev = [round(channel_monthly.get("Amazon MP", {}).get(m, {}).get("net", 0)) for m in months]
    ads_landing["Onzenna"] = {
        "spend": [round(v) for v in onz_spend],
        "spend_proj": proj_array([round(v) for v in onz_spend]),
        "revenue": onz_rev,
        "revenue_proj": proj_array(onz_rev),
        "platforms": "Google Ads + Meta CVR",
        "color": "#6366f1",
    }
    ads_landing["Amazon"] = {
        "spend": [round(v) for v in amz_spend],
        "spend_proj": proj_array([round(v) for v in amz_spend]),
        "revenue": amz_rev,
        "revenue_proj": proj_array(amz_rev),
        "platforms": "Amazon Ads + Meta Traffic",
        "color": "#f59e0b",
    }

    # Brand performance (ad + total sales, from 2026-01+)
    brand_perf_out = {}
    for brand in BRAND_ORDER:
        total_sales_vals = []
        ad_spend_vals = []
        ad_sales_vals = []
        for m in ad_months:
            shopify_net = brand_monthly.get(brand, {}).get(m, {}).get("net", 0)
            amz_net = amz_brand_monthly.get(brand, {}).get(m, {}).get("net", 0)
            total_sales_vals.append(round(shopify_net + amz_net))
            ad_spend_vals.append(round(brand_ad_monthly.get(brand, {}).get(m, {}).get("spend", 0)))
            ad_sales_vals.append(round(brand_ad_monthly.get(brand, {}).get(m, {}).get("sales", 0)))
        organic_vals = [max(0, t - a) for t, a in zip(total_sales_vals, ad_sales_vals)]
        if any(v > 0 for v in total_sales_vals) or any(v > 0 for v in ad_spend_vals):
            entry = {
                "total_sales": total_sales_vals,
                "total_sales_proj": proj_for(total_sales_vals, ad_months),
                "ad_spend": ad_spend_vals,
                "ad_spend_proj": proj_for(ad_spend_vals, ad_months),
                "ad_sales": ad_sales_vals,
                "ad_sales_proj": proj_for(ad_sales_vals, ad_months),
                "organic": organic_vals,
                "organic_proj": proj_for(organic_vals, ad_months),
                "color": BRAND_COLORS.get(brand, "#94a3b8"),
            }
            brand_perf_out[brand] = entry

    # Total monthly revenue & costs (GM = Rev - COGS, CM = GM - MKT)
    total_rev_monthly = []
    total_cogs_monthly = []
    total_gm_monthly = []
    total_ad_spend_monthly = []
    total_disc_monthly = []
    total_seeding_monthly = []
    total_mkt_monthly = []
    total_cm_monthly = []

    for m in months:
        # Total revenue = Shopify GROSS + Amazon GROSS
        # P&L starts from gross (list price basis); discounts shown separately
        shopify_gross = sum(brand_monthly.get(b, {}).get(m, {}).get("gross", 0) for b in BRAND_ORDER + ["Other"])
        shopify_disc = sum(abs(brand_monthly.get(b, {}).get(m, {}).get("disc", 0)) for b in BRAND_ORDER + ["Other"])
        amz_gross = sum(amz_brand_monthly.get(b, {}).get(m, {}).get("gross", 0) for b in BRAND_ORDER + ["Other"])
        amz_net = sum(amz_brand_monthly.get(b, {}).get(m, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
        amz_disc = amz_gross - amz_net  # Amazon discounts/coupons (~15%)
        rev = shopify_gross + amz_gross

        # COGS from SKU-level data (or fallback to brand avg)
        cogs = 0
        for b in BRAND_ORDER + ["Other"]:
            cogs += shop_sku_cogs.get(b, {}).get(m, 0)
            cogs += amz_sku_cogs.get(b, {}).get(m, 0)
        # Fallback: if SKU data missing for this month, use brand avg with units
        if cogs == 0 and rev > 0:
            for b in BRAND_ORDER:
                v = brand_monthly.get(b, {}).get(m, {})
                units = v.get("units", 0)
                if units == 0 and v.get("gross", 0) > 0:
                    units = int(v["gross"] / AVG_PRICE.get(b, 25))
                cogs += units * brand_vw_cogs.get(b, AVG_COGS.get(b, 8))
                amz_v = amz_brand_monthly.get(b, {}).get(m, {})
                amz_units = amz_v.get("units", 0)
                if amz_units == 0 and amz_v.get("net", 0) > 0:
                    amz_units = int(amz_v["net"] / AVG_PRICE.get(b, 25))
                cogs += amz_units * brand_vw_cogs.get(b, AVG_COGS.get(b, 8))
        elif cogs > 0 and rev > 0:
            # Partial SKU data fix (e.g., Oct 2025 SKU starts mid-month):
            # Scale COGS up by daily_units / sku_units ratio
            sku_u = amz_sku_units_m.get(m, 0) + shop_sku_units_m.get(m, 0)
            daily_u = sum(
                amz_brand_monthly.get(b, {}).get(m, {}).get("units", 0)
                + brand_monthly.get(b, {}).get(m, {}).get("units", 0)
                for b in BRAND_ORDER + ["Other"]
            )
            if sku_u > 0 and daily_u > sku_u * 1.2:
                # SKU data covers less than ~83% of daily units -> scale up
                scale = daily_u / sku_u
                cogs = round(cogs * scale)

        gm = rev - cogs  # GM = Total Revenue (gross) - Total COGS

        # MKT Cost 1: Ad Spend (with Amazon Ads backfill for pre-Dec 2025)
        amz_ad = ad_monthly.get("Amazon Ads", {}).get(m, {}).get("spend", 0)
        if amz_ad == 0 and m in _AMZ_ADS_BACKFILL:
            amz_ad = _AMZ_ADS_BACKFILL[m]
        onz_ad = sum(
            ad_monthly.get(p, {}).get(m, {}).get("spend", 0)
            for p in ["Meta CVR", "Meta Traffic", "Google Ads"]
        )
        ad_total = amz_ad + onz_ad

        # MKT Cost 2: Discounts (Shopify disc field + Amazon gross-net gap)
        disc_total = shopify_disc + amz_disc

        # MKT Cost 3: Influencer / Collab (PayPal + shipping $10/unit)
        seeding_total = _INFLUENCER_COST.get(m, 0)

        mkt_total = ad_total + disc_total + seeding_total
        cm = gm - mkt_total  # CM = GM - Total MKT

        total_rev_monthly.append(round(rev))
        total_cogs_monthly.append(round(cogs))
        total_gm_monthly.append(round(gm))
        total_ad_spend_monthly.append(round(ad_total))
        total_disc_monthly.append(round(disc_total))
        total_seeding_monthly.append(round(seeding_total))
        total_mkt_monthly.append(round(mkt_total))
        total_cm_monthly.append(round(cm))

    # Paid vs Organic (monthly)
    paid_monthly = []
    for m in months:
        paid = sum(
            ad_monthly.get(p, {}).get(m, {}).get("sales", 0)
            for p in ["Amazon Ads", "Meta CVR", "Meta Traffic", "Google Ads"]
        )
        paid_monthly.append(round(paid))

    organic_monthly = [max(0, rev - paid) for rev, paid in zip(total_rev_monthly, paid_monthly)]

    # ── Build P&L from DataKeeper ────────────────────────────────────────────
    print("[7.5/8] Building P&L...")
    MONTH_NAMES_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    all_pnl_months = sorted(months)  # DataKeeper months only

    # Build month labels
    pnl_month_labels = []
    for m in all_pnl_months:
        mi = int(m[5:7])
        yr = m[2:4]
        pnl_month_labels.append(f"{MONTH_NAMES_SHORT[mi-1]} {yr}")

    fy2025_months = [m for m in all_pnl_months if m.startswith("2025-")]
    fy2025_idx = len(fy2025_months)

    def _pnl_with_annual(monthly_vals, fy_count):
        out = [round(v) for v in monthly_vals[:fy_count]]
        out.append(round(sum(monthly_vals[:fy_count])))
        out.extend([round(v) for v in monthly_vals[fy_count:]])
        return out

    # ── Revenue by brand (Gross = Shopify net + Amazon gross) ──
    brand_rev_pnl = {}
    for brand in BRAND_ORDER:
        vals = []
        for m in all_pnl_months:
            shopify_v = brand_monthly.get(brand, {}).get(m, {}).get("net", 0)
            amz_v = amz_brand_monthly.get(brand, {}).get(m, {}).get("gross", 0)
            vals.append(round(shopify_v + amz_v))
        if any(v > 0 for v in vals):
            brand_rev_pnl[brand] = {
                "values": _pnl_with_annual(vals, fy2025_idx),
                "color": BRAND_COLORS.get(brand, "#94a3b8"),
            }

    # ── Ad spend from DataKeeper (with Amazon Ads backfill) ──
    onz_spend_arr, amz_spend_arr, google_spend_arr, total_ad_arr = [], [], [], []
    for m in all_pnl_months:
        onz = sum(ad_monthly.get(p, {}).get(m, {}).get("spend", 0)
                  for p in ["Meta CVR", "Meta Traffic", "Google Ads"])
        amz = ad_monthly.get("Amazon Ads", {}).get(m, {}).get("spend", 0)
        if amz == 0 and m in _AMZ_ADS_BACKFILL:
            amz = _AMZ_ADS_BACKFILL[m]
        ggl = ad_monthly.get("Google Ads", {}).get(m, {}).get("spend", 0)
        onz_spend_arr.append(round(onz))
        amz_spend_arr.append(round(amz))
        google_spend_arr.append(round(ggl))
        total_ad_arr.append(round(onz + amz))

    # ── Sales from ads (DataKeeper) ──
    onz_paid_arr, amz_paid_arr, total_paid_arr = [], [], []
    for m in all_pnl_months:
        onz_p = sum(ad_monthly.get(p, {}).get(m, {}).get("sales", 0)
                    for p in ["Meta CVR", "Meta Traffic", "Google Ads"])
        amz_p = ad_monthly.get("Amazon Ads", {}).get(m, {}).get("sales", 0)
        onz_paid_arr.append(round(onz_p))
        amz_paid_arr.append(round(amz_p))
        total_paid_arr.append(round(onz_p + amz_p))

    organic_arr = [max(0, r - p) for r, p in zip(total_rev_monthly, total_paid_arr)]
    cm_after_arr = [g - a for g, a in zip(total_gm_monthly, total_ad_arr)]

    final_labels = list(pnl_month_labels)
    final_labels.insert(fy2025_idx, "FY2025")

    pnl_polar = {
        "months": final_labels,
        "fy2025_idx": fy2025_idx,
        "brand_sales": brand_rev_pnl,
        "total_revenue": _pnl_with_annual(total_rev_monthly, fy2025_idx),
        "cogs": _pnl_with_annual(total_cogs_monthly, fy2025_idx),
        "gross_margin": _pnl_with_annual(total_gm_monthly, fy2025_idx),
        "ad_spend": {
            "onzenna": _pnl_with_annual(onz_spend_arr, fy2025_idx),
            "amazon": _pnl_with_annual(amz_spend_arr, fy2025_idx),
            "total": _pnl_with_annual(total_ad_arr, fy2025_idx),
        },
        "ad_spend_detail": {
            "google": _pnl_with_annual(google_spend_arr, fy2025_idx),
            "amz_grosmimi": _pnl_with_annual([0]*len(all_pnl_months), fy2025_idx),
            "amz_chaenmom": _pnl_with_annual([0]*len(all_pnl_months), fy2025_idx),
            "amz_naeiae": _pnl_with_annual([0]*len(all_pnl_months), fy2025_idx),
        },
        "sales_from_ads": {
            "onzenna": _pnl_with_annual(onz_paid_arr, fy2025_idx),
            "amazon": _pnl_with_annual(amz_paid_arr, fy2025_idx),
            "total": _pnl_with_annual(total_paid_arr, fy2025_idx),
        },
        "organic": {
            "onzenna": _pnl_with_annual([0]*len(all_pnl_months), fy2025_idx),
            "amazon": _pnl_with_annual([0]*len(all_pnl_months), fy2025_idx),
            "total": _pnl_with_annual(organic_arr, fy2025_idx),
        },
        "discounts": _pnl_with_annual(total_disc_monthly, fy2025_idx),
        "influencer_spend": _pnl_with_annual(total_seeding_monthly, fy2025_idx),
        "cm_after_ads": _pnl_with_annual(cm_after_arr, fy2025_idx),
        "cm_final": _pnl_with_annual(
            [g - a - s for g, a, s in zip(total_gm_monthly, total_ad_arr, total_seeding_monthly)],
            fy2025_idx
        ),
    }
    print(f"  P&L built: {len(all_pnl_months)} months, {len(brand_rev_pnl)} brands")

    # ── Channel P&L ──────────────────────────────────────────────────────────
    # Amazon: revenue from amazon_sales_daily (has fees), COGS from units * AVG_COGS
    # Shopify D2C (excl Target+): Shopify orders, COGS from units * AVG_COGS
    # Target+: Shopify target+ channel, COGS, fulfillment = N/A
    print("  Building Channel P&L...")

    # Build monthly Amazon fees from amazon_sales
    amz_fees_monthly = defaultdict(float)
    amz_fees_weekly = defaultdict(float)
    for r in amazon_sales:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        amz_fees_monthly[month] += float(r.get("fees") or 0)
        wk = _week_key(d)
        amz_fees_weekly[wk] += float(r.get("fees") or 0)

    # Build monthly FBA fulfillment costs from amazon_sales_sku_daily
    amz_fulfill_monthly = defaultdict(float)
    amz_fulfill_weekly = defaultdict(float)
    has_fba_fees = False
    for r in amazon_sku:
        d = r.get("date", "")
        if not d or d > through:
            continue
        fba_total = float(r.get("fba_fee_total", 0) or 0)
        if fba_total > 0:
            has_fba_fees = True
            amz_fulfill_monthly[d[:7]] += fba_total
            amz_fulfill_weekly[_week_key(d)] += fba_total
    if has_fba_fees:
        print(f"  FBA fulfillment: {sum(amz_fulfill_monthly.values()):,.0f} total across {len(amz_fulfill_monthly)} months")
    else:
        print("  FBA fulfillment: no data (run amazon_sales collection to fetch FBA fees)")

    # Channel P&L structure: revenue/cogs/selling_fees/fulfillment/ad_spend/gm/cm per month
    # Selling fees: Amazon 15%, Target+ 15%, Shopify 0%, B2B 0%
    # Fulfillment: Amazon FBA from estimated fees report, others n.m.
    CHANNEL_PNL_ORDER = ["Amazon MP", "Onzenna D2C", "Target+", "B2B"]

    # Build monthly Target+ fees from amazon_sales (channel=Target+)
    tp_fees_monthly = defaultdict(float)
    for r in amazon_sales:
        d = r.get("date", "")
        ch = r.get("channel", "")
        if not d or d > through or ch != "Target+":
            continue
        tp_fees_monthly[d[:7]] += float(r.get("fees") or 0)

    def _channel_pnl_monthly(ch, months_list):
        rev_arr, cogs_arr, sell_arr, fulfill_arr, ad_arr = [], [], [], [], []
        for m in months_list:
            rev = 0
            cogs = 0
            sell_fee = 0
            fulfill = 0
            ad_sp = 0

            if ch == "Amazon MP":
                for b in BRAND_ORDER + ["Other"]:
                    rev += amz_brand_monthly.get(b, {}).get(m, {}).get("gross", 0)
                # SKU-level COGS for Amazon
                for b in BRAND_ORDER + ["Other"]:
                    cogs += amz_sku_cogs.get(b, {}).get(m, 0)
                # Partial month: scale up if SKU units < daily units
                amz_daily_u = sum(amz_brand_monthly.get(b, {}).get(m, {}).get("units", 0) for b in BRAND_ORDER + ["Other"])
                amz_sku_u = amz_sku_units_m.get(m, 0)
                if cogs > 0 and amz_sku_u > 0 and amz_daily_u > amz_sku_u * 1.2:
                    cogs = round(cogs * amz_daily_u / amz_sku_u)
                # Fallback if SKU COGS is 0 but revenue exists
                elif cogs == 0 and rev > 0:
                    for b in BRAND_ORDER + ["Other"]:
                        u = amz_brand_monthly.get(b, {}).get(m, {}).get("units", 0)
                        cogs += u * brand_vw_cogs.get(b, AVG_COGS.get(b, 8))
                # Amazon selling fees (referral) + discounts shown in waterfall
                sell_fee = amz_fees_monthly.get(m, 0)
                fulfill = amz_fulfill_monthly.get(m, 0)
                ad_sp = (ad_monthly.get("Amazon Ads", {}).get(m, {}).get("spend", 0)
                         + ad_monthly.get("Meta Traffic", {}).get(m, {}).get("spend", 0))
            elif ch == "Onzenna D2C":
                rev = channel_monthly.get("Onzenna D2C", {}).get(m, {}).get("net", 0)
                # SKU-level COGS — D2C channel only (fixes double-counting bug)
                for b in BRAND_ORDER + ["Other"]:
                    cogs += shop_cogs_by_channel.get("Onzenna D2C", {}).get(b, {}).get(m, 0)
                # Fallback if SKU COGS is 0 but revenue exists
                if cogs == 0 and rev > 0:
                    # Use ratio from total shop_sku_cogs as estimate
                    total_shop = sum(shop_sku_cogs.get(b, {}).get(m, 0) for b in BRAND_ORDER + ["Other"])
                    total_shop_rev = sum(brand_monthly.get(b, {}).get(m, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
                    cogs_rate = total_shop / total_shop_rev if total_shop_rev else 0.30
                    cogs = round(rev * cogs_rate)
                sell_fee = 0
                fulfill = 0  # n.m.
                ad_sp = (ad_monthly.get("Meta CVR", {}).get(m, {}).get("spend", 0)
                         + ad_monthly.get("Google Ads", {}).get(m, {}).get("spend", 0))
            elif ch == "Target+":
                rev = channel_monthly.get("Target+", {}).get(m, {}).get("net", 0)
                # Target+ COGS from SKU data if available
                tp_sku_cogs = sum(shop_cogs_by_channel.get("Target+", {}).get(b, {}).get(m, 0) for b in BRAND_ORDER + ["Other"])
                if tp_sku_cogs > 0:
                    cogs = tp_sku_cogs
                else:
                    orders = channel_monthly.get("Target+", {}).get(m, {}).get("orders", 0)
                    cogs = orders * 10
                sell_fee = tp_fees_monthly.get(m, 0) or round(rev * 0.15)  # from data or 15%
                fulfill = 0  # n.m.
                ad_sp = 0
            elif ch == "B2B":
                rev = channel_monthly.get("B2B", {}).get(m, {}).get("net", 0)
                # B2B COGS from SKU data if available
                b2b_sku_cogs = sum(shop_cogs_by_channel.get("B2B", {}).get(b, {}).get(m, 0) for b in BRAND_ORDER + ["Other"])
                if b2b_sku_cogs > 0:
                    cogs = b2b_sku_cogs
                else:
                    orders = channel_monthly.get("B2B", {}).get(m, {}).get("orders", 0)
                    cogs = orders * 12
                sell_fee = 0
                fulfill = 0
                ad_sp = 0

            rev_arr.append(round(rev))
            cogs_arr.append(round(cogs))
            sell_arr.append(round(sell_fee))
            # Fulfillment: None = n.m. (data not collected)
            if ch == "Amazon MP" and not has_fba_fees:
                fulfill_arr.append(None)
            elif ch in ("Onzenna D2C", "Target+"):
                fulfill_arr.append(None)
            else:
                fulfill_arr.append(round(fulfill))
            ad_arr.append(round(ad_sp))

        gm_arr = [r - c - s - (f or 0) for r, c, s, f in zip(rev_arr, cogs_arr, sell_arr, fulfill_arr)]
        cm_arr = [g - a for g, a in zip(gm_arr, ad_arr)]
        fulfill_nm = any(f is None for f in fulfill_arr)
        return {
            "revenue": rev_arr,
            "cogs": cogs_arr,
            "selling_fees": sell_arr,
            "fulfillment": fulfill_arr,
            "fulfillment_nm": fulfill_nm,
            "ad_spend": ad_arr,
            "gross_margin": gm_arr,
            "contribution_margin": cm_arr,
            "color": CHANNEL_PNL_COLORS.get(ch, "#94a3b8"),
        }

    channel_pnl = {}
    for ch in CHANNEL_PNL_ORDER:
        data = _channel_pnl_monthly(ch, months)
        if any(v > 0 for v in data["revenue"]):
            channel_pnl[ch] = data

    pnl_polar["channel_pnl"] = channel_pnl
    print(f"  Channel P&L: {list(channel_pnl.keys())}")

    # ── Klaviyo email marketing ──────────────────────────────────────────────
    # Flow data = cumulative snapshots (same stats repeated daily per flow).
    # Fix: per flow per month, keep only the latest-date row (best snapshot).
    # Campaign data = one row per campaign (no dedup needed).
    print("\n[7/7] Building Klaviyo email metrics...")

    klav_campaigns = [r for r in klaviyo if r.get("source_type") == "campaign"
                      and r.get("date", "") <= through]
    klav_flows_raw = [r for r in klaviyo if r.get("source_type") == "flow"
                      and r.get("date", "") <= through]

    # Dedup flows: latest date per (source_name, month)
    flow_latest = {}  # (name, month) -> row with max date
    for r in klav_flows_raw:
        key = (r.get("source_name", ""), r["date"][:7])
        if key not in flow_latest or r["date"] > flow_latest[key]["date"]:
            flow_latest[key] = r
    klav_flows = list(flow_latest.values())

    def _agg_rows(rows):
        """Aggregate a list of Klaviyo rows into totals."""
        s = sum(int(r.get("sends") or 0) for r in rows)
        o = sum(int(r.get("opens") or 0) for r in rows)
        c = sum(int(r.get("clicks") or 0) for r in rows)
        cv = sum(int(r.get("conversions") or 0) for r in rows)
        rv = sum(float(r.get("revenue") or 0) for r in rows)
        return {"sends": s, "opens": o, "clicks": c, "conversions": cv, "revenue": rv}

    # Monthly arrays aligned to months[]
    def _klav_monthly_arr(rows, months_list):
        out = []
        for m in months_list:
            m_rows = [r for r in rows if r.get("date", "")[:7] == m]
            out.append(_agg_rows(m_rows))
        return out

    camp_arr = _klav_monthly_arr(klav_campaigns, months)
    flow_arr = _klav_monthly_arr(klav_flows, months)

    klaviyo_data = {
        "campaign_monthly": {
            "sends": [v["sends"] for v in camp_arr],
            "opens": [v["opens"] for v in camp_arr],
            "clicks": [v["clicks"] for v in camp_arr],
            "conversions": [v["conversions"] for v in camp_arr],
            "revenue": [round(v["revenue"]) for v in camp_arr],
            "revenue_proj": proj_array([round(v["revenue"]) for v in camp_arr]),
        },
        "flow_monthly": {
            "sends": [v["sends"] for v in flow_arr],
            "opens": [v["opens"] for v in flow_arr],
            "clicks": [v["clicks"] for v in flow_arr],
            "conversions": [v["conversions"] for v in flow_arr],
            "revenue": [round(v["revenue"]) for v in flow_arr],
            "revenue_proj": proj_array([round(v["revenue"]) for v in flow_arr]),
        },
    }

    # Period summaries (7D, 30D) — dedup flows per period too
    def _klav_period_summary(date_from_str):
        p_camps = [r for r in klav_campaigns if r.get("date", "") >= date_from_str]
        p_flows_raw = [r for r in klav_flows_raw if r.get("date", "") >= date_from_str]
        # Dedup flows: latest date per source_name in this period
        fl = {}
        for r in p_flows_raw:
            name = r.get("source_name", "")
            if name not in fl or r["date"] > fl[name]["date"]:
                fl[name] = r
        p_flows = list(fl.values())
        all_rows = p_camps + p_flows
        agg = _agg_rows(all_rows)
        s = agg["sends"]
        camp_r = sum(float(r.get("revenue") or 0) for r in p_camps)
        flow_r = sum(float(r.get("revenue") or 0) for r in p_flows)
        return {
            **agg,
            "revenue": round(agg["revenue"], 2),
            "open_rate": round(agg["opens"] / s * 100, 1) if s else 0,
            "click_rate": round(agg["clicks"] / s * 100, 2) if s else 0,
            "cvr": round(agg["conversions"] / s * 100, 2) if s else 0,
            "rev_per_send": round(agg["revenue"] / s, 3) if s else 0,
            "campaign_revenue": round(camp_r, 2),
            "flow_revenue": round(flow_r, 2),
        }

    def _klav_top_items(date_from_str, source_type, limit=15):
        if source_type == "campaign":
            p_rows = [r for r in klav_campaigns if r.get("date", "") >= date_from_str]
        else:
            p_raw = [r for r in klav_flows_raw if r.get("date", "") >= date_from_str]
            fl = {}
            for r in p_raw:
                name = r.get("source_name", "")
                if name not in fl or r["date"] > fl[name]["date"]:
                    fl[name] = r
            p_rows = list(fl.values())
        # Group by name
        grouped = defaultdict(lambda: {"sends": 0, "opens": 0, "clicks": 0, "conversions": 0, "revenue": 0.0, "date": ""})
        for r in p_rows:
            name = r.get("source_name", "Unknown")
            grouped[name]["sends"] += int(r.get("sends") or 0)
            grouped[name]["opens"] += int(r.get("opens") or 0)
            grouped[name]["clicks"] += int(r.get("clicks") or 0)
            grouped[name]["conversions"] += int(r.get("conversions") or 0)
            grouped[name]["revenue"] += float(r.get("revenue") or 0)
            grouped[name]["date"] = max(grouped[name]["date"], r.get("date", ""))
        top = sorted(grouped.items(), key=lambda x: x[1]["revenue"], reverse=True)[:limit]
        out = []
        for name, v in top:
            s = v["sends"]
            entry = {
                "name": name, "sends": s,
                "open_rate": round(v["opens"] / s * 100, 1) if s else 0,
                "click_rate": round(v["clicks"] / s * 100, 2) if s else 0,
                "cvr": round(v["conversions"] / s * 100, 2) if s else 0,
                "revenue": round(v["revenue"], 2),
            }
            if source_type == "campaign":
                entry["date"] = v["date"]
            out.append(entry)
        return out

    klaviyo_data["summary_7d"] = _klav_period_summary(d7)
    klaviyo_data["summary_30d"] = _klav_period_summary(d30)
    klaviyo_data["top_campaigns_7d"] = _klav_top_items(d7, "campaign")
    klaviyo_data["top_campaigns_30d"] = _klav_top_items(d30, "campaign")
    klaviyo_data["top_flows_7d"] = _klav_top_items(d7, "flow")
    klaviyo_data["top_flows_30d"] = _klav_top_items(d30, "flow")

    s30 = klaviyo_data["summary_30d"]
    print(f"  Klaviyo: {len(klaviyo)} raw rows -> {len(klav_campaigns)} campaigns + {len(klav_flows)} flows (deduped)")
    print(f"  30D: sends={s30['sends']:,} rev=${s30['revenue']:,.0f} | 7D: sends={klaviyo_data['summary_7d']['sends']:,} rev=${klaviyo_data['summary_7d']['revenue']:,.0f}")

    # ── Weekly data for all tabs ─────────────────────────────────────────────
    print("\n[7.8/8] Building weekly aggregations...")

    # Build week list (last 12 weeks)
    all_week_keys = set()
    for entity in list(brand_weekly.values()) + list(amz_brand_weekly.values()) + list(channel_weekly.values()):
        all_week_keys |= set(entity.keys())
    for platform in ad_weekly.values():
        all_week_keys |= set(platform.keys())

    # Last 12 weeks
    _wk_list_12 = []
    for w_offset in range(11, -1, -1):
        dt_w = today - timedelta(weeks=w_offset)
        iy, iw, _ = dt_w.isocalendar()
        wk = f"{iy}-W{iw:02d}"
        if wk not in _wk_list_12:
            _wk_list_12.append(wk)
    weeks = _wk_list_12

    from datetime import date as _date_cls
    def _wk_label(wk_str):
        parts = wk_str.split("-W")
        try:
            d = _date_cls.fromisocalendar(int(parts[0]), int(parts[1]), 1)
            return f"W{int(parts[1])} ({d.strftime('%b %d')})"
        except Exception:
            return wk_str

    week_labels_all = [_wk_label(w) for w in weeks]

    # Weekly brand revenue
    wk_brand_rev = {}
    for brand in BRAND_ORDER:
        vals = [round(brand_weekly.get(brand, {}).get(w, {}).get("net", 0)
                      + amz_brand_weekly.get(brand, {}).get(w, {}).get("net", 0)) for w in weeks]
        if any(v > 0 for v in vals):
            wk_brand_rev[brand] = {
                "weekly": vals,
                "color": BRAND_COLORS.get(brand, "#94a3b8"),
            }

    # Weekly channel revenue
    wk_channel_rev = {}
    for ch in ["Onzenna D2C", "Amazon MP", "Amazon FBA MCF", "TikTok Shop", "Target+", "B2B"]:
        vals = [round(channel_weekly.get(ch, {}).get(w, {}).get("net", 0)) for w in weeks]
        if any(v > 0 for v in vals):
            wk_channel_rev[ch] = {
                "weekly": vals,
                "color": CHANNEL_COLORS.get(ch, "#94a3b8"),
            }

    # Weekly ad performance
    wk_ad_perf = {}
    for platform in ["Amazon Ads", "Meta CVR", "Meta Traffic", "Google Ads"]:
        spend_vals = [round(ad_weekly.get(platform, {}).get(w, {}).get("spend", 0)) for w in weeks]
        sales_vals = [round(ad_weekly.get(platform, {}).get(w, {}).get("sales", 0)) for w in weeks]
        impr_vals = [ad_weekly.get(platform, {}).get(w, {}).get("impressions", 0) for w in weeks]
        click_vals = [ad_weekly.get(platform, {}).get(w, {}).get("clicks", 0) for w in weeks]
        if any(v > 0 for v in spend_vals):
            wk_ad_perf[platform] = {
                "spend": spend_vals,
                "sales": sales_vals,
                "impressions": impr_vals,
                "clicks": click_vals,
                "color": AD_COLORS.get(platform, "#94a3b8"),
            }

    # Weekly ads landing TROAS
    wk_onz_spend = [0] * len(weeks)
    wk_amz_spend = [0] * len(weeks)
    for i, w in enumerate(weeks):
        for p in ["Google Ads", "Meta CVR"]:
            wk_onz_spend[i] += ad_weekly.get(p, {}).get(w, {}).get("spend", 0)
        for p in ["Amazon Ads", "Meta Traffic"]:
            wk_amz_spend[i] += ad_weekly.get(p, {}).get(w, {}).get("spend", 0)
    wk_onz_rev = [round(channel_weekly.get("Onzenna D2C", {}).get(w, {}).get("net", 0)) for w in weeks]
    wk_amz_rev = [round(channel_weekly.get("Amazon MP", {}).get(w, {}).get("net", 0)) for w in weeks]
    wk_ads_landing = {
        "Onzenna": {
            "spend": [round(v) for v in wk_onz_spend],
            "revenue": wk_onz_rev,
            "platforms": "Google Ads + Meta CVR",
            "color": "#6366f1",
        },
        "Amazon": {
            "spend": [round(v) for v in wk_amz_spend],
            "revenue": wk_amz_rev,
            "platforms": "Amazon Ads + Meta Traffic",
            "color": "#f59e0b",
        },
    }

    # Weekly brand performance (ad + total sales)
    wk_brand_perf = {}
    for brand in BRAND_ORDER:
        total_vals = [round(brand_weekly.get(brand, {}).get(w, {}).get("net", 0)
                           + amz_brand_weekly.get(brand, {}).get(w, {}).get("net", 0)) for w in weeks]
        ad_spend_vals = [round(brand_ad_weekly.get(brand, {}).get(w, {}).get("spend", 0)) for w in weeks]
        ad_sales_vals = [round(brand_ad_weekly.get(brand, {}).get(w, {}).get("sales", 0)) for w in weeks]
        organic_vals = [max(0, t - a) for t, a in zip(total_vals, ad_sales_vals)]
        if any(v > 0 for v in total_vals) or any(v > 0 for v in ad_spend_vals):
            wk_brand_perf[brand] = {
                "total_sales": total_vals,
                "ad_spend": ad_spend_vals,
                "ad_sales": ad_sales_vals,
                "organic": organic_vals,
                "color": BRAND_COLORS.get(brand, "#94a3b8"),
            }

    # Weekly waterfall (GM, CM)
    wk_rev_arr = []
    wk_cogs_arr = []
    wk_gm_arr = []
    wk_ad_spend_arr = []
    wk_disc_arr = []
    wk_mkt_arr = []
    wk_cm_arr = []
    for w in weeks:
        shopify_net = sum(brand_weekly.get(b, {}).get(w, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
        amz_net = sum(amz_brand_weekly.get(b, {}).get(w, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
        rev = shopify_net + amz_net
        cogs = 0
        for b in BRAND_ORDER:
            units = brand_weekly.get(b, {}).get(w, {}).get("units", 0)
            if units == 0 and brand_weekly.get(b, {}).get(w, {}).get("gross", 0) > 0:
                units = int(brand_weekly[b][w]["gross"] / AVG_PRICE.get(b, 25))
            cogs += units * AVG_COGS.get(b, 8)
            amz_units = amz_brand_weekly.get(b, {}).get(w, {}).get("units", 0)
            if amz_units == 0 and amz_brand_weekly.get(b, {}).get(w, {}).get("net", 0) > 0:
                amz_units = int(amz_brand_weekly[b][w]["net"] / AVG_PRICE.get(b, 25))
            cogs += amz_units * AVG_COGS.get(b, 8)
        gm = rev - cogs
        ad_sp = sum(ad_weekly.get(p, {}).get(w, {}).get("spend", 0) for p in ["Amazon Ads", "Meta CVR", "Meta Traffic", "Google Ads"])
        disc = sum(brand_weekly.get(b, {}).get(w, {}).get("disc", 0) for b in BRAND_ORDER + ["Other"])
        mkt = ad_sp + abs(disc)
        cm = gm - mkt
        wk_rev_arr.append(round(rev))
        wk_cogs_arr.append(round(cogs))
        wk_gm_arr.append(round(gm))
        wk_ad_spend_arr.append(round(ad_sp))
        wk_disc_arr.append(round(abs(disc)))
        wk_mkt_arr.append(round(mkt))
        wk_cm_arr.append(round(cm))

    weekly_data = {
        "weeks": weeks,
        "week_labels": week_labels_all,
        "brand_revenue": wk_brand_rev,
        "channel_revenue": wk_channel_rev,
        "ad_performance": wk_ad_perf,
        "ads_landing": wk_ads_landing,
        "brand_performance": wk_brand_perf,
        "waterfall": {
            "revenue": wk_rev_arr,
            "cogs": wk_cogs_arr,
            "gross_margin": wk_gm_arr,
            "ad_spend": wk_ad_spend_arr,
            "discounts": wk_disc_arr,
            "mkt_total": wk_mkt_arr,
            "contribution_margin": wk_cm_arr,
        },
        "channel_pnl": {},
    }

    # Build weekly channel P&L
    def _ch_pnl_wk(ch, wlist):
        rev_a, cogs_a, fees_a, ad_a = [], [], [], []
        for w in wlist:
            rev = cogs = fees = ad_sp = 0
            if ch == "Amazon MP":
                for b in BRAND_ORDER + ["Other"]:
                    net = amz_brand_weekly.get(b, {}).get(w, {}).get("net", 0)
                    units = amz_brand_weekly.get(b, {}).get(w, {}).get("units", 0)
                    if units == 0 and net > 0:
                        units = int(net / AVG_PRICE.get(b, 25))
                    rev += net
                    cogs += units * AVG_COGS.get(b, 8)
                fees = amz_fees_weekly.get(w, 0)
                ad_sp = (ad_weekly.get("Amazon Ads", {}).get(w, {}).get("spend", 0)
                         + ad_weekly.get("Meta Traffic", {}).get(w, {}).get("spend", 0))
            elif ch == "Onzenna D2C":
                rev = channel_weekly.get("Onzenna D2C", {}).get(w, {}).get("net", 0)
                for b in BRAND_ORDER + ["Other"]:
                    bw = brand_weekly.get(b, {}).get(w, {})
                    b_units = bw.get("units", 0)
                    if b_units == 0 and bw.get("net", 0) > 0:
                        b_units = int(bw["net"] / AVG_PRICE.get(b, 25))
                    cogs += b_units * AVG_COGS.get(b, 8)
                ad_sp = (ad_weekly.get("Meta CVR", {}).get(w, {}).get("spend", 0)
                         + ad_weekly.get("Google Ads", {}).get(w, {}).get("spend", 0))
            elif ch == "Target+":
                rev = channel_weekly.get("Target+", {}).get(w, {}).get("net", 0)
                cogs = channel_weekly.get("Target+", {}).get(w, {}).get("orders", 0) * 10
            elif ch == "B2B":
                rev = channel_weekly.get("B2B", {}).get(w, {}).get("net", 0)
                cogs = channel_weekly.get("B2B", {}).get(w, {}).get("orders", 0) * 12
            rev_a.append(round(rev)); cogs_a.append(round(cogs)); fees_a.append(round(fees)); ad_a.append(round(ad_sp))
        gm_a = [r-c-f for r,c,f in zip(rev_a, cogs_a, fees_a)]
        cm_a = [g-a for g,a in zip(gm_a, ad_a)]
        return {"revenue":rev_a,"cogs":cogs_a,"fees":fees_a,"ad_spend":ad_a,"gross_margin":gm_a,"contribution_margin":cm_a,"color":CHANNEL_PNL_COLORS.get(ch,"#94a3b8")}

    for ch in ["Amazon MP", "Onzenna D2C", "Target+", "B2B"]:
        d = _ch_pnl_wk(ch, weeks)
        if any(v > 0 for v in d["revenue"]):
            weekly_data["channel_pnl"][ch] = d

    print(f"  Weekly: {len(weeks)} weeks ({weeks[0]} -> {weeks[-1]})")

    # ── Campaign-level detail (weekly + monthly) ────────────────────────────
    print("\n[8/8] Building campaign-level detail...")

    from datetime import date as _date_type

    # Helper: ISO week label "W12 (Mar 17)"
    def _week_label(iso_yr, iso_wk):
        try:
            d = _date_type.fromisocalendar(iso_yr, iso_wk, 1)
            return f"W{iso_wk} ({d.strftime('%b %d')})"
        except Exception:
            return f"W{iso_wk}"

    # Collect campaign-level daily rows (all platforms)
    campaign_daily = []  # list of dicts with normalized fields

    for r in amazon_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        campaign_daily.append({
            "date": d,
            "platform": "Amazon Ads",
            "campaign_id": r.get("campaign_id", ""),
            "campaign_name": r.get("campaign_name", ""),
            "brand": r.get("brand") or "Other",
            "spend": float(r.get("spend") or 0),
            "sales": float(r.get("sales") or 0),
            "impressions": int(r.get("impressions") or 0),
            "clicks": int(r.get("clicks") or 0),
        })

    for r in meta_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        cname = (r.get("campaign_name") or "").lower()
        landing = (r.get("landing_url") or "").lower()
        is_amz = "amazon" in cname or "amz" in cname or "amazon" in landing
        platform = "Meta Traffic" if is_amz else "Meta CVR"
        campaign_daily.append({
            "date": d,
            "platform": platform,
            "campaign_id": r.get("campaign_id", ""),
            "campaign_name": r.get("campaign_name", ""),
            "brand": r.get("brand") or "Other",
            "spend": float(r.get("spend") or 0),
            "sales": float(r.get("purchase_value") or 0),
            "impressions": int(r.get("impressions") or 0),
            "clicks": int(r.get("clicks") or 0),
        })

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        campaign_daily.append({
            "date": d,
            "platform": "Google Ads",
            "campaign_id": r.get("campaign_id", ""),
            "campaign_name": r.get("campaign_name", ""),
            "brand": "Grosmimi",
            "spend": float(r.get("spend") or 0),
            "sales": float(r.get("conversion_value") or 0),
            "impressions": int(r.get("impressions") or 0),
            "clicks": int(r.get("clicks") or 0),
        })

    # Aggregate by campaign x week and campaign x month
    camp_weekly = defaultdict(lambda: defaultdict(lambda: {
        "spend": 0, "sales": 0, "impressions": 0, "clicks": 0
    }))
    camp_monthly_agg = defaultdict(lambda: defaultdict(lambda: {
        "spend": 0, "sales": 0, "impressions": 0, "clicks": 0
    }))
    camp_meta = {}  # campaign_id -> {name, platform, brand}

    for row in campaign_daily:
        cid = row["campaign_id"]
        d = row["date"]
        month = d[:7]
        dt = datetime.strptime(d, "%Y-%m-%d").date()
        iso_yr, iso_wk, _ = dt.isocalendar()
        wk_key = f"{iso_yr}-W{iso_wk:02d}"

        camp_weekly[cid][wk_key]["spend"] += row["spend"]
        camp_weekly[cid][wk_key]["sales"] += row["sales"]
        camp_weekly[cid][wk_key]["impressions"] += row["impressions"]
        camp_weekly[cid][wk_key]["clicks"] += row["clicks"]

        camp_monthly_agg[cid][month]["spend"] += row["spend"]
        camp_monthly_agg[cid][month]["sales"] += row["sales"]
        camp_monthly_agg[cid][month]["impressions"] += row["impressions"]
        camp_monthly_agg[cid][month]["clicks"] += row["clicks"]

        if cid not in camp_meta:
            camp_meta[cid] = {
                "name": row["campaign_name"],
                "platform": row["platform"],
                "brand": row["brand"],
            }

    # Build week labels (last 12 weeks)
    today_iso = today.isocalendar()
    week_keys = []
    for w_offset in range(11, -1, -1):
        dt_w = today - timedelta(weeks=w_offset)
        iy, iw, _ = dt_w.isocalendar()
        wk = f"{iy}-W{iw:02d}"
        if wk not in week_keys:
            week_keys.append(wk)

    week_labels = []
    for wk in week_keys:
        parts = wk.split("-W")
        week_labels.append(_week_label(int(parts[0]), int(parts[1])))

    # Build campaign detail entries
    def _camp_entry(cid, agg_dict, period_keys):
        m = camp_meta.get(cid, {})
        spend_arr = [round(agg_dict[cid].get(pk, {}).get("spend", 0), 2) for pk in period_keys]
        sales_arr = [round(agg_dict[cid].get(pk, {}).get("sales", 0), 2) for pk in period_keys]
        impr_arr = [agg_dict[cid].get(pk, {}).get("impressions", 0) for pk in period_keys]
        click_arr = [agg_dict[cid].get(pk, {}).get("clicks", 0) for pk in period_keys]
        total_spend = sum(spend_arr)
        total_sales = sum(sales_arr)
        return {
            "id": cid,
            "name": m.get("name", ""),
            "platform": m.get("platform", ""),
            "brand": m.get("brand", "Other"),
            "spend": spend_arr,
            "sales": sales_arr,
            "impressions": impr_arr,
            "clicks": click_arr,
            "total_spend": round(total_spend, 2),
            "total_sales": round(total_sales, 2),
            "roas": round(total_sales / total_spend, 2) if total_spend > 0 else 0,
        }

    # Weekly entries (last 12 weeks, only campaigns with spend)
    weekly_entries = []
    for cid in camp_weekly:
        e = _camp_entry(cid, camp_weekly, week_keys)
        if e["total_spend"] > 0:
            weekly_entries.append(e)
    weekly_entries.sort(key=lambda x: x["total_spend"], reverse=True)

    # Monthly entries (ad_months only)
    monthly_entries = []
    for cid in camp_monthly_agg:
        e = _camp_entry(cid, camp_monthly_agg, ad_months)
        if e["total_spend"] > 0:
            monthly_entries.append(e)
    monthly_entries.sort(key=lambda x: x["total_spend"], reverse=True)

    # Top / Bottom performers (by ROAS, min spend threshold)
    def _top_bottom(entries, min_spend=50):
        qualified = [e for e in entries if e["total_spend"] >= min_spend]
        top = sorted(qualified, key=lambda x: x["roas"], reverse=True)[:10]
        bottom = sorted(qualified, key=lambda x: x["roas"])[:10]
        return top, bottom

    weekly_top, weekly_bottom = _top_bottom(weekly_entries, min_spend=20)
    monthly_top, monthly_bottom = _top_bottom(monthly_entries, min_spend=50)

    # New campaigns: appeared this month but not in previous months
    current_month = ad_months[-1] if ad_months else ""
    prev_months = set(ad_months[:-1]) if len(ad_months) > 1 else set()
    new_campaigns = []
    for cid in camp_monthly_agg:
        has_current = camp_monthly_agg[cid].get(current_month, {}).get("spend", 0) > 0
        has_prev = any(camp_monthly_agg[cid].get(pm, {}).get("spend", 0) > 0 for pm in prev_months)
        if has_current and not has_prev:
            e = _camp_entry(cid, camp_monthly_agg, [current_month])
            if e["total_spend"] > 0:
                new_campaigns.append(e)
    new_campaigns.sort(key=lambda x: x["total_spend"], reverse=True)

    campaign_detail = {
        "week_keys": week_keys,
        "week_labels": week_labels,
        "month_keys": ad_months,
        "weekly_all": weekly_entries,
        "weekly_top": weekly_top,
        "weekly_bottom": weekly_bottom,
        "monthly_all": monthly_entries,
        "monthly_top": monthly_top,
        "monthly_bottom": monthly_bottom,
        "new_campaigns": new_campaigns,
        "current_month": current_month,
    }

    print(f"  Campaigns: {len(camp_meta)} total, weekly={len(weekly_entries)}, monthly={len(monthly_entries)}")
    print(f"  New this month ({current_month}): {len(new_campaigns)}")
    print(f"  Top/Bottom weekly: {len(weekly_top)}/{len(weekly_bottom)}, monthly: {len(monthly_top)}/{len(monthly_bottom)}")

    # ── Serialize brand_ad_by_platform ───────────────────────────────────────
    def _bap_serialize(raw_dict, period_keys):
        out = {}
        for platform in ["Amazon Ads", "Meta CVR", "Meta Traffic", "Google Ads"]:
            brands = dict(raw_dict.get(platform, {}))
            plat_out = {}
            for brand in sorted(brands.keys()):
                spend = [round(brands[brand].get(pk, {}).get("spend", 0), 2) for pk in period_keys]
                if not any(s > 0 for s in spend):
                    continue
                sales = [round(brands[brand].get(pk, {}).get("sales", 0), 2) for pk in period_keys]
                impr = [brands[brand].get(pk, {}).get("impressions", 0) for pk in period_keys]
                clicks = [brands[brand].get(pk, {}).get("clicks", 0) for pk in period_keys]
                plat_out[brand] = {
                    "spend": spend,
                    "sales": sales,
                    "impressions": impr,
                    "clicks": clicks,
                    "color": BRAND_COLORS.get(brand, "#94a3b8"),
                }
            out[platform] = plat_out
        return out

    bap_monthly_out = _bap_serialize(brand_ad_by_platform, ad_months)
    bap_weekly_out = _bap_serialize(brand_ad_by_platform_wk, weeks)
    weekly_data["brand_ad_by_platform"] = bap_weekly_out

    # ── Assemble final data ───────────────────────────────────────────────────
    fin_data = {
        "generated_pst": now_pst.strftime("%Y-%m-%d %H:%M PST"),
        "through_date": through,
        "months": months,
        "data_sources": data_sources,
        "partial_month": partial_month_info,
        "summary": summary,
        "brand_revenue": brand_rev_out,
        "channel_revenue": channel_rev_out,
        "ad_performance": ad_out,
        "ads_landing": ads_landing,
        "ad_start_idx": ad_start_idx,
        "brand_performance": brand_perf_out,
        "paid_organic": {
            "paid": paid_monthly,
            "paid_proj": proj_array(paid_monthly),
            "organic": organic_monthly,
            "organic_proj": proj_array(organic_monthly),
        },
        "waterfall": {
            "revenue": total_rev_monthly,
            "revenue_proj": proj_array(total_rev_monthly),
            "cogs": total_cogs_monthly,
            "cogs_proj": proj_array(total_cogs_monthly),
            "gross_margin": total_gm_monthly,
            "gross_margin_proj": proj_array(total_gm_monthly),
            "ad_spend": total_ad_spend_monthly,
            "ad_spend_proj": proj_array(total_ad_spend_monthly),
            "discounts": total_disc_monthly,
            "discounts_proj": proj_array(total_disc_monthly),
            "seeding": total_seeding_monthly,
            "seeding_proj": proj_array(total_seeding_monthly),
            "mkt_total": total_mkt_monthly,
            "mkt_total_proj": proj_array(total_mkt_monthly),
            "contribution_margin": total_cm_monthly,
            "contribution_margin_proj": proj_array(total_cm_monthly),
        },
        "search_queries": search_data,
        "search_by_brand": search_by_brand,
        "gsc_queries": gsc_data,
        "keyword_rankings": keyword_rankings,
        "kw_positions_summary": kw_positions_summary,
        "keyword_volumes": keyword_volumes,
        "brand_analytics": ba_data,
        "brand_analytics_category": ba_category_top,
        "traffic_sources": traffic_data,
        "pnl_polar": pnl_polar,
        "klaviyo": klaviyo_data,
        "campaign_detail": campaign_detail,
        "brand_ad_by_platform": bap_monthly_out,
        "weekly": weekly_data,
    }

    # ── Write output ──────────────────────────────────────────────────────────
    os.makedirs(OUTPUT.parent, exist_ok=True)
    js_content = "const FIN_DATA = " + json.dumps(fin_data, ensure_ascii=False, indent=1) + ";"
    OUTPUT.write_text(js_content, encoding="utf-8")
    print(f"\n  fin_data.js written: {len(js_content):,} chars")
    print(f"  Summary (30d): Rev ${summary['30d']['total_revenue']:,} | "
          f"Ad ${summary['30d']['total_ad_spend']:,} | "
          f"GM {summary['30d']['gm_pct']}% | "
          f"MER {summary['30d']['mer']}")

    # ── L7: Sanity Check (from 검증이 M-066~M-069) ────────────────────────
    print("\n[SANITY] P&L output validation...")
    warnings = []
    pnl = fin_data["pnl_polar"]
    fy_idx = pnl["fy2025_idx"]
    for i, m in enumerate(pnl["months"]):
        if m == "FY2025":
            continue
        r = pnl["total_revenue"][i]
        c = pnl["cogs"][i]
        ad = pnl["ad_spend"]["total"][i]
        disc = pnl.get("discounts", [0]*len(pnl["months"]))[i]
        inf = pnl.get("influencer_spend", [0]*len(pnl["months"]))[i]
        if r > 0:
            cogs_pct = c / r * 100
            if cogs_pct < 25:
                warnings.append(f"  [WARN] {m}: COGS% {cogs_pct:.0f}% < 25% (partial month data?)")
            elif cogs_pct > 45:
                warnings.append(f"  [WARN] {m}: COGS% {cogs_pct:.0f}% > 45% (revenue using net instead of gross?)")
            disc_pct = disc / r * 100
            if disc_pct < 3 and i >= 5:  # skip early months with sparse data
                warnings.append(f"  [WARN] {m}: Disc% {disc_pct:.0f}% < 3% (discounts missing?)")
        if ad == 0 and m not in ("Jan 25", "Feb 25", "Mar 25", "Apr 25", "May 25"):
            warnings.append(f"  [WARN] {m}: Ad Spend $0 (backfill missing?)")
        if inf == 0:
            warnings.append(f"  [WARN] {m}: Influencer $0 (PR orders not reflected?)")
    # FY month count check
    fy_month_count = fy_idx
    if fy_month_count < 12 and fy_month_count > 0:
        warnings.append(f"  [WARN] FY2025 has only {fy_month_count} months (expected 12, Jan-May missing?)")
    if warnings:
        for w in warnings:
            print(w)
        print(f"  {len(warnings)} warnings found")
    else:
        print("  All checks PASS")

    if args.push:
        import subprocess
        os.chdir(str(ROOT))
        subprocess.run(["git", "add", str(OUTPUT)], check=True)
        subprocess.run(["git", "commit", "-m", "auto: update financial KPI data [skip ci]"], check=False)
        subprocess.run(["git", "push"], check=True)
        print("  Pushed to GitHub")


if __name__ == "__main__":
    generate()
