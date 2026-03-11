"""Create the Shopify discount for Onzenna Loyalty Survey rewards.

Uses GraphQL Admin API (discountCodeBasicCreate) instead of REST PriceRules.
Creates a basic discount code that serves as the "template" for loyalty rewards.
Individual unique codes are generated per customer by generate_survey_discount.py.

Usage:
    python tools/setup_loyalty_price_rule.py
    python tools/setup_loyalty_price_rule.py --dry-run
    python tools/setup_loyalty_price_rule.py --percent 15  # 15% off instead of default 10%

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN (write_discounts scope)
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from env_loader import load_env

load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
GRAPHQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
SECRETS_PATH = os.path.expanduser("~/.wat_secrets")


def graphql_request(query, variables=None):
    """Execute a Shopify Admin GraphQL request."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(GRAPHQL_URL, data=body, method="POST")
    req.add_header("X-Shopify-Access-Token", TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [GraphQL ERROR] {e.code}: {error_body[:500]}")
        raise


def create_discount(percent, dry_run=False):
    """Create a basic discount code via GraphQL."""
    code = "ONZLOYALTY-MASTER"
    title = f"Onzenna Loyalty Survey Reward ({percent}% off)"

    mutation = """
    mutation discountCodeBasicCreate($basicCodeDiscount: DiscountCodeBasicInput!) {
        discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
            codeDiscountNode {
                id
                codeDiscount {
                    ... on DiscountCodeBasic {
                        title
                        codes(first: 1) {
                            nodes {
                                code
                            }
                        }
                    }
                }
            }
            userErrors {
                field
                message
            }
        }
    }
    """

    variables = {
        "basicCodeDiscount": {
            "title": title,
            "code": code,
            "startsAt": "2026-01-01T00:00:00Z",
            "customerGets": {
                "value": {
                    "percentage": percent / 100.0
                },
                "items": {
                    "all": True
                }
            },
            "customerSelection": {
                "all": True
            },
            "usageLimit": None,
            "appliesOncePerCustomer": True,
        }
    }

    if dry_run:
        print(f"  [DRY RUN] Would create discount:")
        print(f"    Title: {title}")
        print(f"    Code: {code}")
        print(f"    Discount: {percent}%")
        return None

    result = graphql_request(mutation, variables)

    # Check for top-level GraphQL errors
    if result.get("errors"):
        for err in result["errors"]:
            print(f"  [GraphQL ERROR] {err.get('message', err)}")
        return None

    data = result.get("data", {}).get("discountCodeBasicCreate")
    if data is None:
        print(f"  [ERROR] Unexpected response: {json.dumps(result)[:500]}")
        return None

    errors = data.get("userErrors", [])

    if errors:
        for err in errors:
            msg = err.get("message", "")
            print(f"  [ERROR] {msg}")
        return None

    node = data.get("codeDiscountNode", {})
    discount_id = node.get("id", "")
    print(f"  [OK] Discount created!")
    print(f"  [OK] ID: {discount_id}")
    print(f"  [OK] Title: {title}")
    print(f"  [OK] Code: {code}")
    print(f"  [OK] Discount: {percent}% off")
    return discount_id


def save_discount_id(discount_id):
    """Save the discount ID to the secrets file."""
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        if "SHOPIFY_LOYALTY_DISCOUNT_ID" not in content:
            with open(SECRETS_PATH, "a", encoding="utf-8") as f:
                f.write(f"\nSHOPIFY_LOYALTY_DISCOUNT_ID={discount_id}\n")
            print(f"  [OK] Auto-saved SHOPIFY_LOYALTY_DISCOUNT_ID to {SECRETS_PATH}")
        else:
            print(f"  [WARN] SHOPIFY_LOYALTY_DISCOUNT_ID already in secrets, update manually")
    except Exception as e:
        print(f"  [WARN] Could not update secrets: {e}")
        print(f"  Add manually: SHOPIFY_LOYALTY_DISCOUNT_ID={discount_id}")


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Create Shopify discount for loyalty survey")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    parser.add_argument("--percent", type=int, default=10, help="Discount percentage (default: 10)")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Onzenna Loyalty Discount Setup (GraphQL)")
    print(f"  Shop: {SHOP}")
    print(f"  Discount: {args.percent}% off")
    print(f"{'=' * 60}\n")

    discount_id = create_discount(args.percent, dry_run=args.dry_run)

    if discount_id:
        save_discount_id(discount_id)

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
