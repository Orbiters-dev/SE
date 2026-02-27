"""Shopify customer lookup by name for influencer gifting.

Searches Shopify customers by name, returns profile + metafields + default address.
Used by n8n Execute Command to power the name-based "login" on the gifting page.

Usage:
    python influencer_customer_lookup.py --name "Jane Smith"
    python influencer_customer_lookup.py --name "Jane Smith" --json-input '{"full_name":"Jane Smith"}'

Output: JSON to stdout
    {"found": true, "customers": [{...}]}
    {"found": false, "customers": []}
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"


def shopify_request(method, path):
    """Make a Shopify REST API GET request."""
    url = f"{BASE}{path}" if path.startswith("/") else f"{BASE}/{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("X-Shopify-Access-Token", TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[API ERROR] {method} {path} -> {e.code}: {error_body[:300]}", file=sys.stderr)
        return None


def search_customers_by_name(full_name):
    """Search Shopify for customers matching the given name. Returns list of matches."""
    encoded = urllib.parse.quote(full_name)
    result = shopify_request(
        "GET",
        f"/customers/search.json?query={encoded}&fields=id,email,first_name,last_name,phone,tags,default_address&limit=10",
    )
    if not result:
        return []

    # Strict filter: exact name match (case-insensitive)
    target = full_name.strip().lower()
    matches = []
    for c in result.get("customers", []):
        cname = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip().lower()
        if cname == target:
            matches.append(c)

    return matches


def get_customer_metafields(customer_id):
    """Fetch influencer-namespace metafields for a customer."""
    result = shopify_request(
        "GET",
        f"/customers/{customer_id}/metafields.json?namespace=influencer",
    )
    if not result:
        return {}

    meta = {}
    for mf in result.get("metafields", []):
        meta[mf["key"]] = mf["value"]
    return meta


def build_customer_response(customer, metafields):
    """Build a clean response dict for a single customer."""
    addr = customer.get("default_address") or {}
    return {
        "id": customer["id"],
        "first_name": customer.get("first_name", ""),
        "last_name": customer.get("last_name", ""),
        "email": customer.get("email", ""),
        "phone": customer.get("phone", ""),
        "default_address": {
            "address1": addr.get("address1", ""),
            "address2": addr.get("address2", ""),
            "city": addr.get("city", ""),
            "province_code": addr.get("province_code", ""),
            "zip": addr.get("zip", ""),
            "country_code": addr.get("country_code", ""),
        },
        "metafields": {
            "instagram": metafields.get("instagram"),
            "tiktok": metafields.get("tiktok"),
            "child_1_birthday": metafields.get("child_1_birthday"),
            "child_2_birthday": metafields.get("child_2_birthday"),
            "submitted_at": metafields.get("submitted_at"),
        },
    }


def lookup(full_name):
    """Main lookup: search by name, fetch metafields, return JSON-ready dict."""
    customers = search_customers_by_name(full_name)

    if not customers:
        return {"found": False, "customers": []}

    results = []
    for c in customers:
        meta = get_customer_metafields(c["id"])
        results.append(build_customer_response(c, meta))

    return {"found": True, "customers": results}


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Lookup Shopify customer by name")
    parser.add_argument("--name", type=str, help="Full name to search")
    parser.add_argument("--json-input", type=str, dest="json_input",
                        help='JSON string with {"full_name": "..."}')
    args = parser.parse_args()

    if not TOKEN:
        print(json.dumps({"error": "SHOPIFY_ACCESS_TOKEN not set"}))
        sys.exit(1)

    # Get name from args
    name = None
    if args.name:
        name = args.name
    elif args.json_input:
        data = json.loads(args.json_input)
        name = data.get("full_name", "").strip()
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
        name = data.get("full_name", "").strip()

    if not name:
        print(json.dumps({"error": "No name provided. Use --name or --json-input"}))
        sys.exit(1)

    result = lookup(name)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
