"""
WAT Tool: Fetch Rakuten RMS order and sales data.

Uses the Rakuten RMS API to pull order/sales data and (when available)
RPP advertising performance for the weekly dashboard.

Prerequisites:
    - Active Rakuten Ichiba shop account with API access
    - RMS API credentials in .env (see workflows/weekly_dashboard_report.md)

Usage:
    python tools/fetch_rakuten_sales.py                 # fetch last 7 days
    python tools/fetch_rakuten_sales.py --days 14        # fetch last 14 days
    python tools/fetch_rakuten_sales.py --check-token    # check credentials only

Output:
    .tmp/rakuten_sales_weekly.json

Setup guide: workflows/weekly_dashboard_report.md
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

RMS_API_BASE = "https://api.rms.rakuten.co.jp/es/2.0"
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp"
OUTPUT_PATH = OUTPUT_DIR / "rakuten_sales_weekly.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Auth ─────────────────────────────────────────────────────────────

def check_credentials() -> dict:
    """Validate that all required .env variables are present."""
    required = {
        "RAKUTEN_SERVICE_SECRET": os.getenv("RAKUTEN_SERVICE_SECRET"),
        "RAKUTEN_LICENSE_KEY": os.getenv("RAKUTEN_LICENSE_KEY"),
    }
    missing = [k for k, v in required.items() if not v]
    return {"ok": len(missing) == 0, "missing": missing, "values": required}


def get_auth_header(service_secret: str, license_key: str) -> dict:
    """Build RMS API auth header (Base64 encoded serviceSecret:licenseKey)."""
    import base64
    credentials = f"{service_secret}:{license_key}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {
        "Authorization": f"ESA {encoded}",
        "Content-Type": "application/json; charset=utf-8",
    }


# ── Order search ─────────────────────────────────────────────────────

def search_orders(headers: dict, since: str, until: str) -> list[dict]:
    """
    Search orders by date range using RMS Order API.

    Args:
        since/until: Date strings in YYYY-MM-DDT00:00:00 format
    """
    url = f"{RMS_API_BASE}/order/searchOrder/"

    # RMS API v2.0 uses JSON
    request_body = {
        "dateType": 1,
        "startDatetime": since,
        "endDatetime": until,
        "PaginationRequestModel": {
            "requestRecordsAmount": 1000,
            "requestPage": 1,
        }
    }

    resp = requests.post(url, json=request_body, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"  [DEBUG] Status: {resp.status_code}")
        print(f"  [DEBUG] Response: {resp.text[:500]}")
        resp.raise_for_status()

    data = resp.json()
    order_numbers = []

    order_models = data.get("orderNumberList", [])
    if order_models:
        for item in order_models:
            if isinstance(item, str):
                order_numbers.append(item)
            elif isinstance(item, dict):
                on = item.get("orderNumber")
                if on:
                    order_numbers.append(on)

    return order_numbers


def get_order_details(headers: dict, order_numbers: list[str]) -> list[dict]:
    """
    Get detailed order information for given order numbers.
    RMS API processes up to 100 orders per request.
    """
    url = f"{RMS_API_BASE}/order/getOrder/"
    all_orders = []

    # Process in batches of 100
    for i in range(0, len(order_numbers), 100):
        batch = order_numbers[i:i+100]

        request_body = {
            "orderNumberList": batch,
            "version": 7,
        }

        resp = requests.post(url, json=request_body, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"  [DEBUG] getOrder status: {resp.status_code}")
            try:
                print(f"  [DEBUG] Response: {resp.text[:500]}")
            except UnicodeEncodeError:
                print(f"  [DEBUG] Response (ascii): {resp.text[:500].encode('ascii', 'replace').decode()}")
            resp.raise_for_status()

        data = resp.json()
        if i == 0:
            print(f"  [DEBUG] Response keys: {list(data.keys())}")
            models = data.get("orderModelList") or data.get("OrderModelList") or []
            print(f"  [DEBUG] orderModelList count: {len(models)}")
            if models and len(models) > 0:
                print(f"  [DEBUG] First order keys: {list(models[0].keys())[:10]}")

        order_list = data.get("OrderModelList") or data.get("orderModelList") or []
        for order in order_list:
            order_data = {
                "order_number": order.get("orderNumber"),
                "order_date": order.get("orderDatetime"),
                "status": order.get("orderProgress"),
                "total_price": float(order.get("totalPrice", 0) or 0),
                "payment_amount": float(order.get("requestPrice", 0) or 0),
                "items": [],
            }

            for pkg in order.get("PackageModelList", order.get("packageModelList", [])):
                for item_model in pkg.get("ItemModelList", pkg.get("itemModelList", [])):
                    order_data["items"].append({
                        "item_name": item_model.get("itemName"),
                        "item_number": item_model.get("itemNumber"),
                        "price": float(item_model.get("price", 0) or 0),
                        "units": int(item_model.get("units", 0) or 0),
                    })

            all_orders.append(order_data)

    return all_orders


def _text(element, tag: str) -> str | None:
    """Safe XML text extraction."""
    el = element.find(tag)
    return el.text if el is not None else None


def _float(element, tag: str) -> float:
    """Safe XML float extraction."""
    el = element.find(tag)
    return float(el.text) if el is not None and el.text else 0.0


def _int(element, tag: str) -> int:
    """Safe XML int extraction."""
    el = element.find(tag)
    return int(el.text) if el is not None and el.text else 0


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch Rakuten RMS sales data")
    parser.add_argument("--check-token", action="store_true", help="Check credentials only")
    parser.add_argument("--days", type=int, default=7, help="Fetch last N days (default: 7)")
    parser.add_argument("--date-from", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--date-to", type=str, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    print("=== Rakuten Sales Weekly Report ===\n")

    # ── Check credentials ────────────────────────────────────────
    print("[1/4] Checking credentials...")
    creds = check_credentials()

    if not creds["ok"]:
        print(f"\n[ERROR] Missing .env variables:")
        for key in creds["missing"]:
            print(f"  - {key}")
        print("\nSee workflows/weekly_dashboard_report.md for setup instructions.")
        sys.exit(1)

    print("  All credentials present.")

    if args.check_token:
        print("\n[OK] Credential check complete.")
        return

    # ── Build auth & date range ──────────────────────────────────
    headers = get_auth_header(
        creds["values"]["RAKUTEN_SERVICE_SECRET"],
        creds["values"]["RAKUTEN_LICENSE_KEY"],
    )

    if args.date_from and args.date_to:
        since_dt = datetime.strptime(args.date_from, "%Y-%m-%d")
        until_dt = datetime.strptime(args.date_to, "%Y-%m-%d")
    else:
        until_dt = datetime.now()
        since_dt = until_dt - timedelta(days=args.days)
    since_str = since_dt.strftime("%Y-%m-%dT00:00:00+0900")
    until_str = until_dt.strftime("%Y-%m-%dT23:59:59+0900")

    # ── Search orders ────────────────────────────────────────────
    print(f"\n[2/4] Searching orders ({since_dt.strftime('%Y-%m-%d')} to {until_dt.strftime('%Y-%m-%d')})...")
    order_numbers = search_orders(headers, since_str, until_str)
    print(f"  Found {len(order_numbers)} order(s)")

    if not order_numbers:
        print("\n  No orders found for this period.")
        output = {
            "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "date_range": {
                "since": since_dt.strftime("%Y-%m-%d"),
                "until": until_dt.strftime("%Y-%m-%d"),
            },
            "summary": {
                "total_orders": 0,
                "total_sales": 0,
                "currency": "JPY",
            },
            "orders": [],
        }
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"  Saved to: {OUTPUT_PATH}")
        return

    # ── Get order details ────────────────────────────────────────
    print(f"\n[3/4] Fetching order details...")
    orders = get_order_details(headers, order_numbers)
    print(f"  Retrieved {len(orders)} order(s) with details")

    # ── Aggregate & save ─────────────────────────────────────────
    print("\n[4/4] Saving results...")

    total_sales = sum(o.get("total_price", 0) for o in orders)
    total_units = sum(
        item.get("units", 0)
        for o in orders
        for item in o.get("items", [])
    )

    output = {
        "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "date_range": {
            "since": since_dt.strftime("%Y-%m-%d"),
            "until": until_dt.strftime("%Y-%m-%d"),
        },
        "summary": {
            "total_orders": len(orders),
            "total_sales": total_sales,
            "total_units": total_units,
            "currency": "JPY",
        },
        "orders": orders,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Total orders: {len(orders)}")
    print(f"  Total sales: ¥{total_sales:,.0f}")
    print(f"  Total units: {total_units}")
    print(f"  Saved to: {OUTPUT_PATH}")
    print("\n[OK] Rakuten sales weekly report complete.")


if __name__ == "__main__":
    main()
