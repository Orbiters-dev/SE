"""
Shopify 월별 브랜드별 매출/COGS 데이터 수집 (Polar Q2 대체)
============================================================
Polar MCP 없이 Shopify Orders API 직접 호출.
Jan 2024 ~ 현재까지 브랜드별 월별 집계 → q2_shopify_brand.json 생성.

COGS 처리:
  - 1단계 (현재): COGS = 0 (GSheet ID 확인 전)
  - 2단계 (추후): COGS GSheet ID를 SHOPIFY_COGS_SHEET_ID 환경변수에 추가 후 자동 읽기
    → Polar Analytics 대시보드 > Connectors > Google Sheets에서 시트 ID 확인

transaction_fees:
  - Shopify transaction fee ≈ 2.9% + $0.30 per order (Shopify Payments 기준)
  - 실제 값은 Shopify Payouts API로 가져오거나 수동 설정 가능
  - 현재: 0으로 설정 (CM 계산에 영향 있음)

사용법:
  python tools/fetch_shopify_cogs_monthly.py
  python tools/fetch_shopify_cogs_monthly.py --start 2024-01 --end 2026-02
  SHOPIFY_COGS_SHEET_ID=1abc... python tools/fetch_shopify_cogs_monthly.py
"""

import argparse
import json
import os
import urllib.parse
import urllib.request
from calendar import monthrange
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from env_loader import load_env

load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
COGS_SHEET_ID = os.getenv("SHOPIFY_COGS_SHEET_ID", "")  # 추후 추가
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / ".tmp" / "polar_data" / "q2_shopify_brand.json"

# ── Brand 판별 (polar_financial_model.py PROD_RULES와 동일) ──────────────────
PROD_RULES = [
    ("PPSU Straw Cup", "Grosmimi"), ("Flip Top", "Grosmimi"), ("KNOTTED", "Grosmimi"),
    ("Stainless Steel Straw", "Grosmimi"), ("Tumbler", "Grosmimi"),
    ("Baby Bottle", "Grosmimi"), ("Easy Baby Bottle", "Grosmimi"),
    ("2-pack", "Grosmimi"), ("Multi Accessory", "Grosmimi"),
    ("Replacement", "Grosmimi"), ("One Touch Cap", "Grosmimi"),
    ("Weighted Kit", "Grosmimi"), ("Strap", "Grosmimi"),
    ("Brush", "Grosmimi"), ("Teether", "Grosmimi"), ("Silicone Plate", "Grosmimi"),
    ("CHA&MOM", "CHA&MOM"), ("Naeiae", "Naeiae"), ("Alpremio", "Alpremio"),
    ("BabyRabbit", "BabyRabbit"), ("Bamboobebe", "Bamboobebe"),
    ("Beemeal", "Beemymagic"), ("Heart Tray", "Beemymagic"),
    ("Comme Moi", "Comme Moi"), ("Nature Love Mere", "Nature Love Mere"),
    ("Hattung", "Hattung"),
]
PR_TAGS = {"pr", "sample", "free sample", "giveaway", "collab", "collaboration", "supporter"}


def classify_brand(product_title: str) -> str:
    for kw, brand in PROD_RULES:
        if kw.lower() in product_title.lower():
            return brand
    return "Other"


def is_pr_order(tags_str: str) -> bool:
    tags = {t.strip().lower() for t in tags_str.split(",")}
    return bool(tags & PR_TAGS)


