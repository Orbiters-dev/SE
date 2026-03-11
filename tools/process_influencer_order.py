"""Process influencer gifting form submission -> Shopify customer + draft order.

Handles:
  - Customer lookup by email (deduplication)
  - Customer creation with proper name (not "Newsletter Subscriber")
  - Customer metafields: instagram, tiktok, child birthdays, submitted_at
  - Draft order with tags "pr, influencer-gifting" and free shipping

Usage:
    python process_influencer_order.py --input payload.json
    python process_influencer_order.py --json '{"form_type": ...}'
    cat payload.json | python process_influencer_order.py
    python process_influencer_order.py --dry-run --input payload.json

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN (write_customers + write_draft_orders scopes)
"""

import os
import sys
import json
import argparse
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from dotenv import load_dotenv

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_dotenv(os.path.join(ROOT, ".env"))

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"
TMP_DIR = os.path.join(ROOT, ".tmp", "process_influencer_order")

# Generic customer names that should be overwritten with form data
GENERIC_NAMES = {"newsletter subscriber", "subscriber", ""}

# Tags applied to every influencer gifting order
ORDER_TAGS = "pr, influencer-gifting"

# Metafield values to skip (form defaults for "no answer")
SKIP_VALUES = {"none", "nope", "n/a", "na", ""}


# ---------------------------------------------------------------------------
# Shopify API helper
# ---------------------------------------------------------------------------

def shopify_request(method, path, data=None):
    """Make a Shopify REST API request. Returns parsed JSON response."""
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


# ---------------------------------------------------------------------------
# Customer operations
# ---------------------------------------------------------------------------

def search_customer_by_email(email):
    """Search Shopify for an existing customer by email. Returns customer dict or None."""
    encoded = urllib.parse.quote(email)
    result = shopify_request(
        "GET",
        f"/customers/search.json?query=email:{encoded}&fields=id,email,first_name,last_name,phone,tags",
    )
    # Shopify search is fuzzy -- exact match required
    for c in result.get("customers", []):
        if (c.get("email") or "").lower() == email.lower():
            return c
    return None


def parse_full_name(full_name):
    """Split 'First Last' into (first_name, last_name)."""
    parts = full_name.strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def build_metafields(payload):
    """Build customer metafields array from form payload."""
    personal = payload.get("personal_info", {})
    baby = payload.get("baby_info", {})
    metafields = []

    # Instagram
    ig = (personal.get("instagram") or "").strip()
    if ig.lower() not in SKIP_VALUES:
        metafields.append({
            "namespace": "influencer",
            "key": "instagram",
            "value": ig,
            "type": "single_line_text_field",
        })

    # TikTok
    tt = (personal.get("tiktok") or "").strip()
    if tt.lower() not in SKIP_VALUES:
        metafields.append({
            "namespace": "influencer",
            "key": "tiktok",
            "value": tt,
            "type": "single_line_text_field",
        })

    # Child 1 birthday
    child1 = baby.get("child_1") if baby else None
    if child1 and child1.get("birthday"):
        metafields.append({
            "namespace": "influencer",
            "key": "child_1_birthday",
            "value": child1["birthday"],
            "type": "date",
        })

    # Child 2 birthday
    child2 = baby.get("child_2") if baby else None
    if child2 and child2.get("birthday"):
        metafields.append({
            "namespace": "influencer",
            "key": "child_2_birthday",
            "value": child2["birthday"],
            "type": "date",
        })

    # Submitted at
    submitted = payload.get("submitted_at")
    if submitted:
        metafields.append({
            "namespace": "influencer",
            "key": "submitted_at",
            "value": submitted,
            "type": "date_time",
        })

    return metafields


