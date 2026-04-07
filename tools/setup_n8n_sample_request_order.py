"""Create n8n workflow: Creator Sample Request -> Draft Order + Airtable.

Triggered by the creator-sample-form page submission.
- Fetches customer's saved shipping address from Shopify
- Creates Shopify draft order (100% discounted)
- Updates Airtable Status to "Sample Shipping"

Webhook: POST https://n8n.orbiters.co.kr/webhook/onzenna-sample-request-submit

Usage:
    python tools/setup_n8n_sample_request_order.py
    python tools/setup_n8n_sample_request_order.py --dry-run
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

from n8n_api_client import n8n_request

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_INBOUND_BASE_ID", "")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_INBOUND_TABLE_ID", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")

WORKFLOW_NAME = "Onzenna: Sample Request -> Draft Order + Airtable"
WEBHOOK_PATH = "onzenna-sample-request-submit"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
SHOPIFY_API = f"https://{SHOPIFY_SHOP}/admin/api/2024-01"



def get_existing_workflow():
    resp = n8n_request("GET", "workflows?limit=50")
    for wf in resp.get("data", []):
        if wf["name"] == WORKFLOW_NAME:
            return wf["id"]
    return None


def build_workflow():
    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Webhook trigger
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": WEBHOOK_PATH,
                    "responseMode": "responseNode",
                    "options": {},
                },
                "id": "webhook-trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": WEBHOOK_PATH,
            },
            # 2. Parse payload
            {
                "parameters": {
                    "jsCode": """const body = $input.first().json.body || $input.first().json;
const email = body.email || '';
const customerId = body.customer_id || '';
const products = body.selected_products || [];
const babyBirthDate = body.baby_birth_date || '';

if (!email) {
  return [{ json: { valid: false, error: 'email required' } }];
}
if (products.length === 0) {
  return [{ json: { valid: false, error: 'no products selected' } }];
}

return [{ json: { valid: true, email, customer_id: customerId, products, baby_birth_date: babyBirthDate } }];""",
                },
                "id": "code-parse",
                "name": "Parse Payload",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [420, 300],
            },
            # 3. Check valid
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [{
                            "id": "valid-check",
                            "leftValue": "={{ $json.valid }}",
                            "rightValue": "true",
                            "operator": {"type": "boolean", "operation": "true"},
                        }],
                        "combinator": "and",
                    },
                },
                "id": "if-valid",
                "name": "Is Valid?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [640, 300],
            },
            # 4a. Respond error
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ JSON.stringify({ error: $json.error }) }}',
                    "options": {"responseCode": 400},
                },
                "id": "respond-error",
                "name": "Respond Error",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [860, 480],
            },
            # 4b. Fetch Shopify customer (to get saved address)
            {
                "parameters": {
                    "method": "GET",
                    "url": f"={SHOPIFY_API}/customers/{{{{{{ $json.customer_id }}}}}}.json",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                        ]
                    },
                    "options": {"timeout": 15000},
                },
                "id": "http-fetch-customer",
                "name": "Fetch Customer",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [860, 200],
                "onError": "continueRegularOutput",
            },
            # 5. Build draft order payload
            {
                "parameters": {
                    "jsCode": f"""const customerResp = $input.first().json;
const parseData = $('Parse Payload').first().json;

const customer = customerResp.customer || {{}};
const addr = customer.default_address || {{}};

const lineItems = parseData.products.map(p => ({{
  variant_id: parseInt(p.variant_id) || null,
  quantity: 1,
  applied_discount: {{
    description: 'Creator Sample',
    value_type: 'percentage',
    value: '100',
    amount: '0.00',
  }},
}})).filter(li => li.variant_id);

const draftOrderPayload = {{
  draft_order: {{
    customer: customer.id ? {{ id: customer.id }} : undefined,
    email: parseData.email,
    shipping_address: {{
      first_name: addr.first_name || customer.first_name || '',
      last_name: addr.last_name || customer.last_name || '',
      address1: addr.address1 || '',
      address2: addr.address2 || '',
      city: addr.city || '',
      province_code: addr.province_code || '',
      zip: addr.zip || '',
      country_code: addr.country_code || 'US',
      phone: addr.phone || customer.phone || '',
    }},
    line_items: lineItems,
    note: 'Creator Sample Request - ' + parseData.email,
    tags: 'creator-sample,onzenna',
    send_receipt: false,
  }}
}};

