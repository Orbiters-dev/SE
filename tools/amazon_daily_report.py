"""
WAT Tool: Amazon daily sales report → Teams AMAZON channel.

Reads yesterday's data from DataKeeper (local NAS) and posts brand-level summary.

Usage:
  python tools/amazon_daily_report.py
  python tools/amazon_daily_report.py --date 2026-03-15  # 指定日
"""
import sys
import io
import os
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).parent.parent / ".env")

JST = timezone(timedelta(hours=9))
DATAKEEPER = Path(__file__).parent.parent.parent / "Shared" / "datakeeper" / "latest"
WEBHOOK = os.getenv("TEAMS_AMAZON_WEBHOOK_URL")

BRAND_FLAG = {
    "Grosmimi": "🎀",
    "Naeiae": "🌿",
    "CHA&MOM": "🍵",
}


def fetch_yesterday(report_date: str):
    """Read DataKeeper amazon_sales_daily.json and filter to report_date."""
    data_file = DATAKEEPER / "amazon_sales_daily.json"
    if not data_file.exists():
        raise FileNotFoundError(f"DataKeeper file not found: {data_file}")

    with open(data_file, encoding="utf-8") as f:
        rows = json.load(f)

    brands = {}
    for row in rows:
        if row.get("date") != report_date:
            continue
        brand = row.get("brand", "Unknown")
        if brand not in brands:
            brands[brand] = {
                "gross_sales": 0.0,
                "net_sales": 0.0,
                "orders": 0,
                "units": 0,
                "fees": 0.0,
                "refunds": 0.0,
            }
        brands[brand]["gross_sales"] += row.get("gross_sales") or 0.0
        brands[brand]["net_sales"] += row.get("net_sales") or 0.0
        brands[brand]["orders"] += row.get("orders") or 0
        brands[brand]["units"] += row.get("units") or 0
        brands[brand]["fees"] += row.get("fees") or 0.0
        brands[brand]["refunds"] += row.get("refunds") or 0.0

    return brands


def post_to_teams(report_date: str, brands: dict):
    total_gross = sum(b["gross_sales"] for b in brands.values())
    total_net = sum(b["net_sales"] for b in brands.values())
    total_orders = sum(b["orders"] for b in brands.values())
    total_units = sum(b["units"] for b in brands.values())

    body = [
        {
            "type": "TextBlock",
            "text": f"📦 Amazon 前日レポート — {report_date}",
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
                {"title": "注文数合計", "value": f"{total_orders} 件"},
                {"title": "販売数合計", "value": f"{total_units} 個"},
                {"title": "売上合計 (Gross)", "value": f"${total_gross:,.2f}"},
                {"title": "純売上 (Net)", "value": f"${total_net:,.2f}"},
            ],
            "spacing": "Small",
        },
    ]

    if brands:
        body.append({"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━━━", "spacing": "Medium"})
        body.append({"type": "TextBlock", "text": "🏷️ ブランド別", "weight": "Bolder"})
        for brand, data in sorted(brands.items(), key=lambda x: x[1]["gross_sales"], reverse=True):
            flag = BRAND_FLAG.get(brand, "")
            facts = [
                {"title": "注文 / 販売数", "value": f"{data['orders']} 件 / {data['units']} 個"},
                {"title": "Gross売上", "value": f"${data['gross_sales']:,.2f}"},
                {"title": "Net売上", "value": f"${data['net_sales']:,.2f}"},
                {"title": "手数料", "value": f"${data['fees']:,.2f}"},
            ]
            if data["refunds"] > 0:
                facts.append({"title": "返金", "value": f"${data['refunds']:,.2f}"})
            body.append({
                "type": "TextBlock",
                "text": f"{flag} {brand}",
                "weight": "Bolder",
                "spacing": "Medium",
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
                    {"type": "TextBlock", "text": f"📦 Amazon 前日レポート — {report_date}", "weight": "Bolder", "size": "Large"},
                    {"type": "TextBlock", "text": "データなし", "spacing": "Medium", "isSubtle": True},
                ],
            },
        }],
    }
    requests.post(WEBHOOK, json=payload, timeout=15)
    print(f"No data for {report_date}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=str, default=None, help="対象日 YYYY-MM-DD (default: 前日)")
    args = p.parse_args()

    if not WEBHOOK:
        print("ERROR: TEAMS_AMAZON_WEBHOOK_URL not set in .env", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(JST).date()
    report_date = args.date or (today - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Fetching Amazon sales for {report_date} from DataKeeper...")
    brands = fetch_yesterday(report_date)

    if not brands:
        post_empty(report_date)
        return

    post_to_teams(report_date, brands)


if __name__ == "__main__":
    main()
