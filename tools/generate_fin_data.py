"""Generate fin_data.js for Financial KPIs dashboard tab.

Pulls data from DataKeeper (Shopify, Amazon, Meta, Google, GA4) and computes:
  - Revenue by brand, channel, month
  - Ad spend by platform
  - Ad-attributed vs organic revenue
  - Top search queries
  - GA4 traffic sources
  - Marketing spend waterfall → Contribution Margin

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


# ── Polar Excel parser ─────────────────────────────────────────────────────
POLAR_XLSX = ROOT / "Data Storage" / "_archive" / "Monthly Sales by brands_raw.xlsx"
POLAR_SHEET = "IR 매출분석"

# Map CSV brand names to our standard names
POLAR_BRAND_MAP = {
    "Grosmimi": "Grosmimi",
    "Alpremio": "Alpremio",
    "Naeiae": "Naeiae",
    "CHA&MOM": "CHA&MOM",
    "Comme Moi": "Comme Moi",
    "BabyRabbit": "BabyRabbit",
    "BambooBebe": "BambooBebe",
    "Hattung": "Hattung",
    "beemymagic": "beemymagic",
    "Easy Shower": "Easy Shower",
    "Nature Love Mere": "Nature Love Mere",
}

POLAR_BRAND_COLORS = {
    "Grosmimi": "#8b5cf6", "Alpremio": "#f97316", "Naeiae": "#eab308",
    "CHA&MOM": "#0ea5e9", "Comme Moi": "#14b8a6", "BabyRabbit": "#f472b6",
    "BambooBebe": "#a3e635", "Hattung": "#fb923c", "beemymagic": "#c084fc",
    "Easy Shower": "#94a3b8", "Nature Love Mere": "#6b7280",
}


def parse_polar_excel():
    """Parse the Polar Excel file (폴라 희망 sheet) and return P&L data from Jan-25 onwards.

    Reads directly from Data Storage/_archive/Monthly Sales by brands_raw.xlsx
    instead of CSV export. Amazon Ads costs for 2025 come from this file.
    """
    if not POLAR_XLSX.exists():
        print(f"  [WARN] Polar Excel not found: {POLAR_XLSX}")
        return None

    import openpyxl
    wb = openpyxl.load_workbook(str(POLAR_XLSX), data_only=True)
    ws = wb[POLAR_SHEET]

    # Build month column mapping from row 3 (datetime objects)
    month_cols = {}  # "2025-01" -> col_idx
    for c in range(6, min(ws.max_column + 1, 60)):
        v = ws.cell(3, c).value
        if v and hasattr(v, "strftime"):
            month_cols[v.strftime("%Y-%m")] = c

    # Target months: Jan-25 through latest available
    target_months = []
    for yr in [2025, 2026]:
        for mi in range(1, 13):
            key = f"{yr}-{mi:02d}"
            if key in month_cols:
                target_months.append(key)
            if yr == 2026 and mi >= 3:
                break

    if not target_months:
        print("  [WARN] No target months found in Polar Excel")
        wb.close()
        return None

    n = len(target_months)
    zeros = [0.0] * n

    def _val(row, col):
        v = ws.cell(row, col).value
        if v is None or v == "" or v == "-":
            return 0.0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    def _get_vals(row):
        return [_val(row, month_cols[m]) for m in target_months]

    def _find_row(keyword, start=1, col=2):
        """Find row where cell in col matches keyword exactly."""
        for r in range(start, ws.max_row + 1):
            v = ws.cell(r, col).value
            if v and isinstance(v, str) and v.strip() == keyword:
                return r
        return None

    def _find_row_contains(keyword, start=1, col=2):
        """Find row where cell in col contains keyword."""
        for r in range(start, ws.max_row + 1):
            v = ws.cell(r, col).value
            if v and isinstance(v, str) and keyword in v:
                return r
        return None

    def _find_in(section_start, name, max_rows=20, col=3):
        """Find a row within a section where col matches name."""
        for r in range(section_start + 1, min(section_start + max_rows, ws.max_row + 1)):
            v = ws.cell(r, col).value
            if v and isinstance(v, str) and v.strip() == name:
                return r
        return None

    def _find_in_contains(section_start, keyword, max_rows=20, col=3):
        for r in range(section_start + 1, min(section_start + max_rows, ws.max_row + 1)):
            v = ws.cell(r, col).value
            if v and isinstance(v, str) and keyword in v:
                return r
        return None

    # ── Section 1: Sales By Brands (LFU+FLT) ──
    sec_sales = _find_row("Sales By Brands (USD)")
    brand_sales = {}
    total_sales = list(zeros)
    if sec_sales:
        for brand in POLAR_BRAND_MAP:
            br = _find_in(sec_sales, brand, 20)
            if br:
                brand_sales[brand] = _get_vals(br)
        # Total row: "LFU+FLT 매출"
        tr = _find_in_contains(sec_sales, "LFU+FLT", 20)
        if tr:
            total_sales = _get_vals(tr)

    # ── ADS by Channel ──
    sec_ads = _find_row("ADS by Channel") or _find_row("Ads Spent")
    ad_spend_onzenna = list(zeros)
    ad_spend_amazon = list(zeros)
    ad_spend_total = list(zeros)
    ad_spend_google = list(zeros)
    ad_spend_amz_grosmimi = list(zeros)
    ad_spend_amz_chaenmom = list(zeros)
    ad_spend_amz_naeiae = list(zeros)

    if sec_ads:
        for r in range(sec_ads + 1, min(sec_ads + 30, ws.max_row + 1)):
            c3 = str(ws.cell(r, 3).value or "").strip()
            c4 = str(ws.cell(r, 4).value or "").strip()
            if c3 == "ONZENNA":
                ad_spend_onzenna = _get_vals(r)
            elif c3 == "Amazon":
                ad_spend_amazon = _get_vals(r)
            elif c3 == "Total Ads Spent":
                ad_spend_total = _get_vals(r)
                break
            # Sub-breakdowns (column D)
            if c4.lower() in ("google ads",):
                ad_spend_google = _get_vals(r)
            elif c4 == "Grosmimi" and r > sec_ads + 8:
                ad_spend_amz_grosmimi = _get_vals(r)
            elif "Cha" in c4 and "mom" in c4.lower():
                ad_spend_amz_chaenmom = _get_vals(r)
            elif "Naeiae" in c4 or "Others" in c4:
                ad_spend_amz_naeiae = _get_vals(r)

    # ── Sales from Ads ──
    sec_sales_ads = _find_row("Sales from Ads")
    sales_from_ads_total = list(zeros)
    sales_from_ads_onz = list(zeros)
    sales_from_ads_amz = list(zeros)

    if sec_sales_ads:
        for r in range(sec_sales_ads + 1, min(sec_sales_ads + 20, ws.max_row + 1)):
            c3 = str(ws.cell(r, 3).value or "").strip()
            if c3 == "ONZENNA":
                sales_from_ads_onz = _get_vals(r)
            elif c3 == "Amazon":
                sales_from_ads_amz = _get_vals(r)
            elif c3 == "Total Sales from Ads":
                sales_from_ads_total = _get_vals(r)
                break

    # ── Organic Sales ──
    sec_organic = _find_row("Organic Sales")
    organic_total = list(zeros)
    organic_onz = list(zeros)
    organic_amz = list(zeros)

    if sec_organic:
        for r in range(sec_organic + 1, min(sec_organic + 15, ws.max_row + 1)):
            c3 = str(ws.cell(r, 3).value or "").strip()
            if c3 == "ONZENNA":
                organic_onz = _get_vals(r)
            elif c3 == "AMZ":
                organic_amz = _get_vals(r)
            elif c3 == "Total Organic Sales":
                organic_total = _get_vals(r)
                break
        # Fallback: compute from ONZENNA + AMZ if no total row
        if all(v == 0 for v in organic_total) and any(v > 0 for v in organic_onz):
            organic_total = [a + b for a, b in zip(organic_onz, organic_amz)]

    # ── CM before/after Ads ──
    sec_cm_before = _find_row("CM before Ads")
    cm_before_total = list(zeros)
    cm_before_onz = list(zeros)
    cm_before_amz = list(zeros)

    if sec_cm_before:
        for r in range(sec_cm_before + 1, min(sec_cm_before + 15, ws.max_row + 1)):
            c3 = str(ws.cell(r, 3).value or "").strip()
            if c3 == "ONZENNA":
                cm_before_onz = _get_vals(r)
            elif c3 == "AMZ":
                cm_before_amz = _get_vals(r)
            elif "Total CM before Ads" in c3:
                cm_before_total = _get_vals(r)
                break
        if all(v == 0 for v in cm_before_total) and any(v > 0 for v in cm_before_onz):
            cm_before_total = [a + b for a, b in zip(cm_before_onz, cm_before_amz)]

    sec_cm_after = _find_row("CM After Ads")
    cm_after_total = list(zeros)
    cm_after_onz = list(zeros)
    cm_after_amz = list(zeros)

    if sec_cm_after:
        for r in range(sec_cm_after + 1, min(sec_cm_after + 15, ws.max_row + 1)):
            c3 = str(ws.cell(r, 3).value or "").strip()
            if c3 == "ONZENNA":
                cm_after_onz = _get_vals(r)
            elif c3 == "AMZ":
                cm_after_amz = _get_vals(r)
            elif "total cm after ads" in c3.lower():
                cm_after_total = _get_vals(r)
                break
        if all(v == 0 for v in cm_after_total) and any(v > 0 for v in cm_after_onz):
            cm_after_total = [a + b for a, b in zip(cm_after_onz, cm_after_amz)]

    # ── Influencer Spend ──
    sec_influencer = _find_row("Paid influencer collabs")
    influencer_total = list(zeros)
    if sec_influencer:
        # "Monthly Total" is in column B (2)
        for r in range(sec_influencer + 2, min(sec_influencer + 60, ws.max_row + 1)):
            v = ws.cell(r, 2).value
            if v and isinstance(v, str) and v.strip() == "Monthly Total":
                influencer_total = _get_vals(r)
                break

    # ── Final CM (after ads + influencer) ──
    sec_final_cm = _find_row_contains("Total CM After ads & influencer")
    cm_final = list(zeros)
    if sec_final_cm:
        cm_final = _get_vals(sec_final_cm)

    # COGS = Revenue - CM before Ads
    cogs = [round(rev - cm) for rev, cm in zip(total_sales, cm_before_total)]

    # ── Build FY2025 annual total ──
    num_2025 = min(12, len(target_months))

    def _annual(arr):
        return round(sum(arr[:num_2025]))

    MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_labels = []
    for m in target_months[:num_2025]:
        mi = int(m[5:7])
        yr = m[2:4]
        month_labels.append(f"{MONTH_NAMES[mi - 1]} {yr}")
    month_labels.append("FY2025")
    for m in target_months[num_2025:]:
        mi = int(m[5:7])
        yr = m[2:4]
        month_labels.append(f"{MONTH_NAMES[mi - 1]} {yr}")

    def _with_annual(arr):
        """Insert FY2025 total after the first 12 months."""
        out = [round(v) for v in arr[:num_2025]]
        out.append(_annual(arr))
        out.extend([round(v) for v in arr[num_2025:]])
        return out

    result = {
        "months": month_labels,
        "fy2025_idx": num_2025,
        "brand_sales": {},
        "total_revenue": _with_annual(total_sales),
        "cogs": _with_annual(cogs),
        "gross_margin": _with_annual(cm_before_total),
        "ad_spend": {
            "onzenna": _with_annual(ad_spend_onzenna),
            "amazon": _with_annual(ad_spend_amazon),
            "total": _with_annual(ad_spend_total),
        },
        "ad_spend_detail": {
            "google": _with_annual(ad_spend_google),
            "amz_grosmimi": _with_annual(ad_spend_amz_grosmimi),
            "amz_chaenmom": _with_annual(ad_spend_amz_chaenmom),
            "amz_naeiae": _with_annual(ad_spend_amz_naeiae),
        },
        "sales_from_ads": {
            "onzenna": _with_annual(sales_from_ads_onz),
            "amazon": _with_annual(sales_from_ads_amz),
            "total": _with_annual(sales_from_ads_total),
        },
        "organic": {
            "onzenna": _with_annual(organic_onz),
            "amazon": _with_annual(organic_amz),
            "total": _with_annual(organic_total),
        },
        "influencer_spend": _with_annual(influencer_total),
        "cm_after_ads": _with_annual(cm_after_total),
        "cm_final": _with_annual(cm_final),
    }

    for brand, vals in brand_sales.items():
        result["brand_sales"][brand] = {
            "values": _with_annual(vals),
            "color": POLAR_BRAND_COLORS.get(brand, "#94a3b8"),
        }

    wb.close()
    print(f"  Polar Excel parsed: {len(target_months)} months, {len(brand_sales)} brands")
    return result


def generate():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Financial KPIs data")
    parser.add_argument("--months", type=int, default=9)
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
    print(f"  Shopify: {len(shopify)} rows, Amazon Sales: {len(amazon_sales)}")
    print(f"  Amazon Ads: {len(amazon_ads)}, Meta: {len(meta_ads)}, Google: {len(google_ads)}")
    print(f"  GA4: {len(ga4)}, Search Terms: {len(search_terms)}, GSC: {len(gsc)}")
    print(f"  Brand Analytics: {len(brand_analytics)}, Shopify SKU: {len(shopify_sku)}, Amazon SKU: {len(amazon_sku)}")

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
    ]

    # ── Partial month detection ───────────────────────────────────────────────
    through_date_obj = datetime.strptime(through, "%Y-%m-%d").date()
    current_month = through[:7]  # e.g. "2026-03"
    days_elapsed = through_date_obj.day
    days_in_month = calendar.monthrange(through_date_obj.year, through_date_obj.month)[1]
    is_partial = days_elapsed < days_in_month
    fm_multiplier = round(days_in_month / days_elapsed, 4) if days_elapsed > 0 else 1
    print(f"  Partial month: {current_month} ({days_elapsed}/{days_in_month}d) → multiplier {fm_multiplier}x")

    partial_month_info = {
        "month": current_month,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "is_partial": is_partial,
        "multiplier": fm_multiplier,
    }

    # ── 2. Revenue by Brand (Shopify only, PR/Amazon excluded) ─────────────────
    # Amazon channel = stale FBA MCF rows in PG (now reclassified as D2C in current code)
    # True Amazon Marketplace sales come from amazon_sales_daily (SP-API)
    SKIP_CHANNELS = {"PR", "Amazon"}
    print("\n[2/7] Computing revenue by brand...")
    brand_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gross": 0, "net": 0, "disc": 0, "orders": 0, "units": 0
    }))

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

    # Amazon SP-API revenue by brand
    amz_brand_monthly = defaultdict(lambda: defaultdict(lambda: {
        "net": 0, "orders": 0, "units": 0
    }))
    for r in amazon_sales:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        brand = r.get("brand") or "Other"
        if brand not in BRAND_ORDER:
            brand = "Other"
        amz_brand_monthly[brand][month]["net"] += float(r.get("net_sales") or 0)
        amz_brand_monthly[brand][month]["orders"] += int(r.get("orders") or 0)
        amz_brand_monthly[brand][month]["units"] += int(r.get("units") or 0)

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

    # Amazon Marketplace (SP-API)
    for r in amazon_sales:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        channel_monthly["Amazon MP"][month]["net"] += float(r.get("net_sales") or 0)
        channel_monthly["Amazon MP"][month]["orders"] += int(r.get("orders") or 0)

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

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        ad_monthly["Google Ads"][month]["spend"] += float(r.get("spend") or 0)
        ad_monthly["Google Ads"][month]["sales"] += float(r.get("conversion_value") or 0)
        ad_monthly["Google Ads"][month]["impressions"] += int(r.get("impressions") or 0)
        ad_monthly["Google Ads"][month]["clicks"] += int(r.get("clicks") or 0)

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

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        # All Google Ads campaigns are Grosmimi (Mint | prefix)
        brand_ad_monthly["Grosmimi"][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_monthly["Grosmimi"][month]["sales"] += float(r.get("conversion_value") or 0)

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
    print(f"  Months: {months[0]} → {months[-1]} ({len(months)} months)")
    print(f"  Ad months: {ad_months[0] if ad_months else 'none'} → {ad_months[-1] if ad_months else 'none'} (from idx {ad_start_idx})")

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
    # Onzenna channel: Google Ads + Meta CVR → Shopify D2C revenue
    # Amazon channel: Amazon Ads + Meta Traffic → Amazon MP revenue
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
        # Total revenue = shopify + amazon SP-API
        shopify_net = sum(brand_monthly.get(b, {}).get(m, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
        amz_net = sum(amz_brand_monthly.get(b, {}).get(m, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
        rev = shopify_net + amz_net

        # COGS from Shopify + Amazon (brand-level avg)
        cogs = 0
        for b in BRAND_ORDER:
            # Shopify COGS
            v = brand_monthly.get(b, {}).get(m, {})
            units = v.get("units", 0)
            if units == 0 and v.get("gross", 0) > 0:
                units = int(v["gross"] / AVG_PRICE.get(b, 25))
            cogs += units * AVG_COGS.get(b, 8)
            # Amazon COGS
            amz_v = amz_brand_monthly.get(b, {}).get(m, {})
            amz_units = amz_v.get("units", 0)
            if amz_units == 0 and amz_v.get("net", 0) > 0:
                amz_units = int(amz_v["net"] / AVG_PRICE.get(b, 25))
            cogs += amz_units * AVG_COGS.get(b, 8)

        gm = rev - cogs  # GM = Total Revenue - Total COGS

        # MKT Cost 1: Ad Spend
        ad_total = sum(
            ad_monthly.get(p, {}).get(m, {}).get("spend", 0)
            for p in ["Amazon Ads", "Meta CVR", "Meta Traffic", "Google Ads"]
        )

        # MKT Cost 2: Discounts (Shopify, absolute value)
        disc_total = sum(
            abs(brand_monthly.get(b, {}).get(m, {}).get("disc", 0))
            for b in BRAND_ORDER + ["Other"]
        )

        # MKT Cost 3: Seeding / Influencer collab (not yet in DataKeeper)
        seeding_total = 0

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

    # ── Parse Polar CSV for full P&L ────────────────────────────────────────
    print("[7.5/8] Parsing Polar Excel for P&L...")
    pnl_polar = parse_polar_excel()

    # ── Append months beyond Excel with DataKeeper data ───────────────────
    if pnl_polar:
        MONTH_NAMES_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        # Find which YYYY-MM keys the Polar data already covers
        polar_month_keys = set()
        for lbl in pnl_polar["months"]:
            if lbl.startswith("FY"):
                continue
            parts = lbl.split()  # e.g. "Jan 25"
            if len(parts) == 2:
                mi = MONTH_NAMES_SHORT.index(parts[0]) + 1
                yr = 2000 + int(parts[1])
                polar_month_keys.add(f"{yr}-{mi:02d}")

        # months from DataKeeper that are NOT in Polar yet
        extra_months = sorted(m for m in months if m not in polar_month_keys and m > "2025-12")

        if extra_months:
            fy_idx = pnl_polar["fy2025_idx"]
            for em in extra_months:
                mi = int(em[5:7])
                yr = em[2:4]
                lbl = f"{MONTH_NAMES_SHORT[mi-1]} {yr}"
                pnl_polar["months"].append(lbl)

                # Revenue & COGS from waterfall (already computed from DataKeeper)
                wf_idx = months.index(em) if em in months else None
                rev = total_rev_monthly[wf_idx] if wf_idx is not None else 0
                cogs_v = total_cogs_monthly[wf_idx] if wf_idx is not None else 0
                gm = total_gm_monthly[wf_idx] if wf_idx is not None else 0
                ad_total_v = total_ad_spend_monthly[wf_idx] if wf_idx is not None else 0

                pnl_polar["total_revenue"].append(rev)
                pnl_polar["cogs"].append(cogs_v)
                pnl_polar["gross_margin"].append(gm)

                # Ad spend breakdown from ad_monthly
                onz_spend = sum(
                    ad_monthly.get(p, {}).get(em, {}).get("spend", 0)
                    for p in ["Meta CVR", "Meta Traffic", "Google Ads"]
                )
                amz_spend = ad_monthly.get("Amazon Ads", {}).get(em, {}).get("spend", 0)
                pnl_polar["ad_spend"]["onzenna"].append(round(onz_spend))
                pnl_polar["ad_spend"]["amazon"].append(round(amz_spend))
                pnl_polar["ad_spend"]["total"].append(round(onz_spend + amz_spend))

                # Detail breakdowns
                google_spend = ad_monthly.get("Google Ads", {}).get(em, {}).get("spend", 0)
                pnl_polar["ad_spend_detail"]["google"].append(round(google_spend))
                # Amazon brand breakdown not available from DK aggregation — use 0
                pnl_polar["ad_spend_detail"]["amz_grosmimi"].append(0)
                pnl_polar["ad_spend_detail"]["amz_chaenmom"].append(0)
                pnl_polar["ad_spend_detail"]["amz_naeiae"].append(0)

                # Sales from ads — use DK paid data
                paid_v = sum(
                    ad_monthly.get(p, {}).get(em, {}).get("sales", 0)
                    for p in ["Amazon Ads", "Meta CVR", "Meta Traffic", "Google Ads"]
                )
                onz_paid = sum(
                    ad_monthly.get(p, {}).get(em, {}).get("sales", 0)
                    for p in ["Meta CVR", "Meta Traffic", "Google Ads"]
                )
                amz_paid = ad_monthly.get("Amazon Ads", {}).get(em, {}).get("sales", 0)
                pnl_polar["sales_from_ads"]["onzenna"].append(round(onz_paid))
                pnl_polar["sales_from_ads"]["amazon"].append(round(amz_paid))
                pnl_polar["sales_from_ads"]["total"].append(round(paid_v))

                # Organic
                org_v = max(0, rev - round(paid_v))
                pnl_polar["organic"]["onzenna"].append(0)
                pnl_polar["organic"]["amazon"].append(0)
                pnl_polar["organic"]["total"].append(org_v)

                # Influencer spend not in DK
                pnl_polar["influencer_spend"].append(0)

                # CM after ads = GM - ad spend
                cm_after = gm - round(onz_spend + amz_spend)
                pnl_polar["cm_after_ads"].append(cm_after)
                pnl_polar["cm_final"].append(cm_after)

                # Brand sales — append 0 for each brand (DK doesn't have Polar brand breakdown)
                for brand in pnl_polar["brand_sales"]:
                    pnl_polar["brand_sales"][brand]["values"].append(0)

            print(f"  Appended {len(extra_months)} extra months from DataKeeper: {extra_months}")

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

    if args.push:
        import subprocess
        os.chdir(str(ROOT))
        subprocess.run(["git", "add", str(OUTPUT)], check=True)
        subprocess.run(["git", "commit", "-m", "auto: update financial KPI data [skip ci]"], check=False)
        subprocess.run(["git", "push"], check=True)
        print("  Pushed to GitHub")


if __name__ == "__main__":
    generate()
