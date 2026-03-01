"""Create n8n workflow: Onzenna Loyalty Survey -> Discount Code + Metafields.

Webhook receives loyalty survey data, generates a unique ONZWELCOME- discount code,
creates it in Shopify, saves loyalty metafields to the customer record, and returns
the discount code in the webhook response.

Usage:
    python tools/setup_n8n_loyalty_survey.py
    python tools/setup_n8n_loyalty_survey.py --dry-run

Prerequisites:
    .env: N8N_API_KEY, N8N_BASE_URL, SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN
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
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

WORKFLOW_NAME = "Onzenna: Loyalty Survey -> Gift Card"
WEBHOOK_PATH = "onzenna-loyalty-survey"

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_INBOUND_BASE_ID", "appT2gLRR0PqMFgII")
CUSTOMERS_TABLE_ID = os.getenv("AIRTABLE_CUSTOMERS_TABLE_ID", "tblLjgNhDOdkdQwuE")
ORBITOOLS_CRED_ID = "mF9WJI64MUwl0gSU"


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
    master_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CUSTOMERS_TABLE_ID}"

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
                    "jsCode": """// Parse loyalty survey payload
const body = $input.first().json.body || $input.first().json;
const sd = body.survey_data || {};

return [{
  json: {
    customer_id: body.customer_id || null,
    customer_email: body.customer_email || null,
    submitted_at: body.submitted_at || new Date().toISOString(),
    challenges: Array.isArray(sd.challenges) ? sd.challenges : [],
    advice_format: Array.isArray(sd.advice_format) ? sd.advice_format : [],
    product_categories: Array.isArray(sd.product_categories) ? sd.product_categories : [],
    purchase_frequency: sd.purchase_frequency || null,
    product_discovery: Array.isArray(sd.product_discovery) ? sd.product_discovery : [],
    purchase_criteria: Array.isArray(sd.purchase_criteria) ? sd.purchase_criteria : [],
  }
}];""",
                },
                "id": "code-parse",
                "name": "Parse Payload",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [420, 300],
            },
            # 3. Build gift card request body
            {
                "parameters": {
                    "jsCode": """// Build $10 gift card request
const customerId = $input.first().json.customer_id;
const giftCard = {
  initial_value: "10.00",
  currency: "USD",
  note: "Onzenna Loyalty Survey reward"
};
if (customerId) {
  giftCard.customer_id = customerId;
}
return [{ json: { gift_card_body: JSON.stringify({ gift_card: giftCard }) } }];""",
                },
                "id": "code-build-gift-card",
                "name": "Build Gift Card Request",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [640, 180],
            },
            # 4. Create $10 gift card in Shopify
            # Requires write_gift_cards scope on the access token
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{shopify_base}/gift_cards.json",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "raw",
                    "body": "={{ $json.gift_card_body }}",
                    "options": {"timeout": 15000},
                },
                "id": "http-create-gift-card",
                "name": "Create Gift Card",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [860, 180],
                "onError": "continueRegularOutput",
            },
            # 5. Respond with gift card code
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": """={{ JSON.stringify({ success: true, gift_card_code: $json.gift_card ? $json.gift_card.code : null }) }}""",
                    "options": {},
                },
                "id": "respond-ok",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1080, 180],
            },
            # 6. Check if we can find the customer (parallel branch)
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "has-email",
                                "leftValue": "={{ $('Parse Payload').first().json.customer_email }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "notEmpty"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-has-email",
                "name": "Has Email?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [640, 420],
            },
            # 7. Search Shopify customer by email
            {
                "parameters": {
                    "method": "GET",
                    "url": f"={shopify_base}/customers/search.json?query=email:{{{{$('Parse Payload').first().json.customer_email}}}}",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                        ]
                    },
                    "options": {"timeout": 15000},
                },
                "id": "http-search-customer",
                "name": "Search Customer",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [860, 420],
                "onError": "continueRegularOutput",
            },
            # 8. Build loyalty metafields (includes gift card code)
            {
                "parameters": {
                    "jsCode": """// Build loyalty metafields from survey data
const customers = $input.first().json.customers || [];
if (customers.length === 0) {
  return [{ json: { found: false } }];
}

