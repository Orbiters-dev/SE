#!/usr/bin/env python3
"""
Clone n8n workflows into a test folder/tag for independent testing.

Usage:
    python tools/clone_n8n_to_test.py --dry-run              # Preview only
    python tools/clone_n8n_to_test.py                         # Execute clone
    python tools/clone_n8n_to_test.py --tag "my-tag"          # Custom tag
    python tools/clone_n8n_to_test.py --delete                # Delete all cloned test workflows
"""

import sys, os, json, argparse, copy, time, urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from env_loader import load_env
load_env()

N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

# ----- Target workflow IDs (Pathlight Workflows + Full Pipeline) -----
TARGET_WORKFLOWS = {
    # Pathlight Workflows folder (10)
    "ufMPgU6cjwuzLM0y": "Orbiters: Shopify Fulfillment -> Airtable",
    "fwwOeLiDLSnR77E1": "Orbiters: Outreach - Draft Generation",
    "l86XnrL1JPFOMSA4GOoYy": "Orbiters: Syncly Data Processing",
    "K99grtW9iWq8V79f": "Orbiters: Outreach - Reply Handler",
    "A3CfH-zVXqNUQoTEWyOeQ": "Orbiters: Shopify Fulfillment (archive)",
    "jf9uxkPww2xeCr82": "Orbiters: Outreach - Approval Send",
    "HeJtfn0m3PJoPzg0": "Orbiters: Docusign Contracting",
    "jH3YKdFFRupaIyQW": "Orbiters: Content Tracking",
    "fsrnGT7aPn5jfVQ5m7I8C": "Orbiters: ManyChat Automation",
    "s1AP_dYRZGstsIcYHUA9O": "Orbiters: AI Outreach (archive)",
    # Additional low-touch workflows
    "F0sv8RsCS1v56Gkw": "Influencer Gifting -> Shopify Draft Order",
    "IlbMQ5UkvrZXQZLA": "Influencer Customer Lookup",
    # Full Pipeline (JH&SY)
    "EqOhbPZ4mwvDQRmw": "Onzenna - Influencer Full Pipeline",
}

TEST_PREFIX = "[WJ TEST] "
WEBHOOK_PREFIX_OLD = ""  # will match any webhook path
WEBHOOK_PREFIX_NEW = "wj-test-"

# Schedule trigger types that should be disabled
SCHEDULE_TRIGGER_TYPES = {
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.cron",
}

# Trigger types that create webhook endpoints
WEBHOOK_TRIGGER_TYPES = {
    "n8n-nodes-base.webhook",
}


def n8n_request(method, path, data=None):
    url = f"{N8N_BASE_URL}/api/v1{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-N8N-API-KEY", N8N_API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [n8n ERROR] {e.code}: {error_body[:500]}")
        raise


def get_or_create_tag(tag_name):
    """Find existing tag or create new one."""
    result = n8n_request("GET", "/tags?limit=100")
    tags = result.get("data", result if isinstance(result, list) else [])
    for t in tags:
        if t.get("name") == tag_name:
            return t["id"]
    # Create new tag
    new_tag = n8n_request("POST", "/tags", {"name": tag_name})
    print(f"  Created tag: {tag_name} (id={new_tag['id']})")
    return new_tag["id"]


def transform_workflow(wf_json):
    """Transform a workflow for test use:
    - Prefix name
    - Disable schedule triggers
    - Change webhook paths
    - Keep only API-accepted fields
    """
    original_name = wf_json.get("name", "Unknown")

    # Only keep fields accepted by POST /workflows
    ALLOWED_FIELDS = {"name", "nodes", "connections", "settings"}
    wf = {k: copy.deepcopy(v) for k, v in wf_json.items() if k in ALLOWED_FIELDS}

    # Prefix name
    wf["name"] = f"{TEST_PREFIX}{original_name}"

    # Process nodes
    schedule_nodes_disabled = []
    webhook_nodes_changed = []

    for node in wf.get("nodes", []):
        node_type = node.get("type", "")

        # Disable schedule triggers by marking them disabled
        if node_type in SCHEDULE_TRIGGER_TYPES:
            node["disabled"] = True
            schedule_nodes_disabled.append(node.get("name", "?"))

        # Change webhook paths to avoid conflicts
        if node_type in WEBHOOK_TRIGGER_TYPES:
            params = node.get("parameters", {})
            old_path = params.get("path", "")
            if old_path:
                new_path = f"{WEBHOOK_PREFIX_NEW}{old_path}"
                params["path"] = new_path
                if "webhookId" in node:
                    node["webhookId"] = new_path
                webhook_nodes_changed.append(f"{old_path} -> {new_path}")

    return wf, {
        "original_name": original_name,
        "new_name": wf["name"],
        "schedule_disabled": schedule_nodes_disabled,
        "webhook_changed": webhook_nodes_changed,
        "node_count": len(wf.get("nodes", [])),
    }


def list_test_workflows(tag_name):
    """Find all workflows with the test tag."""
    result = n8n_request("GET", "/workflows?limit=200")
    test_wfs = []
    for wf in result.get("data", []):
        tags = [t.get("name") for t in wf.get("tags", [])]
        if tag_name in tags:
            test_wfs.append(wf)
    return test_wfs


