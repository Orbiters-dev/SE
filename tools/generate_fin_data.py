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
    "TikTok Shop": "#ec4899", "B2B": "#10b981", "Other": "#94a3b8",
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
    print(f"  Months: {months[0]} → {months[-1]} ({len(months)} months)")

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
                "color": BRAND_COLORS.get(brand, "#94a3b8"),
            }

    channel_rev_out = {}
    for ch in ["Onzenna D2C", "Amazon MP", "Amazon FBA MCF", "TikTok Shop", "B2B"]:
        vals = [round(channel_monthly.get(ch, {}).get(m, {}).get("net", 0)) for m in months]
        if any(v > 0 for v in vals):
            channel_rev_out[ch] = {
                "monthly": vals,
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
                "sales": sales_vals,
                "impressions": impr_vals,
                "clicks": click_vals,
                "color": AD_COLORS.get(platform, "#94a3b8"),
            }

    # Total monthly revenue & costs
    total_rev_monthly = []
    total_ad_spend_monthly = []
    total_gm_monthly = []
    total_cm_monthly = []

    for m in months:
        # Total revenue = shopify + amazon SP-API
        shopify_net = sum(brand_monthly.get(b, {}).get(m, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
        amz_net = sum(amz_brand_monthly.get(b, {}).get(m, {}).get("net", 0) for b in BRAND_ORDER + ["Other"])
        rev = shopify_net + amz_net

        # Estimated COGS from Shopify (brand-level avg)
        cogs = 0
        for b in BRAND_ORDER:
            v = brand_monthly.get(b, {}).get(m, {})
            units = v.get("units", 0)
            if units == 0 and v.get("gross", 0) > 0:
                units = int(v["gross"] / AVG_PRICE.get(b, 25))
            cogs += units * AVG_COGS.get(b, 8)

        gm = shopify_net - cogs

        # Total ad spend
        ad_total = sum(
            ad_monthly.get(p, {}).get(m, {}).get("spend", 0)
            for p in ["Amazon Ads", "Meta Ads", "Google Ads"]
        )

        cm = gm - ad_total

        total_rev_monthly.append(round(rev))
        total_ad_spend_monthly.append(round(ad_total))
        total_gm_monthly.append(round(gm))
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
        "summary": summary,
        "brand_revenue": brand_rev_out,
        "channel_revenue": channel_rev_out,
        "ad_performance": ad_out,
        "paid_organic": {
            "paid": paid_monthly,
            "organic": organic_monthly,
        },
        "waterfall": {
            "revenue": total_rev_monthly,
            "ad_spend": total_ad_spend_monthly,
            "gross_margin": total_gm_monthly,
            "contribution_margin": total_cm_monthly,
        },
        "search_queries": search_data,
        "gsc_queries": gsc_data,
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