const cid = customers[0].id;
const parsed = $('Parse Payload').first().json;
// Gift card code from the Create Gift Card node (may be null if Shopify call failed)
const gcResult = $('Create Gift Card').first().json;
const giftCardCode = gcResult.gift_card ? gcResult.gift_card.code : null;
const now = new Date().toISOString();

const metafields = [];

const addJson = (key, value) => {
  if (Array.isArray(value) && value.length > 0) {
    metafields.push({ namespace: 'onzenna_loyalty', key, value: JSON.stringify(value), type: 'json' });
  }
};
const addText = (key, value) => {
  if (value) metafields.push({ namespace: 'onzenna_loyalty', key, value: String(value), type: 'single_line_text_field' });
};

addJson('challenges', parsed.challenges);
addJson('advice_format', parsed.advice_format);
addJson('product_categories', parsed.product_categories);
addText('purchase_frequency', parsed.purchase_frequency);
addJson('product_discovery', parsed.product_discovery);
addJson('purchase_criteria', parsed.purchase_criteria);
addText('gift_card_code', giftCardCode);
metafields.push({ namespace: 'onzenna_loyalty', key: 'loyalty_completed_at', value: now, type: 'date_time' });

return [{
  json: {
    found: true,
    customer_id: cid,
    shopify_body: { customer: { id: cid, metafields } },
  }
}];""",
                },
                "id": "code-build-metafields",
                "name": "Build Metafields",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1080, 420],
            },
            # 9. Check customer was found
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "found-check",
                                "leftValue": "={{ $json.found }}",
                                "rightValue": "true",
                                "operator": {"type": "boolean", "operation": "true"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-customer-found",
                "name": "Customer Found?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [1300, 420],
            },
            # 10. Save metafields to Shopify
            {
                "parameters": {
                    "method": "PUT",
                    "url": f"={shopify_base}/customers/{{{{$json.customer_id}}}}.json",
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
                    "jsonBody": "={{ JSON.stringify($json.shopify_body) }}",
                    "options": {"timeout": 30000},
                },
                "id": "http-save-metafields",
                "name": "Save Metafields",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1520, 420],
                "onError": "continueRegularOutput",
            },
            # 11. Search Airtable Master by email
            {
                "parameters": {
                    "method": "GET",
                    "url": master_url,
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                        ]
                    },
                    "sendQuery": True,
                    "queryParameters": {
                        "parameters": [
                            {
                                "name": "filterByFormula",
                                "value": "={{ '{Email}=\\'' + $('Parse Payload').first().json.customer_email + '\\'' }}",
                            }
                        ]
                    },
                    "options": {"timeout": 15000},
                },
                "id": "http-search-master",
                "name": "Search Airtable Master",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1740, 420],
                "onError": "continueRegularOutput",
            },
            # 12. Extract master record ID + gift card code
            {
                "parameters": {
                    "jsCode": """const records = $input.first().json.records || [];
const parsed = $('Parse Payload').first().json;
const gcResult = $('Create Gift Card').first().json;
const giftCardCode = gcResult.gift_card ? gcResult.gift_card.code : '';

if (records.length === 0) {
  return [{ json: { found_in_master: false, customer_email: parsed.customer_email, gift_card_code: giftCardCode } }];
}

