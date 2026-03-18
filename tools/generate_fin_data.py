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
BRAND_ORDER = ["Grosmimi", "Naeiae", "CHA&MOM", "Onzenna", "Alpremio"]
BRAND_COLORS = {
    "Grosmimi": "#8b5cf6", "Naeiae": "#eab308", "CHA&MOM": "#0ea5e9",
    "Onzenna": "#ec4899", "Alpremio": "#f97316", "Other": "#94a3b8",
}
CHANNEL_COLORS = {
    "Onzenna D2C": "#6366f1", "Amazon MP": "#f59e0b", "Amazon FBA MCF": "#fb923c",
    "TikTok Shop": "#ec4899", "Target+": "#ef4444", "B2B": "#10b981", "Other": "#94a3b8",
}
AD_COLORS = {
    "Amazon Ads": "#f59e0b", "Meta Ads": "#3b82f6", "Google Ads": "#10b981",
}
AVG_COGS = {
    "Grosmimi": 8.41, "Naeiae": 5.35, "CHA&MOM": 7.53,
    "Onzenna": 5.35, "Alpremio": 12.57,
}
AVG_PRICE = {
    "Grosmimi": 28.0, "Naeiae": 18.0, "CHA&MOM": 32.0,
    "Onzenna": 22.0, "Alpremio": 38.0,
}


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
    print(f"  Shopify: {len(shopify)} rows, Amazon Sales: {len(amazon_sales)}")
    print(f"  Amazon Ads: {len(amazon_ads)}, Meta: {len(meta_ads)}, Google: {len(google_ads)}")
    print(f"  GA4: {len(ga4)}, Search Terms: {len(search_terms)}, GSC: {len(gsc)}")

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

    # ── 2. Revenue by Brand (Shopify only, PR excluded) ───────────────────────
    print("\n[2/7] Computing revenue by brand...")
    brand_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gross": 0, "net": 0, "disc": 0, "orders": 0, "units": 0
    }))

    for r in shopify:
        d = r.get("date", "")
        if not d or d > through:
            continue
        if r.get("channel") == "PR":
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
        if r.get("channel") == "PR":
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
        ad_monthly["Meta Ads"][month]["spend"] += float(r.get("spend") or 0)
        ad_monthly["Meta Ads"][month]["sales"] += float(r.get("revenue") or r.get("conversions_value") or 0)
        ad_monthly["Meta Ads"][month]["impressions"] += int(r.get("impressions") or 0)
        ad_monthly["Meta Ads"][month]["clicks"] += int(r.get("clicks") or 0)

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        ad_monthly["Google Ads"][month]["spend"] += float(r.get("spend") or 0)
        ad_monthly["Google Ads"][month]["sales"] += float(r.get("conversions_value") or r.get("revenue") or 0)
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
        brand_ad_monthly[brand][month]["sales"] += float(r.get("revenue") or r.get("conversions_value") or 0)

    for r in google_ads:
        d = r.get("date", "")
        if not d or d > through:
            continue
        month = d[:7]
        # All Google Ads campaigns are Grosmimi (Mint | prefix)
        brand_ad_monthly["Grosmimi"][month]["spend"] += float(r.get("spend") or 0)
        brand_ad_monthly["Grosmimi"][month]["sales"] += float(r.get("conversions_value") or r.get("revenue") or 0)

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
            if not d or d < date_from or d > date_to or r.get("channel") == "PR":
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
                ad_attributed_sales += float(r.get("revenue") or r.get("conversions_value") or 0)
        for r in google_ads:
            d = r.get("date", "")
            if d and date_from <= d <= date_to:
                total_ad_spend += float(r.get("spend") or 0)
                ad_attributed_sales += float(r.get("conversions_value") or r.get("revenue") or 0)

        gm = shopify_rev - shopify_cogs  # GM on Shopify only (Amazon COGS not available)
        cm = gm - total_ad_spend  # Contribution Margin = GM - Ad Spend

        return {
            "total_revenue": round(total_rev),
            "shopify_revenue": round(shopify_rev),
            "amazon_revenue": round(amz_rev),
            "total_orders": total_orders,
            "total_ad_spend": round(total_ad_spend),
            "ad_attributed_sales": round(ad_attributed_sales),
            "organic_revenue": round(total_rev - ad_attributed_sales) if total_rev > ad_attributed_sales else 0,
            "gross_margin": round(gm),
            "gm_pct": round(gm / shopify_rev * 100, 1) if shopify_rev else 0,
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

    # Amazon search terms (top 30 by spend)
    st_agg = defaultdict(lambda: {"impressions": 0, "clicks": 0, "spend": 0, "sales": 0, "orders": 0})
    for r in search_terms:
        q = (r.get("query") or r.get("search_term") or "").strip().lower()
        if not q:
            continue
        st_agg[q]["impressions"] += int(r.get("impressions") or 0)
        st_agg[q]["clicks"] += int(r.get("clicks") or 0)
        st_agg[q]["spend"] += float(r.get("spend") or r.get("cost") or 0)
        st_agg[q]["sales"] += float(r.get("sales") or r.get("revenue") or 0)
        st_agg[q]["orders"] += int(r.get("orders") or r.get("conversions") or 0)

    top_queries = sorted(st_agg.items(), key=lambda x: x[1]["spend"], reverse=True)[:30]
    search_data = []
    for q, v in top_queries:
        acos = round(v["spend"] / v["sales"] * 100, 1) if v["sales"] else 0
        ctr = round(v["clicks"] / v["impressions"] * 100, 2) if v["impressions"] else 0
        cvr = round(v["orders"] / v["clicks"] * 100, 2) if v["clicks"] else 0
        search_data.append({
            "query": q,
            "impressions": v["impressions"],
            "clicks": v["clicks"],
            "ctr": ctr,
            "spend": round(v["spend"], 2),
            "sales": round(v["sales"], 2),
            "orders": v["orders"],
            "acos": acos,
            "cvr": cvr,
        })

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
    for platform in ["Amazon Ads", "Meta Ads", "Google Ads"]:
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
        if any(v > 0 for v in total_sales_vals) or any(v > 0 for v in ad_spend_vals):
            brand_perf_out[brand] = {
                "total_sales": total_sales_vals,
                "total_sales_proj": proj_for(total_sales_vals, ad_months),
                "ad_spend": ad_spend_vals,
                "ad_spend_proj": proj_for(ad_spend_vals, ad_months),
                "ad_sales": ad_sales_vals,
                "color": BRAND_COLORS.get(brand, "#94a3b8"),
            }

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
            for p in ["Amazon Ads", "Meta Ads", "Google Ads"]
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
            for p in ["Amazon Ads", "Meta Ads", "Google Ads"]
        )
        paid_monthly.append(round(paid))

    organic_monthly = [max(0, rev - paid) for rev, paid in zip(total_rev_monthly, paid_monthly)]

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
        "gsc_queries": gsc_data,
        "keyword_rankings": keyword_rankings,
        "kw_positions_summary": kw_positions_summary,
        "keyword_volumes": keyword_volumes,
        "traffic_sources": traffic_data,
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
