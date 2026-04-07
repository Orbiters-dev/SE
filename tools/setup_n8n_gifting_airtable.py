"""Add Airtable save nodes to Gifting workflow.

Replaces the broken orphan "Update Creator: Needs Review" Code node
(which tried to fetch() Airtable directly -- impossible in n8n Code nodes)
with proper HTTP Request nodes:

  [Create Draft Order] -> [Prepare Airtable Payload] -> [Save to Airtable]
                       -> [Success Response]  (existing, in parallel)

Uses Airtable upsert (PATCH with performUpsert) so duplicate emails
are updated instead of duplicated.

Usage:
    python tools/setup_n8n_gifting_airtable.py --dry-run
    python tools/setup_n8n_gifting_airtable.py
    python tools/setup_n8n_gifting_airtable.py --workflow-id 4q5NCzMb3nMGYqL4  # WJ TEST
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env

load_env()

from n8n_api_client import n8n_request

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")

# Production gifting workflow
DEFAULT_WORKFLOW_ID = "F0sv8RsCS1v56Gkw"

# Inbound Applicants table (shared, our API key has access)
AIRTABLE_BASE_ID = "appT2gLRR0PqMFgII"
AIRTABLE_TABLE_ID = "tbloYjIEr5OtEppT0"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"

# Code node: prepare Airtable upsert payload
# NO optional chaining (?.) -- n8n Code node compatibility
PREPARE_AT_CODE = """
var draftData = $('Create Draft Order').first().json;
var draftOrder = draftData.draft_order || {};
var formData = $('Process Form Data').first().json;
var body = $('Webhook').first().json.body || $('Webhook').first().json;
var personal = body.personal_info || {};
var baby = body.baby_info || {};

// Get customer ID from the customer create/update step
var custData = $('Create or Update Customer').first().json;
var customerId = '';
if (custData && custData.customer) {
  customerId = String(custData.customer.id);
}

// Build fields
var fields = {
  "Email": formData.email || '',
  "Name": formData.firstName ? (formData.firstName + ' ' + (formData.lastName || '')).trim() : (personal.full_name || ''),
  "Username": (personal.instagram || body.instagramHandle || '').replace(/^@/, ''),
  "Phone": personal.phone || body.phone || '',
  "Status": "New",
  "Last Contact At": new Date().toISOString().split('T')[0]
};

// Add Draft Order info if available
if (draftOrder.id) {
  fields["Draft Order ID"] = String(draftOrder.id);
}
if (draftOrder.name) {
  fields["Draft Order Name"] = draftOrder.name;
}
if (customerId) {
  fields["Shopify Customer ID"] = customerId;
}

// TikTok handle
var tiktok = personal.tiktok || '';
if (tiktok) {
  fields["TikTok Handle"] = tiktok.replace(/^@/, '');
}

// Baby info
var child1 = (baby.child_1) || {};
if (child1.birthday) {
  fields["Child 1 Birthday"] = child1.birthday;
}

// Selected products as comma-separated string
var products = body.selected_products || body.selectedProducts || [];
if (products.length > 0) {
  if (typeof products[0] === 'object') {
    fields["Selected Products"] = products.map(function(p) { return p.title || p.name || p.variant_id || ''; }).join(', ');
  } else {
    fields["Selected Products"] = products.join(', ');
  }
}

// Shipping address as text
var addr = body.shipping_address || {};
var addrParts = [addr.street || addr.address1 || '', addr.apt || '', addr.city || '', addr.state || addr.province || '', addr.zip || ''].filter(function(x) { return x; });
if (addrParts.length > 0) {
  fields["Shipping Address"] = addrParts.join(', ');
}