return [{{ json: {{ draft_order_payload: draftOrderPayload, email: parseData.email }} }}];""",
                },
                "id": "code-build-order",
                "name": "Build Draft Order",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1080, 200],
            },
            # 6. Create Shopify draft order
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{SHOPIFY_API}/draft_orders.json",
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
                    "options": {"timeout": 20000},
                },
                "id": "http-create-draft-order",
                "name": "Create Draft Order",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1300, 200],
                "onError": "continueRegularOutput",
            },
            # 7. Find Airtable record by email
            {
                "parameters": {
                    "method": "GET",
                    "url": "={{ '" + AIRTABLE_URL + "?filterByFormula=' + encodeURIComponent('{Email}=\"' + $('Build Draft Order').first().json.email + '\"') + '&maxRecords=1' }}",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                        ]
                    },
                    "options": {"timeout": 15000},
                },
                "id": "http-find-airtable",
                "name": "Find Airtable Record",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1520, 200],
                "onError": "continueRegularOutput",
            },
            # 8. Update Airtable status to "Sample Shipping"
            {
                "parameters": {
                    "jsCode": """const findResp = $input.first().json;
const orderResp = $('Create Draft Order').first().json;
const buildData = $('Build Draft Order').first().json;

const records = findResp.records || [];
if (records.length === 0) {
  return [{ json: { airtable_updated: false, reason: 'no_record_found', email: buildData.email } }];
}

const recordId = records[0].id;
const draftOrder = orderResp.draft_order || {};

return [{
  json: {
    record_id: recordId,
    draft_order_id: String(draftOrder.id || ''),
    draft_order_name: draftOrder.name || '',
    email: buildData.email,
  }
}];""",
                },
                "id": "code-prep-update",
                "name": "Prep Airtable Update",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1740, 200],
            },
            # 9. PATCH Airtable
            {
                "parameters": {
                    "method": "PATCH",
                    "url": AIRTABLE_URL,
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "id": $json.record_id, "fields": { "Status Check": ["Shipping Sample"], "Draft Order ID": $json.draft_order_id } }] }) }}',
                    "options": {"timeout": 15000},
                },
                "id": "http-update-airtable",
                "name": "Update Airtable Status",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1960, 200],
                "onError": "continueRegularOutput",
            },
            # 10. Respond OK
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ JSON.stringify({ ok: true, draft_order: $("Create Draft Order").first().json.draft_order }) }}',
                    "options": {"responseCode": 200},
                },
                "id": "respond-ok",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [2180, 200],
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Parse Payload", "type": "main", "index": 0}]]
            },
            "Parse Payload": {
                "main": [[{"node": "Is Valid?", "type": "main", "index": 0}]]
            },
            "Is Valid?": {
                "main": [
                    [{"node": "Fetch Customer", "type": "main", "index": 0}],
                    [{"node": "Respond Error", "type": "main", "index": 0}],
                ]
            },
            "Fetch Customer": {
                "main": [[{"node": "Build Draft Order", "type": "main", "index": 0}]]
            },
            "Build Draft Order": {
                "main": [[{"node": "Create Draft Order", "type": "main", "index": 0}]]
            },
            "Create Draft Order": {
                "main": [[{"node": "Find Airtable Record", "type": "main", "index": 0}]]
            },
            "Find Airtable Record": {
                "main": [[{"node": "Prep Airtable Update", "type": "main", "index": 0}]]
            },
            "Prep Airtable Update": {
                "main": [[{"node": "Update Airtable Status", "type": "main", "index": 0}]]
            },
            "Update Airtable Status": {
                "main": [[{"node": "Respond OK", "type": "main", "index": 0}]]
            },
        },
        "settings": {"executionOrder": "v1"},
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Create n8n workflow: Sample Request -> Draft Order")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Shopify: {SHOPIFY_SHOP}")
    print(f"{'=' * 60}\n")

    wf = build_workflow()

    if args.dry_run:
        print("[DRY RUN] Workflow JSON:")
        print(json.dumps(wf, indent=2, ensure_ascii=False)[:1000])
        return

    existing_id = get_existing_workflow()

    if existing_id:
        print(f"  [FOUND] Existing workflow (ID: {existing_id})")
        n8n_request("PUT", f"workflows/{existing_id}", wf)
        print("  [OK] Updated workflow")
        n8n_request("POST", f"workflows/{existing_id}/activate")
        print("  [OK] Workflow activated")
    else:
        result = n8n_request("POST", "workflows", wf)
        wf_id = result.get("id")
        print(f"  [CREATED] New workflow (ID: {wf_id})")
        n8n_request("POST", f"workflows/{wf_id}/activate")
        print("  [OK] Workflow activated")

    print(f"\n  Webhook: {N8N_BASE_URL}/webhook/{WEBHOOK_PATH}")
    print(f"  Flow: Form Submit -> Fetch Shopify Address -> Draft Order -> Airtable: 'Sample Shipping'")
    print(f"\n{'=' * 60}")
    print("  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