def load_cogs_from_gsheet() -> dict:
    """
    Google Sheets에서 SKU → COGS 매핑 읽기.
    SHOPIFY_COGS_SHEET_ID 설정 시 활성화.
    Returns: {sku: cost_per_unit}
    """
    if not COGS_SHEET_ID:
        return {}

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
        creds = Credentials.from_service_account_file(
            Path(__file__).resolve().parent.parent / creds_path,
            scopes=SCOPES
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(COGS_SHEET_ID)
        ws = sh.get_worksheet(0)
        rows = ws.get_all_values()

        cogs_map = {}
        for row in rows[1:]:  # 헤더 건너뜀
            if len(row) >= 2:
                sku = (row[0] or "").strip()
                try:
                    cost = float((row[1] or "0").replace(",", "").replace("$", ""))
                    if sku:
                        cogs_map[sku] = cost
                except (ValueError, IndexError):
                    pass
        print(f"  COGS GSheet에서 {len(cogs_map)}개 SKU 로드")
        return cogs_map
    except Exception as e:
        print(f"  ⚠️ COGS GSheet 로드 실패: {e}")
        return {}


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
        "fields": "id,tags,financial_status,line_items,total_price,total_discounts",
        "limit": 250,
    })
    url = f"{BASE}/orders.json?{params}"
    orders = []
    while url:
        data, url = shopify_get(url)
        orders.extend(data.get("orders", []))
    return orders


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

    cogs_map = load_cogs_from_gsheet()
    if not cogs_map:
        print("  [INFO] SHOPIFY_COGS_SHEET_ID 없음 -> COGS = 0 (환경변수 추가 시 자동 계산)\n")

    print(f"[Shopify COGS] 브랜드별 월별 집계: {args.start} ~ {args.end}\n")

    rows = []
    for y, m in month_range(args.start, args.end):
        date_key = f"{y:04d}-{m:02d}-01"
        print(f"  {date_key} 조회 중...", end=" ", flush=True)

        orders = fetch_orders_for_month(y, m)
        print(f"{len(orders)}개 주문", end=" → ", flush=True)

        # 브랜드별 집계
        agg = defaultdict(lambda: {
            "gross_sales": 0.0, "discounts": 0.0,
            "total_orders": 0, "cogs": 0.0,
        })

        for order in orders:
            if order.get("financial_status") == "voided":
                continue
            # PR 주문은 Q2에서 제외 (D2C Shopify 매출만 집계)
            if is_pr_order(order.get("tags") or ""):
                continue

            total_discount = float(order.get("total_discounts") or 0)
            line_items = order.get("line_items") or []
            order_total_line = sum(
                float(li.get("price") or 0) * int(li.get("quantity") or 1)
                for li in line_items
            )

            brand_counted = set()
            for li in line_items:
                product_title = (li.get("title") or li.get("name") or "").strip()
                brand = classify_brand(product_title)
                li_qty = int(li.get("quantity") or 1)
                li_price = float(li.get("price") or 0)
                li_gross = li_price * li_qty
                li_discount = -(total_discount * li_gross / order_total_line) if order_total_line > 0 else 0.0

                # COGS: SKU 기준으로 GSheet에서 가져옴
                sku = (li.get("sku") or "").strip()
                unit_cost = cogs_map.get(sku, 0.0)
                li_cogs = unit_cost * li_qty

                agg[brand]["gross_sales"] += li_gross
                agg[brand]["discounts"] += li_discount
                agg[brand]["cogs"] += li_cogs
                if brand not in brand_counted:
                    agg[brand]["total_orders"] += 1
                    brand_counted.add(brand)

        month_rows = []
        for brand, metrics in agg.items():
            gross = metrics["gross_sales"]
            disc = metrics["discounts"]
            cogs = metrics["cogs"]
            net = gross + disc
            transaction_fees = 0.0  # 추후 Shopify Payouts API로 보완 가능
            cm1 = net - cogs - transaction_fees
            cm2 = cm1  # CM2 = CM1 (추가 비용 없을 경우)

            month_rows.append({
                "shopify_sales_main.computed.total_sales": round(net, 6),
                "shopify_sales_main.computed.contribution_margin_1": round(cm1, 6),
                "shopify_sales_main.computed.contribution_margin_2": round(cm2, 6),
                "shopify_sales_main.raw.gross_sales": round(gross, 6),
                "shopify_sales_main.raw.discounts": round(disc, 6),
                "shopify_sales_main.raw.total_orders": metrics["total_orders"],
                "shopify_sales_main.raw.cost_of_products_custom": round(cogs, 6),
                "shopify_sales_main.raw.transaction_fees": transaction_fees,
                "custom_5036": brand,
                "date": date_key,
            })

        rows.extend(month_rows)
        print(f"{len(month_rows)}개 브랜드")

    total = {
        "shopify_sales_main.computed.total_sales": sum(r["shopify_sales_main.computed.total_sales"] for r in rows),
        "shopify_sales_main.computed.contribution_margin_1": sum(r["shopify_sales_main.computed.contribution_margin_1"] for r in rows),
        "shopify_sales_main.computed.contribution_margin_2": sum(r["shopify_sales_main.computed.contribution_margin_2"] for r in rows),
        "shopify_sales_main.raw.gross_sales": sum(r["shopify_sales_main.raw.gross_sales"] for r in rows),
        "shopify_sales_main.raw.discounts": sum(r["shopify_sales_main.raw.discounts"] for r in rows),
        "shopify_sales_main.raw.total_orders": sum(r["shopify_sales_main.raw.total_orders"] for r in rows),
        "shopify_sales_main.raw.cost_of_products_custom": sum(r["shopify_sales_main.raw.cost_of_products_custom"] for r in rows),
        "shopify_sales_main.raw.transaction_fees": 0,
    }

    output = {"tableData": rows, "totalData": [total]}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] 저장: {OUTPUT_PATH}")
    print(f"   총 레코드: {len(rows)}개")
    print(f"   총 매출: ${total['shopify_sales_main.raw.gross_sales']:,.0f}")
    if not cogs_map:
        print(f"\n[주의] COGS = 0 상태. Polar 대시보드에서 COGS GSheet ID 확인 후 .env에 추가:")
        print(f"   SHOPIFY_COGS_SHEET_ID=<시트ID>")


if __name__ == "__main__":
    main()
