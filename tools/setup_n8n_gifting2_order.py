"""Create n8n workflow: Gifting2 Submit -> Shopify Draft Order + Airtable Update.

Workflow nodes:
  Webhook (POST) -> Build Order Payload -> Create Shopify Customer + Draft Order
                                        -> Update Airtable Record

Usage:
    python tools/setup_n8n_gifting2_order.py
    python tools/setup_n8n_gifting2_order.py --dry-run

Prerequisites:
    .wat_secrets: N8N_API_KEY, N8N_BASE_URL, SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN,
                  AIRTABLE_API_KEY, AIRTABLE_INBOUND_BASE_ID, AIRTABLE_INBOUND_TABLE_ID
"""

import os
import sys
import json
import urllib.request
import urllib.error
import argparse
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
load_env()

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "toddie-4080.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_INBOUND_BASE_ID", "")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_INBOUND_TABLE_ID", "")

WORKFLOW_NAME = "Onzenna: Gifting2 -> Draft Order + Airtable"


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


def find_existing_workflow():
    result = n8n_request("GET", "/workflows?limit=100")
    for wf in result.get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf
    return None


def build_workflow():
    shopify_base = f"https://{SHOPIFY_SHOP}/admin/api/2024-01"
    airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"

    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Webhook trigger
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "onzenna-gifting2-submit",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "id": "webhook-trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "onzenna-gifting2-submit",
            },
            # 2. Build Shopify payloads
            {
                "parameters": {
                    "jsCode": """// Build Shopify customer + draft order payloads from gifting2 form
const payload = $input.first().json.body || $input.first().json;
const pi = payload.personal_info || {};
const addr = payload.shipping_address || {};
const baby = payload.baby_info || {};
const products = payload.selected_products || [];

// Parse name
const nameParts = (pi.full_name || '').trim().split(' ');
const firstName = nameParts[0] || '';
const lastName = nameParts.slice(1).join(' ') || '';

// Customer search/create payload
const customerPayload = {
  customer: {
    first_name: firstName,
    last_name: lastName,
    email: pi.email,
    phone: pi.phone,
    tags: 'pr, influencer-gifting, inbound-onz',
    metafields: [
      { namespace: 'influencer', key: 'instagram', value: pi.instagram || '', type: 'single_line_text_field' },
      { namespace: 'influencer', key: 'tiktok', value: pi.tiktok || '', type: 'single_line_text_field' },
    ],
    addresses: [{
      address1: addr.street || '',
      address2: addr.apt || '',
      city: addr.city || '',
      province_code: addr.state || '',
      zip: addr.zip || '',
      country_code: addr.country || 'US',
    }],
  }
};

// Draft order payload
const lineItems = products.map(p => ({
  variant_id: p.variant_id,
  quantity: 1,
  title: p.title + (p.color && p.color !== 'Default' ? ' - ' + p.color : ''),
  applied_discount: { value_type: 'percentage', value: '100.0', title: 'Creator Sample', description: 'Inbound creator gifting' },
}));

const child1 = baby.child_1 ? 'Child 1: ' + baby.child_1.birthday + ' (' + baby.child_1.age_months + 'mo)' : '';
const child2 = baby.child_2 ? ', Child 2: ' + baby.child_2.birthday + ' (' + baby.child_2.age_months + 'mo)' : '';

const draftOrderPayload = {
  draft_order: {
    line_items: lineItems,
    shipping_address: {
      first_name: firstName,
      last_name: lastName,
      address1: addr.street || '',
      address2: addr.apt || '',
      city: addr.city || '',
      province_code: addr.state || '',
      zip: addr.zip || '',
      country_code: addr.country || 'US',
    },
    tags: 'pr, influencer-gifting, inbound-onz',
    note: 'Inbound Creator Sample Request\\n' +
          'IG: ' + (pi.instagram || 'N/A') + ' | TikTok: ' + (pi.tiktok || 'N/A') + '\\n' +
          child1 + child2 + '\\n' +
          'Submitted: ' + (payload.submitted_at || ''),
    shipping_line: { title: 'Free Shipping (Creator)', price: '0.00' },
  }
};

return [{
  json: {
    email: pi.email,
    customer_payload: customerPayload,
    draft_order_payload: draftOrderPayload,
    airtable_email: payload.airtable_email || pi.email,
    submitted_at: payload.submitted_at,
  }
}];"""
                },
                "id": "code-build",
                "name": "Build Payloads",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [420, 300],
            },
            # 3. Search for existing customer
            {
                "parameters": {
                    "method": "GET",
                    "url": f"={shopify_base}/customers/search.json?query=email:{{{{$json.email}}}}",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                        ]
                    },
                    "options": {"timeout": 30000},
                },
                "id": "http-customer-search",
                "name": "Search Customer",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [640, 200],
            },
            # 4. Create or use existing customer, then create draft order
            {
                "parameters": {
                    "jsCode": """// Determine customer ID and prepare draft order
const searchResult = $input.first().json;
const buildData = $('Build Payloads').first().json;
const customers = searchResult.customers || [];

let customerId = null;
if (customers.length > 0) {
  customerId = customers[0].id;
}

// If no customer found, we'll create one in the next step
return [{
  json: {
    customer_id: customerId,
    customer_exists: customerId !== null,
    customer_payload: buildData.customer_payload,
    draft_order_payload: buildData.draft_order_payload,
    airtable_email: buildData.airtable_email,
    submitted_at: buildData.submitted_at,
    email: buildData.email,
  }
}];"""
                },
                "id": "code-check-customer",
                "name": "Check Customer",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [860, 200],
            },
            # 5. Create customer (if not exists) via Shopify
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{shopify_base}/customers.json",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json.customer_payload) }}",
                    "options": {"timeout": 30000},
                },
                "id": "http-create-customer",
                "name": "Create Customer",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1080, 100],
            },
            # 6. Merge customer ID
            {
                "parameters": {
                    "jsCode": """// Get customer ID from creation or existing search
const checkData = $('Check Customer').first().json;
let customerId = checkData.customer_id;

// If we just created a customer, get the ID
if (!customerId) {
  const createResult = $input.first().json;
  customerId = createResult.customer?.id || null;
}

// Attach customer to draft order
const draftPayload = checkData.draft_order_payload;
if (customerId) {
  draftPayload.draft_order.customer = { id: customerId };
}

return [{
  json: {
    customer_id: customerId,
    draft_order_payload: draftPayload,
    airtable_email: checkData.airtable_email,
    submitted_at: checkData.submitted_at,
  }
}];"""
                },
                "id": "code-merge-customer",
                "name": "Merge Customer ID",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1300, 200],
            },
            # 7. Create Draft Order
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{shopify_base}/draft_orders.json",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json.draft_order_payload) }}",
                    "options": {"timeout": 30000},
                },
                "id": "http-create-order",
                "name": "Create Draft Order",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1520, 200],
            },
            # 8. Update Airtable
            {
                "parameters": {
                    "jsCode": f"""// Find and update Airtable record by email
const orderResult = $input.first().json;
const mergeData = $('Merge Customer ID').first().json;
const draftOrder = orderResult.draft_order || {{}};
const draftOrderId = draftOrder.id || '';
const draftOrderName = draftOrder.name || '';
const airtableEmail = mergeData.airtable_email;

return [{{
  json: {{
    airtable_email: airtableEmail,
    draft_order_id: String(draftOrderId),
    draft_order_name: draftOrderName,
    customer_id: mergeData.customer_id,
  }}
}}];"""
                },
                "id": "code-prep-airtable",
                "name": "Prep Airtable Update",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1740, 200],
            },
            # 9. Find Airtable record by email
            {
                "parameters": {
                    "method": "GET",
                    "url": f"={airtable_url}?filterByFormula={{{{encodeURIComponent('{{Email}}=\"' + $json.airtable_email + '\"')}}}}",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                        ]
                    },
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-find",
                "name": "Find Airtable Record",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1960, 200],
            },
            # 10. Update Airtable record
            {
                "parameters": {
                    "jsCode": f"""// Update Airtable record with draft order info
const findResult = $input.first().json;
const prepData = $('Prep Airtable Update').first().json;
const records = findResult.records || [];

if (records.length === 0) {{
  return [{{ json: {{ success: true, airtable_updated: false, reason: 'no_record_found' }} }}];
}}

const recordId = records[0].id;
const updateUrl = '{airtable_url}';

return [{{
  json: {{
    update_url: updateUrl,
    record_id: recordId,
    draft_order_id: prepData.draft_order_id,
    draft_order_name: prepData.draft_order_name,
  }}
}}];"""
                },
                "id": "code-build-airtable-update",
                "name": "Build Airtable Update",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [2180, 200],
            },
            # 11. PATCH Airtable
            {
                "parameters": {
                    "method": "PATCH",
                    "url": airtable_url,
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "id": $json.record_id, "fields": { "Sample Form Completed": true, "Draft Order ID": $json.draft_order_id } }] }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-patch",
                "name": "Update Airtable",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2400, 200],
            },
            # 12. Respond
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ JSON.stringify({ success: true, draft_order_id: $("Create Draft Order").first().json.draft_order?.id, message: "Sample request processed" }) }}',
                    "options": {},
                },
                "id": "respond-ok",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [2620, 200],
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Build Payloads", "type": "main", "index": 0}]]
            },
            "Build Payloads": {
                "main": [[{"node": "Search Customer", "type": "main", "index": 0}]]
            },
            "Search Customer": {
                "main": [[{"node": "Check Customer", "type": "main", "index": 0}]]
            },
            "Check Customer": {
                "main": [[{"node": "Create Customer", "type": "main", "index": 0}]]
            },
            "Create Customer": {
                "main": [[{"node": "Merge Customer ID", "type": "main", "index": 0}]]
            },
            "Merge Customer ID": {
                "main": [[{"node": "Create Draft Order", "type": "main", "index": 0}]]
            },
            "Create Draft Order": {
                "main": [[{"node": "Prep Airtable Update", "type": "main", "index": 0}]]
            },
            "Prep Airtable Update": {
                "main": [[{"node": "Find Airtable Record", "type": "main", "index": 0}]]
            },
            "Find Airtable Record": {
                "main": [[{"node": "Build Airtable Update", "type": "main", "index": 0}]]
            },
            "Build Airtable Update": {
                "main": [[{"node": "Update Airtable", "type": "main", "index": 0}]]
            },
            "Update Airtable": {
                "main": [[{"node": "Respond OK", "type": "main", "index": 0}]]
            },
        },
        "settings": {
            "executionOrder": "v1",
        },
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Create n8n workflow: Gifting2 -> Draft Order + Airtable")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Shop: {SHOPIFY_SHOP}")
    print(f"{'=' * 60}\n")

    existing = find_existing_workflow()
    if existing:
        wf_id = existing["id"]
        print(f"  [FOUND] Existing workflow (ID: {wf_id})")

        if args.dry_run:
            print(f"  [DRY RUN] Would update workflow {wf_id}")
            return

        wf_def = build_workflow()
        n8n_request("PUT", f"/workflows/{wf_id}", wf_def)
        print(f"  [OK] Updated workflow")
    else:
        print(f"  [NEW] Creating workflow: {WORKFLOW_NAME}")

        if args.dry_run:
            print(f"  [DRY RUN] Would create new workflow")
            wf_def = build_workflow()
            print(f"  Nodes: {len(wf_def['nodes'])}")
            for n in wf_def["nodes"]:
                print(f"    - {n['name']} ({n['type']})")
            return

        wf_def = build_workflow()
        result = n8n_request("POST", "/workflows", wf_def)
        wf_id = result.get("id")
        print(f"  [OK] Created workflow (ID: {wf_id})")

    # Activate
    try:
        n8n_request("POST", f"/workflows/{wf_id}/activate")
        print(f"  [OK] Workflow activated")
    except Exception as e:
        print(f"  [WARN] Could not activate: {e}")

    webhook_url = f"{N8N_BASE_URL}/webhook/onzenna-gifting2-submit"
    print(f"\n  Webhook URL: {webhook_url}")
    print(f"\n  Add to ~/.wat_secrets:")
    print(f"    N8N_GIFTING2_WEBHOOK={webhook_url}")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
