"""Create an n8n workflow that saves form survey data to Shopify customer metafields.

Creates a webhook-triggered workflow:
  Webhook (POST) -> Code Node (build metafields) -> HTTP Request (Shopify Admin API)

Usage:
    python tools/setup_n8n_metafield_sync.py
    python tools/setup_n8n_metafield_sync.py --dry-run

Prerequisites:
    .wat_secrets: N8N_API_KEY, N8N_BASE_URL, SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN
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
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "toddie-4080.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

WORKFLOW_NAME = "Onzenna: Save Survey Metafields"



def find_existing_workflow():
    """Check if the workflow already exists."""
    result = n8n_request("GET", "/workflows?limit=100")
    for wf in result.get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf
    return None


def build_workflow():
    """Build the n8n workflow definition."""
    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "onzenna-save-metafields",
                    "responseMode": "responseNode",
                    "options": {}
                },
                "id": "webhook-trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [250, 300],
                "webhookId": "onzenna-save-metafields",
            },
            {
                "parameters": {
                    "jsCode": """// Build metafields array from form payload
const payload = $input.first().json.body || $input.first().json;
const formType = payload.form_type || '';
const customerId = payload.customer_id;
const surveyData = payload.survey_data || {};
const submittedAt = payload.submitted_at || new Date().toISOString();

if (!customerId) {
  return [{ json: { success: false, reason: 'no_customer_id' } }];
}

// Map form type to namespace
const nsMap = {
  'onzenna_core_signup': 'onzenna_survey',
  'onzenna_creator_signup': 'onzenna_creator',
};
const namespace = nsMap[formType];
if (!namespace) {
  return [{ json: { success: false, reason: 'unknown_form_type: ' + formType } }];
}

// Type mapping
const fieldTypes = {
  journey_stage: 'single_line_text_field',
  baby_birth_month: 'single_line_text_field',
  has_other_children: 'boolean',
  other_child_birth: 'single_line_text_field',
  third_child_birth: 'single_line_text_field',
  primary_platform: 'single_line_text_field',
  primary_handle: 'single_line_text_field',
  other_platforms: 'json',
  other_handles: 'json',
  following_size: 'single_line_text_field',
  hashtags: 'single_line_text_field',
  content_type: 'json',
  content_type_other: 'single_line_text_field',
  has_brand_partnerships: 'single_line_text_field',
  brand_names: 'single_line_text_field',
};

const metafields = [];

for (const [key, value] of Object.entries(surveyData)) {
  if (value === null || value === '' || (Array.isArray(value) && value.length === 0)) continue;

  let mfType = fieldTypes[key] || 'single_line_text_field';
  let mfValue = value;

  if (typeof value === 'boolean') {
    mfType = 'boolean';
    mfValue = String(value);
  } else if (Array.isArray(value) || typeof value === 'object') {
    mfType = 'json';
    mfValue = JSON.stringify(value);
  } else {
    mfValue = String(value);
  }

  metafields.push({ namespace, key, value: mfValue, type: mfType });
}

// Add completed_at timestamp
const completedKey = namespace === 'onzenna_survey' ? 'signup_completed_at' : 'creator_completed_at';
metafields.push({ namespace, key: completedKey, value: submittedAt, type: 'date_time' });

return [{
  json: {
    customer_id: customerId,
    metafields: metafields,
    shopify_body: {
      customer: {
        id: customerId,
        metafields: metafields,
      }
    }
  }
}];"""
                },
                "id": "code-build-metafields",
                "name": "Build Metafields",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [470, 300],
            },
            {
                "parameters": {
                    "method": "PUT",
                    "url": f"=https://{SHOPIFY_SHOP}/admin/api/2024-01/customers/{{{{$json.customer_id}}}}.json",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {
                                "name": "X-Shopify-Access-Token",
                                "value": SHOPIFY_TOKEN,
                            },
                            {
                                "name": "Content-Type",
                                "value": "application/json",
                            },
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json.shopify_body) }}",
                    "options": {
                        "timeout": 30000,
                    },
                },
                "id": "http-shopify-save",
                "name": "Save to Shopify",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [690, 300],
            },
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={{ JSON.stringify({ success: true, customer_id: $('Build Metafields').first().json.customer_id, metafields_saved: $('Build Metafields').first().json.metafields.length }) }}",
                    "options": {},
                },
                "id": "respond-success",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [910, 300],
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Build Metafields", "type": "main", "index": 0}]]
            },
            "Build Metafields": {
                "main": [[{"node": "Save to Shopify", "type": "main", "index": 0}]]
            },
            "Save to Shopify": {
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

    parser = argparse.ArgumentParser(description="Create n8n workflow for metafield sync")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Metafield Sync Workflow")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Shop: {SHOPIFY_SHOP}")
    print(f"{'=' * 60}\n")

    # Check for existing workflow
    existing = find_existing_workflow()
    if existing:
        wf_id = existing["id"]
        print(f"  [FOUND] Existing workflow: {WORKFLOW_NAME} (ID: {wf_id})")
        print(f"  Updating...")

        if args.dry_run:
            print(f"  [DRY RUN] Would update workflow {wf_id}")
            return

        wf_def = build_workflow()
        result = n8n_request("PUT", f"/workflows/{wf_id}", wf_def)
        print(f"  [OK] Updated workflow")
    else:
        print(f"  [NEW] Creating workflow: {WORKFLOW_NAME}")

        if args.dry_run:
            print(f"  [DRY RUN] Would create new workflow")
            return

        wf_def = build_workflow()
        result = n8n_request("POST", "/workflows", wf_def)
        wf_id = result.get("id")
        print(f"  [OK] Created workflow (ID: {wf_id})")

    # Activate the workflow
    try:
        n8n_request("POST", f"/workflows/{wf_id}/activate")
        print(f"  [OK] Workflow activated")
    except Exception as e:
        print(f"  [WARN] Could not activate: {e}")

    webhook_url = f"{N8N_BASE_URL}/webhook/onzenna-save-metafields"
    print(f"\n  Webhook URL: {webhook_url}")
    print(f"\n  NOTE: The HTTP Request node needs Shopify credentials configured in n8n.")
    print(f"  Set up 'Header Auth' credential with:")
    print(f"    Name: X-Shopify-Access-Token")
    print(f"    Value: {SHOPIFY_TOKEN[:10]}...")
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
