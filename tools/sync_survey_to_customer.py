"""Sync Onzenna survey data from order metafields to customer metafields.

When a customer completes checkout, the Checkout UI Extension writes survey
answers as order metafields. This tool copies those metafields to the customer
record so they persist across orders.

Usage:
    python tools/sync_survey_to_customer.py --order-id 1234567890
    python tools/sync_survey_to_customer.py --order-id 1234567890 --dry-run
    echo '{"order_id": 123, "customer_id": 456, "survey_data": {...}}' | python tools/sync_survey_to_customer.py --from-webhook

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN (read_orders, write_customers)
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

# Namespaces to sync from order to customer
SURVEY_NAMESPACES = ["onzenna_survey", "onzenna_creator"]

# Form type -> metafield namespace mapping
FORM_TYPE_NAMESPACE = {
    "onzenna_core_signup": "onzenna_survey",
    "onzenna_creator_signup": "onzenna_creator",
}

# Fields in survey_data that map to metafields (with type overrides)
FIELD_TYPES = {
    # Core signup
    "journey_stage": "single_line_text_field",
    "baby_birth_month": "single_line_text_field",
    "has_other_children": "boolean",
    "other_child_birth": "single_line_text_field",
    "third_child_birth": "single_line_text_field",
    # Creator signup
    "primary_platform": "single_line_text_field",
    "primary_handle": "single_line_text_field",
    "other_platforms": "json",
    "other_handles": "json",
    "following_size": "single_line_text_field",
    "hashtags": "single_line_text_field",
    "content_type": "json",
    "content_type_other": "single_line_text_field",
    "has_brand_partnerships": "single_line_text_field",
    "brand_names": "single_line_text_field",
}


def shopify_request(method, path, data=None):
    url = f"{BASE}{path}" if path.startswith("/") else f"{BASE}/{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Shopify-Access-Token", TOKEN)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp_body = r.read()
            return json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {method} {path} -> {e.code}: {error_body[:500]}")
        raise


def get_order_metafields(order_id):
    """Fetch metafields for an order, filtered to survey namespaces."""
    result = shopify_request("GET", f"/orders/{order_id}/metafields.json")
    all_mf = result.get("metafields", [])
    survey_mf = [m for m in all_mf if m.get("namespace") in SURVEY_NAMESPACES]
    return survey_mf


def get_order(order_id):
    """Fetch order to get customer_id."""
    result = shopify_request("GET", f"/orders/{order_id}.json?fields=id,customer")
    return result.get("order", {})


def sync_metafields_to_customer(customer_id, metafields, dry_run=False):
    """Write order metafields to the customer record."""
    if not metafields:
        print("  No survey metafields found on order")
        return False

    # Convert order metafields to customer metafield format
    customer_mf = []
    for mf in metafields:
        customer_mf.append({
            "namespace": mf["namespace"],
            "key": mf["key"],
            "value": mf["value"],
            "type": mf["type"],
        })

    if dry_run:
        print(f"  [DRY RUN] Would sync {len(customer_mf)} metafields to customer {customer_id}:")
        for mf in customer_mf:
            print(f"    {mf['namespace']}.{mf['key']} = {mf['value'][:50]}")
        return True

    update_data = {
        "customer": {
            "id": customer_id,
            "metafields": customer_mf,
        }
    }

    shopify_request("PUT", f"/customers/{customer_id}.json", update_data)
    print(f"  [OK] Synced {len(customer_mf)} metafields to customer {customer_id}")
    return True


def process_from_order_id(order_id, dry_run=False):
    """Full flow: order ID -> fetch metafields -> sync to customer."""
    print(f"  Fetching order {order_id}...")
    order = get_order(order_id)
    customer = order.get("customer")

    if not customer:
        print(f"  [WARN] Order {order_id} has no customer (guest checkout)")
        return {"success": False, "reason": "guest_checkout"}

    customer_id = customer["id"]
    print(f"  Customer ID: {customer_id}")

    print(f"  Fetching order metafields...")
    metafields = get_order_metafields(order_id)
    print(f"  Found {len(metafields)} survey metafields")

    ok = sync_metafields_to_customer(customer_id, metafields, dry_run=dry_run)

    return {
        "success": ok,
        "order_id": order_id,
        "customer_id": customer_id,
        "metafields_synced": len(metafields),
    }


def process_from_webhook(payload, dry_run=False):
    """Process webhook payload with pre-extracted survey data."""
    customer_id = payload.get("customer_id")
    order_id = payload.get("order_id")
    survey_data = payload.get("survey_data", {})

    if not customer_id:
        print("  [ERROR] No customer_id in webhook payload")
        return {"success": False, "reason": "no_customer_id"}

    # Build metafields from survey_data
    metafields = []
    for namespace, fields in survey_data.items():
        if namespace not in SURVEY_NAMESPACES:
            continue
        for key, value in fields.items():
            mf_type = "single_line_text_field"
            if isinstance(value, bool):
                mf_type = "boolean"
                value = str(value).lower()
            elif isinstance(value, (list, dict)):
                mf_type = "json"
                value = json.dumps(value)
            elif key.endswith("_at"):
                mf_type = "date_time"

            metafields.append({
                "namespace": namespace,
                "key": key,
                "value": str(value),
                "type": mf_type,
            })

    ok = sync_metafields_to_customer(customer_id, metafields, dry_run=dry_run)

    return {
        "success": ok,
        "order_id": order_id,
        "customer_id": customer_id,
        "metafields_synced": len(metafields),
    }


def process_from_form_payload(payload, dry_run=False):
    """Process form submission payload and save survey_data as customer metafields.

    Accepts payloads in the format sent by core-signup and creator-signup pages:
    {
        "form_type": "onzenna_core_signup" | "onzenna_creator_signup",
        "customer_id": 123,
        "customer_email": "...",
        "submitted_at": "...",
        "survey_data": { "field": "value", ... }
    }
    """
    customer_id = payload.get("customer_id")
    form_type = payload.get("form_type", "")
    survey_data = payload.get("survey_data", {})
    submitted_at = payload.get("submitted_at", datetime.now(timezone.utc).isoformat())

    if not customer_id:
        print("  [WARN] No customer_id in form payload (guest user)")
        return {"success": False, "reason": "no_customer_id"}

    namespace = FORM_TYPE_NAMESPACE.get(form_type)
    if not namespace:
        print(f"  [ERROR] Unknown form_type: {form_type}")
        return {"success": False, "reason": "unknown_form_type"}

    metafields = []
    for key, value in survey_data.items():
        if value is None or value == "" or value == []:
            continue

        mf_type = FIELD_TYPES.get(key, "single_line_text_field")

        if isinstance(value, bool):
            mf_type = "boolean"
            value = str(value).lower()
        elif isinstance(value, (list, dict)):
            mf_type = "json"
            value = json.dumps(value)
        else:
            value = str(value)

        metafields.append({
            "namespace": namespace,
            "key": key,
            "value": value,
            "type": mf_type,
        })

    # Add completed_at timestamp
    completed_key = "signup_completed_at" if namespace == "onzenna_survey" else "creator_completed_at"
    metafields.append({
        "namespace": namespace,
        "key": completed_key,
        "value": submitted_at,
        "type": "date_time",
    })

    print(f"  Form type: {form_type} -> namespace: {namespace}")
    print(f"  Customer: {customer_id}")
    print(f"  Metafields to save: {len(metafields)}")

    ok = sync_metafields_to_customer(customer_id, metafields, dry_run=dry_run)

    return {
        "success": ok,
        "customer_id": customer_id,
        "form_type": form_type,
        "metafields_synced": len(metafields),
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Sync order survey metafields to customer")
    parser.add_argument("--order-id", type=int, help="Shopify order ID to sync")
    parser.add_argument("--from-webhook", action="store_true", help="Read webhook payload from stdin (namespace-keyed)")
    parser.add_argument("--from-form", action="store_true", help="Read form submission payload from stdin")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Onzenna Survey Sync: Customer Metafields")
    print(f"{'=' * 60}\n")

    if args.from_form:
        if sys.stdin.isatty():
            print("[ERROR] --from-form expects JSON on stdin")
            sys.exit(1)
        payload = json.load(sys.stdin)
        result = process_from_form_payload(payload, dry_run=args.dry_run)
    elif args.from_webhook:
        if sys.stdin.isatty():
            print("[ERROR] --from-webhook expects JSON on stdin")
            sys.exit(1)
        payload = json.load(sys.stdin)
        result = process_from_webhook(payload, dry_run=args.dry_run)
    elif args.order_id:
        result = process_from_order_id(args.order_id, dry_run=args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)

    print(f"\n{json.dumps(result, ensure_ascii=False)}")

    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
