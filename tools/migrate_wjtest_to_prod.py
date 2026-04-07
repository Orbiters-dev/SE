#!/usr/bin/env python3
"""
Migrate WJ TEST-only n8n workflows to PROD.
Reverse of clone_n8n_to_test.py.

Usage:
    python tools/migrate_wjtest_to_prod.py --discover-cred      # Find PROD AT credential ID
    python tools/migrate_wjtest_to_prod.py --dry-run             # Preview changes only
    python tools/migrate_wjtest_to_prod.py                       # Execute migration
"""

import sys, os, json, argparse, copy, time, urllib.request, urllib.error, ssl

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from env_loader import load_env
load_env()

from n8n_api_client import n8n_request

N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

# ─── WJ TEST workflows to migrate (no PROD equivalent) ──────────────────────
WJ_TEST_WORKFLOWS = {
    "2vsXyHtjo79hnFoD": "Orbiters: Shipped -> Delivered",
    "82t55jurzbY3iUM4": "Orbiters: Delivered -> Posted",
    "zKmOX0tEWi6EBT9h": "Orbiters: Content Tracking v2",
}

# ─── Known PROD workflow to discover AT credential from ──────────────────────
PROD_REFERENCE_WF = "ufMPgU6cjwuzLM0y"  # Shopify Fulfillment -> Airtable

# ─── Airtable ID replacements (WJ TEST → PROD) ──────────────────────────────
AIRTABLE_REPLACEMENTS = {
    # Base
    "appT2gLRR0PqMFgII": "app3Vnmh7hLAVsevE",
    # Creators
    "tbl7zJ1MscP852p9N": "tblv2Jw3ZAtAMhiYY",
    # Conversations
    "tblUnBCTmGzBb4BjZ": "tblNeTyVwMomsfSk7",
    # Applicants → Orders (merged in PROD)
    "tbloYjIEr5OtEppT0": "tblQUz8zQRDdZvES3",
    # Content
    "tblSva2askQRwgGV1": "tble4cuyVnXP4OvZR",
    # Orders
    "tblCcWpvDZX7UZmSd": "tblQUz8zQRDdZvES3",
    # Dashboard/Config — same ID in both, no replacement needed
}

# ─── Shopify store replacement ───────────────────────────────────────────────
SHOPIFY_REPLACEMENTS = {
    "toddie-4080.myshopify.com": "mytoddie.myshopify.com",
    "toddie-4080": "mytoddie",
}

# ─── AT credential (WJ TEST) ────────────────────────────────────────────────
WJ_TEST_AT_CRED_ID = "59gWUPbiysH2lxd8"

# ─── Webhook prefix to strip ────────────────────────────────────────────────
WJ_TEST_WEBHOOK_PREFIX = "wj-test-"

# ─── Name prefix to strip ───────────────────────────────────────────────────
WJ_TEST_NAME_PREFIX = "[WJ TEST] "

# ─── PROD tag ────────────────────────────────────────────────────────────────
PROD_TAG = "Pathlight"

# Schedule/webhook trigger types
SCHEDULE_TRIGGER_TYPES = {
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.cron",
}
WEBHOOK_TRIGGER_TYPES = {
    "n8n-nodes-base.webhook",
}


# ─── SSL context for Windows ────────────────────────────────────────────────
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE



def get_or_create_tag(tag_name):
    """Find existing tag or create new one."""
    result = n8n_request("GET", "/tags?limit=100")
    tags = result.get("data", result if isinstance(result, list) else [])
    for t in tags:
        if t.get("name") == tag_name:
            return t["id"]
    new_tag = n8n_request("POST", "/tags", {"name": tag_name})
    print(f"  Created tag: {tag_name} (id={new_tag['id']})")
    return new_tag["id"]


def discover_prod_at_credential():
    """Find PROD Airtable credential ID by inspecting a known PROD workflow."""
    print(f"Inspecting PROD workflow {PROD_REFERENCE_WF} for AT credential...")
    wf = n8n_request("GET", f"/workflows/{PROD_REFERENCE_WF}")
    for node in wf.get("nodes", []):
        for cred_type, cred_data in node.get("credentials", {}).items():
            if "airtable" in cred_type.lower():
                cred_id = cred_data.get("id")
                cred_name = cred_data.get("name", "?")
                print(f"  Found: {cred_name} (id={cred_id})")
                return cred_id, cred_name
    return None, None


