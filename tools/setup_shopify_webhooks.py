"""Register Shopify webhooks for customer/order sync to n8n.

Registers webhooks:
  - customers/create -> n8n customer sync
  - customers/update -> n8n customer sync
  - orders/create    -> n8n order sync
  - orders/updated   -> n8n order sync

Usage:
    python tools/setup_shopify_webhooks.py
    python tools/setup_shopify_webhooks.py --dry-run
    python tools/setup_shopify_webhooks.py --list
    python tools/setup_shopify_webhooks.py --clean   (remove existing pipeline webhooks)

Prerequisites:
    .wat_secrets: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN, N8N_BASE_URL
"""

import os
import sys
import json
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

WEBHOOKS_TO_REGISTER = [
    {
        "topic": "customers/create",
        "address": f"{N8N_BASE_URL}/webhook/shopify-customer-sync",
    },
    {
        "topic": "customers/update",
        "address": f"{N8N_BASE_URL}/webhook/shopify-customer-sync",
    },
    {
        "topic": "orders/create",
        "address": f"{N8N_BASE_URL}/webhook/shopify-order-sync",
    },
    {
        "topic": "orders/updated",
        "address": f"{N8N_BASE_URL}/webhook/shopify-order-sync",
    },
]

# Identify our webhooks by n8n URL prefix
OUR_PREFIX = f"{N8N_BASE_URL}/webhook/shopify-"


def shopify_request(method, path, data=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Shopify-Access-Token", TOKEN)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {e.code}: {error_body[:500]}")
        raise


def list_webhooks():
    """List all registered webhooks."""
    result = shopify_request("GET", "/webhooks.json")
    return result.get("webhooks", [])


def create_webhook(topic, address):
    """Register a new webhook."""
    payload = {
        "webhook": {
            "topic": topic,
            "address": address,
            "format": "json",
        }
    }
    return shopify_request("POST", "/webhooks.json", payload)


def delete_webhook(webhook_id):
    """Delete a webhook by ID."""
    shopify_request("DELETE", f"/webhooks/{webhook_id}.json")


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Register Shopify webhooks for n8n sync")
    parser.add_argument("--dry-run", action="store_true", help="Preview without registering")
    parser.add_argument("--list", action="store_true", help="List existing webhooks")
    parser.add_argument("--clean", action="store_true", help="Remove existing pipeline webhooks before registering")
    args = parser.parse_args()

    if not SHOP or not TOKEN:
        print("[ERROR] SHOPIFY_SHOP and SHOPIFY_ACCESS_TOKEN must be set in ~/.wat_secrets")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Shopify Webhooks Setup")
    print(f"  Shop: {SHOP}")
    print(f"  n8n:  {N8N_BASE_URL}")
    print(f"{'=' * 60}\n")

    # List existing
    existing = list_webhooks()
    our_webhooks = [w for w in existing if w.get("address", "").startswith(OUR_PREFIX)]

    if args.list:
        print(f"  All webhooks ({len(existing)} total):\n")
        for w in existing:
            marker = " [OURS]" if w.get("address", "").startswith(OUR_PREFIX) else ""
            print(f"    {w['id']:>12}  {w['topic']:<25} -> {w['address']}{marker}")
        print()
        return

    # Clean existing pipeline webhooks if requested
    if args.clean and our_webhooks:
        print(f"  Cleaning {len(our_webhooks)} existing pipeline webhooks...")
        for w in our_webhooks:
            if args.dry_run:
                print(f"    [DRY RUN] Would delete: {w['id']} ({w['topic']})")
            else:
                delete_webhook(w["id"])
                print(f"    [OK] Deleted: {w['id']} ({w['topic']})")
        our_webhooks = []

    # Build map of existing (topic -> address) for dedup
    existing_map = {(w["topic"], w["address"]) for w in existing}

    # Register
    registered = 0
    skipped = 0
    for wh in WEBHOOKS_TO_REGISTER:
        topic = wh["topic"]
        address = wh["address"]
        key = (topic, address)

        if key in existing_map:
            print(f"  [SKIP] {topic} -> already registered")
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [DRY RUN] Would register: {topic} -> {address}")
            registered += 1
            continue

        try:
            result = create_webhook(topic, address)
            wh_id = result.get("webhook", {}).get("id", "?")
            print(f"  [OK] {topic} -> {address} (ID: {wh_id})")
            registered += 1
        except Exception as e:
            print(f"  [FAIL] {topic}: {e}")

    print(f"\n  Summary: {registered} registered, {skipped} skipped")
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
