"""Fetch Shopify influencer orders (PR, supporter, sample) with fulfillment data.

Two-pass approach:
  1) Tag-based queries (fast): PR, supporter, supporters, sample, free sample
  2) Full order scan (comprehensive): checks ALL orders' notes for keywords

Saves to .tmp/polar_data/q10_influencer_orders.json
"""
import os, json, urllib.request, urllib.parse, time, re
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"
OUT = os.path.join(ROOT, ".tmp", "polar_data", "q10_influencer_orders.json")

# Tags to query from Shopify API (separate requests per tag)
QUERY_TAGS = ["PR", "supporter", "supporters", "sample", "free sample",
              "giveaway", "collab", "collaboration"]

# Keywords to match in individual tags (case-insensitive substring)
INFLUENCER_KEYWORDS = ("pr", "supporter", "sample", "influencer", "giveaway", "collab")

# Keywords to match in order notes
NOTE_KEYWORDS = ("pr", "sample", "supporter", "influencer", "giveaway", "collab")


def shopify_get(url):
    """GET with auth header, returns (data_dict, next_link_url or None)."""
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": TOKEN})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        link_header = resp.headers.get("Link", "")
        next_url = None
        if 'rel="next"' in link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    next_url = part.split("<")[1].split(">")[0]
        return data, next_url


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


def main():
    if not TOKEN:
        print("ERROR: SHOPIFY_ACCESS_TOKEN must be set in .env")
        return

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

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"orders": all_orders}, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {OUT}")


if __name__ == "__main__":
    main()