def deep_replace_strings(obj, replacements):
    """Recursively replace substrings in all string values."""
    if isinstance(obj, str):
        result = obj
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result
    elif isinstance(obj, dict):
        return {k: deep_replace_strings(v, replacements) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_replace_strings(item, replacements) for item in obj]
    return obj


def transform_for_prod(wf_json, prod_at_cred_id=None, override_name=None):
    """Transform a WJ TEST workflow for PROD deployment."""
    original_name = wf_json.get("name", "Unknown")

    # Use override name if provided, else strip [WJ TEST] prefix
    if override_name:
        new_name = override_name
    else:
        new_name = original_name
        if new_name.startswith(WJ_TEST_NAME_PREFIX):
            new_name = new_name[len(WJ_TEST_NAME_PREFIX):]

    # Only keep POST-accepted fields
    ALLOWED_FIELDS = {"name", "nodes", "connections", "settings"}
    wf = {k: copy.deepcopy(v) for k, v in wf_json.items() if k in ALLOWED_FIELDS}
    wf["name"] = new_name

    # Build full replacement map
    all_replacements = dict(AIRTABLE_REPLACEMENTS)
    all_replacements.update(SHOPIFY_REPLACEMENTS)
    if prod_at_cred_id:
        all_replacements[WJ_TEST_AT_CRED_ID] = prod_at_cred_id

    # Apply replacements recursively
    wf = deep_replace_strings(wf, all_replacements)

    # Process nodes for webhooks and schedules
    webhook_changes = []
    schedules_enabled = []
    replacements_found = []

    for node in wf.get("nodes", []):
        node_type = node.get("type", "")

        # Webhook: strip wj-test- prefix from path
        if node_type in WEBHOOK_TRIGGER_TYPES:
            params = node.get("parameters", {})
            old_path = params.get("path", "")
            if old_path.startswith(WJ_TEST_WEBHOOK_PREFIX):
                new_path = old_path[len(WJ_TEST_WEBHOOK_PREFIX):]
                params["path"] = new_path
                if "webhookId" in node:
                    node["webhookId"] = new_path
                webhook_changes.append(f"{old_path} -> {new_path}")

        # Schedule triggers: re-enable (were disabled by clone_n8n_to_test.py)
        if node_type in SCHEDULE_TRIGGER_TYPES:
            if node.get("disabled"):
                del node["disabled"]
                schedules_enabled.append(node.get("name", "?"))

    return wf, {
        "original_name": original_name,
        "new_name": new_name,
        "webhook_changes": webhook_changes,
        "schedules_enabled": schedules_enabled,
        "node_count": len(wf.get("nodes", [])),
    }


def check_existing_workflow(name):
    """Check if a workflow with this name already exists."""
    result = n8n_request("GET", "/workflows?limit=200")
    for wf in result.get("data", []):
        if wf.get("name") == name:
            return wf["id"]
    return None


