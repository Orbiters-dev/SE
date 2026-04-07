"""Add PostgreSQL save nodes to existing Gifting workflow.

Adds two nodes in parallel with existing flow:
  [Webhook] -> (existing nodes) -> [Success Response]
            -> [Prepare PG Payload] -> [Save to PostgreSQL]

Usage:
    python tools/setup_n8n_gifting_pg.py
    python tools/setup_n8n_gifting_pg.py --dry-run
    python tools/setup_n8n_gifting_pg.py --workflow-id 4q5NCzMb3nMGYqL4  # WJ TEST
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

# Production gifting workflow
DEFAULT_WORKFLOW_ID = "F0sv8RsCS1v56Gkw"

PG_API_URL = "https://orbitools.orbiters.co.kr/api/onzenna/gifting/save/"

# Code node: NO optional chaining (?.) — n8n Code node compatibility
PREPARE_PG_CODE = """
var webhookData = $('Webhook').first().json;
var formData = webhookData.body || webhookData;

var personal = formData.personal_info || {};
var baby = formData.baby_info || {};
var addr = formData.shipping_address || {};
var child1 = (baby.child_1) || {};
var child2 = (baby.child_2) || {};

var payload = {
  email: (personal.email || formData.email || '').trim().toLowerCase(),
  full_name: personal.full_name || ((formData.firstName || '') + ' ' + (formData.lastName || '')).trim(),
  phone: personal.phone || formData.phone || '',
  instagram: personal.instagram || formData.instagramHandle || '',
  tiktok: personal.tiktok || '',
  child_1_birthday: child1.birthday || '',
  child_1_age_months: child1.age_months || null,
  child_2_birthday: child2.birthday || '',
  child_2_age_months: child2.age_months || null,
  selected_products: formData.selected_products || formData.selectedProducts || [],
  shipping_address: {
    street: addr.street || addr.address1 || '',
    apt: addr.apt || '',
    city: addr.city || '',
    state: addr.state || addr.province || '',
    zip: addr.zip || '',
    country: addr.country || 'US'
  }
};

// Add Shopify data if available from previous nodes
try {
  var shopifyResult = $('Create Shopify Customer').first().json;
  if (shopifyResult && shopifyResult.customer) {
    payload.shopify_customer_id = String(shopifyResult.customer.id);
  }
} catch(e) {}

try {
  var draftResult = $('Create Draft Order').first().json;
  if (draftResult && draftResult.draft_order) {
    payload.shopify_draft_order_id = String(draftResult.draft_order.id);
    payload.shopify_draft_order_name = draftResult.draft_order.name || '';
  }
} catch(e) {}

return [{json: payload}];
""".strip()



def get_workflow(wf_id):
    return n8n_request("GET", f"/workflows/{wf_id}")


def has_pg_nodes(wf):
    for node in wf.get("nodes", []):
        if node.get("name") == "Save to PostgreSQL":
            return True
    return False


def add_pg_nodes(wf):
    nodes = wf.get("nodes", [])
    connections = wf.get("connections", {})

    # Find rightmost X position for placement
    max_x = max((n.get("position", [0, 0])[0] for n in nodes), default=400)
    # Place PG nodes below existing flow
    pg_y = max((n.get("position", [0, 0])[1] for n in nodes), default=300) + 250

    # Node 1: Prepare PG Payload (Code)
    prepare_node = {
        "parameters": {
            "jsCode": PREPARE_PG_CODE,
        },
        "id": "prepare-pg-payload",
        "name": "Prepare PG Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [max_x - 200, pg_y],
    }

    # Node 2: Save to PostgreSQL (HTTP Request)
    save_node = {
        "parameters": {
            "method": "POST",
            "url": PG_API_URL,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json) }}",
            "options": {
                "timeout": 10000,
            },
        },
        "id": "save-to-pg",
        "name": "Save to PostgreSQL",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [max_x + 100, pg_y],
    }

    nodes.append(prepare_node)
    nodes.append(save_node)

    # Connect: Webhook -> Prepare PG Payload -> Save to PostgreSQL
    webhook_name = "Webhook"
    for node in nodes:
        if node.get("type", "").endswith(".webhook"):
            webhook_name = node["name"]
            break

    if webhook_name not in connections:
        connections[webhook_name] = {"main": [[]]}

    # Add Prepare PG Payload as additional output from Webhook
    webhook_outputs = connections[webhook_name].get("main", [[]])
    if len(webhook_outputs) == 0:
        webhook_outputs.append([])
    # Add to first output (parallel with existing connections)
    webhook_outputs[0].append({
        "node": "Prepare PG Payload",
        "type": "main",
        "index": 0,
    })
    connections[webhook_name]["main"] = webhook_outputs

    # Connect Prepare PG Payload -> Save to PostgreSQL
    connections["Prepare PG Payload"] = {
        "main": [[{
            "node": "Save to PostgreSQL",
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

    wf_id = args.workflow_id
    print(f"Fetching workflow {wf_id}...")
    wf = get_workflow(wf_id)
    print(f"  Name: {wf.get('name')}")
    print(f"  Nodes: {len(wf.get('nodes', []))}")
    print(f"  Active: {wf.get('active')}")

    if has_pg_nodes(wf):
        print("  PG nodes already exist! Skipping.")
        return

    print("Adding PG save nodes...")
    updated = add_pg_nodes(wf)
    print(f"  New node count: {len(updated['nodes'])}")

    if args.dry_run:
        print("\n[DRY RUN] Would update workflow with:")
        for n in updated["nodes"]:
            print(f"  - {n['name']} ({n['type']})")
        print("\nConnections from Webhook:")
        wh_conns = updated["connections"].get("Webhook", {}).get("main", [[]])
        for conn in wh_conns[0]:
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

    print("\nDone! PG save nodes added to gifting workflow.")
    print(f"  Prepare PG Payload -> Save to PostgreSQL ({PG_API_URL})")


if __name__ == "__main__":
    main()
