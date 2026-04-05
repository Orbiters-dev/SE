"""Amazon Product Search Ranking Collector.

Searches Amazon for generic keywords and finds where our products
(Grosmimi, Naeiae, CHA&MOM) appear in the search results.

Uses Apify junglee/amazon-crawler to scrape actual Amazon search result pages.

Usage:
    python tools/collect_search_ranking.py                  # Collect all keywords
    python tools/collect_search_ranking.py --keyword "sippy cup"  # Single keyword
    python tools/collect_search_ranking.py --dry-run         # Show what would be collected
    python tools/collect_search_ranking.py --skip-pg          # Local cache only
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env
load_env()

import requests

# ── Config ──────────────────────────────────────────────────────────────

CACHE_DIR = os.path.join(DIR, "..", ".tmp", "datakeeper")
os.makedirs(CACHE_DIR, exist_ok=True)

APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
APIFY_BASE = "https://api.apify.com/v2"

# Orbitools API for PG push
ORBITOOLS_BASE = os.environ.get("ORBITOOLS_BASE", "https://orbitools.orbiters.co.kr/api/datakeeper")
ORBITOOLS_USER = os.environ.get("ORBITOOLS_USER", "")
ORBITOOLS_PASS = os.environ.get("ORBITOOLS_PASS", "")

# Our product ASINs per brand (top sellers to track)
OUR_ASINS = {
    "Grosmimi": {
        "B07RRT71CZ", "B082KZFGZG", "B082KZY3CX", "B083921731",
        "B09DD28LSF", "B09DD2CXTL", "B0DB7SPP2P", "B0DCV766MB",
        "B0F4CRT6LV", "B0F1XGS9JF", "B0FXKBPXTB",
    },
    "Naeiae": {
        "B0BMJCWYB6", "B0BMJCPP71", "B0BMJCPK4P", "B0BMJDXH6C",
        "B0BMJCFYC1", "B0D7B6C17S", "B0D7B7QBJY",
    },
    "CHA&MOM": set(),  # Will be populated from sales data
}

# All our ASINs as a flat set for quick lookup
ALL_OUR_ASINS = set()
for _brand, _asins in OUR_ASINS.items():
    ALL_OUR_ASINS.update(_asins)

# ASIN → brand reverse mapping
ASIN_TO_BRAND = {}
for _brand, _asins in OUR_ASINS.items():
    for _asin in _asins:
        ASIN_TO_BRAND[_asin] = _brand

# Keywords to search, grouped by brand
SEARCH_KEYWORDS = {
    "Grosmimi": [
        "sippy cup", "toddler cup", "straw cup", "baby straw cup",
        "toddler straw cup", "training cup", "ppsu bottle",
        "weighted straw cup", "transition cup",
    ],
    "Naeiae": [
        "baby snack", "baby rice puff", "baby puffs", "toddler snack",
        "baby rice cracker", "baby teething wafer", "organic baby snack",
        "korean baby food",
    ],
    "CHA&MOM": [
        "baby wipes", "baby lotion", "baby wash", "baby cream",
    ],
}

# How many results to scan per keyword (4 pages × ~24 = ~96 products)
MAX_ITEMS_PER_KEYWORD = 96


def _load_asins_from_cache():
    """Load additional ASINs from local sales cache."""
    cache_path = os.path.join(CACHE_DIR, "amazon_sales_sku_daily.json")
    if not os.path.exists(cache_path):
        return

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            asin = r.get("asin")
            brand = r.get("brand")
            if asin and brand and brand in OUR_ASINS:
                OUR_ASINS[brand].add(asin)
                ALL_OUR_ASINS.add(asin)
                ASIN_TO_BRAND[asin] = brand
        print(f"  Loaded ASINs from cache: {len(ALL_OUR_ASINS)} total")
    except Exception as e:
        print(f"  Warning: Could not load ASINs from cache: {e}")


def search_amazon_apify(keyword: str, max_items: int = MAX_ITEMS_PER_KEYWORD) -> list:
    """Search Amazon via Apify and return product results with positions.

    Returns list of dicts: [{asin, title, price, rating, reviews, position}, ...]
    Position is 1-indexed (first result = 1).
    """
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN not set")

    search_url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}"

    # Run the free actor synchronously
    run_url = f"{APIFY_BASE}/acts/junglee~free-amazon-product-scraper/run-sync-get-dataset-items"
    payload = {
        "categoryUrls": [{"url": search_url}],
        "maxItems": max_items,
    }

    print(f"    Searching: '{keyword}' (max {max_items} items)...", flush=True)

    resp = requests.post(
        run_url,
        json=payload,
        params={"token": APIFY_TOKEN},
        timeout=300,  # 5 min max
    )

    if resp.status_code != 200 and resp.status_code != 201:
        print(f"    Apify error {resp.status_code}: {resp.text[:200]}")
        return []

    items = resp.json()
    if not isinstance(items, list):
        print(f"    Unexpected response format: {type(items)}")
        return []

    results = []
    for i, item in enumerate(items):
        asin = item.get("asin", "")
        results.append({
            "asin": asin,
            "title": item.get("title", ""),
            "brand_name": item.get("brand", ""),  # brand from Amazon listing
            "price": _parse_price(item.get("price", "")),
            "rating": item.get("stars", 0) or 0,
            "reviews": item.get("reviewsCount", 0) or 0,
            "position": i + 1,  # 1-indexed
            "is_sponsored": item.get("sponsored", False),
        })

    print(f"    Got {len(results)} products", flush=True)
    return results


def _parse_price(price_str) -> float:
    """Parse price from various formats: '$19.99', '19.99', {'value': 19.99}."""
    if isinstance(price_str, (int, float)):
        return float(price_str)
    if isinstance(price_str, dict):
        return float(price_str.get("value", 0) or 0)
    if isinstance(price_str, str):
        cleaned = price_str.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


# Brand name patterns to match in Amazon listing brand/title fields
BRAND_PATTERNS = {
    "Grosmimi": ["grosmimi", "gros mini"],
    "Naeiae": ["naeiae", "naiae"],
    "CHA&MOM": ["cha&mom", "cha and mom", "chaenmam", "cha & mom"],
}


def find_our_products(search_results: list, brand: str) -> dict:
    """Find our brand's products in search results.

    Matches by: 1) known ASIN, 2) brand name in listing, 3) brand name in title.
    Returns first match: {position, asin, title, price, rating, reviews} or None.
    """
    brand_asins = OUR_ASINS.get(brand, set())
    patterns = BRAND_PATTERNS.get(brand, [brand.lower()])

    # Pass 1: exact ASIN match
    for item in search_results:
        if item["asin"] in brand_asins:
            return item

    # Pass 2: brand name match in listing brand field or title
    for item in search_results:
        listing_brand = (item.get("brand_name") or "").lower()
        listing_title = (item.get("title") or "").lower()
        for pat in patterns:
            if pat in listing_brand or pat in listing_title:
                return item

    return None


def collect_search_rankings(keywords_filter=None, dry_run=False):
    """Collect search rankings for all configured keywords.

    Returns list of row dicts ready for PG push.
    """
    _load_asins_from_cache()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_rows = []

    for brand, keywords in SEARCH_KEYWORDS.items():
        print(f"\n[{brand}]")

        for keyword in keywords:
            if keywords_filter and keyword not in keywords_filter:
                continue

            if dry_run:
                print(f"  [DRY RUN] Would search: '{keyword}' for {brand}")
                continue

            try:
                results = search_amazon_apify(keyword)

                # Find our product position
                match = find_our_products(results, brand)

                row = {
                    "date": today,
                    "brand": brand,
                    "keyword": keyword,
                    "market": "US",
                    "position": match["position"] if match else -1,
                    "asin": match["asin"] if match else "",
                    "title": (match["title"] or "")[:500] if match else "",
                    "price": match["price"] if match else 0,
                    "rating": match["rating"] if match else 0,
                    "reviews": match["reviews"] if match else 0,
                    "total_results": len(results),
                }
                all_rows.append(row)

                pos_str = f"#{match['position']}" if match else "NOT FOUND (top 48)"
                print(f"  '{keyword}' → {brand}: {pos_str}", flush=True)

                # Save cache incrementally so data is available during collection
                _save_cache(all_rows)

                # Rate limiting — be gentle with Apify
                time.sleep(2)

            except Exception as e:
                print(f"  ERROR '{keyword}': {e}")
                all_rows.append({
                    "date": today,
                    "brand": brand,
                    "keyword": keyword,
                    "market": "US",
                    "position": -1,
                    "asin": "",
                    "title": "",
                    "price": 0,
                    "rating": 0,
                    "reviews": 0,
                    "total_results": 0,
                })

    return all_rows


def _save_cache(rows):
    """Save to local JSON cache."""
    cache_path = os.path.join(CACHE_DIR, "amazon_search_ranking.json")

    # Load existing and merge (keep last 90 days)
    existing = []
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    existing = [r for r in existing if r.get("date", "") >= cutoff]

    # Remove today's data for the same keywords (upsert)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_keys = {(r["brand"], r["keyword"], r["market"]) for r in rows}
    existing = [
        r for r in existing
        if r.get("date") != today or (r.get("brand"), r.get("keyword"), r.get("market")) not in new_keys
    ]

    merged = existing + rows
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, default=str, ensure_ascii=False, indent=1)

    print(f"\n[Cache] Saved {len(rows)} new rows, {len(merged)} total")


def _push_to_pg(rows):
    """Push rows to PG via orbitools API."""
    if not ORBITOOLS_USER or not ORBITOOLS_PASS:
        print("[PG] No credentials, skipping")
        return

    batch_size = 200
    total_created = 0
    total_updated = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            resp = requests.post(
                f"{ORBITOOLS_BASE}/save/",
                json={"table": "amazon_search_ranking", "rows": batch},
                auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            total_created += data.get("created", 0)
            total_updated += data.get("updated", 0)
        except Exception as e:
            print(f"  [PG] Batch {i}-{i+len(batch)} failed: {e}")

    print(f"[PG] Created {total_created}, Updated {total_updated}")


def main():
    parser = argparse.ArgumentParser(description="Amazon Product Search Ranking Collector")
    parser.add_argument("--keyword", help="Single keyword to search")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be collected")
    parser.add_argument("--skip-pg", action="store_true", help="Skip PG push")
    args = parser.parse_args()

    print("=" * 60)
    print("Amazon Product Search Ranking Collector")
    print(f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"ASINs: {len(ALL_OUR_ASINS)} tracked")
    print(f"Keywords: {sum(len(v) for v in SEARCH_KEYWORDS.values())} total")
    print("=" * 60)

    keywords_filter = [args.keyword] if args.keyword else None
    rows = collect_search_rankings(keywords_filter=keywords_filter, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN] No data collected")
        return

    if not rows:
        print("\nNo rows collected")
        return

    _save_cache(rows)

    if not args.skip_pg:
        _push_to_pg(rows)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    found = [r for r in rows if r["position"] > 0]
    not_found = [r for r in rows if r["position"] <= 0]
    print(f"  Found: {len(found)}/{len(rows)} keywords")
    for r in sorted(found, key=lambda x: x["position"]):
        print(f"    #{r['position']:>2}  {r['brand']:12s}  '{r['keyword']}'")
    if not_found:
        print(f"  Not in top {MAX_ITEMS_PER_KEYWORD}:")
        for r in not_found:
            print(f"         {r['brand']:12s}  '{r['keyword']}'")


if __name__ == "__main__":
    main()
