"""Create Airtable base "Inbound from ONZ" for influencer inbound pipeline.

Creates a base with an "Applicants" table containing fields for:
  - Creator signup form data
  - Instagram/TikTok scraped metrics
  - Application status tracking
  - Sample request workflow

Usage:
    python tools/setup_airtable_inbound.py
    python tools/setup_airtable_inbound.py --dry-run
    python tools/setup_airtable_inbound.py --workspace-id wsp_xxxxx

Prerequisites:
    .wat_secrets: AIRTABLE_API_KEY (Personal Access Token with schema.bases:write scope)
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
BASE_NAME = "Inbound from ONZ"
TABLE_NAME = "Applicants"


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


def list_bases():
    """List existing Airtable bases."""
    result = airtable_request("GET", "/meta/bases")
    return result.get("bases", [])


def find_existing_base():
    """Check if the target base already exists."""
    bases = list_bases()
    for b in bases:
        if b.get("name") == BASE_NAME:
            return b
    return None


def get_workspace_id():
    """Try to auto-detect workspace ID."""
    # Method 1: /meta/workspaces (needs workspacesAndBases:read scope)
    try:
        result = airtable_request("GET", "/meta/workspaces")
        workspaces = result.get("workspaces", [])
        if workspaces:
            return workspaces[0]["id"], workspaces[0].get("name", "")
    except Exception:
        pass
    return None, None


def create_table_in_base(base_id, table_schema):
    """Create a table in an existing base via POST /meta/bases/{baseId}/tables."""
    return airtable_request("POST", f"/meta/bases/{base_id}/tables", table_schema)


def build_table_schema():
    """Build the Applicants table field definitions."""
    return {
        "name": TABLE_NAME,
        "fields": [
            {"name": "Name", "type": "singleLineText"},
            {"name": "Email", "type": "email"},
            {"name": "Instagram Handle", "type": "singleLineText"},
            {"name": "TikTok Handle", "type": "singleLineText"},
            {
                "name": "Primary Platform",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "instagram", "color": "pinkLight2"},
                        {"name": "tiktok", "color": "cyanLight2"},
                        {"name": "youtube", "color": "redLight2"},
                        {"name": "pinterest", "color": "orangeLight2"},
                        {"name": "blog", "color": "greenLight2"},
                    ]
                },
            },
            {
                "name": "Following Size (Self-reported)",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "under_1k", "color": "blueLight2"},
                        {"name": "1k_10k", "color": "greenLight2"},
                        {"name": "10k_50k", "color": "yellowLight2"},
                        {"name": "50k_plus", "color": "redLight2"},
                    ]
                },
            },
            {
                "name": "Content Type",
                "type": "multipleSelects",
                "options": {
                    "choices": [
                        {"name": "reviews", "color": "blueLight2"},
                        {"name": "day_in_the_life", "color": "greenLight2"},
                        {"name": "educational", "color": "yellowLight2"},
                        {"name": "humor", "color": "orangeLight2"},
                        {"name": "aesthetic_lifestyle", "color": "pinkLight2"},
                        {"name": "other", "color": "grayLight2"},
                    ]
                },
            },
            {
                "name": "Has Brand Partnerships",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "yes", "color": "greenLight2"},
                        {"name": "no_but_interested", "color": "yellowLight2"},
                        {"name": "not_interested", "color": "grayLight2"},
                    ]
                },
            },
            {"name": "Brand Names", "type": "singleLineText"},
            {
                "name": "IG Followers (Scraped)",
                "type": "number",
                "options": {"precision": 0},
            },
            {
                "name": "IG Media Count",
                "type": "number",
                "options": {"precision": 0},
            },
            {
                "name": "TikTok Followers (Scraped)",
                "type": "number",
                "options": {"precision": 0},
            },
            {
                "name": "TikTok Avg Views (30d)",
                "type": "number",
                "options": {"precision": 0},
            },
            {
                "name": "Journey Stage",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "trying_to_conceive", "color": "pinkLight2"},
                        {"name": "pregnant", "color": "yellowLight2"},
                        {"name": "new_mom_0_12m", "color": "greenLight2"},
                        {"name": "mom_toddler_1_3y", "color": "blueLight2"},
                    ]
                },
            },
            {"name": "Baby Birth Month", "type": "singleLineText"},
            {
                "name": "Has Other Children",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "true", "color": "greenLight2"},
                        {"name": "false", "color": "grayLight2"},
                        {"name": "yes", "color": "greenLight2"},
                        {"name": "no", "color": "grayLight2"},
                    ]
                },
            },
            {"name": "Other Child Birth", "type": "singleLineText"},
            {"name": "Third Child Birth", "type": "singleLineText"},
            {"name": "Phone", "type": "phoneNumber"},
            {
                "name": "Shopify Customer ID",
                "type": "number",
                "options": {"precision": 0},
            },
            {
                "name": "Status",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "New", "color": "blueLight2"},
                        {"name": "Under Review", "color": "yellowLight2"},
                        {"name": "Accepted", "color": "greenLight2"},
                        {"name": "Rejected", "color": "redLight2"},
                    ]
                },
            },
            {
                "name": "Sample Form Sent",
                "type": "checkbox",
                "options": {"icon": "check", "color": "greenBright"},
            },
            {
                "name": "Sample Form Completed",
                "type": "checkbox",
                "options": {"icon": "check", "color": "greenBright"},
            },
            {"name": "Draft Order ID", "type": "singleLineText"},
            {
                "name": "Submitted At",
                "type": "dateTime",
                "options": {
                    "timeZone": "America/New_York",
                    "dateFormat": {"name": "iso"},
                    "timeFormat": {"name": "24hour"},
                },
            },
            {"name": "Notes", "type": "multilineText"},
        ],
    }


def save_result(base_id, table_id, workspace_id=None):
    """Save IDs to .tmp and print instructions."""
    print(f"\n  Add these to ~/.wat_secrets:")
    print(f"    AIRTABLE_INBOUND_BASE_ID={base_id}")
    if table_id:
        print(f"    AIRTABLE_INBOUND_TABLE_ID={table_id}")

    os.makedirs(os.path.join(DIR, "..", ".tmp", "airtable"), exist_ok=True)
    info = {
        "base_id": base_id,
        "base_name": BASE_NAME,
        "table_id": table_id,
        "table_name": TABLE_NAME,
        "workspace_id": workspace_id,
    }
    info_path = os.path.join(DIR, "..", ".tmp", "airtable", "inbound_base_info.json")
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    print(f"\n  Info saved to .tmp/airtable/inbound_base_info.json")


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Create Airtable base for influencer inbound pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--workspace-id", type=str, help="Airtable workspace ID (for creating new base)")
    parser.add_argument("--base-id", type=str, help="Use existing base (skip base creation, just create table)")
    args = parser.parse_args()

    if not AIRTABLE_API_KEY:
        print("[ERROR] AIRTABLE_API_KEY not set in ~/.wat_secrets")
        print("  1. Go to https://airtable.com/create/tokens")
        print("  2. Create a Personal Access Token with scopes:")
        print("     - data.records:read")
        print("     - data.records:write")
        print("     - schema.bases:read")
        print("     - schema.bases:write")
        print("  3. Add AIRTABLE_API_KEY=patXXX to ~/.wat_secrets")
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

    # --- Mode 1: User provided --base-id (add table to existing base) ---
    if args.base_id:
        base_id = args.base_id
        print(f"  Using existing base: {base_id}")
        print(f"  Creating table '{TABLE_NAME}'...")
        result = create_table_in_base(base_id, table_schema)
        table_id = result.get("id")
        print(f"  [OK] Table created: {table_id}")
        save_result(base_id, table_id)
        print(f"\n{'=' * 60}")
        print(f"  DONE")
        print(f"{'=' * 60}\n")
        return

    # --- Mode 2: Check for existing base ---
    print("  Checking existing bases...")
    try:
        existing = find_existing_base()
        if existing:
            base_id = existing["id"]
            print(f"  [FOUND] Base '{BASE_NAME}' already exists: {base_id}")
            print(f"  Checking tables...")
            try:
                tables_result = airtable_request("GET", f"/meta/bases/{base_id}/tables")
                existing_tables = tables_result.get("tables", [])
                applicants = next((t for t in existing_tables if t["name"] == TABLE_NAME), None)
                if applicants:
                    table_id = applicants["id"]
                    print(f"  [FOUND] Table '{TABLE_NAME}' already exists: {table_id}")
                    save_result(base_id, table_id)
                    print(f"\n{'=' * 60}")
                    print(f"  DONE (already set up)")
                    print(f"{'=' * 60}\n")
                    return
                else:
                    print(f"  Table '{TABLE_NAME}' not found, creating...")
                    result = create_table_in_base(base_id, table_schema)
                    table_id = result.get("id")
                    print(f"  [OK] Table created: {table_id}")
                    save_result(base_id, table_id)
                    print(f"\n{'=' * 60}")
                    print(f"  DONE")
                    print(f"{'=' * 60}\n")
                    return
            except Exception as e:
                print(f"  [WARN] Could not check tables: {e}")
    except Exception as e:
        print(f"  [WARN] Could not list bases: {e}")

    # --- Mode 3: Create new base ---
    workspace_id = args.workspace_id
    if not workspace_id:
        print("  Detecting workspace...")
        workspace_id, ws_name = get_workspace_id()
        if workspace_id:
            print(f"  Using workspace: {ws_name or workspace_id}")

    if not workspace_id:
        print("\n  [INFO] Cannot auto-detect workspace ID.")
        print("  Two options:")
        print("")
        print("  Option A: Create base manually in Airtable UI, then run:")
        print("    python tools/setup_airtable_inbound.py --base-id appXXXXX")
        print("    (Find base ID in the URL: airtable.com/appXXXXX/...)")
        print("")
        print("  Option B: Find workspace ID and run:")
        print("    python tools/setup_airtable_inbound.py --workspace-id wspXXXXX")
        print("    (Find workspace ID in Airtable URL when viewing workspace)")
        sys.exit(1)

    print(f"\n  Creating base '{BASE_NAME}'...")
    base_payload = {
        "name": BASE_NAME,
        "workspaceId": workspace_id,
        "tables": [table_schema],
    }
    result = airtable_request("POST", "/meta/bases", base_payload)
    base_id = result.get("id")
    tables = result.get("tables", [])
    print(f"  [OK] Base created: {base_id}")

    table_id = None
    if tables:
        table_id = tables[0].get("id")
        print(f"  [OK] Table created: {table_id}")

    save_result(base_id, table_id, workspace_id)
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