// Filter out empty values (Airtable rejects nulls)
var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{
    fields: cleanFields
  }],
  performUpsert: {
    fieldsToMergeOn: ["Email"]
  },
  typecast: true
}}];
""".strip()



def get_workflow(wf_id):
    return n8n_request("GET", f"/workflows/{wf_id}")


def add_airtable_nodes(wf):
    nodes = wf.get("nodes", [])
    connections = wf.get("connections", {})

    # Remove orphaned "Update Creator: Needs Review" node
    orphan_name = "Update Creator: Needs Review"
    nodes = [n for n in nodes if n.get("name") != orphan_name]
    # Also remove its connections
    connections.pop(orphan_name, None)
    # Remove references to it from other nodes' connections
    for src in list(connections.keys()):
        for output_list in connections[src].get("main", []):
            connections[src]["main"] = [
                [c for c in outputs if c.get("node") != orphan_name]
                for outputs in connections[src].get("main", [])
            ]

    # Check if Airtable nodes already exist
    for node in nodes:
        if node.get("name") == "Save to Airtable":
            print("  Airtable nodes already exist! Skipping.")
            return None

    # Find placement coordinates
    max_x = max((n.get("position", [0, 0])[0] for n in nodes), default=400)
    max_y = max((n.get("position", [0, 0])[1] for n in nodes), default=300)
    # Place below PG nodes (which are at max_y area)
    at_y = max_y + 250

    # Node 1: Prepare Airtable Payload (Code)
    prepare_node = {
        "parameters": {
            "jsCode": PREPARE_AT_CODE,
        },
        "id": "prepare-at-payload",
        "name": "Prepare Airtable Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [max_x - 200, at_y],
    }

    # Node 2: Save to Airtable (HTTP Request with upsert)
    save_node = {
        "parameters": {
            "method": "PATCH",
            "url": AIRTABLE_URL,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {
                        "name": "Authorization",
                        "value": f"Bearer {AIRTABLE_API_KEY}",
                    },
                    {
                        "name": "Content-Type",
                        "value": "application/json",
                    },
                ],
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json) }}",
            "options": {
                "timeout": 10000,
            },
        },
        "id": "save-to-airtable",
        "name": "Save to Airtable",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [max_x + 100, at_y],
    }

    nodes.append(prepare_node)
    nodes.append(save_node)

    # Connect: Create Draft Order -> Prepare Airtable Payload -> Save to Airtable
    draft_order_name = "Create Draft Order"
    if draft_order_name not in connections:
        connections[draft_order_name] = {"main": [[]]}

    draft_outputs = connections[draft_order_name].get("main", [[]])
    if len(draft_outputs) == 0:
        draft_outputs.append([])
    # Add Prepare Airtable Payload as additional output
    draft_outputs[0].append({
        "node": "Prepare Airtable Payload",
        "type": "main",
        "index": 0,
    })
    connections[draft_order_name]["main"] = draft_outputs

    # Connect Prepare Airtable Payload -> Save to Airtable
    connections["Prepare Airtable Payload"] = {
        "main": [[{
            "node": "Save to Airtable",
            "type": "main",
            "index": 0,
        }]]
    }

    return {
        "name": wf.get("name", "Influencer Gifting"),
        "nodes": nodes,
        "connections": connections,
        "settings": wf.get("settings", {}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workflow-id", default=DEFAULT_WORKFLOW_ID)
    args = parser.parse_args()

    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    wf_id = args.workflow_id
    print(f"Fetching workflow {wf_id}...")
    wf = get_workflow(wf_id)
    print(f"  Name: {wf.get('name')}")
    print(f"  Nodes: {len(wf.get('nodes', []))}")
    print(f"  Active: {wf.get('active')}")

    # Check for orphaned node
    orphan_exists = any(
        n.get("name") == "Update Creator: Needs Review"
        for n in wf.get("nodes", [])
    )
    if orphan_exists:
        print("  Found orphaned 'Update Creator: Needs Review' node -- will remove it")

    print("Adding Airtable upsert nodes...")
    updated = add_airtable_nodes(wf)
    if updated is None:
        return

    print(f"  New node count: {len(updated['nodes'])}")

    if args.dry_run:
        print("\n[DRY RUN] Would update workflow with:")
        for n in updated["nodes"]:
            print(f"  - {n['name']} ({n['type']})")
        print("\nConnections from Create Draft Order:")
        do_conns = updated["connections"].get("Create Draft Order", {}).get("main", [[]])
        for conn in do_conns[0]:
            print(f"  -> {conn['node']}")
        print("\nConnections from Prepare Airtable Payload:")
        at_conns = updated["connections"].get("Prepare Airtable Payload", {}).get("main", [[]])
        for conn in at_conns[0]:
            print(f"  -> {conn['node']}")
        return

    # Deactivate before update
    if wf.get("active"):
        print("Deactivating workflow...")
        n8n_request("POST", f"/workflows/{wf_id}/deactivate")

    print("Updating workflow...")
    result = n8n_request("PUT", f"/workflows/{wf_id}", updated)
    print(f"  Updated: {len(result.get('nodes', []))} nodes")

    print("Reactivating workflow...")
    n8n_request("POST", f"/workflows/{wf_id}/activate")

    print("\nDone! Airtable upsert nodes added to gifting workflow.")
    print(f"  Create Draft Order -> Prepare Airtable Payload -> Save to Airtable")
    print(f"  Airtable: {AIRTABLE_URL}")
    print(f"  Upsert key: Email")


if __name__ == "__main__":
    main()
