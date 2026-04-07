"""Create n8n workflow: Airtable Creator Update -> Shopify Customer Metafields.

Polls Airtable every 5 minutes for recently modified records.
For each record, searches Shopify customer by email and updates metafields
with creator pipeline data (status, handles, draft_order_id, etc.).

Usage:
    python tools/setup_n8n_airtable_to_shopify_metafields.py
    python tools/setup_n8n_airtable_to_shopify_metafields.py --dry-run

Prerequisites:
    .env: N8N_API_KEY, N8N_BASE_URL, AIRTABLE_API_KEY,
          AIRTABLE_INBOUND_BASE_ID, AIRTABLE_INBOUND_TABLE_ID,
          SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN
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
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

WORKFLOW_NAME = "Onzenna: Airtable Update -> Shopify Metafields"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
SHOPIFY_API = f"https://{SHOPIFY_SHOP}/admin/api/2024-01"



def get_existing_workflow():
    resp = n8n_request("GET", "workflows?limit=50")
    for wf in resp.get("data", []):
        if wf["name"] == WORKFLOW_NAME:
            return wf["id"]
    return None


def build_workflow():
    filter_formula = "IS_AFTER(LAST_MODIFIED_TIME(), DATEADD(NOW(), -10, 'minutes'))"
    airtable_url_with_params = (
        f"{AIRTABLE_URL}"
        f"?filterByFormula={urllib.request.quote(filter_formula)}"
        f"&maxRecords=100"
    )

    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Schedule Trigger - every 5 minutes
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": 5}]
                    }
                },
                "id": "schedule-trigger",
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [240, 300],
            },
            # 2. Fetch recently modified Airtable records
            {
                "parameters": {
                    "method": "GET",
                    "url": airtable_url_with_params,
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"}
                        ]
                    },
                    "options": {"timeout": 15000},
                },
                "id": "http-fetch-airtable",
                "name": "Fetch Airtable Records",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [460, 300],
                "onError": "continueRegularOutput",
            },
            # 3. Split records and extract fields
            {
                "parameters": {
                    "jsCode": """const records = $input.first().json.records || [];
if (records.length === 0) {
  return [{ json: { skipped: true, count: 0 } }];
}
return records.map(record => {
  const f = record.fields || {};
  return {
    json: {
      email: f['Email'] || f['email'] || null,
      airtable_record_id: record.id,
      // Creator pipeline
      status: f['Status'] || null,
      draft_order_id: f['Draft Order ID'] || null,
      // Creator profile
      instagram_handle: f['Instagram Handle'] || null,
      tiktok_handle: f['TikTok Handle'] || null,
      following_size: f['Following Size (Self-reported)'] || f['Following Size'] || null,
      primary_platform: f['Primary Platform'] || null,
      hashtags: f['Hashtags'] || null,
      content_type: f['Content Type'] || null,
      content_type_other: f['Content Type Other'] || null,
      brand_names: f['Brand Names'] || null,
      other_platforms: f['Other Platforms'] || null,
      status_check: f['Status Check'] || null,
      // Baby / survey
      journey_stage: f['Journey Stage'] || null,
      baby_birth_month: f['Baby Birth Month'] || null,
      has_other_children: f['Has Other Children'] != null ? String(f['Has Other Children']) : null,
      other_child_birth: f['Other Child Birth'] || null,
      third_child_birth: f['Third Child Birth'] || null,
    }
  };
}).filter(item => item.json.email);""",
                },
                "id": "code-split-records",
                "name": "Split Records",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [680, 300],
            },
            # 4. Check if email exists
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "has-email",
                                "leftValue": "={{ $json.email }}",
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
                "position": [900, 300],
            },
            # 5. Search Shopify customer by email
            {
                "parameters": {
                    "method": "GET",
                    "url": f"={SHOPIFY_API}/customers/search.json?query=email:{{{{encodeURIComponent($json.email)}}}}&limit=1",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                        ]
                    },
                    "options": {"timeout": 15000},
                },
                "id": "http-search-customer",
                "name": "Search Shopify Customer",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1120, 200],
                "onError": "continueRegularOutput",
            },
            # 6. Build metafields payload
            {
                "parameters": {
                    "jsCode": """const searchResp = $input.first().json;
const d = $('Split Records').item.json;

const customers = searchResp.customers || [];
if (customers.length === 0) {
  return [{ json: { found: false, email: d.email } }];
}

const customerId = customers[0].id;
const metafields = [];

const addText = (ns, key, value) => {
  if (value !== null && value !== undefined && value !== '') {
    metafields.push({ namespace: ns, key, value: String(value), type: 'single_line_text_field' });
  }
};
const addJson = (ns, key, value) => {
  if (Array.isArray(value) && value.length > 0) {
    metafields.push({ namespace: ns, key, value: JSON.stringify(value), type: 'json' });
  } else if (value && typeof value === 'object') {
    metafields.push({ namespace: ns, key, value: JSON.stringify(value), type: 'json' });
  }
};
const addBool = (ns, key, value) => {
  if (value !== null && value !== undefined && value !== '') {
    const boolStr = (value === true || value === 'true' || value === '1' || value === 'yes') ? 'true' : 'false';
    metafields.push({ namespace: ns, key, value: boolStr, type: 'boolean' });
  }
};

