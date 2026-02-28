"""
Shopify 월별 매출 데이터 수집 (Polar Q1 대체)
============================================
Polar MCP 없이 Shopify Orders API 직접 호출.
Jan 2024 ~ 현재까지 월별 집계 → q1_channel_brand_product.json 생성.

Channel 판별 기준:
  - source_name "web"/"iphone"/"android"/etc.  → D2C
  - order tags "b2b"/"wholesale"               → B2B
  - order tags "pr"/"sample"/"giveaway"        → PR
  - source_name "amazon"                       → Amazon - Grosmimi USA (기본값)
  - source_name "tiktok_shop"                  → TikTok

Brand/Product 판별: PROD_RULES 키워드 매핑 (polar_financial_model.py와 동일)

사용법:
  python tools/no_polar/fetch_shopify_sales_monthly.py
  python tools/no_polar/fetch_shopify_sales_monthly.py --start 2024-01 --end 2026-02
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from calendar import monthrange
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/
from env_loader import load_env

load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / ".tmp" / "polar_data" / "q1_channel_brand_product.json"

# ── 동일 매핑 (polar_financial_model.py에서 가져옴) ──────────────────────────
PROD_RULES = [
    ("PPSU Straw Cup", "Grosmimi", "PPSU Straw Cup"),
    ("Flip Top", "Grosmimi", "Flip Top Cup"),
    ("KNOTTED", "Grosmimi", "Flip Top Cup"),
    ("Stainless Steel Straw", "Grosmimi", "Stainless Cup"),
    ("Tumbler", "Grosmimi", "Tumbler"),
    ("Baby Bottle", "Grosmimi", "Baby Bottle"),
    ("Easy Baby Bottle", "Grosmimi", "Baby Bottle"),
    ("2-pack", "Grosmimi", "Bundles"),
    ("Multi Accessory", "Grosmimi", "Bundles"),
    ("Replacement", "Grosmimi", "Replacement Parts"),
    ("Replacements", "Grosmimi", "Replacement Parts"),
    ("One Touch Cap", "Grosmimi", "Replacement Parts"),
    ("Weighted Kit", "Grosmimi", "Replacement Parts"),
    ("Strap", "Grosmimi", "Accessories"),
    ("Brush", "Grosmimi", "Accessories"),
    ("Teether", "Grosmimi", "Accessories"),
    ("Silicone Plate", "Grosmimi", "Accessories"),
    ("CHA&MOM", "CHA&MOM", "Skincare"),
    ("Naeiae", "Naeiae", "Food & Snacks"),
    ("Alpremio", "Alpremio", "Baby Carrier"),
    ("BabyRabbit", "BabyRabbit", "Apparel"),
    ("Bamboobebe", "Bamboobebe", "Bamboo Products"),
    ("Beemeal", "Beemymagic", "Tableware"),
    ("Heart Tray", "Beemymagic", "Tableware"),
    ("Comme Moi", "Comme Moi", "Educational Toys"),
    ("Nature Love Mere", "Nature Love Mere", "Baby Care"),
    ("Hattung", "Hattung", "Other"),
    ("B2B Wholesale", "Other", "Wholesale"),
]

PR_TAGS = {"pr", "sample", "free sample", "giveaway", "collab", "collaboration", "supporter", "supporters"}
B2B_TAGS = {"b2b", "wholesale", "distributor"}
AMAZON_SOURCES = {"amazon", "amazon_marketplace_web"}
TIKTOK_SOURCES = {"tiktok_shop", "tiktok"}


def classify_product(name: str):
    for kw, brand, cat in PROD_RULES:
        if kw.lower() in name.lower():
            return brand, cat
    return "Other", "Other"


def classify_channel(order: dict) -> str:
    """Shopify 주문에서 채널 판별"""
    source = (order.get("source_name") or "").lower().strip()
    tags_raw = order.get("tags") or ""
    tags = {t.strip().lower() for t in tags_raw.split(",")}

    # PR/Sample 먼저 체크 (태그 우선)
    if tags & PR_TAGS:
        return "PR"
    # B2B/Wholesale
    if tags & B2B_TAGS or "wholesale" in source:
        return "B2B"
    # Amazon
    if source in AMAZON_SOURCES or "amazon" in source:
        return "Amazon - Grosmimi USA"
    # TikTok
    if source in TIKTOK_SOURCES:
        return "TikTok"
    # Target+ — Shopify에서는 별도 앱으로 관리, 태그로 구분
    if "target" in tags or "target+" in tags:
        return "Target+"
    # FBM (Fulfillment by Merchant)
    if "fbm" in tags or "fbm" in source:
        return "FBM"
    # 기본 = D2C (Online Store)
    return "D2C"


def shopify_get(url: str) -> tuple:
    """GET 요청 → (data, next_url)"""
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
    """특정 월의 모든 주문 가져오기"""
    last_day = monthrange(year, month)[1]
    created_at_min = f"{year:04d}-{month:02d}-01T00:00:00"
    created_at_max = f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59"

    params = urllib.parse.urlencode({
        "status": "any",
        "created_at_min": created_at_min,
        "created_at_max": created_at_max,
        "fields": "id,created_at,source_name,tags,line_items,financial_status,total_price,subtotal_price,total_discounts",
        "limit": 250,
    })
    url = f"{BASE}/orders.json?{params}"
    orders = []

    while url:
        data, url = shopify_get(url)
        batch = data.get("orders", [])
        orders.extend(batch)

    return orders


def aggregate_orders(orders: list, date_key: str) -> dict:
    """
    주문 목록을 (channel, brand, product) 키로 집계.
    Returns: {(channel, brand, product): {gross, discounts, orders, net}}
    """
    agg = defaultdict(lambda: {
        "blended_gross_sales": 0.0,
        "blended_discounts": 0.0,
        "blended_total_orders": 0,
        "blended_total_sales": 0.0,
    })

    for order in orders:
        # 취소/환불 주문 제외 (financial_status: "refunded", "voided")
        fin_status = order.get("financial_status", "")
        if fin_status in ("voided",):
            continue

        channel = classify_channel(order)
        total_discount = float(order.get("total_discounts") or 0)
        total_price = float(order.get("total_price") or 0)

        line_items = order.get("line_items") or []
        if not line_items:
            # 라인 아이템 없는 주문: 전체 금액을 Other/Other로
            key = (channel, "Other", "Other")
            agg[key]["blended_gross_sales"] += total_price
            agg[key]["blended_total_orders"] += 1
            agg[key]["blended_total_sales"] += total_price
            continue

        # 라인 아이템별로 분배
        order_total_line = sum(float(li.get("price") or 0) * int(li.get("quantity") or 1) for li in line_items)
        order_counted = False

        for li in line_items:
            product_title = (li.get("title") or li.get("name") or "").strip()
            brand, cat = classify_product(product_title)
            product_label = cat  # Polar의 custom_5037은 product category (e.g. "PPSU Straw Cup")

            li_qty = int(li.get("quantity") or 1)
            li_price = float(li.get("price") or 0)
            li_gross = li_price * li_qty

            # 할인은 전체 주문 금액 비율로 배분
            li_discount = 0.0
            if order_total_line > 0:
                li_discount = -(total_discount * li_gross / order_total_line)

            key = (channel, brand, product_label)
            agg[key]["blended_gross_sales"] += li_gross
            agg[key]["blended_discounts"] += li_discount
            agg[key]["blended_total_sales"] += li_gross + li_discount
            if not order_counted:
                agg[key]["blended_total_orders"] += 1
                order_counted = True

    return agg


def month_range(start_ym: str, end_ym: str):
    sy, sm = int(start_ym[:4]), int(start_ym[5:7])
    ey, em = int(end_ym[:4]), int(end_ym[5:7])
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m"))
    args = parser.parse_args()

    if not TOKEN:
        raise SystemExit("❌ SHOPIFY_ACCESS_TOKEN 환경변수가 없습니다.")

    print(f"[Shopify] 월별 매출 수집: {args.start} ~ {args.end}\n")

    rows = []
    for y, m in month_range(args.start, args.end):
        date_key = f"{y:04d}-{m:02d}-01"
        print(f"  {date_key} 조회 중...", end=" ", flush=True)

        orders = fetch_orders_for_month(y, m)
        print(f"{len(orders)}개 주문", end=" → ", flush=True)

        agg = aggregate_orders(orders, date_key)

        month_rows = []
        for (channel, brand, product), metrics in agg.items():
            if metrics["blended_gross_sales"] == 0:
                continue
            month_rows.append({
                "blended_gross_sales": round(metrics["blended_gross_sales"], 6),
                "blended_discounts": round(metrics["blended_discounts"], 6),
                "blended_total_orders": metrics["blended_total_orders"],
                "blended_total_sales": round(metrics["blended_total_sales"], 6),
                "custom_5005": channel,
                "custom_5036": brand,
                "custom_5037": product,
                "date": date_key,
            })

        rows.extend(month_rows)
        print(f"{len(month_rows)}개 레코드")

    # totalData 집계
    total = {
        "blended_gross_sales": sum(r["blended_gross_sales"] for r in rows),
        "blended_discounts": sum(r["blended_discounts"] for r in rows),
        "blended_total_orders": sum(r["blended_total_orders"] for r in rows),
        "blended_total_sales": sum(r["blended_total_sales"] for r in rows),
    }

    output = {"tableData": rows, "totalData": [total]}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] 저장: {OUTPUT_PATH}")
    print(f"   총 레코드: {len(rows)}개")
    print(f"   총 매출: ${total['blended_gross_sales']:,.0f}")
    print(f"\n[참고] Amazon/Target+/TikTok 주문이 Shopify에 없는 경우 누락됩니다.")
    print(f"   해당 채널은 기존 Polar 캐시 JSON과 병합을 권장합니다.")


if __name__ == "__main__":
    main()
