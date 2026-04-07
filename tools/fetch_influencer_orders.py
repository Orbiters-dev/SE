"""Fetch Shopify influencer orders (PR, supporter, sample) with fulfillment data.

Two-pass approach:
  1) Tag-based queries (fast): PR, supporter, supporters, sample, free sample
  2) Full order scan (comprehensive): checks ALL orders' notes for keywords

Saves to .tmp/polar_data/q10_influencer_orders.json AND pushes to PostgreSQL gk_influencer_orders.
"""
import os, json, urllib.parse, time, re, sys
import requests as _requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_dotenv(os.path.join(ROOT, ".env"))

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"
OUT = os.path.join(ROOT, ".tmp", "polar_data", "q10_influencer_orders.json")

_SESSION = _requests.Session()
_SESSION.headers.update({"X-Shopify-Access-Token": TOKEN})

# Tags to query from Shopify API (separate requests per tag)
QUERY_TAGS = ["PR", "supporter", "supporters", "sample", "free sample",
              "giveaway", "collab", "collaboration"]

# Keywords to match in individual tags (case-insensitive substring)
INFLUENCER_KEYWORDS = ("pr", "supporter", "sample", "influencer", "giveaway", "collab")

# Keywords to match in order notes
NOTE_KEYWORDS = ("pr", "sample", "supporter", "influencer", "giveaway", "collab")


