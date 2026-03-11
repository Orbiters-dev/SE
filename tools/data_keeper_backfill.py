"""Data Keeper Backfill - Import existing q*.json history into PostgreSQL.

Reads Polar-schema JSON files from .tmp/polar_data/ and converts them
to Data Keeper format, then pushes to PostgreSQL via orbitools API.

Usage:
    python tools/data_keeper_backfill.py                  # All sources
    python tools/data_keeper_backfill.py --source q5      # Amazon Ads only
    python tools/data_keeper_backfill.py --dry-run         # Preview without pushing
    python tools/data_keeper_backfill.py --save-cache      # Also save to local cache
"""

import os
import sys
import json
import argparse
from datetime import datetime

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env
load_env()

POLAR_DIR = os.path.join(DIR, "..", ".tmp", "polar_data")
CACHE_DIR = os.path.join(DIR, "..", ".tmp", "datakeeper")
os.makedirs(CACHE_DIR, exist_ok=True)

ORBITOOLS_BASE = "https://orbitools.orbiters.co.kr/api/datakeeper"
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")


def _load_polar(filename):
    """Load a Polar-schema JSON file."""
    path = os.path.join(POLAR_DIR, filename)
    if not os.path.exists(path):
        print(f"  [SKIP] {filename} not found")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("tableData", []) if isinstance(data, dict) else data
    print(f"  Loaded {filename}: {len(rows)} rows")
    return rows


