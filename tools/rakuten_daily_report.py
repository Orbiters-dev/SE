"""
WAT Tool: Rakuten daily order report → Teams RAKUTEN channel.

Fetches previous day's orders and posts SKU-level summary.

Usage:
  python tools/rakuten_daily_report.py
  python tools/rakuten_daily_report.py --date 2026-03-15  # 指定日
"""
import sys
import io
import os
import argparse
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from rakuten_rms_client import RakutenRMSClient

JST = timezone(timedelta(hours=9))
CONFIG = Path(__file__).parent.parent / "credentials" / "rakuten_rms_config.json"
WEBHOOK = os.getenv("TEAMS_RAKUTEN_WEBHOOK_URL")


def fetch_yesterday(report_date: str):
    """Fetch orders for a specific date (YYYY-MM-DD)."""
    client = RakutenRMSClient(str(CONFIG))
    today = datetime.now(JST).date()
    target = datetime.strptime(report_date, "%Y-%m-%d").date()
    days_back = (today - target).days + 1
    order_numbers = client.search_order_numbers(days=days_back)
    if not order_numbers:
        return None

    orders = client.get_orders(order_numbers)

    sku_units = defaultdict(int)
    sku_sales = defaultdict(float)
    sku_name = {}

    for o in orders:
        order_date = (o.get("orderDatetime") or "")[:10]
        if order_date != report_date:
            continue
        for pkg in (o.get("PackageModelList") or []):
            for item in (pkg.get("ItemModelList") or []):
                sku = item.get("manageNumber") or str(item.get("itemId") or "unknown")
                units = int(item.get("units") or 1)
                price = float(item.get("priceTaxIncl") or item.get("price") or 0)
                name_full = item.get("itemName") or ""
                name_short = name_full.split("/")[0].replace("【グロミミ公式】", "").strip()[:30]
                sku_units[sku] += units
                sku_sales[sku] += price * units
                sku_name[sku] = name_short

    return sku_units, sku_sales, sku_name


def post_to_teams(report_date: str, sku_units, sku_sales, sku_name):
    total_units = sum(sku_units.values())
    total_sales = sum(sku_sales.values())
    skus = sorted(sku_units.keys(), key=lambda s: sku_units[s], reverse=True)

    body = [
        {
            "type": "TextBlock",
            "text": f"🛒 楽天 前日レポート — {report_date}",
            "weight": "Bolder",
            "size": "Large",
        },
        {
            "type": "TextBlock",
            "text": f"報告時刻: {datetime.now(JST).strftime('%H:%M')} JST",
            "isSubtle": True,
            "spacing": "None",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
        {
            "type": "FactSet",
            "facts": [
                {"title": "注文数合計", "value": f"{total_units} 個"},
                {"title": "売上合計", "value": f"¥{total_sales:,.0f}"},
            ],
            "spacing": "Small",
        },
    ]

    if skus:
        body.append({"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━━━", "spacing": "Medium"})
        body.append({"type": "TextBlock", "text": "📦 SKU別", "weight": "Bolder"})
        facts = []
        for sku in skus:
            facts.append({
                "title": sku_name.get(sku, sku),
                "value": f"{sku_units[sku]}個 / ¥{sku_sales[sku]:,.0f}",
            })
        body.append({"type": "FactSet", "facts": facts, "spacing": "Small"})

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {"type": "AdaptiveCard", "version": "1.4", "body": body},
        }],
    }

    resp = requests.post(WEBHOOK, json=payload, timeout=15)
    if resp.status_code == 202:
        print(f"Teams posted OK ({report_date})")
    else:
        print(f"Teams error: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        sys.exit(1)


def post_empty(report_date: str):
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "type": "AdaptiveCard", "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": f"🛒 楽天 前日レポート — {report_date}", "weight": "Bolder", "size": "Large"},
                    {"type": "TextBlock", "text": "注文なし", "spacing": "Medium", "isSubtle": True},
                ],
            },
        }],
    }
    requests.post(WEBHOOK, json=payload, timeout=15)
    print(f"No orders for {report_date}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=str, default=None, help="対象日 YYYY-MM-DD (default: 前日)")
    args = p.parse_args()

    if not WEBHOOK:
        print("ERROR: TEAMS_RAKUTEN_WEBHOOK_URL not set in .env", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(JST).date()
    report_date = args.date or (today - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Fetching orders for {report_date}...")
    result = fetch_yesterday(report_date)

    if result is None or sum(result[0].values()) == 0:
        post_empty(report_date)
        return

    sku_units, sku_sales, sku_name = result
    post_to_teams(report_date, sku_units, sku_sales, sku_name)


if __name__ == "__main__":
    main()
