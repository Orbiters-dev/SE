"""Bulk import existing Shopify customers and orders to PostgreSQL via n8n webhooks.

Fetches all customers/orders from Shopify REST API and sends them to
the n8n sync webhooks (setup_n8n_customer_sync.py, setup_n8n_order_sync.py).

Usage:
    python tools/shopify_bulk_import.py                    # Import both customers and orders
    python tools/shopify_bulk_import.py --customers-only   # Import customers only
    python tools/shopify_bulk_import.py --orders-only      # Import orders only
    python tools/shopify_bulk_import.py --dry-run          # Count without importing
    python tools/shopify_bulk_import.py --limit 10         # Import first N only (for testing)

Prerequisites:
    .wat_secrets: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN, N8N_BASE_URL
    n8n: Customer sync + order sync workflows must be active
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from env_loader import load_env

load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

CUSTOMER_WEBHOOK = f"{N8N_BASE_URL}/webhook/shopify-customer-sync"
ORDER_WEBHOOK = f"{N8N_BASE_URL}/webhook/shopify-order-sync"


def shopify_get(url):
    """GET with auth header, returns (data, next_link_url or None)."""
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
        link_header = resp.headers.get("Link", "")
        next_url = None
        if 'rel="next"' in link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part.split("<")[1].split(">")[0]
        return data, next_url


def send_to_webhook(webhook_url, payload):
    """POST payload to n8n webhook."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"error": True, "code": e.code, "body": error_body[:200]}
    except Exception as e:
        return {"error": True, "message": str(e)}


def import_customers(limit=None, dry_run=False):
    """Fetch all Shopify customers and send to n8n webhook."""
    print("\n  Importing customers...")
    url = f"{BASE}/customers.json?limit=250"
    total = 0
    success = 0
    failed = 0

    while url:
        data, next_url = shopify_get(url)
        customers = data.get("customers", [])

        for customer in customers:
            total += 1

            if limit and total > limit:
                print(f"    Reached limit ({limit}), stopping.")
                return total - 1, success, failed

            if dry_run:
                name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
                email = customer.get("email", "")
                if total <= 5:
                    print(f"    [{total}] {name} <{email}>")
                success += 1
                time.sleep(0.5)
                continue

            # Send to n8n customer sync webhook
            result = send_to_webhook(CUSTOMER_WEBHOOK, {"customer": customer})
            if result.get("error"):
                failed += 1
                if failed <= 3:
                    print(f"    [FAIL] Customer {customer['id']}: {result}")
            else:
                success += 1

            if total % 50 == 0:
                print(f"    Progress: {total} customers processed ({success} ok, {failed} failed)")

            # Rate limit: ~2 requests/second to avoid overwhelming n8n
            time.sleep(0.5)

        url = next_url
        if url:
            time.sleep(0.5)

    return total, success, failed


def import_orders(limit=None, dry_run=False):
    """Fetch all Shopify orders and send to n8n webhook."""
    print("\n  Importing orders...")
    url = f"{BASE}/orders.json?status=any&limit=250"
    total = 0
    success = 0
    failed = 0

    while url:
        data, next_url = shopify_get(url)
        orders = data.get("orders", [])

        for order in orders:
            total += 1

            if limit and total > limit:
                print(f"    Reached limit ({limit}), stopping.")
                return total - 1, success, failed

            if dry_run:
                name = order.get("name", "")
                price = order.get("total_price", "0")
                status = order.get("financial_status", "")
                if total <= 5:
                    print(f"    [{total}] {name} ${price} ({status})")
                continue

            # Send to n8n order sync webhook
            result = send_to_webhook(ORDER_WEBHOOK, {"order": order})
            if result.get("error"):
                failed += 1
                if failed <= 3:
                    print(f"    [FAIL] Order {order['id']}: {result}")
            else:
                success += 1

            if total % 50 == 0:
                print(f"    Progress: {total} orders processed ({success} ok, {failed} failed)")

            time.sleep(0.5)

        url = next_url
        if url:
            time.sleep(0.5)

    return total, success, failed


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Bulk import Shopify data to PostgreSQL via n8n")
    parser.add_argument("--dry-run", action="store_true", help="Count and preview without importing")
    parser.add_argument("--customers-only", action="store_true", help="Import customers only")
    parser.add_argument("--orders-only", action="store_true", help="Import orders only")
    parser.add_argument("--limit", type=int, help="Max records to import (for testing)")
    args = parser.parse_args()

    if not SHOP or not TOKEN:
        print("[ERROR] SHOPIFY_SHOP and SHOPIFY_ACCESS_TOKEN must be set in ~/.wat_secrets")
        sys.exit(1)

    do_customers = not args.orders_only
    do_orders = not args.customers_only

    print(f"\n{'=' * 60}")
    print(f"  Shopify Bulk Import -> PostgreSQL (via n8n)")
    print(f"  Shop: {SHOP}")
    print(f"  n8n:  {N8N_BASE_URL}")
    if args.dry_run:
        print(f"  Mode: DRY RUN (preview only)")
    if args.limit:
        print(f"  Limit: {args.limit} records")
    print(f"{'=' * 60}")

    results = {}

    if do_customers:
        c_total, c_success, c_failed = import_customers(
            limit=args.limit, dry_run=args.dry_run
        )
        results["customers"] = {"total": c_total, "success": c_success, "failed": c_failed}
        print(f"\n  Customers: {c_total} total, {c_success} synced, {c_failed} failed")

    if do_orders:
        o_total, o_success, o_failed = import_orders(
            limit=args.limit, dry_run=args.dry_run
        )
        results["orders"] = {"total": o_total, "success": o_success, "failed": o_failed}
        print(f"\n  Orders: {o_total} total, {o_success} synced, {o_failed} failed")

    print(f"\n{'=' * 60}")
    print(f"  BULK IMPORT {'(DRY RUN) ' if args.dry_run else ''}COMPLETE")
    for key, val in results.items():
        print(f"    {key}: {val['total']} processed")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