// onzenna_creator fields
addText('onzenna_creator', 'creator_status', d.status);
addText('onzenna_creator', 'instagram_handle', d.instagram_handle);
addText('onzenna_creator', 'tiktok_handle', d.tiktok_handle);
addText('onzenna_creator', 'following_size', d.following_size);
addText('onzenna_creator', 'primary_platform', d.primary_platform);
addText('onzenna_creator', 'hashtags', d.hashtags);
addJson('onzenna_creator', 'content_type', d.content_type);
addText('onzenna_creator', 'content_type_other', d.content_type_other);
addText('onzenna_creator', 'brand_names', d.brand_names);
addText('onzenna_creator', 'draft_order_id', d.draft_order_id);
// other_platforms: might be string or array
if (d.other_platforms) {
  if (Array.isArray(d.other_platforms)) {
    metafields.push({ namespace: 'onzenna_creator', key: 'other_platforms', value: JSON.stringify(d.other_platforms), type: 'json' });
  } else {
    metafields.push({ namespace: 'onzenna_creator', key: 'other_platforms', value: JSON.stringify([String(d.other_platforms)]), type: 'json' });
  }
}
addJson('onzenna_creator', 'status_check', d.status_check);

// onzenna_survey fields
addText('onzenna_survey', 'journey_stage', d.journey_stage);
addText('onzenna_survey', 'baby_birth_month', d.baby_birth_month);
addBool('onzenna_survey', 'has_other_children', d.has_other_children);
addText('onzenna_survey', 'other_child_birth', d.other_child_birth);
addText('onzenna_survey', 'third_child_birth', d.third_child_birth);

return [{
  json: {
    found: true,
    customer_id: customerId,
    email: d.email,
    metafields_count: metafields.length,
    shopify_body: {
      customer: {
        id: customerId,
        metafields: metafields,
      }
    }
  }
}];""",
                },
                "id": "code-build-metafields",
                "name": "Build Metafields",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1340, 200],
            },
            # 7. Check if customer was found
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": False, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "customer-found",
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
                "position": [1560, 200],
            },
            # 8. Update Shopify customer metafields
            {
                "parameters": {
                    "method": "PUT",
                    "url": f"={SHOPIFY_API}/customers/{{{{$json.customer_id}}}}.json",
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
                    "options": {"timeout": 20000},
                },
                "id": "http-update-shopify",
                "name": "Update Shopify Metafields",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1780, 120],
                "onError": "continueRegularOutput",
            },
        ],
        "connections": {
            "Schedule Trigger": {
                "main": [[{"node": "Fetch Airtable Records", "type": "main", "index": 0}]]
            },
            "Fetch Airtable Records": {
                "main": [[{"node": "Split Records", "type": "main", "index": 0}]]
            },
            "Split Records": {
                "main": [[{"node": "Has Email?", "type": "main", "index": 0}]]
            },
            "Has Email?": {
                "main": [
                    [{"node": "Search Shopify Customer", "type": "main", "index": 0}],
                    [],
                ]
            },
            "Search Shopify Customer": {
                "main": [[{"node": "Build Metafields", "type": "main", "index": 0}]]
            },
            "Build Metafields": {
                "main": [[{"node": "Customer Found?", "type": "main", "index": 0}]]
            },
            "Customer Found?": {
                "main": [
                    [{"node": "Update Shopify Metafields", "type": "main", "index": 0}],
                    [],
                ]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Airtable -> Shopify Metafields")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set")
        sys.exit(1)

    missing = []
    if not AIRTABLE_API_KEY:
        missing.append("AIRTABLE_API_KEY")
    if not AIRTABLE_BASE_ID:
        missing.append("AIRTABLE_INBOUND_BASE_ID")
    if not AIRTABLE_TABLE_ID:
        missing.append("AIRTABLE_INBOUND_TABLE_ID")
    if not SHOPIFY_TOKEN:
        missing.append("SHOPIFY_ACCESS_TOKEN")
    if missing:
        print(f"[ERROR] Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Shop: {SHOPIFY_SHOP}")
    print(f"  Airtable Base: {AIRTABLE_BASE_ID}")
    print(f"{'=' * 60}\n")

    wf = build_workflow()

    if args.dry_run:
        print("[DRY RUN] Workflow JSON:")
        print(json.dumps(wf, indent=2, ensure_ascii=False)[:2000])
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

    print(f"\n  Schedule: Every 5 minutes")
    print(f"  Flow: Airtable (last 10 min modified) -> Search Shopify by email -> Update metafields")
    print(f"  Namespace: onzenna_creator")
    print(f"  Fields synced: creator_status, instagram_handle, tiktok_handle,")
    print(f"                 following_size, primary_platform, brand_names, draft_order_id")
    print(f"\n  NOTE: Run setup_survey_metafields.py first to register metafield definitions.")
    print(f"\n{'=' * 60}")
    print("  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
