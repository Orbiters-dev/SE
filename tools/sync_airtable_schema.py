"""
sync_airtable_schema.py
Sync missing fields from William's Creators table to [WJ Test] Creators.
Read-only on William CRM, write-only on WJ Test.

Usage:
    python tools/sync_airtable_schema.py              # dry-run (default)
    python tools/sync_airtable_schema.py --apply       # actually create fields
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
from env_loader import load_env
load_env()

import requests

API_KEY = os.environ["AIRTABLE_API_KEY"]
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# William CRM (READ ONLY)
WILLIAM_BASE = "appNPVxj4gUJl9v15"
WILLIAM_CREATORS = "tblv2Jw3ZAtAMhiYY"

# WJ Test (WRITE TARGET)
WJ_BASE = "appT2gLRR0PqMFgII"
WJ_CREATORS = "tbl7zJ1MscP852p9N"
WJ_CONTENT = "tblSva2askQRwgGV1"
WJ_ORDERS = "tblCcWpvDZX7UZmSd"
WJ_CONVERSATIONS = "tblUnBCTmGzBb4BjZ"

# Linked record table mapping: William table -> WJ Test table
LINKED_TABLE_MAP = {
    "tble4cuyVnXP4OvZR": WJ_CONTENT,       # Content
    "tblQUz8zQRDdZvES3": WJ_ORDERS,        # Orders
    "tblNeTyVwMomsfSk7": WJ_CONVERSATIONS,  # Conversation
}

# Fields that exist in WJ with different names (skip these)
NAME_MAP = {
    "Last Update Date": "Last Updated Date",
    "Avg Views": "Average views",
    "Avg Likes": "Average likes",
    "Avg. ER": "Average ER",
    "ManyChat Opt-In": "ManyChat Opted In",
    "Conversation": "[WJ Test] Conversations",
}


def get_schema(base_id):
    r = requests.get(f"https://api.airtable.com/v0/meta/bases/{base_id}/tables", headers=HEADERS)
    r.raise_for_status()
    return {t["id"]: t for t in r.json()["tables"]}


def add_field(base_id, table_id, field_def, dry_run=True):
    if dry_run:
        print(f"  [DRY RUN] Would add: {field_def['name']} ({field_def['type']})")
        return None
    r = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields",
        headers=HEADERS,
        json=field_def,
    )
    if r.status_code == 200:
        print(f"  [OK] Added: {field_def['name']} ({field_def['type']})")
        return r.json()
    else:
        print(f"  [ERROR] {field_def['name']}: {r.status_code} {r.text[:200]}")
        return None


def build_field_def(william_field, wj_field_names):
    """Build a field definition for creating in WJ Test."""
    name = william_field["name"]
    ftype = william_field["type"]

    # Skip if already exists (exact name or mapped name)
    if name in wj_field_names:
        return None
    if name in NAME_MAP and NAME_MAP[name] in wj_field_names:
        return None

    # Skip rollup fields (need linked records first, handle separately)
    if ftype == "rollup":
        return None

    field_def = {"name": name, "type": ftype}

    if ftype == "singleSelect" and "options" in william_field:
        choices = [{"name": c["name"]} for c in william_field["options"].get("choices", [])]
        field_def["options"] = {"choices": choices}

    elif ftype == "multipleRecordLinks" and "options" in william_field:
        linked_to = william_field["options"].get("linkedTableId", "")
        if linked_to in LINKED_TABLE_MAP:
            field_def["options"] = {
                "linkedTableId": LINKED_TABLE_MAP[linked_to],
            }
        else:
            print(f"  [SKIP] {name}: linked to unknown table {linked_to}")
            return None

    elif ftype == "number" and "options" in william_field:
        field_def["options"] = {"precision": william_field["options"].get("precision", 0)}

    elif ftype == "date" and "options" in william_field:
        field_def["options"] = william_field["options"]

    elif ftype == "checkbox":
        field_def["options"] = {"icon": "check", "color": "greenBright"}

    return field_def


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually create fields (default: dry-run)")
    args = parser.parse_args()
    dry_run = not args.apply

    print("=" * 60)
    print(f"Schema Sync: William Creators -> [WJ Test] Creators")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    print("=" * 60)

    # Get schemas
    william_schemas = get_schema(WILLIAM_BASE)
    wj_schemas = get_schema(WJ_BASE)

    william_creators = william_schemas[WILLIAM_CREATORS]
    wj_creators = wj_schemas[WJ_CREATORS]

    wj_field_names = {f["name"] for f in wj_creators["fields"]}

    print(f"\nWilliam Creators: {len(william_creators['fields'])} fields")
    print(f"[WJ Test] Creators: {len(wj_field_names)} fields")

    # Phase 1: Add simple fields (non-linked, non-rollup)
    print("\n--- Phase 1: Simple fields ---")
    added = 0
    for wf in william_creators["fields"]:
        if wf["type"] in ("multipleRecordLinks", "rollup"):
            continue
        field_def = build_field_def(wf, wj_field_names)
        if field_def:
            result = add_field(WJ_BASE, WJ_CREATORS, field_def, dry_run)
            if result:
                wj_field_names.add(field_def["name"])
            added += 1

    # Phase 2: Add linked record fields
    print("\n--- Phase 2: Linked record fields ---")
    for wf in william_creators["fields"]:
        if wf["type"] != "multipleRecordLinks":
            continue
        field_def = build_field_def(wf, wj_field_names)
        if field_def:
            result = add_field(WJ_BASE, WJ_CREATORS, field_def, dry_run)
            if result:
                wj_field_names.add(field_def["name"])
            added += 1

    # Phase 3: Note rollup fields (manual or separate step)
    print("\n--- Phase 3: Rollup fields (manual) ---")
    for wf in william_creators["fields"]:
        if wf["type"] == "rollup":
            if wf["name"] not in wj_field_names:
                print(f"  [TODO] {wf['name']} - needs linked record field first, then rollup config")
            else:
                print(f"  [OK] {wf['name']} already exists")

    # Summary
    print(f"\n--- Summary ---")
    print(f"Fields to add/added: {added}")
    print(f"Name mappings (already exist with different name):")
    for w_name, wj_name in NAME_MAP.items():
        if wj_name in wj_field_names:
            print(f"  William '{w_name}' -> WJ '{wj_name}'")

    if dry_run:
        print(f"\nRun with --apply to actually create fields.")


if __name__ == "__main__":
    main()