def _push(table, rows, dry_run=False, save_cache=False):
    """Push converted rows to PG and optionally save cache."""
    if not rows:
        print(f"  [SKIP] {table}: 0 rows")
        return

    if save_cache:
        cache_path = os.path.join(CACHE_DIR, f"{table}.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, default=str, ensure_ascii=False)
        print(f"  [Cache] {table}: {len(rows)} rows")

    if dry_run:
        print(f"  [DRY] {table}: {len(rows)} rows (would push)")
        if rows:
            print(f"    Sample: {json.dumps(rows[0], default=str)[:200]}")
        return

    # Push in chunks
    chunk_size = 500
    total_created = 0
    total_updated = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        try:
            resp = requests.post(
                f"{ORBITOOLS_BASE}/save/",
                json={"table": table, "rows": chunk},
                auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
                timeout=60,
            )
            resp.raise_for_status()
            r = resp.json()
            total_created += r.get("created", 0)
            total_updated += r.get("updated", 0)
        except Exception as e:
            print(f"  [ERROR] {table} chunk {i//chunk_size}: {e}")
    print(f"  [PG] {table}: +{total_created} new, ~{total_updated} updated")


# ══════════════════════════════════════════════════════════════════════════
# SOURCE CONVERTERS
# ══════════════════════════════════════════════════════════════════════════

def backfill_q1(dry_run, save_cache):
    """Q1: Shopify sales by channel/brand/product -> shopify_orders_daily."""
    print("\n[Q1] Shopify Sales -> shopify_orders_daily")
    polar = _load_polar("q1_channel_brand_product.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        # Monthly data -> use first day of month as date
        brand = r.get("custom_5036", "Unknown")  # brand dimension
        channel = r.get("custom_5005", "D2C")    # channel dimension
        rows.append({
            "date": date,
            "brand": brand,
            "channel": channel,
            "gross_sales": float(r.get("blended_gross_sales", 0) or 0),
            "discounts": float(r.get("blended_discounts", 0) or 0),
            "net_sales": float(r.get("blended_total_sales", 0) or 0),
            "orders": int(r.get("blended_total_orders", 0) or 0),
            "units": 0,
            "refunds": 0,
        })
    _push("shopify_orders_daily", rows, dry_run, save_cache)


def backfill_q13a(dry_run, save_cache):
    """Q13a: Shopify D2C daily -> shopify_orders_daily (D2C only)."""
    print("\n[Q13a] Shopify D2C Daily -> shopify_orders_daily")
    polar = _load_polar("q13a_shopify_d2c_daily.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        rows.append({
            "date": date,
            "brand": "All",
            "channel": "D2C",
            "gross_sales": float(r.get("shopify_sales_main.raw.gross_sales", 0) or 0),
            "discounts": float(r.get("shopify_sales_main.raw.discounts", 0) or 0),
            "net_sales": float(r.get("shopify_sales_main.computed.total_sales", 0) or 0),
            "orders": int(r.get("shopify_sales_main.raw.total_orders", 0) or 0),
            "units": 0,
            "refunds": 0,
        })
    _push("shopify_orders_daily", rows, dry_run, save_cache)


def backfill_q3(dry_run, save_cache):
    """Q3: Amazon sales by brand -> amazon_sales_daily."""
    print("\n[Q3] Amazon Sales -> amazon_sales_daily")
    polar = _load_polar("q3_amazon_brand.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        brand = r.get("custom_5036", "Unknown")
        rows.append({
            "date": date,
            "seller_id": "all",
            "brand": brand,
            "channel": "Amazon",
            "gross_sales": float(r.get("amazonsp_order_items.raw.gross_sales_amazon", 0) or 0),
            "net_sales": float(r.get("amazonsp_order_items.computed.net_sales_amazon", 0) or 0),
            "orders": int(r.get("amazonsp_order_items.raw.total_orders_amazon", 0) or 0),
            "units": 0,
            "fees": float(r.get("amazonsp_order_items.raw.total_fees_amazon", 0) or 0),
            "refunds": 0,
        })
    _push("amazon_sales_daily", rows, dry_run, save_cache)


def backfill_q5(dry_run, save_cache):
    """Q5: Amazon Ads by campaign -> amazon_ads_daily."""
    print("\n[Q5] Amazon Ads -> amazon_ads_daily")
    polar = _load_polar("q5_amazon_ads_campaign.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        campaign = r.get("campaign") or "Unknown"
        rows.append({
            "date": date,
            "profile_id": "backfill",
            "brand": _detect_brand(campaign),
            "campaign_id": f"bf_{hash(campaign + date) % 10**9}",
            "campaign_name": campaign,
            "ad_type": "SP",
            "impressions": int(r.get("amazonads_campaign.raw.impressions", 0) or 0),
            "clicks": int(r.get("amazonads_campaign.raw.clicks", 0) or 0),
            "spend": float(r.get("amazonads_campaign.raw.cost", 0) or 0),
            "sales": float(r.get("amazonads_campaign.raw.attributed_sales", 0) or 0),
            "purchases": 0,
        })
    _push("amazon_ads_daily", rows, dry_run, save_cache)


def backfill_q6(dry_run, save_cache):
    """Q6: Meta/Facebook Ads by campaign -> meta_ads_daily (campaign-level)."""
    print("\n[Q6] Meta Ads -> meta_ads_daily")
    polar = _load_polar("q6_facebook_ads_campaign.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        campaign = r.get("campaign") or "Unknown"
        spend = float(r.get("facebookads_ad_platform_and_device.raw.spend", 0) or 0)
        pv = float(r.get("facebookads_ad_platform_and_device.raw.purchases_conversion_value", 0) or 0)
        rows.append({
            "date": date,
            "ad_id": f"bf_{hash(campaign + date) % 10**9}",
            "ad_name": campaign,
            "campaign_id": f"bf_c_{hash(campaign) % 10**9}",
            "campaign_name": campaign,
            "brand": _detect_brand(campaign),
            "campaign_type": "cvr",
            "impressions": int(r.get("facebookads_ad_platform_and_device.raw.impressions", 0) or 0),
            "clicks": int(r.get("facebookads_ad_platform_and_device.raw.clicks", 0) or 0),
            "spend": spend,
            "reach": 0,
            "frequency": 0,
            "purchases": 0,
            "purchase_value": pv,
        })
    _push("meta_ads_daily", rows, dry_run, save_cache)


def backfill_q7(dry_run, save_cache):
    """Q7: Google Ads by campaign -> google_ads_daily."""
    print("\n[Q7] Google Ads -> google_ads_daily")
    polar = _load_polar("q7_google_ads_campaign.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        campaign = r.get("campaign") or "Unknown"
        rows.append({
            "date": date,
            "customer_id": "backfill",
            "campaign_id": f"bf_{hash(campaign + date) % 10**9}",
            "campaign_name": campaign,
            "brand": _detect_brand(campaign),
            "impressions": int(r.get("googleads_campaign_and_device.raw.impressions", 0) or 0),
            "clicks": int(r.get("googleads_campaign_and_device.raw.clicks", 0) or 0),
            "spend": float(r.get("googleads_campaign_and_device.raw.cost", 0) or 0),
            "conversions": 0,
            "conversion_value": float(r.get("googleads_campaign_and_device.raw.conversion_value", 0) or 0),
        })
    _push("google_ads_daily", rows, dry_run, save_cache)


def backfill_q13b(dry_run, save_cache):
    """Q13b: GA4 daily by channel -> ga4_daily."""
    print("\n[Q13b] GA4 -> ga4_daily")
    polar = _load_polar("q13b_ga4_by_channel_daily.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        rows.append({
            "date": date,
            "channel_grouping": r.get("custom_internal-default-channel-grouping", "(all)"),
            "sessions": int(r.get("ga_main.raw.sessions", 0) or 0),
            "purchases": int(r.get("ga_main.raw.ecommerce_purchases", 0) or 0),
        })
    # Also add totals from q13b_ga4_daily.json
    polar_total = _load_polar("q13b_ga4_daily.json")
    for r in polar_total:
        date = r.get("date", "")
        if not date:
            continue
        rows.append({
            "date": date,
            "channel_grouping": "(all)",
            "sessions": int(r.get("ga_main.raw.sessions", 0) or 0),
            "purchases": int(r.get("ga_main.raw.ecommerce_purchases", 0) or 0),
        })
    _push("ga4_daily", rows, dry_run, save_cache)


def backfill_q13e(dry_run, save_cache):
    """Q13e: Klaviyo campaigns daily -> klaviyo_daily."""
    print("\n[Q13e] Klaviyo -> klaviyo_daily")
    polar = _load_polar("q13e_klaviyo_campaigns_daily.json")
    rows = []
    for r in polar:
        date = r.get("date", "")
        if not date:
            continue
        rows.append({
            "date": date,
            "source_type": "campaign",
            "source_name": "all_campaigns",
            "source_id": f"kl_{date}",
            "sends": int(r.get("klaviyo_sales_main.raw.campaign_send", 0) or 0),
            "opens": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue": float(r.get("klaviyo_sales_main.raw.campaign_revenue", 0) or 0),
        })
    _push("klaviyo_daily", rows, dry_run, save_cache)


def _detect_brand(name):
    """Detect brand from campaign/product name."""
    n = (name or "").lower()
    if "grosmimi" in n:
        return "Grosmimi"
    if any(k in n for k in ["cha&mom", "chamom", "orbitool", "cha_mom"]):
        return "CHA&MOM"
    if "naeiae" in n or "fleeters" in n:
        return "Naeiae"
    if "onzenna" in n:
        return "Onzenna"
    if "alpremio" in n:
        return "Alpremio"
    return "Unknown"


# ══════════════════════════════════════════════════════════════════════════

ALL_SOURCES = {
    "q1": backfill_q1,
    "q13a": backfill_q13a,
    "q3": backfill_q3,
    "q5": backfill_q5,
    "q6": backfill_q6,
    "q7": backfill_q7,
    "q13b": backfill_q13b,
    "q13e": backfill_q13e,
}


def main():
    parser = argparse.ArgumentParser(description="Data Keeper Backfill")
    parser.add_argument("--source", type=str, default="all",
                        help=f"Source to backfill ({', '.join(ALL_SOURCES.keys())}, all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without pushing to PG")
    parser.add_argument("--save-cache", action="store_true",
                        help="Also save to local datakeeper cache")
    args = parser.parse_args()

    print("=== Data Keeper Backfill ===")
    print(f"  Source: {args.source}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Save cache: {args.save_cache}")

    sources = ALL_SOURCES if args.source == "all" else {args.source: ALL_SOURCES.get(args.source)}

    for name, fn in sources.items():
        if fn is None:
            print(f"\n[SKIP] Unknown source: {name}")
            continue
        fn(args.dry_run, args.save_cache)

    print("\n=== Backfill Complete ===")


if __name__ == "__main__":
    main()
