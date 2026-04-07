"""Create n8n workflow: Core Signup -> PostgreSQL (master) + Airtable + Shopify.

Webhook: onzenna-core-signup

Flow (PG-first):
  Webhook -> Parse Payload -> Save to PostgreSQL (FIRST - master data)
                           -> Respond OK
                           -> Create Airtable Master Record (parallel)
                              -> Update PG with Airtable Record ID
                           -> Has customer_id?
                              YES -> Build + Save Core Metafields to Shopify
                              NO  -> Search Shopify by email -> Customer Found?
                                     YES -> Build + Save Core Metafields
                                         -> Update Airtable Master (Shopify CID)
                                     NO  -> Create Shopify Account (invite email)
                                         -> Build + Save Core Metafields
                                         -> Update Airtable Master (Shopify CID)

Usage:
    python tools/setup_n8n_core_signup.py
    python tools/setup_n8n_core_signup.py --dry-run

Prerequisites:
    .env / .wat_secrets: N8N_API_KEY, N8N_BASE_URL,
                         AIRTABLE_API_KEY, AIRTABLE_INBOUND_BASE_ID,
                         AIRTABLE_CUSTOMERS_TABLE_ID,
                         SHOPIFY_SHOP, SHOPIFY_ACCESS_TOKEN
"""

import os
import sys
import json
import urllib.request
import urllib.error
import argparse
from env_loader import load_env

load_env()

from n8n_api_client import n8n_request

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_INBOUND_BASE_ID", "appT2gLRR0PqMFgII")
CUSTOMERS_TABLE_ID = os.getenv("AIRTABLE_CUSTOMERS_TABLE_ID", "tblLjgNhDOdkdQwuE")
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

ORBITOOLS_CRED_ID = "mF9WJI64MUwl0gSU"
WORKFLOW_NAME = "Onzenna: Core Signup -> Master"



def find_existing_workflow():
    result = n8n_request("GET", "/workflows?limit=100")
    for wf in result.get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf
    return None


# Inline JS helper included in each "Build Metafields" code node
METAFIELD_BUILD_JS = """function buildCoreMetafields(coreData) {
  const mfs = [];
  const addMF = (key, value, type) => {
    if (value !== null && value !== undefined && value !== '') {
      mfs.push({ namespace: 'onzenna_survey', key, value: String(value), type: type || 'single_line_text_field' });
    }
  };
  addMF('journey_stage', coreData.journey_stage);
  addMF('baby_birth_month', coreData.baby_birth_month);
  if (coreData.has_other_children !== null && coreData.has_other_children !== undefined) {
    mfs.push({ namespace: 'onzenna_survey', key: 'has_other_children', value: String(coreData.has_other_children), type: 'boolean' });
  }
  addMF('other_child_birth', coreData.other_child_birth);
  addMF('third_child_birth', coreData.third_child_birth);
  mfs.push({ namespace: 'onzenna_survey', key: 'signup_completed_at', value: new Date().toISOString(), type: 'date_time' });
  return mfs;
}"""