def delete_test_workflows(tag_name, dry_run=False):
    """Delete all workflows with the test tag."""
    test_wfs = list_test_workflows(tag_name)
    if not test_wfs:
        print("No test workflows found to delete.")
        return

    print(f"\nFound {len(test_wfs)} test workflow(s) to delete:")
    for wf in test_wfs:
        print(f"  [{wf['id']}] {wf['name']} (active={wf.get('active')})")

    if dry_run:
        print("\n[DRY RUN] Would delete the above workflows.")
        return

    for wf in test_wfs:
        wf_id = wf["id"]
        name = wf["name"]
        try:
            # Deactivate first if active
            if wf.get("active"):
                n8n_request("POST", f"/workflows/{wf_id}/deactivate")
            n8n_request("DELETE", f"/workflows/{wf_id}")
            print(f"  Deleted: {name}")
        except Exception as e:
            print(f"  Failed to delete {name}: {e}")
        time.sleep(0.3)

    print(f"\nDeleted {len(test_wfs)} test workflow(s).")


def main():
    parser = argparse.ArgumentParser(description="Clone n8n workflows for testing")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--tag", default="wj-test-1", help="Tag name for test workflows")
    parser.add_argument("--delete", action="store_true", help="Delete all test workflows")
    parser.add_argument("--ids", help="Comma-separated workflow IDs to clone (default: all targets)")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("ERROR: N8N_API_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    tag_name = args.tag

    # Delete mode
    if args.delete:
        delete_test_workflows(tag_name, dry_run=args.dry_run)
        return

    # Determine which workflows to clone
    if args.ids:
        ids_to_clone = {wid.strip(): TARGET_WORKFLOWS.get(wid.strip(), "?")
                        for wid in args.ids.split(",")}
    else:
        ids_to_clone = TARGET_WORKFLOWS

    # Check for existing test workflows to avoid duplicates
    existing_test = list_test_workflows(tag_name)
    existing_names = {wf["name"] for wf in existing_test}

    print(f"=== n8n Workflow Clone Tool ===")
    print(f"Base URL: {N8N_BASE_URL}")
    print(f"Tag: {tag_name}")
    print(f"Target workflows: {len(ids_to_clone)}")
    print(f"Existing test workflows: {len(existing_test)}")
    if args.dry_run:
        print("[DRY RUN MODE]")
    print()

    # Get or create tag
    if not args.dry_run:
        tag_id = get_or_create_tag(tag_name)
    else:
        tag_id = "dry-run-tag-id"

    # Process each workflow
    results = []
    skipped = 0

    for wf_id, expected_name in ids_to_clone.items():
        test_name = f"{TEST_PREFIX}{expected_name}"
        if test_name in existing_names:
            print(f"  SKIP (already exists): {test_name}")
            skipped += 1
            continue

        # Fetch full workflow
        try:
            wf_full = n8n_request("GET", f"/workflows/{wf_id}")
        except Exception as e:
            print(f"  ERROR fetching [{wf_id}] {expected_name}: {e}")
            results.append({"id": wf_id, "name": expected_name, "status": "fetch_error"})
            continue

        # Transform
        transformed, info = transform_workflow(wf_full)

        print(f"  {info['original_name']}")
        print(f"    -> {info['new_name']} ({info['node_count']} nodes)")
        if info["schedule_disabled"]:
            print(f"    Schedules disabled: {', '.join(info['schedule_disabled'])}")
        if info["webhook_changed"]:
            for wh in info["webhook_changed"]:
                print(f"    Webhook: {wh}")

        if args.dry_run:
            results.append({"id": wf_id, "status": "would_create", **info})
            continue

        # Create the cloned workflow
        try:
            created = n8n_request("POST", "/workflows", transformed)
            new_id = created.get("id", "?")
            # Add tag via dedicated tags endpoint
            try:
                n8n_request("PUT", f"/workflows/{new_id}/tags",
                            [{"id": tag_id}])
            except Exception:
                pass  # Tag assignment is best-effort
            print(f"    Created: {new_id}")
            results.append({"id": wf_id, "new_id": new_id, "status": "created", **info})
        except Exception as e:
            print(f"    ERROR creating: {e}")
            results.append({"id": wf_id, "status": "create_error", **info})

        time.sleep(0.5)  # Rate limit

    # Summary
    created_count = sum(1 for r in results if r.get("status") == "created")
    error_count = sum(1 for r in results if "error" in r.get("status", ""))
    would_count = sum(1 for r in results if r.get("status") == "would_create")

    print(f"\n=== Summary ===")
    if args.dry_run:
        print(f"  Would create: {would_count}")
    else:
        print(f"  Created: {created_count}")
    print(f"  Skipped (existing): {skipped}")
    print(f"  Errors: {error_count}")
    print(f"\nAll test workflows are INACTIVE by default.")
    print(f"Filter by tag '{tag_name}' in n8n UI to find them.")
    print(f"To create a folder: manually create 'WJ Test1' folder in n8n UI,")
    print(f"then drag the tagged workflows into it.")


if __name__ == "__main__":
    main()
