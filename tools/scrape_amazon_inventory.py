"""
Amazon Seller Central Inventory Scraper
Uses Firecrawl API to scrape inventory data with browser session cookies.

Usage:
    python tools/scrape_amazon_inventory.py

Output:
    .tmp/raw_inventory.json
"""

import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
AMAZON_COOKIES = os.getenv("AMAZON_SELLER_CENTRAL_COOKIES")
FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v1"
OUTPUT_PATH = os.path.join(".tmp", "raw_inventory.json")

# Seller Central pages to scrape
PAGES_TO_SCRAPE = {
    "all_inventory": "https://sellercentral.amazon.com/myinventory/inventory",
    "inactive": "https://sellercentral.amazon.com/myinventory/inventory?status=INACTIVE",
    "suppressed": "https://sellercentral.amazon.com/listing/suppressed",
    "stranded": "https://sellercentral.amazon.com/reportcentral/STRANDED_INVENTORY/1",
}

# JSON schema for Firecrawl's LLM extraction
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "listings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "Seller SKU identifier"
                    },
                    "asin": {
                        "type": "string",
                        "description": "Amazon Standard Identification Number"
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Product title or name"
                    },
                    "status": {
                        "type": "string",
                        "description": "Listing status: Active, Inactive, Suppressed, Blocked, Stranded, Deactivated, or Removed"
                    },
                    "price": {
                        "type": "string",
                        "description": "Current listing price (e.g. '$19.99')"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Current inventory quantity / stock level"
                    },
                    "sales_30_days": {
                        "type": "integer",
                        "description": "Number of units sold in the last 30 days"
                    },
                    "buy_box_status": {
                        "type": "string",
                        "description": "Whether seller owns the Buy Box: 'winning', 'losing', 'suppressed', or 'none'"
                    },
                    "alerts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Any listing quality alerts or warnings displayed"
                    },
                    "compliance_requests": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Any compliance or policy action requests"
                    },
                    "inactive_reason": {
                        "type": "string",
                        "description": "Reason the listing is inactive or deactivated (if applicable)"
                    },
                    "stranded_reason": {
                        "type": "string",
                        "description": "Reason inventory is stranded (if applicable)"
                    }
                },
                "required": ["sku"]
            },
            "description": "All inventory listings visible on the page"
        },
        "page_summary": {
            "type": "string",
            "description": "Brief summary of the page content and any notable information"
        }
    }
}


def check_prerequisites():
    """Validate required env vars are set."""
    if not FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY is not set in .env")
    if not AMAZON_COOKIES:
        raise ValueError(
            "AMAZON_SELLER_CENTRAL_COOKIES is not set in .env\n"
            "See workflows/amazon_inventory_health.md for instructions."
        )


def scrape_page(page_name: str, url: str) -> dict:
    """
    Scrape a single Seller Central page using Firecrawl extract mode.
    Returns parsed inventory data.
    """
    print(f"  Scraping: {page_name} ({url})")

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "url": url,
        "formats": ["extract"],
        "headers": {
            "Cookie": AMAZON_COOKIES,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
        "waitFor": 5000,
        "extract": {
            "schema": EXTRACT_SCHEMA,
            "prompt": (
                "Extract all inventory listing rows from this Amazon Seller Central page. "
                "For each listing, capture the SKU, ASIN, product name, status, price, "
                "quantity, sales data, Buy Box status, any alerts or warnings, "
                "compliance requests, and reasons for any inactive/stranded status. "
                "If a field is not visible, omit it rather than guessing."
            ),
        },
    }

    try:
        response = requests.post(
            f"{FIRECRAWL_BASE_URL}/scrape",
            json=payload,
            headers=headers,
            timeout=90,
        )
    except requests.exceptions.Timeout:
        print(f"  [TIMEOUT] {page_name} timed out after 90s")
        return {"listings": [], "error": "timeout"}
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] {page_name}: {e}")
        return {"listings": [], "error": str(e)}

    if response.status_code != 200:
        print(f"  [HTTP {response.status_code}] {page_name}: {response.text[:200]}")
        return {"listings": [], "error": f"HTTP {response.status_code}"}

    data = response.json()

    # Firecrawl returns extracted data under data.extract
    extracted = data.get("data", {}).get("extract", {})

    if not extracted:
        print(f"  [WARN] {page_name}: No data extracted (possible auth failure or empty page)")
        # Save raw response for debugging
        debug_path = os.path.join(".tmp", f"debug_{page_name}.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  [DEBUG] Raw response saved to {debug_path}")
        return {"listings": [], "error": "no_data"}

    listings = extracted.get("listings", [])
    print(f"  Found {len(listings)} listings on {page_name}")

    return extracted


def merge_listings(all_results: dict) -> list:
    """
    Merge listings from multiple pages, deduplicating by SKU.
    Later pages (inactive, suppressed, stranded) override status from the main page.
    """
    merged = {}  # sku -> listing dict

    # Process in order: all_inventory first (baseline), then specific status pages
    page_priority = ["all_inventory", "inactive", "suppressed", "stranded"]

    for page_name in page_priority:
        if page_name not in all_results:
            continue
        listings = all_results[page_name].get("listings", [])
        for listing in listings:
            sku = listing.get("sku", "").strip()
            if not sku:
                continue

            if sku in merged:
                # Override with more specific status info
                existing = merged[sku]
                # Merge alerts and compliance_requests
                existing_alerts = existing.get("alerts", [])
                new_alerts = listing.get("alerts", [])
                existing["alerts"] = list(set(existing_alerts + new_alerts))

                existing_compliance = existing.get("compliance_requests", [])
                new_compliance = listing.get("compliance_requests", [])
                existing["compliance_requests"] = list(set(existing_compliance + new_compliance))

                # Override status if coming from a specific status page
                if page_name != "all_inventory":
                    for key in ["status", "inactive_reason", "stranded_reason"]:
                        if listing.get(key):
                            existing[key] = listing[key]
            else:
                merged[sku] = listing.copy()

            # Tag source page
            merged[sku]["_source_page"] = page_name

    return list(merged.values())


def main():
    print("=== Amazon Inventory Scraper ===\n")

    # Validate setup
    check_prerequisites()

    # Ensure output directory exists
    os.makedirs(".tmp", exist_ok=True)

    # Scrape all pages
    all_results = {}
    for page_name, url in PAGES_TO_SCRAPE.items():
        all_results[page_name] = scrape_page(page_name, url)
        # Be polite — wait between requests
        time.sleep(2)

    # Merge and deduplicate
    print("\nMerging results...")
    merged = merge_listings(all_results)
    print(f"Total unique SKUs found: {len(merged)}")

    # Save output
    output = {
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_skus": len(merged),
        "listings": merged,
        "raw_page_results": {
            page: {
                "listing_count": len(result.get("listings", [])),
                "error": result.get("error"),
                "page_summary": result.get("page_summary"),
            }
            for page, result in all_results.items()
        },
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nRaw data saved to: {OUTPUT_PATH}")
    print("Run 'python tools/generate_health_report.py' to create the Excel report.")


if __name__ == "__main__":
    main()
