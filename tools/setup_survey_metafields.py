"""Register Onzenna survey metafield definitions in Shopify Admin.

Creates metafield definitions for three namespaces:
  - onzenna_survey  (Part 1: Core Signup at checkout)
  - onzenna_creator (Part 2: Creator Branch on thank-you page)
  - onzenna_loyalty (Part 3: Loyalty Unlock page)

Usage:
    python tools/setup_survey_metafields.py
    python tools/setup_survey_metafields.py --dry-run

Prerequisites:
    .env: SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN (write_customers scope)
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_env()

SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-01"
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

# GraphQL endpoint for metafield definitions
GRAPHQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"


# ---------------------------------------------------------------------------
# Metafield definitions for all 3 survey parts
# ---------------------------------------------------------------------------

METAFIELD_DEFINITIONS = [
    # Part 1: Core Signup (onzenna_survey)
    {
        "name": "Journey Stage",
        "namespace": "onzenna_survey",
        "key": "journey_stage",
        "type": "single_line_text_field",
        "description": "Where the customer is in their parenting journey (trying_to_conceive, pregnant, new_mom_0_12m, mom_toddler_1_3y)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Baby Birth Month",
        "namespace": "onzenna_survey",
        "key": "baby_birth_month",
        "type": "single_line_text_field",
        "description": "Baby's birth month and year in YYYY-MM format",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Has Other Children",
        "namespace": "onzenna_survey",
        "key": "has_other_children",
        "type": "boolean",
        "description": "Whether the customer has other children besides the baby",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Other Child Birth",
        "namespace": "onzenna_survey",
        "key": "other_child_birth",
        "type": "single_line_text_field",
        "description": "Second child's date of birth in YYYY-MM-DD or YYYY-MM format",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Third Child Birth",
        "namespace": "onzenna_survey",
        "key": "third_child_birth",
        "type": "single_line_text_field",
        "description": "Third child's date of birth in YYYY-MM-DD or YYYY-MM format",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Survey Completed At",
        "namespace": "onzenna_survey",
        "key": "signup_completed_at",
        "type": "date_time",
        "description": "Timestamp when Part 1 Core Signup was completed",
        "ownerType": "CUSTOMER",
    },

    # Part 2: Creator Branch (onzenna_creator)
    {
        "name": "Primary Platform",
        "namespace": "onzenna_creator",
        "key": "primary_platform",
        "type": "single_line_text_field",
        "description": "Creator's most active platform (instagram, tiktok, youtube, pinterest, blog)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Primary Handle",
        "namespace": "onzenna_creator",
        "key": "primary_handle",
        "type": "single_line_text_field",
        "description": "Creator's handle on their primary platform",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Other Platforms",
        "namespace": "onzenna_creator",
        "key": "other_platforms",
        "type": "json",
        "description": "Additional platform + handle pairs (up to 3)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Following Size",
        "namespace": "onzenna_creator",
        "key": "following_size",
        "type": "single_line_text_field",
        "description": "Approximate follower count range (under_1k, 1k_10k, 10k_50k, 50k_plus)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Hashtags",
        "namespace": "onzenna_creator",
        "key": "hashtags",
        "type": "single_line_text_field",
        "description": "Comma-separated hashtags the creator typically uses",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Content Type",
        "namespace": "onzenna_creator",
        "key": "content_type",
        "type": "json",
        "description": "Types of content created (reviews, day_in_the_life, educational, humor, aesthetic_lifestyle)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Has Brand Partnerships",
        "namespace": "onzenna_creator",
        "key": "has_brand_partnerships",
        "type": "single_line_text_field",
        "description": "Brand partnership status (yes, no_but_interested, not_interested)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Brand Names",
        "namespace": "onzenna_creator",
        "key": "brand_names",
        "type": "single_line_text_field",
        "description": "Names of brands the creator has worked with",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Content Type Other",
        "namespace": "onzenna_creator",
        "key": "content_type_other",
        "type": "single_line_text_field",
        "description": "Custom content type description when 'Other' is selected",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Creator Profile Completed At",
        "namespace": "onzenna_creator",
        "key": "creator_completed_at",
        "type": "date_time",
        "description": "Timestamp when Part 2 Creator Branch was completed",
        "ownerType": "CUSTOMER",
    },

    # Part 3: Loyalty Unlock (onzenna_loyalty)
    {
        "name": "Parenting Challenges",
        "namespace": "onzenna_loyalty",
        "key": "challenges",
        "type": "json",
        "description": "Biggest parenting challenges (sleep, feeding, development, postpartum, products, routine)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Advice Format Preference",
        "namespace": "onzenna_loyalty",
        "key": "advice_format",
        "type": "json",
        "description": "Preferred advice formats (short_videos, articles, recommendations, community, expert_qa)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Product Categories",
        "namespace": "onzenna_loyalty",
        "key": "product_categories",
        "type": "json",
        "description": "Most-shopped product categories (feeding, skincare, clothing, nursery, toys, postpartum)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Purchase Frequency",
        "namespace": "onzenna_loyalty",
        "key": "purchase_frequency",
        "type": "single_line_text_field",
        "description": "How often they buy baby products (weekly, monthly, every_few_months, only_when_needed)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Product Discovery Channels",
        "namespace": "onzenna_loyalty",
        "key": "product_discovery",
        "type": "json",
        "description": "Where they discover new products (instagram, tiktok, google, word_of_mouth, blogs, pinterest)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Purchase Criteria",
        "namespace": "onzenna_loyalty",
        "key": "purchase_criteria",
        "type": "json",
        "description": "What matters most when buying (safety, brand_trust, price, ingredients, aesthetic, reviews)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Loyalty Discount Code",
        "namespace": "onzenna_loyalty",
        "key": "discount_code",
        "type": "single_line_text_field",
        "description": "Generated discount coupon code for completing the loyalty survey",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Loyalty Completed At",
        "namespace": "onzenna_loyalty",
        "key": "loyalty_completed_at",
        "type": "date_time",
        "description": "Timestamp when Part 3 Loyalty Unlock was completed",
        "ownerType": "CUSTOMER",
    },

    # Creator Pipeline Status (onzenna_creator)
    {
        "name": "Creator Status",
        "namespace": "onzenna_creator",
        "key": "creator_status",
        "type": "single_line_text_field",
        "description": "Current creator pipeline status from Airtable (Pending, Accepted, Rejected, etc.)",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Instagram Handle",
        "namespace": "onzenna_creator",
        "key": "instagram_handle",
        "type": "single_line_text_field",
        "description": "Creator's Instagram handle",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "TikTok Handle",
        "namespace": "onzenna_creator",
        "key": "tiktok_handle",
        "type": "single_line_text_field",
        "description": "Creator's TikTok handle",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Accepted At",
        "namespace": "onzenna_creator",
        "key": "accepted_at",
        "type": "date_time",
        "description": "Timestamp when creator was accepted into the program",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Sample Shipped At",
        "namespace": "onzenna_creator",
        "key": "sample_shipped_at",
        "type": "date_time",
        "description": "Timestamp when creator sample was shipped",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Draft Order ID",
        "namespace": "onzenna_creator",
        "key": "draft_order_id",
        "type": "single_line_text_field",
        "description": "Shopify draft order ID for creator sample request",
        "ownerType": "CUSTOMER",
    },
    {
        "name": "Status Check",
        "namespace": "onzenna_creator",
        "key": "status_check",
        "type": "json",
        "description": "Airtable Status Check multi-select values (e.g. Shipping Sample)",
        "ownerType": "CUSTOMER",
    },
]


# ---------------------------------------------------------------------------
# Shopify GraphQL helper
# ---------------------------------------------------------------------------

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


def create_metafield_definition(defn, dry_run=False):
    """Create a single metafield definition via GraphQL."""
    name = defn["name"]
    namespace = defn["namespace"]
    key = defn["key"]
    mf_type = defn["type"]
    description = defn["description"]
    owner_type = defn["ownerType"]

    if dry_run:
        print(f"  [DRY RUN] Would create: {owner_type}.{namespace}.{key} ({mf_type})")
        return True

    mutation = """
    mutation CreateMetafieldDefinition($definition: MetafieldDefinitionInput!) {
        metafieldDefinitionCreate(definition: $definition) {
            createdDefinition {
                id
                name
                namespace
                key
                type {
                    name
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
        "definition": {
            "name": name,
            "namespace": namespace,
            "key": key,
            "type": mf_type,
            "description": description,
            "ownerType": owner_type,
        }
    }

    result = graphql_request(mutation, variables)

    data = result.get("data", {}).get("metafieldDefinitionCreate", {})
    errors = data.get("userErrors", [])

    if errors:
        for err in errors:
            msg = err.get("message", "")
            # "already exists" is not a failure -- just skip
            if "already exists" in msg.lower() or "taken" in msg.lower() or "is in use" in msg.lower():
                print(f"  [SKIP] {namespace}.{key} -- already exists")
                return True
            print(f"  [ERROR] {namespace}.{key}: {msg}")
        return False

    created = data.get("createdDefinition")
    if created:
        print(f"  [OK] Created {namespace}.{key} ({mf_type})")
        return True

    print(f"  [WARN] {namespace}.{key} -- unexpected response: {json.dumps(result)[:200]}")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Register Onzenna survey metafield definitions in Shopify")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Onzenna Survey Metafield Setup")
    print(f"  Shop: {SHOP}")
    print(f"  Definitions: {len(METAFIELD_DEFINITIONS)}")
    if args.dry_run:
        print(f"  Mode: DRY RUN")
    print(f"{'=' * 60}\n")

    success = 0
    failed = 0

    for defn in METAFIELD_DEFINITIONS:
        ok = create_metafield_definition(defn, dry_run=args.dry_run)
        if ok:
            success += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {success} OK, {failed} failed (total: {len(METAFIELD_DEFINITIONS)})")
    print(f"{'=' * 60}\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