def main():
    parser = argparse.ArgumentParser(description="Migrate WJ TEST workflows to PROD")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--discover-cred", action="store_true", help="Find PROD AT credential ID")
    parser.add_argument("--ids", help="Comma-separated WJ TEST workflow IDs (default: all 3)")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("ERROR: N8N_API_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    # ─── Discover PROD credential ────────────────────────────────────────
    prod_cred_id, prod_cred_name = discover_prod_at_credential()
    if not prod_cred_id:
        print("ERROR: Could not discover PROD Airtable credential.")
        sys.exit(1)

    print(f"\nPROD AT Credential: {prod_cred_name} (id={prod_cred_id})")

    if args.discover_cred:
        return

    # ─── Determine target workflows ──────────────────────────────────────
    if args.ids:
        targets = {wid.strip(): WJ_TEST_WORKFLOWS.get(wid.strip(), "?")
                   for wid in args.ids.split(",")}
    else:
        targets = WJ_TEST_WORKFLOWS

    print(f"\n{'='*60}")
    print(f"  WJ TEST → PROD Migration")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Workflows: {len(targets)}")
    print(f"  AT Credential: {WJ_TEST_AT_CRED_ID} → {prod_cred_id}")
    if args.dry_run:
        print(f"  [DRY RUN MODE]")
    print(f"{'='*60}\n")

    # ─── Process each workflow ───────────────────────────────────────────
    results = []

    for wf_id, expected_name in targets.items():
        print(f"\n--- {expected_name} [{wf_id}] ---")

        # Fetch WJ TEST workflow
        try:
            wf_full = n8n_request("GET", f"/workflows/{wf_id}")
        except Exception as e:
            print(f"  ERROR fetching: {e}")
            results.append({"wj_id": wf_id, "name": expected_name, "status": "fetch_error"})
            continue

        # Transform for PROD (use expected_name as override to avoid conflicts)
        transformed, info = transform_for_prod(wf_full, prod_cred_id, override_name=expected_name)

        print(f"  Name: {info['original_name']} → {info['new_name']}")
        print(f"  Nodes: {info['node_count']}")
        if info["webhook_changes"]:
            for wh in info["webhook_changes"]:
                print(f"  Webhook: {wh}")
        if info["schedules_enabled"]:
            print(f"  Schedules re-enabled: {', '.join(info['schedules_enabled'])}")

        # Show replacements applied
        print(f"  AT Base: appT2gLRR0PqMFgII → app3Vnmh7hLAVsevE")
        print(f"  AT Cred: {WJ_TEST_AT_CRED_ID} → {prod_cred_id}")

        # Check for existing PROD workflow with same name
        existing_id = check_existing_workflow(info["new_name"])
        if existing_id:
            print(f"  [WARN] PROD workflow already exists: {existing_id}")
            print(f"    Skipping to avoid duplicate. Delete or rename first.")
            results.append({"wj_id": wf_id, "name": info["new_name"],
                          "status": "exists", "existing_id": existing_id})
            continue

        if args.dry_run:
            results.append({"wj_id": wf_id, "name": info["new_name"],
                          "status": "would_create", **info})
            continue

        # Create PROD workflow (INACTIVE by default)
        try:
            created = n8n_request("POST", "/workflows", transformed)
            new_id = created.get("id", "?")

            # Tag with Pathlight
            try:
                tag_id = get_or_create_tag(PROD_TAG)
                n8n_request("PUT", f"/workflows/{new_id}/tags", [{"id": tag_id}])
            except Exception:
                pass

            print(f"  CREATED: {new_id} (INACTIVE)")
            results.append({"wj_id": wf_id, "prod_id": new_id,
                          "name": info["new_name"], "status": "created", **info})
        except Exception as e:
            print(f"  ERROR creating: {e}")
            results.append({"wj_id": wf_id, "name": info["new_name"],
                          "status": "create_error"})

        time.sleep(0.5)

    # ─── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Migration Summary")
    print(f"{'='*60}")

    created = [r for r in results if r.get("status") == "created"]
    would = [r for r in results if r.get("status") == "would_create"]
    errors = [r for r in results if "error" in r.get("status", "")]
    exists = [r for r in results if r.get("status") == "exists"]

    if args.dry_run:
        print(f"  Would create: {len(would)}")
    else:
        print(f"  Created: {len(created)}")
    print(f"  Already exists: {len(exists)}")
    print(f"  Errors: {len(errors)}")

    if created:
        print(f"\n  New PROD Workflow IDs:")
        for r in created:
            print(f"    {r['wj_id']} → {r['prod_id']}  ({r['name']})")
        print(f"\n  All workflows are INACTIVE. Verify in n8n UI, then activate manually.")

    if would:
        print(f"\n  [DRY RUN] Would create:")
        for r in would:
            print(f"    {r['wj_id']} → {r['new_name']}  ({r['node_count']} nodes)")


if __name__ == "__main__":
    main()