def ensure_customer(payload, dry_run=False):
    """Find or create a Shopify customer. Returns (customer_id, action_taken)."""
    personal = payload.get("personal_info", {})
    email = personal.get("email", "").strip()
    full_name = personal.get("full_name", "").strip()
    phone = personal.get("phone", "").strip()
    first_name, last_name = parse_full_name(full_name)

    if not email:
        raise ValueError("Email is required but missing from payload")

    metafields = build_metafields(payload)

    # Step 1: Search for existing customer
    print(f"  Searching for customer: {email}")
    existing = search_customer_by_email(email)

    if existing:
        customer_id = existing["id"]
        existing_name = f"{existing.get('first_name', '')} {existing.get('last_name', '')}".strip()
        print(f"  Found existing customer: ID={customer_id}, name='{existing_name}'")

        # Build update payload
        update_data = {"customer": {"id": customer_id}}

        # Always upsert metafields
        if metafields:
            update_data["customer"]["metafields"] = metafields

        # Update name only if current name is generic or empty
        if existing_name.lower() in GENERIC_NAMES:
            print(f"  Updating generic name '{existing_name}' -> '{full_name}'")
            update_data["customer"]["first_name"] = first_name
            update_data["customer"]["last_name"] = last_name

        # Update phone if missing
        if not existing.get("phone") and phone:
            update_data["customer"]["phone"] = phone

        # Merge tags (add pr + influencer-gifting if not present)
        existing_tags = existing.get("tags", "") or ""
        tag_set = {t.strip().lower() for t in existing_tags.split(",") if t.strip()}
        new_tags = {"pr", "influencer-gifting"}
        if not new_tags.issubset(tag_set):
            merged = existing_tags
            for tag in sorted(new_tags):
                if tag not in tag_set:
                    merged = f"{merged}, {tag}" if merged else tag
            update_data["customer"]["tags"] = merged

        if dry_run:
            print(f"  [DRY RUN] Would update customer {customer_id}")
            print(f"    Update payload: {json.dumps(update_data, indent=2)}")
            return customer_id, "update_skipped"

        shopify_request("PUT", f"/customers/{customer_id}.json", update_data)
        time.sleep(0.5)
        print(f"  Customer updated: {customer_id}")
        return customer_id, "updated"

    else:
        # Step 2: Create new customer
        print(f"  No existing customer found. Creating new...")

        create_data = {
            "customer": {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone if phone else None,
                "tags": ORDER_TAGS,
                "verified_email": True,
                "send_email_invite": False,
            }
        }
        if metafields:
            create_data["customer"]["metafields"] = metafields

        if dry_run:
            print(f"  [DRY RUN] Would create customer: {full_name} <{email}>")
            print(f"    Create payload: {json.dumps(create_data, indent=2)}")
            return None, "create_skipped"

        result = shopify_request("POST", "/customers.json", create_data)
        customer_id = result["customer"]["id"]
        time.sleep(0.5)
        print(f"  Customer created: {customer_id} ({full_name})")
        return customer_id, "created"


# ---------------------------------------------------------------------------
# Draft order operations
# ---------------------------------------------------------------------------

def build_draft_order(payload, customer_id):
    """Build the Shopify draft order payload from form data."""
    personal = payload.get("personal_info", {})
    shipping = payload.get("shipping_address", {})
    products = payload.get("selected_products", [])
    full_name = personal.get("full_name", "").strip()
    first_name, last_name = parse_full_name(full_name)

    # Line items
    line_items = []
    for p in products:
        variant_id = p.get("variant_id")
        if variant_id:
            line_items.append({"variant_id": int(variant_id), "quantity": 1})
        else:
            line_items.append({
                "title": p.get("title", "Unknown Product"),
                "quantity": 1,
                "price": str(p.get("price", "0")).replace("$", ""),
            })

    if not line_items:
        raise ValueError("No products selected in payload")

    # Note (human-readable summary, canonical data lives in metafields)
    note_lines = [
        "Influencer Gifting Application",
        "---",
        f"Instagram: {personal.get('instagram', 'N/A')}",
        f"TikTok: {personal.get('tiktok', 'N/A')}",
    ]
    baby = payload.get("baby_info", {})
    if baby and baby.get("child_1"):
        bday = baby["child_1"].get("birthday", "N/A")
        age = baby["child_1"].get("age_months", "?")
        note_lines.append(f"Child 1: {bday} ({age} months)")
    if baby and baby.get("child_2"):
        bday = baby["child_2"].get("birthday", "N/A")
        age = baby["child_2"].get("age_months", "?")
        note_lines.append(f"Child 2: {bday} ({age} months)")
    note_lines.append(f"Submitted: {payload.get('submitted_at', 'N/A')}")

    # Shipping address
    shipping_address = {
        "first_name": first_name,
        "last_name": last_name,
        "address1": shipping.get("street", ""),
        "address2": shipping.get("apt", ""),
        "city": shipping.get("city", ""),
        "province": shipping.get("state", ""),
        "zip": shipping.get("zip", ""),
        "country": shipping.get("country", "US"),
        "phone": personal.get("phone", ""),
    }

    return {
        "draft_order": {
            "line_items": line_items,
            "customer": {"id": customer_id},
            "shipping_address": shipping_address,
            "billing_address": shipping_address,
            "tags": ORDER_TAGS,
            "note": "\n".join(note_lines),
            "shipping_line": {
                "title": "Influencer Gifting - Free Shipping",
                "price": "0.00",
            },
            "use_customer_default_address": False,
        }
    }