return [{
  json: {
    found_in_master: true,
    record_id: records[0].id,
    customer_email: parsed.customer_email,
    gift_card_code: giftCardCode,
  }
}];"""
                },
                "id": "code-extract-master",
                "name": "Extract Master Record",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1960, 420],
            },
            # 13. In master table?
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "master-found",
                                "leftValue": "={{ $json.found_in_master }}",
                                "rightValue": "true",
                                "operator": {"type": "boolean", "operation": "true"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-master-found",
                "name": "In Master Table?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [2180, 420],
            },
            # 14. Update Airtable Master - Loyalty Status + Gift Card Code
            {
                "parameters": {
                    "method": "PATCH",
                    "url": master_url,
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
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "id": $("Extract Master Record").first().json.record_id, "fields": { "Loyalty Survey Status": "Completed", "Gift Card Code": $("Extract Master Record").first().json.gift_card_code } }] }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-master-loyalty",
                "name": "Update Master (Loyalty)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2400, 340],
                "onError": "continueRegularOutput",
            },
            # 15. Update PostgreSQL - Loyalty Status
            {
                "parameters": {
                    "method": "POST",
                    "url": "https://orbitools.orbiters.co.kr/api/onzenna/customers/update-status/",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpBasicAuth",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": '={{ JSON.stringify({ email: $("Extract Master Record").first().json.customer_email, loyalty_survey_status: "completed", gift_card_code: $("Extract Master Record").first().json.gift_card_code }) }}',
                    "options": {"timeout": 15000},
                },
                "credentials": {
                    "httpBasicAuth": {
                        "id": ORBITOOLS_CRED_ID,
                        "name": "MVP module admin auth",
                    }
                },
                "id": "http-pg-loyalty",
                "name": "Update PostgreSQL (Loyalty)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2400, 500],
                "onError": "continueRegularOutput",
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Parse Payload", "type": "main", "index": 0}]]
            },
            "Parse Payload": {
                "main": [
                    [
                        {"node": "Build Gift Card Request", "type": "main", "index": 0},
                        {"node": "Has Email?", "type": "main", "index": 0},
                    ]
                ]
            },
            "Build Gift Card Request": {
                "main": [[{"node": "Create Gift Card", "type": "main", "index": 0}]]
            },
            "Create Gift Card": {
                "main": [[{"node": "Respond OK", "type": "main", "index": 0}]]
            },
            "Has Email?": {
                "main": [
                    [{"node": "Search Customer", "type": "main", "index": 0}],
                    [],
                ]
            },
            "Search Customer": {
                "main": [[{"node": "Build Metafields", "type": "main", "index": 0}]]
            },
            "Build Metafields": {
                "main": [[{"node": "Customer Found?", "type": "main", "index": 0}]]
            },
            "Customer Found?": {
                "main": [
                    [{"node": "Save Metafields", "type": "main", "index": 0}],
                    [],
                ]
            },
            "Save Metafields": {
                "main": [[{"node": "Search Airtable Master", "type": "main", "index": 0}]]
            },
            "Search Airtable Master": {
                "main": [[{"node": "Extract Master Record", "type": "main", "index": 0}]]
            },
            "Extract Master Record": {
                "main": [[{"node": "In Master Table?", "type": "main", "index": 0}]]
            },
            "In Master Table?": {
                "main": [
                    [
                        {"node": "Update Master (Loyalty)", "type": "main", "index": 0},
                        {"node": "Update PostgreSQL (Loyalty)", "type": "main", "index": 0},
                    ],
                    [],
                ]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Loyalty Survey -> Discount Code")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set")
        sys.exit(1)
    if not SHOPIFY_TOKEN:
        print("[ERROR] SHOPIFY_ACCESS_TOKEN not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Shop: {SHOPIFY_SHOP}")
    print(f"  Reward: $10 Shopify gift card per survey completion")
    print(f"  Note: Requires write_gift_cards scope on access token")
    print(f"{'=' * 60}\n")

    existing = find_existing_workflow()

    if args.dry_run:
        wf = build_workflow()
        print(f"  [DRY RUN] Nodes: {len(wf['nodes'])}")
        for n in wf["nodes"]:
            print(f"    - {n['name']} ({n['type']})")
        return

    wf = build_workflow()

    if existing:
        wf_id = existing["id"]
        print(f"  [FOUND] Existing workflow (ID: {wf_id})")
        n8n_request("PUT", f"/workflows/{wf_id}", wf)
        print(f"  [OK] Updated workflow")
    else:
        result = n8n_request("POST", "/workflows", wf)
        wf_id = result.get("id")
        print(f"  [CREATED] New workflow (ID: {wf_id})")

    n8n_request("POST", f"/workflows/{wf_id}/activate")
    print(f"  [OK] Workflow activated")

    webhook_url = f"{N8N_BASE_URL}/webhook/{WEBHOOK_PATH}"
    print(f"\n  Webhook URL: {webhook_url}")
    print(f"\n  Add to .env:")
    print(f"    N8N_LOYALTY_SURVEY_WEBHOOK={webhook_url}")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
