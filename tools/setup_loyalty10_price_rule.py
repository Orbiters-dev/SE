"""Create Shopify Price Rule: Loyalty10 (10% off, combinable with other discounts).

Creates a REST price rule that allows individual unique LOYALTY10-XXXXXX codes
to be generated per customer. Each code will have usage_limit=1.

The price rule is set with combines_with so codes stack with other discounts.

Usage:
    python tools/setup_loyalty10_price_rule.py
    python tools/setup_loyalty10_price_rule.py --dry-run

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN
"""

import os
import sys
import json
import urllib.request
import urllib.error
import argparse
from env_loader import load_env

load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"
BASE_URL = f"https://{SHOP}/admin/api/{API_VERSION}"

RULE_TITLE = "Onzenna Loyalty Survey - 10% off (combinable)"


def shopify_request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Shopify-Access-Token", TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [ERROR] {e.code}: {error_body[:500]}")
        raise


def find_existing_rule():
    result = shopify_request("GET", "/price_rules.json?limit=250")
    for rule in result.get("price_rules", []):
        if rule.get("title") == RULE_TITLE:
            return rule
    return None


def create_price_rule(dry_run=False):
    payload = {
        "price_rule": {
            "title": RULE_TITLE,
            "value_type": "percentage",
            "value": "-10.0",
            "customer_selection": "all",
            "target_type": "line_item",
            "target_selection": "all",
            "allocation_method": "across",
            "once_per_customer": False,
            "usage_limit": None,
            "starts_at": "2026-01-01T00:00:00Z",
            "combines_with": {
                "order_discounts": True,
                "product_discounts": True,
                "shipping_discounts": True,
            },
        }
    }

    if dry_run:
        print("  [DRY RUN] Would create price rule:")
        print(f"    Title: {RULE_TITLE}")
        print("    Discount: 10% off all products")
        print("    Combines with: order + product + shipping discounts")
        print("    Usage limit per code: set at code creation (1 use)")
        return None

    result = shopify_request("POST", "/price_rules.json", payload)
    rule = result.get("price_rule", {})
    rule_id = rule.get("id")
    print(f"  [OK] Price rule created!")
    print(f"  [OK] ID: {rule_id}")
    print(f"  [OK] Title: {rule.get('title')}")
    print(f"  [OK] Combines with: {rule.get('combines_with')}")
    return rule_id


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Create Shopify Loyalty10 price rule")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup Shopify Price Rule: Loyalty10")
    print(f"  Shop: {SHOP}")
    print(f"{'=' * 60}\n")

    existing = find_existing_rule()
    if existing:
        rule_id = existing["id"]
        print(f"  [FOUND] Existing rule: {RULE_TITLE}")
        print(f"  [OK] ID: {rule_id}")
        print(f"  [OK] Combines with: {existing.get('combines_with')}")
    else:
        rule_id = create_price_rule(dry_run=args.dry_run)

    if rule_id:
        print(f"\n  Update setup_n8n_loyalty_survey.py:")
        print(f"    PRICE_RULE_ID = \"{rule_id}\"")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