def create_draft_order(payload, customer_id, dry_run=False):
    """Create a Shopify draft order. Returns draft order data dict."""
    order_data = build_draft_order(payload, customer_id)

    if dry_run:
        items = order_data["draft_order"]["line_items"]
        print(f"  [DRY RUN] Would create draft order with {len(items)} item(s)")
        print(f"    Tags: {order_data['draft_order']['tags']}")
        return {"id": "DRY_RUN", "name": "DRY_RUN"}

    result = shopify_request("POST", "/draft_orders.json", order_data)
    draft = result.get("draft_order", {})
    print(f"  Draft order created: {draft.get('name', '?')} (ID: {draft.get('id', '?')})")
    return draft


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_payload(payload):
    """Validate the incoming form payload. Returns list of error strings."""
    errors = []

    if payload.get("form_type") != "influencer_gifting":
        errors.append(f"Unexpected form_type: {payload.get('form_type')}")

    personal = payload.get("personal_info", {})
    if not personal.get("email"):
        errors.append("Missing personal_info.email")
    if not personal.get("full_name"):
        errors.append("Missing personal_info.full_name")

    products = payload.get("selected_products", [])
    if not products:
        errors.append("No selected_products")
    for i, p in enumerate(products):
        if not p.get("variant_id") and not p.get("title"):
            errors.append(f"Product {i}: missing both variant_id and title")

    shipping = payload.get("shipping_address", {})
    for field in ("street", "city", "state", "zip"):
        if not shipping.get(field):
            errors.append(f"Missing shipping_address.{field}")

    if not payload.get("terms_accepted"):
        errors.append("terms_accepted is not True")

    return errors


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def process(payload, dry_run=False):
    """Process a single influencer gifting form submission. Returns result dict."""
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{'=' * 60}")
    print(f"  {prefix}Processing Influencer Gifting Order")
    print(f"{'=' * 60}")

    # Validate
    errors = validate_payload(payload)
    if errors:
        print(f"\n  VALIDATION ERRORS:")
        for e in errors:
            print(f"    - {e}")
        return {"success": False, "errors": errors}

    personal = payload["personal_info"]
    print(f"  Name:     {personal['full_name']}")
    print(f"  Email:    {personal['email']}")
    print(f"  Products: {len(payload['selected_products'])}")

    # Step 1: Customer
    print(f"\n  [Step 1/2] Customer")
    customer_id, customer_action = ensure_customer(payload, dry_run=dry_run)

    # Step 2: Draft Order
    print(f"\n  [Step 2/2] Draft Order")
    if dry_run and customer_id is None:
        # Use a placeholder for dry-run when customer would be created
        customer_id = 0
    draft = create_draft_order(payload, customer_id, dry_run=dry_run)

    result = {
        "success": True,
        "customer_id": customer_id,
        "customer_action": customer_action,
        "draft_order_id": draft.get("id"),
        "draft_order_name": draft.get("name"),
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }

    # Save result to tmp
    os.makedirs(TMP_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(TMP_DIR, f"order_result_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Result saved: {out_path}")

    print(f"\n{'=' * 60}")
    print(f"  {prefix}DONE")
    print(f"  Customer: {customer_id} ({customer_action})")
    print(f"  Draft Order: {draft.get('name', 'N/A')}")
    print(f"{'=' * 60}\n")

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(
        description="Process influencer gifting form -> Shopify customer + draft order"
    )
    parser.add_argument("--input", type=str, help="Path to JSON payload file")
    parser.add_argument("--json", type=str, dest="json_str", help="JSON payload as string")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without API calls")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set in .env")
        print("  Run: python tools/shopify_oauth.py  (with write_customers scope)")
        sys.exit(1)

    # Read payload
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif args.json_str:
        payload = json.loads(args.json_str)
    elif not sys.stdin.isatty():
        payload = json.load(sys.stdin)
    else:
        parser.print_help()
        print("\nError: Provide payload via --input, --json, or stdin")
        sys.exit(1)

    result = process(payload, dry_run=args.dry_run)

    if not result.get("success"):
        sys.exit(1)

    # Final JSON output for n8n piping
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
