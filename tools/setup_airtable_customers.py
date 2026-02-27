"""Create Airtable base "Shopify Customers" for team operations.

Creates a base with a "Customers" table containing fields for:
  - Customer basic info (from Shopify)
  - Calculated metrics (LTV, order count, etc.)
  - Team operational fields (segment, notes, tags)

Usage:
    python tools/setup_airtable_customers.py
    python tools/setup_airtable_customers.py --dry-run
    python tools/setup_airtable_customers.py --base-id appXXXXX

Prerequisites:
    .wat_secrets: AIRTABLE_API_KEY
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
load_env()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_URL = "https://api.airtable.com/v0"
BASE_NAME = "Shopify Customers"
TABLE_NAME = "Customers"


def airtable_request(method, path, data=None):
    url = f"{AIRTABLE_BASE_URL}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {AIRTABLE_API_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {e.code}: {error_body[:500]}")
        raise


def find_existing_base():
    result = airtable_request("GET", "/meta/bases")
    for b in result.get("bases", []):
        if b.get("name") == BASE_NAME:
            return b
    return None


def build_table_schema():
    return {
        "name": TABLE_NAME,
        "fields": [
            # -- Shopify 기본정보 --
            {"name": "Shopify ID", "type": "number", "options": {"precision": 0}},
            {"name": "Email", "type": "email"},
            {"name": "First Name", "type": "singleLineText"},
            {"name": "Last Name", "type": "singleLineText"},
            {"name": "Phone", "type": "phoneNumber"},
            {"name": "Tags", "type": "singleLineText"},
            {"name": "State", "type": "singleLineText"},
            {"name": "City", "type": "singleLineText"},
            {"name": "Country", "type": "singleLineText"},
            {
                "name": "Created At",
                "type": "dateTime",
                "options": {
                    "timeZone": "America/New_York",
                    "dateFormat": {"name": "iso"},
                    "timeFormat": {"name": "24hour"},
                },
            },
            # -- 계산 지표 --
            {
                "name": "LTV",
                "type": "currency",
                "options": {"precision": 2, "symbol": "$"},
            },
            {"name": "Order Count", "type": "number", "options": {"precision": 0}},
            {
                "name": "Avg Order Value",
                "type": "currency",
                "options": {"precision": 2, "symbol": "$"},
            },
            {
                "name": "Last Order Date",
                "type": "dateTime",
                "options": {
                    "timeZone": "America/New_York",
                    "dateFormat": {"name": "iso"},
                    "timeFormat": {"name": "24hour"},
                },
            },
            {"name": "Days Since Last Order", "type": "number", "options": {"precision": 0}},
            {
                "name": "RFM Segment",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Champions", "color": "greenLight2"},
                        {"name": "Loyal", "color": "blueLight2"},
                        {"name": "Potential Loyalist", "color": "cyanLight2"},
                        {"name": "Recent", "color": "yellowLight2"},
                        {"name": "Promising", "color": "orangeLight2"},
                        {"name": "Need Attention", "color": "pinkLight2"},
                        {"name": "At Risk", "color": "redLight2"},
                        {"name": "Hibernating", "color": "grayLight2"},
                        {"name": "Lost", "color": "grayDark1"},
                    ]
                },
            },
            # -- 팀 운영 필드 --
            {"name": "Pattern Tags", "type": "singleLineText"},
            {"name": "Top Product", "type": "singleLineText"},
            {"name": "Team Notes", "type": "multilineText"},
            {
                "name": "Priority",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "High", "color": "redLight2"},
                        {"name": "Medium", "color": "yellowLight2"},
                        {"name": "Low", "color": "grayLight2"},
                    ]
                },
            },
            {
                "name": "Last Synced",
                "type": "dateTime",
                "options": {
                    "timeZone": "America/New_York",
                    "dateFormat": {"name": "iso"},
                    "timeFormat": {"name": "24hour"},
                },
            },
        ],
    }


def save_result(base_id, table_id):
    print(f"\n  Add these to ~/.wat_secrets:")
    print(f"    AIRTABLE_CUSTOMERS_BASE_ID={base_id}")
    if table_id:
        print(f"    AIRTABLE_CUSTOMERS_TABLE_ID={table_id}")


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Create Airtable base for Shopify customers")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--base-id", type=str, help="Use existing base (skip creation)")
    args = parser.parse_args()

    if not AIRTABLE_API_KEY:
        print("[ERROR] AIRTABLE_API_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Airtable: Create '{BASE_NAME}'")
    print(f"{'=' * 60}\n")

    table_schema = build_table_schema()
    print(f"  Table: {TABLE_NAME} ({len(table_schema['fields'])} fields)")

    if args.dry_run:
        print(f"\n  [DRY RUN] Would create base '{BASE_NAME}' with table '{TABLE_NAME}'")
        print(f"  Fields:")
        for f in table_schema["fields"]:
            print(f"    - {f['name']} ({f['type']})")
        return

    # Mode 1: Existing base provided
    if args.base_id:
        base_id = args.base_id
        print(f"  Using existing base: {base_id}")
        print(f"  Creating table '{TABLE_NAME}'...")
        result = airtable_request("POST", f"/meta/bases/{base_id}/tables", table_schema)
        table_id = result.get("id")
        print(f"  [OK] Table created: {table_id}")
        save_result(base_id, table_id)
        print(f"\n{'=' * 60}")
        print(f"  DONE")
        print(f"{'=' * 60}\n")
        return

    # Mode 2: Check existing
    print("  Checking existing bases...")
    existing = find_existing_base()
    if existing:
        base_id = existing["id"]
        print(f"  [FOUND] Base '{BASE_NAME}' already exists: {base_id}")
        try:
            tables_result = airtable_request("GET", f"/meta/bases/{base_id}/tables")
            existing_tables = tables_result.get("tables", [])
            customers_table = next((t for t in existing_tables if t["name"] == TABLE_NAME), None)
            if customers_table:
                table_id = customers_table["id"]
                print(f"  [FOUND] Table '{TABLE_NAME}' already exists: {table_id}")
                save_result(base_id, table_id)
                print(f"\n  DONE (already set up)")
                return
            else:
                print(f"  Creating table '{TABLE_NAME}'...")
                result = airtable_request("POST", f"/meta/bases/{base_id}/tables", table_schema)
                table_id = result.get("id")
                print(f"  [OK] Table created: {table_id}")
                save_result(base_id, table_id)
                print(f"\n{'=' * 60}")
                print(f"  DONE")
                print(f"{'=' * 60}\n")
                return
        except Exception as e:
            print(f"  [WARN] Could not check tables: {e}")

    # Mode 3: Create new (manual step needed)
    print("\n  [INFO] Base does not exist yet.")
    print("  Please create the base manually in Airtable UI, then run:")
    print(f"    python tools/setup_airtable_customers.py --base-id appXXXXX")
    print("  (Find base ID in URL: airtable.com/appXXXXX/...)")


if __name__ == "__main__":
    main()