def build_workflow():
    master_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CUSTOMERS_TABLE_ID}"
    shopify_base = f"https://{SHOPIFY_SHOP}/admin/api/2024-01"

    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # ── 1. Webhook ─────────────────────────────────────────────────
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "onzenna-core-signup",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "id": "webhook-trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "onzenna-core-signup",
            },
            # ── 2. Parse Payload ───────────────────────────────────────────
            {
                "parameters": {
                    "jsCode": """const payload = $input.first().json.body || $input.first().json;

const customerName = payload.customer_name || '';
const customerEmail = payload.customer_email || payload.email || '';
const customerId = payload.customer_id || payload.shopify_customer_id || null;
const submittedAt = payload.submitted_at || new Date().toISOString();
const coreData = payload.core_signup_data || {};
const contactData = payload.contact || {};
const shippingData = payload.shipping_address || {};

// Normalize has_other_children to boolean
let hasOther = coreData.has_other_children;
if (typeof hasOther === 'string') {
  hasOther = ['true', '1', 'yes'].includes(hasOther.toLowerCase());
}

// Build Airtable master record fields (filter nulls)
const rawFields = {
  "Name": customerName || null,
  "Email": customerEmail || null,
  "Phone": contactData.phone || null,
  "Journey Stage": coreData.journey_stage || null,
  "Baby Birth Month": coreData.baby_birth_month || null,
  "Has Other Children": hasOther !== null && hasOther !== undefined ? hasOther : null,
  "Other Child Birth": coreData.other_child_birth || null,
  "Third Child Birth": coreData.third_child_birth || null,
  "Address": shippingData.address1 || null,
  "City": shippingData.city || null,
  "State": shippingData.province || null,
  "ZIP": shippingData.zip || null,
  "Country": shippingData.country || null,
  "Shopify Customer ID": customerId ? Number(customerId) : null,
  "Creator Application Status": "None",
  "Loyalty Survey Status": "Not Started",
  "Core Signup At": submittedAt,
};
const airtable_fields = {};
for (const [k, v] of Object.entries(rawFields)) {
  if (v !== null && v !== undefined && v !== '') {
    airtable_fields[k] = v;
  }
}

// Split name for Shopify account creation
const nameParts = customerName.trim().split(' ');
const firstName = nameParts[0] || customerName;
const lastName = nameParts.slice(1).join(' ') || '';

return [{
  json: {
    airtable_fields,
    customer_name: customerName,
    customer_email: customerEmail,
    customer_id: customerId ? String(customerId) : null,
    first_name: firstName,
    last_name: lastName,
    submitted_at: submittedAt,
    core_data: coreData,
    has_other: hasOther,
    contact_data: contactData,
    shipping_data: shippingData,
    raw_payload: payload,
  }
}];"""
                },
                "id": "code-parse",
                "name": "Parse Payload",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [420, 300],
            },
            # ── 3. Create Airtable Master Record ───────────────────────────
            {
                "parameters": {
                    "method": "POST",
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
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "fields": $("Parse Payload").first().json.airtable_fields }], "typecast": true }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-create",
                "name": "Create Airtable Master",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [880, 220],
                "onError": "continueRegularOutput",
            },
            # ── 4. Respond OK (fast, from PG save branch) ──────────────────
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ JSON.stringify({ success: true, message: "Core signup received" }) }}',
                    "options": {},
                },
                "id": "respond-ok",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [880, 80],
            },
            # ── 5. Save to PostgreSQL (Orbitools) ──────────────────────────
            {
                "parameters": {
                    "method": "POST",
                    "url": "https://orbitools.orbiters.co.kr/api/onzenna/customers/save/",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpBasicAuth",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": """={{ JSON.stringify((() => {
  const p = $('Parse Payload').first().json;
  return {
    email: p.customer_email,
    customer_email: p.customer_email,
    customer_name: p.customer_name,
    customer_id: p.customer_id,
    shopify_customer_id: p.customer_id,
    submitted_at: p.submitted_at,
    core_signup_data: p.core_data,
    contact: p.contact_data,
    shipping_address: p.shipping_data,
    raw_payload: p.raw_payload,
  };
})()) }}""",
                    "options": {"timeout": 15000},
                },
                "credentials": {
                    "httpBasicAuth": {
                        "id": ORBITOOLS_CRED_ID,
                        "name": "MVP module admin auth",
                    }
                },
                "id": "http-postgres-save",
                "name": "Save to PostgreSQL",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [640, 300],
                "onError": "continueRegularOutput",
            },
            # ── 6. Has customer_id from form? ──────────────────────────────
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "cid-check",
                                "leftValue": "={{ $('Parse Payload').first().json.customer_id }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "notEmpty"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-has-cid",
                "name": "Has customer_id?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [880, 400],
            },
            # ── 7a. Build Core Metafields (direct — has CID) ───────────────
            {
                "parameters": {
                    "jsCode": METAFIELD_BUILD_JS + """

const parsed = $('Parse Payload').first().json;
const customerId = parsed.customer_id;
const metafields = buildCoreMetafields(parsed.core_data || {});

return [{
  json: {
    customer_id: customerId,
    shopify_body: { customer: { id: customerId, metafields } },
  }
}];"""
                },
                "id": "code-mf-direct",
                "name": "Build Metafields (Direct)",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1120, 320],
            },
            # ── 7b. Save Metafields to Shopify (direct) ────────────────────
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
                "id": "http-mf-direct",
                "name": "Save Metafields (Direct)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1360, 320],
                "onError": "continueRegularOutput",
            },
            # ── 8a. Search Shopify by email (no CID) ───────────────────────
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
                "id": "http-shopify-search",
                "name": "Search Shopify",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1120, 500],
                "onError": "continueRegularOutput",
            },
            # ── 8b. Parse search result ────────────────────────────────────
            {
                "parameters": {
                    "jsCode": """const customers = $input.first().json.customers || [];
const parsed = $('Parse Payload').first().json;
if (customers.length > 0) {
  const cust = customers[0];
  return [{ json: { found: true, customer_id: String(cust.id), parsed } }];
} else {
  return [{ json: { found: false, customer_id: null, parsed } }];
}"""
                },
                "id": "code-parse-search",
                "name": "Parse Search Result",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1360, 500],
            },
            # ── 8c. Customer Found? ────────────────────────────────────────
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
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
                "id": "if-found",
                "name": "Customer Found?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [1600, 500],
            },
            # ── 9a. Build Core Metafields (found customer) ─────────────────
            {
                "parameters": {
                    "jsCode": METAFIELD_BUILD_JS + """

const parsed = $('Parse Payload').first().json;
const customerId = $('Parse Search Result').first().json.customer_id;
const metafields = buildCoreMetafields(parsed.core_data || {});

let airtableRecordId = null;
try {
  const at = $('Create Airtable Master').first().json;
  airtableRecordId = at.records && at.records[0] ? at.records[0].id : null;
} catch(e) {}

return [{
  json: {
    customer_id: customerId,
    airtable_record_id: airtableRecordId,
    shopify_body: { customer: { id: customerId, metafields } },
  }
}];"""
                },
                "id": "code-mf-found",
                "name": "Build Metafields (Found)",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1840, 400],
            },
            # ── 9b. Save Metafields (found) ────────────────────────────────
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
                "id": "http-mf-found",
                "name": "Save Metafields (Found)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2080, 400],
                "onError": "continueRegularOutput",
            },
            # ── 9c. Update Airtable Master with Shopify CID (found) ─────────
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
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "id": $("Build Metafields (Found)").first().json.airtable_record_id, "fields": { "Shopify Customer ID": Number($("Build Metafields (Found)").first().json.customer_id) } }] }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-cid-found",
                "name": "Update Airtable CID (Found)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2320, 400],
                "onError": "continueRegularOutput",
            },
            # ── 10a. Create Shopify Account (guest — not found) ────────────
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
                    "jsonBody": """={{ JSON.stringify({
  customer: {
    email: $('Parse Payload').first().json.customer_email,
    first_name: $('Parse Payload').first().json.first_name,
    last_name: $('Parse Payload').first().json.last_name,
    send_email_invite: true,
    verified_email: true,
  }
}) }}""",
                    "options": {"timeout": 30000},
                },
                "id": "http-create-account",
                "name": "Create Shopify Account",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1840, 620],
                "onError": "continueRegularOutput",
            },
            # ── 10b. Build Core Metafields (new account) ───────────────────
            {
                "parameters": {
                    "jsCode": METAFIELD_BUILD_JS + """

const parsed = $('Parse Payload').first().json;
const newCustomer = $input.first().json.customer || {};
const customerId = newCustomer.id ? String(newCustomer.id) : null;
const metafields = buildCoreMetafields(parsed.core_data || {});

let airtableRecordId = null;
try {
  const at = $('Create Airtable Master').first().json;
  airtableRecordId = at.records && at.records[0] ? at.records[0].id : null;
} catch(e) {}

return [{
  json: {
    customer_id: customerId,
    airtable_record_id: airtableRecordId,
    shopify_body: customerId ? { customer: { id: customerId, metafields } } : null,
  }
}];"""
                },
                "id": "code-mf-new",
                "name": "Build Metafields (New)",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [2080, 620],
            },
            # ── 10c. Save Metafields (new account) ────────────────────────
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "has-new-cid",
                                "leftValue": "={{ $json.customer_id }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "notEmpty"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-new-cid",
                "name": "New Account Created?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [2320, 620],
            },
            # ── 10d. Save Metafields to Shopify (new) ─────────────────────
            {
                "parameters": {
                    "method": "PUT",
                    "url": f"={shopify_base}/customers/{{{{$('Build Metafields (New)').first().json.customer_id}}}}.json",
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
                    "jsonBody": "={{ JSON.stringify($('Build Metafields (New)').first().json.shopify_body) }}",
                    "options": {"timeout": 30000},
                },
                "id": "http-mf-new",
                "name": "Save Metafields (New)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2560, 540],
                "onError": "continueRegularOutput",
            },
            # ── 10e. Update Airtable Master with new Shopify CID ───────────
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
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "id": $("Build Metafields (New)").first().json.airtable_record_id, "fields": { "Shopify Customer ID": Number($("Build Metafields (New)").first().json.customer_id) } }] }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-cid-new",
                "name": "Update Airtable CID (New)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2560, 720],
                "onError": "continueRegularOutput",
            },
            # ── 11. Update PG with Airtable Record ID (backfill) ────────────
            {
                "parameters": {
                    "method": "POST",
                    "url": "https://orbitools.orbiters.co.kr/api/onzenna/customers/update-airtable-id/",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpBasicAuth",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": """={{ JSON.stringify({
  email: $('Parse Payload').first().json.customer_email,
  airtable_master_record_id: (() => {
    try {
      const at = $('Create Airtable Master').first().json;
      return (at.records && at.records[0]) ? at.records[0].id : null;
    } catch(e) { return null; }
  })(),
}) }}""",
                    "options": {"timeout": 15000},
                },
                "credentials": {
                    "httpBasicAuth": {
                        "id": ORBITOOLS_CRED_ID,
                        "name": "MVP module admin auth",
                    }
                },
                "id": "http-pg-update-at-id",
                "name": "Update PG Airtable ID",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1100, 220],
                "onError": "continueRegularOutput",
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Parse Payload", "type": "main", "index": 0}]]
            },
            "Parse Payload": {
                "main": [[{"node": "Save to PostgreSQL", "type": "main", "index": 0}]]
            },
            "Save to PostgreSQL": {
                "main": [
                    [
                        {"node": "Respond OK", "type": "main", "index": 0},
                        {"node": "Create Airtable Master", "type": "main", "index": 0},
                        {"node": "Has customer_id?", "type": "main", "index": 0},
                    ]
                ]
            },
            "Create Airtable Master": {
                "main": [
                    [
                        {"node": "Update PG Airtable ID", "type": "main", "index": 0},
                    ]
                ]
            },
            # Shopify branch: direct (has CID)
            "Has customer_id?": {
                "main": [
                    [{"node": "Build Metafields (Direct)", "type": "main", "index": 0}],
                    [{"node": "Search Shopify", "type": "main", "index": 0}],
                ]
            },
            "Build Metafields (Direct)": {
                "main": [[{"node": "Save Metafields (Direct)", "type": "main", "index": 0}]]
            },
            # Shopify branch: search → found or create
            "Search Shopify": {
                "main": [[{"node": "Parse Search Result", "type": "main", "index": 0}]]
            },
            "Parse Search Result": {
                "main": [[{"node": "Customer Found?", "type": "main", "index": 0}]]
            },
            "Customer Found?": {
                "main": [
                    [{"node": "Build Metafields (Found)", "type": "main", "index": 0}],
                    [{"node": "Create Shopify Account", "type": "main", "index": 0}],
                ]
            },
            "Build Metafields (Found)": {
                "main": [[{"node": "Save Metafields (Found)", "type": "main", "index": 0}]]
            },
            "Save Metafields (Found)": {
                "main": [[{"node": "Update Airtable CID (Found)", "type": "main", "index": 0}]]
            },
            "Create Shopify Account": {
                "main": [[{"node": "Build Metafields (New)", "type": "main", "index": 0}]]
            },
            "Build Metafields (New)": {
                "main": [[{"node": "New Account Created?", "type": "main", "index": 0}]]
            },
            "New Account Created?": {
                "main": [
                    [
                        {"node": "Save Metafields (New)", "type": "main", "index": 0},
                        {"node": "Update Airtable CID (New)", "type": "main", "index": 0},
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Core Signup -> Master")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set")
        sys.exit(1)

    missing = []
    if not AIRTABLE_API_KEY:
        missing.append("AIRTABLE_API_KEY")
    if not CUSTOMERS_TABLE_ID:
        missing.append("AIRTABLE_CUSTOMERS_TABLE_ID")
    if not SHOPIFY_TOKEN:
        missing.append("SHOPIFY_ACCESS_TOKEN")
    if missing:
        print(f"[WARN] Missing env vars: {', '.join(missing)}")
        if not args.dry_run:
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Airtable Master Table: {CUSTOMERS_TABLE_ID}")
    print(f"  Shopify: {SHOPIFY_SHOP}")
    print(f"{'=' * 60}\n")

    existing = find_existing_workflow()
    if existing:
        wf_id = existing["id"]
        print(f"  [FOUND] Existing workflow (ID: {wf_id})")

        if args.dry_run:
            wf_def = build_workflow()
            print(f"  [DRY RUN] Would update workflow {wf_id}")
            print(f"  Nodes: {len(wf_def['nodes'])}")
            for n in wf_def["nodes"]:
                print(f"    - {n['name']} ({n['type']})")
            return

        wf_def = build_workflow()
        n8n_request("PUT", f"/workflows/{wf_id}", wf_def)
        print(f"  [OK] Updated workflow")
    else:
        print(f"  [NEW] Creating workflow: {WORKFLOW_NAME}")

        if args.dry_run:
            wf_def = build_workflow()
            print(f"  [DRY RUN] Would create workflow")
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

    webhook_url = f"{N8N_BASE_URL}/webhook/onzenna-core-signup"
    print(f"\n  Webhook URL: {webhook_url}")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
