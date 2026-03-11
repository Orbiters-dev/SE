"""Create Airtable "Onzenna Customers" master table.

Creates the master customer list table in the existing Airtable base.
All core signup customers land here; status columns track creator/loyalty progress.

Usage:
    python tools/setup_airtable_customers_table.py
    python tools/setup_airtable_customers_table.py --dry-run

Prerequisites:
    .env: AIRTABLE_API_KEY, AIRTABLE_BASE_ID
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from env_loader import load_env

load_env()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appT2gLRR0PqMFgII")
TABLE_NAME = "Onzenna Customers"
SECRETS_PATH = os.path.expanduser("~/.wat_secrets")


def airtable_request(method, path, data=None):
    url = f"https://api.airtable.com/v0{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {AIRTABLE_API_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"  [ERROR] {e.code}: {err[:400]}")
        raise


def find_existing_table():
    result = airtable_request("GET", f"/meta/bases/{BASE_ID}/tables")
    for t in result.get("tables", []):
        if t.get("name") == TABLE_NAME:
            return t
    return None


def build_table_schema():
    return {
        "name": TABLE_NAME,
        "fields": [
            {"name": "Name", "type": "singleLineText"},
            {"name": "Email", "type": "email"},
            {"name": "Phone", "type": "phoneNumber"},
            {
                "name": "Journey Stage",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "trying_to_conceive"},
                        {"name": "pregnant"},
                        {"name": "new_mom_0_12m"},
                        {"name": "mom_toddler_1_3y"},
                        {"name": "gift_shopping"},
                        {"name": "just_browsing"},
                    ]
                },
            },
            {"name": "Baby Birth Month", "type": "singleLineText"},
            {"name": "Has Other Children", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
            {"name": "Other Child Birth", "type": "singleLineText"},
            {"name": "Third Child Birth", "type": "singleLineText"},
            {"name": "Address", "type": "singleLineText"},
            {"name": "City", "type": "singleLineText"},
            {"name": "State", "type": "singleLineText"},
            {"name": "ZIP", "type": "singleLineText"},
            {"name": "Country", "type": "singleLineText"},
            {"name": "Shopify Customer ID", "type": "number", "options": {"precision": 0}},
            {
                "name": "Creator Application Status",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "None", "color": "grayLight2"},
                        {"name": "Applied", "color": "blueLight2"},
                        {"name": "Accepted", "color": "greenLight2"},
                        {"name": "Rejected", "color": "redLight2"},
                    ]
                },
            },
            {
                "name": "Loyalty Survey Status",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Not Started", "color": "grayLight2"},
                        {"name": "Completed", "color": "greenLight2"},
                    ]
                },
            },
            {"name": "Gift Card Code", "type": "singleLineText"},
            {"name": "Core Signup At", "type": "dateTime", "options": {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": "utc"}},
            {"name": "Creator Applied At", "type": "dateTime", "options": {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": "utc"}},
            {"name": "Loyalty Completed At", "type": "dateTime", "options": {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": "utc"}},
        ],
    }


def save_table_id(table_id):
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
    if "AIRTABLE_CUSTOMERS_TABLE_ID" not in content:
        with open(SECRETS_PATH, "a", encoding="utf-8") as f:
            f.write(f"\nAIRTABLE_CUSTOMERS_TABLE_ID={table_id}\n")
        print(f"  [SAVED] AIRTABLE_CUSTOMERS_TABLE_ID={table_id} -> {SECRETS_PATH}")
    else:
        print(f"  [SKIP] AIRTABLE_CUSTOMERS_TABLE_ID already in secrets. Update manually if needed.")
        print(f"         Value: {table_id}")


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Create Airtable Onzenna Customers master table")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not AIRTABLE_API_KEY:
        print("[ERROR] AIRTABLE_API_KEY not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup Airtable: {TABLE_NAME}")
    print(f"  Base: {BASE_ID}")
    print(f"{'=' * 60}\n")

    existing = find_existing_table()
    if existing:
        table_id = existing["id"]
        print(f"  [FOUND] Table already exists: {TABLE_NAME}")
        print(f"  [OK] ID: {table_id}")
        save_table_id(table_id)
        print(f"\n{'=' * 60}")
        print(f"  DONE (already existed)")
        print(f"{'=' * 60}\n")
        return

    if args.dry_run:
        schema = build_table_schema()
        print(f"  [DRY RUN] Would create table: {TABLE_NAME}")
        print(f"  Fields ({len(schema['fields'])}):")
        for f in schema["fields"]:
            print(f"    - {f['name']} ({f['type']})")
        return

    schema = build_table_schema()
    result = airtable_request("POST", f"/meta/bases/{BASE_ID}/tables", schema)
    table_id = result.get("id")
    print(f"  [OK] Table created: {TABLE_NAME}")
    print(f"  [OK] ID: {table_id}")
    save_table_id(table_id)

    print(f"\n  Add to .env if not auto-saved:")
    print(f"    AIRTABLE_CUSTOMERS_TABLE_ID={table_id}")
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
