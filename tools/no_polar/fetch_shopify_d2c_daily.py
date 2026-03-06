"""
fetch_shopify_d2c_daily.py - Shopify D2C daily sales collector (Q13a)

Fetches Shopify orders, filters D2C channel only, aggregates by day.
Channel classification reuses logic from fetch_shopify_sales_monthly.py.

Output: .tmp/polar_data/q13a_shopify_d2c_daily.json
Format: {"tableData": [{"shopify_sales_main.raw.gross_sales": X,
                        "shopify_sales_main.raw.discounts": X,
                        "shopify_sales_main.computed.total_sales": X,
                        "shopify_sales_main.raw.total_orders": N,
                        "date": "YYYY-MM-DD"}]}

Usage:
    python tools/no_polar/fetch_shopify_d2c_daily.py --start 2024-01 --end 2026-03
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from dateutil.relativedelta import relativedelta

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUTPUT_PATH = ROOT / ".tmp" / "polar_data" / "q13a_shopify_d2c_daily.json"

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

# --- Channel classification (same as fetch_shopify_sales_monthly.py) ---
PR_TAGS = {"pr", "sample", "free sample", "giveaway", "collab", "collaboration", "supporter", "supporters"}
B2B_TAGS = {"b2b", "wholesale", "distributor"}
AMAZON_SOURCES = {"amazon", "amazon_marketplace_web"}
TIKTOK_SOURCES = {"tiktok_shop", "tiktok"}


def classify_channel(order: dict) -> str:
    source = (order.get("source_name") or "").lower().strip()
    tags_raw = order.get("tags") or ""
    tags = {t.strip().lower() for t in tags_raw.split(",")}

    if tags & PR_TAGS:
        return "PR"
    if tags & B2B_TAGS or "wholesale" in source:
        return "B2B"
    if source in AMAZON_SOURCES or "amazon" in source:
        return "Amazon"
    if source in TIKTOK_SOURCES:
        return "TikTok"
    if "target" in tags or "target+" in tags:
        return "Target+"
    if "fbm" in tags or "fbm" in source:
        return "FBM"
    return "D2C"


def shopify_get(url: str) -> tuple:
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        link_header = resp.headers.get("Link", "")
        next_url = None
        if 'rel="next"' in link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part.split("<")[1].split(">")[0]
        return data, next_url


def fetch_orders_for_month(year: int, month: int) -> list:
    last_day = monthrange(year, month)[1]
    params = urllib.parse.urlencode({
        "status": "any",
        "created_at_min": f"{year:04d}-{month:02d}-01T00:00:00",
        "created_at_max": f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59",
        "fields": "id,created_at,source_name,tags,line_items,financial_status,total_price,subtotal_price,total_discounts",
        "limit": 250,
    })
    url = f"{BASE}/orders.json?{params}"
    orders = []
    while url:
        data, url = shopify_get(url)
        orders.extend(data.get("orders", []))
    return orders


def aggregate_d2c_daily(orders: list) -> dict:
    """Filter D2C only, aggregate by day."""
    bucket = defaultdict(lambda: {"gross": 0.0, "discounts": 0.0, "orders": 0})

    for order in orders:
        fin_status = order.get("financial_status", "")
        if fin_status in ("refunded", "voided"):
            continue

        if classify_channel(order) != "D2C":
            continue

        created = (order.get("created_at") or "")[:10]
        if not created:
            continue

        gross = 0.0
        for li in order.get("line_items", []):
            qty = int(li.get("quantity", 0))
            price = float(li.get("price", 0))
            gross += qty * price

        discounts = float(order.get("total_discounts", 0) or 0)

        bucket[created]["gross"] += gross
        bucket[created]["discounts"] += discounts
        bucket[created]["orders"] += 1

    return bucket


def main():
    parser = argparse.ArgumentParser(description="Fetch Shopify D2C daily sales (Q13a)")
    parser.add_argument("--start", default="2024-01", help="Start month YYYY-MM")
    parser.add_argument("--end",   default=None,      help="End month YYYY-MM")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set")
        sys.exit(1)

    today = date.today()
    start = datetime.strptime(args.start, "%Y-%m").date().replace(day=1)
    end_str = args.end or today.strftime("%Y-%m")
    end = datetime.strptime(end_str, "%Y-%m").date().replace(day=1)

    print(f"[Shopify D2C Daily] {start} ~ {end} | Shop: {SHOP}")

    all_daily = defaultdict(lambda: {"gross": 0.0, "discounts": 0.0, "orders": 0})
    cur = start
    while cur <= end:
        y, m = cur.year, cur.month
        print(f"  Fetching {y}-{m:02d}...", end="", flush=True)
        orders = fetch_orders_for_month(y, m)
        monthly = aggregate_d2c_daily(orders)
        for dk, v in monthly.items():
            all_daily[dk]["gross"] += v["gross"]
            all_daily[dk]["discounts"] += v["discounts"]
            all_daily[dk]["orders"] += v["orders"]
        print(f" {len(orders)} orders, {len(monthly)} D2C days")
        cur += relativedelta(months=1)
        time.sleep(0.5)

    table_data = []
    for dk in sorted(all_daily.keys()):
        v = all_daily[dk]
        net = v["gross"] - v["discounts"]
        table_data.append({
            "shopify_sales_main.raw.gross_sales":     round(v["gross"], 6),
            "shopify_sales_main.raw.discounts":       round(-v["discounts"], 6),
            "shopify_sales_main.computed.total_sales": round(net, 6),
            "shopify_sales_main.raw.total_orders":     v["orders"],
            "date": dk,
        })

    print(f"\n[Shopify D2C Daily] {len(table_data)} daily rows")
    total_net = sum(r["shopify_sales_main.computed.total_sales"] for r in table_data)
    print(f"[Shopify D2C Daily] Total net sales: ${total_net:,.0f}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"tableData": table_data}, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Q13a -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
