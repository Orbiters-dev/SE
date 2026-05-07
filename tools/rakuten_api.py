"""
Rakuten RMS API - Order/Sales data fetcher

Uses searchOrder + getOrder to pull weekly sales totals.
Auth: ESA Base64(serviceSecret:licenseKey)
Endpoint: https://api.rms.rakuten.co.jp/es/2.0/order/searchOrder/
"""

import os, sys, io, json, base64
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests

def _setup_encoding():
    if hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

SERVICE_SECRET = os.getenv("RAKUTEN_SERVICE_SECRET")
LICENSE_KEY = os.getenv("RAKUTEN_LICENSE_KEY")

BASE_URL = "https://api.rms.rakuten.co.jp/es/2.0/order"


def _auth_header():
    """Build ESA auth header: Base64(serviceSecret:licenseKey)"""
    cred = f"{SERVICE_SECRET}:{LICENSE_KEY}"
    b64 = base64.b64encode(cred.encode()).decode()
    return {
        "Authorization": f"ESA {b64}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def search_orders(date_from, date_to, status_list=None):
    """Search orders by date range.

    Args:
        date_from: "YYYY-MM-DDThh:mm:ss+0900"
        date_to:   "YYYY-MM-DDThh:mm:ss+0900"
        status_list: list of status codes (default [700] = payment complete)

    Returns: list of order numbers
    """
    if status_list is None:
        # 100:주문확인대기, 200:라쿠텐처리중, 300:배송대기,
        # 400:변경확인대기, 500:발송됨, 600:결제처리,
        # 700:결제처리완료, 800:취소대기, 900:취소확인
        status_list = [100, 200, 300, 400, 500, 600, 700]

    payload = {
        "orderProgressList": status_list,
        "dateType": 1,  # 주문일 기준
        "startDatetime": date_from,
        "endDatetime": date_to,
        "PaginationRequestModel": {
            "requestRecordsAmount": 1000,
            "requestPage": 1,
        }
    }

    resp = requests.post(
        f"{BASE_URL}/searchOrder/",
        headers=_auth_header(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # Check for API errors
    msg_model = data.get("MessageModelList", [])
    if msg_model:
        for m in msg_model:
            msg_type = m.get("messageType", "")
            msg_code = m.get("messageCode", "")
            message = m.get("message", "")
            print(f"  [{msg_type}] {msg_code}: {message}")

    order_numbers = data.get("orderNumberList", [])
    total = data.get("PaginationResponseModel", {}).get("totalRecordsAmount", 0)
    print(f"  Found {total} orders ({len(order_numbers)} returned)")
    return order_numbers


def get_order_details(order_numbers):
    """Get order details including payment amounts.

    Returns: list of order dicts with totalPrice, etc.
    """
    if not order_numbers:
        return []

    # API allows max 100 orders per request
    all_orders = []
    for i in range(0, len(order_numbers), 100):
        batch = order_numbers[i:i+100]
        payload = {
            "orderNumberList": batch,
            "version": 7,
        }

        resp = requests.post(
            f"{BASE_URL}/getOrder/",
            headers=_auth_header(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        orders = data.get("OrderModelList", [])
        all_orders.extend(orders)

    return all_orders


def weekly_sales(date_from_str, date_to_str):
    """Get total sales for a date range.

    Args:
        date_from_str: "YYYY-MM-DD"
        date_to_str:   "YYYY-MM-DD"

    Returns: dict with total_sales, order_count
    """
    tz = "+0900"
    start = f"{date_from_str}T00:00:00{tz}"
    end = f"{date_to_str}T23:59:59{tz}"

    print(f"\nSearching orders: {date_from_str} ~ {date_to_str}")
    order_nums = search_orders(start, end)

    if not order_nums:
        return {"total_sales": 0, "order_count": 0, "orders": []}

    print(f"  Fetching details for {len(order_nums)} orders...")
    orders = get_order_details(order_nums)

    total = 0
    for o in orders:
        # totalPrice = 商品合計金額 (item total)
        # requestPrice = 決済金額 (payment amount including shipping)
        price = o.get("totalPrice", 0) or 0
        total += price

    print(f"  Total sales: ¥{total:,}")
    return {
        "total_sales": total,
        "order_count": len(orders),
        "orders": orders,
    }


def test_connection():
    """Quick test: search last 7 days of completed orders."""
    print("=" * 50)
    print("Rakuten RMS API Connection Test")
    print("=" * 50)
    print(f"Service Secret: {SERVICE_SECRET[:10]}... (loaded)")
    print(f"License Key: {LICENSE_KEY[:10]}... (loaded)")

    today = datetime.now()
    week_ago = today - timedelta(days=7)

    result = weekly_sales(
        week_ago.strftime("%Y-%m-%d"),
        today.strftime("%Y-%m-%d"),
    )

    print(f"\n--- Result ---")
    print(f"Orders: {result['order_count']}")
    print(f"Total Sales: ¥{result['total_sales']:,}")

    if result["orders"]:
        print(f"\nSample order:")
        o = result["orders"][0]
        print(f"  Order#: {o.get('orderNumber', 'N/A')}")
        print(f"  Date: {o.get('orderDatetime', 'N/A')}")
        print(f"  Total: ¥{o.get('totalPrice', 0):,}")

    return result


if __name__ == "__main__":
    _setup_encoding()
    test_connection()
