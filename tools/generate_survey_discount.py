"""Generate a unique Shopify discount code for a customer who completed the loyalty survey.

Creates a unique one-time-use discount code under the loyalty PriceRule,
then writes it to the customer's metafield.

Usage:
    python tools/generate_survey_discount.py --customer-id 1234567890
    python tools/generate_survey_discount.py --customer-id 1234567890 --dry-run

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN, SHOPIFY_LOYALTY_PRICE_RULE_ID
"""

import os
import sys
import json
import argparse
import secrets
import string
import urllib.request
import urllib.error
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
PRICE_RULE_ID = os.getenv("SHOPIFY_LOYALTY_PRICE_RULE_ID")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

CODE_PREFIX = "ONZWELCOME"
CODE_LENGTH = 6


def shopify_request(method, path, data=None):
    url = f"{BASE}{path}" if path.startswith("/") else f"{BASE}/{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Shopify-Access-Token", TOKEN)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {method} {path} -> {e.code}: {error_body[:500]}")
        raise


def generate_code():
    """Generate a unique discount code like ONZWELCOME-A7K3X2."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(CODE_LENGTH))
    return f"{CODE_PREFIX}-{suffix}"


def create_discount_code(dry_run=False):
    """Create a unique discount code under the loyalty PriceRule."""
    code = generate_code()

    if dry_run:
        print(f"  [DRY RUN] Would create discount code: {code}")
        return code

    data = {
        "discount_code": {
            "code": code
        }
    }

    if not PRICE_RULE_ID:
        raise RuntimeError("SHOPIFY_LOYALTY_PRICE_RULE_ID not set in environment")
    result = shopify_request("POST", f"/price_rules/{PRICE_RULE_ID}/discount_codes.json", data)
    created = result.get("discount_code", {})
    actual_code = created.get("code", code)
    print(f"  [OK] Discount code created: {actual_code} (ID: {created.get('id')})")
    return actual_code


def save_code_to_customer(customer_id, code, dry_run=False):
    """Write the discount code to the customer's onzenna_loyalty.discount_code metafield."""
    if dry_run:
        print(f"  [DRY RUN] Would save code {code} to customer {customer_id}")
        return

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    update_data = {
        "customer": {
            "id": customer_id,
            "metafields": [
                {
                    "namespace": "onzenna_loyalty",
                    "key": "discount_code",
                    "value": code,
                    "type": "single_line_text_field",
                },
                {
                    "namespace": "onzenna_loyalty",
                    "key": "loyalty_completed_at",
                    "value": now,
                    "type": "date_time",
                },
            ]
        }
    }

    shopify_request("PUT", f"/customers/{customer_id}.json", update_data)
    print(f"  [OK] Metafields saved to customer {customer_id}")


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Generate loyalty survey discount code")
    parser.add_argument("--customer-id", type=int, required=True, help="Shopify customer ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    if not PRICE_RULE_ID:
        print("[ERROR] SHOPIFY_LOYALTY_PRICE_RULE_ID not set in .env")
        print("  Run: python tools/setup_loyalty_price_rule.py")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Generate Loyalty Discount Code")
    print(f"  Customer ID: {args.customer_id}")
    print(f"  PriceRule ID: {PRICE_RULE_ID}")
    print(f"{'=' * 60}\n")

    # Generate and create the code
    code = create_discount_code(dry_run=args.dry_run)

    # Save to customer metafields
    save_code_to_customer(args.customer_id, code, dry_run=args.dry_run)

    # Output for piping to n8n or other tools
    result = {
        "success": True,
        "customer_id": args.customer_id,
        "discount_code": code,
    }
    print(f"\n{json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