def shopify_get(url, retries=3):
    """GET with auth header + retry, returns (data_dict, next_link_url or None)."""
    for attempt in range(retries):
        try:
            resp = _SESSION.get(url, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            link_header = resp.headers.get("Link", "")
            next_url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split("<")[1].split(">")[0]
            return data, next_url
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"    [retry {attempt+1}/{retries}] {e} — waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def is_influencer_order(tags_str, note_str=""):
    """Check if order qualifies as influencer based on tags or note."""
    tag_list = [t.strip().lower() for t in tags_str.split(",")]
    # Tags: substring match is OK (tags are intentionally set)
    for tag in tag_list:
        for kw in INFLUENCER_KEYWORDS:
            if kw in tag:
                return True
    # Notes: word boundary match to avoid false positives (e.g. "product" matching "pr")
    note_lower = (note_str or "").lower()
    if note_lower:
        for kw in NOTE_KEYWORDS:
            if re.search(rf'\b{re.escape(kw)}\b', note_lower):
                return True
    return False


def parse_order(o):
    """Extract relevant fields from a Shopify order."""
    customer = o.get("customer", {}) or {}
    cust_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    cust_email = customer.get("email", "") or ""

    line_items = []
    for li in o.get("line_items", []):
        line_items.append({
            "title": li.get("title", ""),
            "variant_title": li.get("variant_title", ""),
            "sku": li.get("sku", ""),
            "quantity": li.get("quantity", 0),
            "price": li.get("price", "0"),
        })

    return {
        "id": o["id"],
        "name": o.get("name", ""),
        "created_at": o.get("created_at", ""),
        "tags": o.get("tags", ""),
        "note": o.get("note", "") or "",
        "financial_status": o.get("financial_status", ""),
        "fulfillment_status": o.get("fulfillment_status"),
        "total_price": o.get("total_price", "0"),
        "customer_name": cust_name,
        "customer_email": cust_email,
        "line_items": line_items,
    }


def fetch_by_tags():
    """Pass 1: Tag-based queries (fast)."""
    seen_ids = set()
    orders = []

    for tag_query in QUERY_TAGS:
        encoded_tag = urllib.parse.quote(tag_query)
        url = f"{BASE}/orders.json?status=any&tag={encoded_tag}&limit=250"
        tag_count = 0

        while url:
            data, next_url = shopify_get(url)
            for o in data.get("orders", []):
                oid = o["id"]
                if oid in seen_ids:
                    continue
                tags = o.get("tags", "")
                note = o.get("note", "") or ""
                if not is_influencer_order(tags, note):
                    continue
                seen_ids.add(oid)
                orders.append(parse_order(o))
                tag_count += 1

            url = next_url
            if url:
                time.sleep(0.5)

        if tag_count:
            print(f"    tag={tag_query}: {tag_count} new orders")

    return orders, seen_ids


def fetch_by_note_scan(seen_ids):
    """Pass 2: Full order scan — check notes for keywords."""
    orders = []
    total_scanned = 0
    note_found = 0
    url = f"{BASE}/orders.json?status=any&limit=250"

    while url:
        data, next_url = shopify_get(url)
        batch = data.get("orders", [])
        total_scanned += len(batch)

        for o in batch:
            oid = o["id"]
            if oid in seen_ids:
                continue
            tags = o.get("tags", "")
            note = o.get("note", "") or ""
            if not is_influencer_order(tags, note):
                continue
            seen_ids.add(oid)
            orders.append(parse_order(o))
            note_found += 1

        url = next_url
        if url:
            time.sleep(0.5)

    print(f"    Scanned {total_scanned} total orders, found {note_found} new influencer orders")
    return orders


def _detect_brand(line_items):
    """Detect brand from line item titles/SKUs."""
    for li in line_items:
        title = (li.get("title", "") or "").lower()
        sku = (li.get("sku", "") or "").lower()
        combined = title + " " + sku
        if any(k in combined for k in ("grosmimi", "ppsu", "straw cup", "tumbler")):
            return "Grosmimi"
        if any(k in combined for k in ("chaenmom", "cha&mom", "cha &")):
            return "CHA&MOM"
        if any(k in combined for k in ("naeiae", "나이아이")):
            return "Naeiae"
    return "Other"


def _extract_handle(note, tags):
    """Try to extract IG handle from note or tags."""
    # Check note for @handle pattern
    if note:
        m = re.search(r'@([a-zA-Z0-9_.]+)', note)
        if m:
            return m.group(0)
    # Check tags for handle-like patterns
    for tag in (tags or "").split(","):
        tag = tag.strip()
        if tag.startswith("@"):
            return tag
    return ""


def _get_shipping_date(o_raw):
    """Extract shipping date from fulfillment data if available."""
    # parse_order doesn't include fulfillments, so we look at created_at as fallback
    return o_raw.get("created_at", "")[:10] if o_raw.get("created_at") else None


def to_pg_rows(orders):
    """Transform parsed Shopify orders → gk_influencer_orders schema."""
    rows = []
    for o in orders:
        product_types = set()
        product_names = []
        for li in o.get("line_items", []):
            product_names.append(li.get("title", ""))
            title_lower = (li.get("title", "") or "").lower()
            if "straw cup" in title_lower:
                product_types.add("Straw Cup")
            elif "tumbler" in title_lower:
                product_types.add("Tumbler")
            elif "bottle" in title_lower:
                product_types.add("Baby Bottle")
            elif "accessory" in title_lower or "replacement" in title_lower:
                product_types.add("Accessory")

        rows.append({
            "order_id": str(o["id"]),
            "order_name": o.get("name", ""),
            "customer_name": o.get("customer_name", ""),
            "customer_email": o.get("customer_email", ""),
            "account_handle": _extract_handle(o.get("note", ""), o.get("tags", "")),
            "channel": "Shopify",
            "product_types": ", ".join(sorted(product_types)) if product_types else "",
            "product_names": " | ".join(product_names),
            "influencer_fee": float(o.get("total_price", 0)),
            "shipping_date": o.get("created_at", "")[:10] or None,
            "fulfillment_status": o.get("fulfillment_status") or "unfulfilled",
            "brand": _detect_brand(o.get("line_items", [])),
            "tags": o.get("tags", ""),
        })
    return rows


def push_to_pg(orders):
    """Push orders to PostgreSQL via push_content_to_pg."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from push_content_to_pg import push_influencer_orders
        pg_rows = to_pg_rows(orders)
        result = push_influencer_orders(pg_rows)
        print(f"  [PG] influencer_orders: +{result['created']} new, ~{result['updated']} updated")
        if result.get("errors"):
            print(f"  [PG WARN] {len(result['errors'])} errors")
        return result
    except Exception as e:
        print(f"  [PG ERROR] Failed to push influencer orders: {e}")
        return {"created": 0, "updated": 0, "errors": [str(e)]}


def main():
    if not TOKEN:
        print("ERROR: SHOPIFY_ACCESS_TOKEN must be set in .env")
        sys.exit(1)

    print(f"Fetching influencer orders from {SHOP}...")

    # Pass 1: tag-based
    print("  Pass 1: Tag-based queries...")
    tag_orders, seen_ids = fetch_by_tags()
    print(f"    → {len(tag_orders)} orders from tags")

    # Pass 2: full note scan
    print("  Pass 2: Full order scan (note keywords)...")
    note_orders = fetch_by_note_scan(seen_ids)
    print(f"    → {len(note_orders)} additional orders from notes")

    all_orders = tag_orders + note_orders
    print(f"  Total: {len(all_orders)} influencer orders")

    shipped = sum(1 for o in all_orders if o.get("fulfillment_status") in ("fulfilled", "shipped"))
    print(f"  Shipped/Fulfilled: {shipped}")

    # Date range
    dates = sorted(o["created_at"][:7] for o in all_orders if o.get("created_at"))
    if dates:
        print(f"  Date range: {dates[0]} to {dates[-1]}")

    # Save JSON (existing behavior)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"orders": all_orders}, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {OUT}")

    # Push to PostgreSQL (NEW)
    if all_orders:
        print("  Pushing to PostgreSQL...")
        push_to_pg(all_orders)
    else:
        print("  No orders to push to PG")


if __name__ == "__main__":
    main()
