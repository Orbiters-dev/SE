"""Create n8n workflow: Creator Signup -> Airtable + Instagram Scrape.

Workflow nodes:
  Webhook (POST) -> Parse Payload -> Create Airtable Record
                                  -> Instagram Scrape -> Update Airtable

Usage:
    python tools/setup_n8n_creator_to_airtable.py
    python tools/setup_n8n_creator_to_airtable.py --dry-run

Prerequisites:
    .wat_secrets: N8N_API_KEY, N8N_BASE_URL, AIRTABLE_API_KEY,
                  AIRTABLE_INBOUND_BASE_ID, AIRTABLE_INBOUND_TABLE_ID,
                  META_ACCESS_TOKEN, INSTAGRAM_BUSINESS_USER_ID
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
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_INBOUND_BASE_ID", "")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_INBOUND_TABLE_ID", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("INSTAGRAM_BUSINESS_USER_ID", "")
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "toddie-4080.myshopify.com")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

WORKFLOW_NAME = "Onzenna: Creator Signup -> Airtable"


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
    airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    shopify_metafields_url = f"https://{SHOPIFY_SHOP}/admin/api/2024-01/customers"

    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Webhook trigger
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "onzenna-creator-to-airtable",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "id": "webhook-trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "onzenna-creator-to-airtable",
            },
            # 2. Parse payload (extract creator-signup data + any core-signup data from form)
            {
                "parameters": {
                    "jsCode": """// Parse creator signup payload
const payload = $input.first().json.body || $input.first().json;

const customerName = payload.customer_name || '';
const customerEmail = payload.customer_email || '';
const customerId = payload.customer_id || null;
const submittedAt = payload.submitted_at || new Date().toISOString();
const surveyData = payload.survey_data || {};
const coreSignupData = payload.core_signup_data || {};

// Extract Instagram/TikTok handles
let igHandle = '';
let tiktokHandle = '';
const primaryPlatform = surveyData.primary_platform || '';
const primaryHandle = surveyData.primary_handle || '';

if (primaryPlatform === 'instagram') {
  igHandle = primaryHandle;
} else if (primaryPlatform === 'tiktok') {
  tiktokHandle = primaryHandle;
}

// Check other_platforms for additional handles
const otherPlatforms = surveyData.other_platforms || [];
const otherHandles = surveyData.other_handles || [];
if (Array.isArray(otherPlatforms)) {
  otherPlatforms.forEach((p, i) => {
    const h = otherHandles[i] || '';
    if (p === 'instagram' && !igHandle) igHandle = h;
    if (p === 'tiktok' && !tiktokHandle) tiktokHandle = h;
  });
}

// Content type: array -> multiselect
let contentType = surveyData.content_type || [];
if (typeof contentType === 'string') {
  try { contentType = JSON.parse(contentType); } catch(e) { contentType = [contentType]; }
}

// Build fields, filtering out null/empty values (Airtable rejects nulls)
const rawFields = {
  "Name": customerName || null,
  "Email": customerEmail || null,
  "Instagram Handle": igHandle.replace(/^@/, '') || null,
  "TikTok Handle": tiktokHandle.replace(/^@/, '') || null,
  "Primary Platform": primaryPlatform || null,
  "Following Size (Self-reported)": surveyData.following_size || null,
  "Content Type": contentType.length > 0 ? contentType : null,
  "Has Brand Partnerships": surveyData.has_brand_partnerships || null,
  "Brand Names": surveyData.brand_names || null,
  "Journey Stage": coreSignupData.journey_stage || null,
  "Baby Birth Month": coreSignupData.baby_birth_month || null,
  "Shopify Customer ID": customerId,
  "Status": "New",
  "Submitted At": submittedAt,
};

// Remove null/undefined/empty string values
const airtable_fields = {};
for (const [k, v] of Object.entries(rawFields)) {
  if (v !== null && v !== undefined && v !== '') {
    airtable_fields[k] = v;
  }
}

return [{
  json: {
    airtable_fields,
    ig_handle: igHandle.replace(/^@/, ''),
    tiktok_handle: tiktokHandle.replace(/^@/, ''),
    customer_id: customerId,
    has_core_data: !!(coreSignupData.journey_stage || coreSignupData.baby_birth_month),
  }
}];"""
                },
                "id": "code-parse",
                "name": "Parse Payload",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [420, 300],
            },
            # 3. Check if we need to fetch core-signup data from Shopify
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "cid-check",
                                "leftValue": "={{ $json.customer_id }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "notEmpty"},
                            },
                            {
                                "id": "no-core-data",
                                "leftValue": "={{ $json.has_core_data }}",
                                "rightValue": "false",
                                "operator": {"type": "boolean", "operation": "false"},
                            },
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-need-metafields",
                "name": "Need Shopify Metafields?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [640, 300],
            },
            # 4a. Fetch customer metafields from Shopify
            {
                "parameters": {
                    "method": "GET",
                    "url": f"={shopify_metafields_url}/{{{{$('Parse Payload').first().json.customer_id}}}}/metafields.json?namespace=onzenna_survey",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "X-Shopify-Access-Token", "value": SHOPIFY_TOKEN},
                        ]
                    },
                    "options": {"timeout": 15000},
                },
                "id": "http-shopify-metafields",
                "name": "Fetch Shopify Metafields",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [880, 240],
                "onError": "continueRegularOutput",
            },
            # 4b. Merge metafield data into airtable_fields
            {
                "parameters": {
                    "jsCode": """// Merge core-signup metafields into airtable fields
const parsed = $('Parse Payload').first().json;
const fields = { ...parsed.airtable_fields };

// Extract onzenna_survey metafields from Shopify response
const metafields = $input.first().json.metafields || [];
for (const mf of metafields) {
  if (mf.namespace !== 'onzenna_survey') continue;
  if (mf.key === 'journey_stage' && !fields['Journey Stage']) {
    fields['Journey Stage'] = mf.value;
  }
  if (mf.key === 'baby_birth_month' && !fields['Baby Birth Month']) {
    fields['Baby Birth Month'] = mf.value;
  }
}

return [{
  json: {
    airtable_fields: fields,
    ig_handle: parsed.ig_handle,
    tiktok_handle: parsed.tiktok_handle,
    customer_id: parsed.customer_id,
  }
}];"""
                },
                "id": "code-merge-metafields",
                "name": "Merge Core Data",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1100, 240],
            },
            # 4c. Pass-through when no metafield fetch needed
            {
                "parameters": {
                    "jsCode": """// Pass through existing parsed data as-is
const parsed = $('Parse Payload').first().json;
return [{
  json: {
    airtable_fields: parsed.airtable_fields,
    ig_handle: parsed.ig_handle,
    tiktok_handle: parsed.tiktok_handle,
    customer_id: parsed.customer_id,
  }
}];"""
                },
                "id": "code-passthrough",
                "name": "Use Form Data",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [880, 420],
            },
            # 5. Create Airtable record
            {
                "parameters": {
                    "method": "POST",
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
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "fields": $json.airtable_fields }], "typecast": true }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-create",
                "name": "Create Airtable Record",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1320, 300],
            },
            # 6. Respond OK
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ JSON.stringify({ success: true, message: "Creator added to Airtable" }) }}',
                    "options": {},
                },
                "id": "respond-ok",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1540, 200],
            },
            # 7. Instagram scrape conditional
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "conditions": [
                            {
                                "id": "ig-check",
                                "leftValue": "={{ $('Parse Payload').first().json.ig_handle }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "notEmpty"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-has-ig",
                "name": "Has IG Handle?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [1540, 440],
            },
            # 8. Instagram Graph API call (non-blocking on error)
            {
                "parameters": {
                    "method": "GET",
                    "url": f"=https://graph.facebook.com/v21.0/{IG_USER_ID}",
                    "authentication": "none",
                    "sendQuery": True,
                    "queryParameters": {
                        "parameters": [
                            {
                                "name": "fields",
                                "value": "=business_discovery.username({{ $('Parse Payload').first().json.ig_handle }}){followers_count,media_count,biography,username,name}",
                            },
                            {"name": "access_token", "value": META_ACCESS_TOKEN},
                        ]
                    },
                    "options": {"timeout": 30000},
                },
                "id": "http-ig-scrape",
                "name": "Scrape Instagram",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1760, 380],
                "onError": "continueRegularOutput",
            },
            # 9. Extract IG metrics
            {
                "parameters": {
                    "jsCode": """// Extract IG metrics from business_discovery response
const bd = $input.first().json.business_discovery || {};

// Get Airtable record ID
let recordId = null;
try {
  const airtableResp = $('Create Airtable Record').first().json;
  recordId = (airtableResp.records && airtableResp.records[0])
    ? airtableResp.records[0].id : null;
} catch(e) {}

const igFollowers = bd.followers_count || 0;
const igMediaCount = bd.media_count || 0;

if (!recordId || igFollowers === 0) {
  return [{ json: { skip_update: true } }];
}

return [{
  json: {
    record_id: recordId,
    ig_followers: igFollowers,
    ig_media_count: igMediaCount,
    skip_update: false,
  }
}];"""
                },
                "id": "code-extract-ig",
                "name": "Extract IG Metrics",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1980, 380],
            },
            # 10. Check if we should update Airtable
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "skip-check",
                                "leftValue": "={{ $json.skip_update }}",
                                "rightValue": "false",
                                "operator": {"type": "boolean", "operation": "false"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-should-update",
                "name": "Has IG Data?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [2200, 380],
            },
            # 11. Update Airtable with IG metrics
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
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "id": $json.record_id, "fields": { "IG Followers (Scraped)": $json.ig_followers, "IG Media Count": $json.ig_media_count } }] }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-update",
                "name": "Update Airtable (IG)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2420, 320],
            },
            # === NEW: Email-based Shopify lookup + metafield save ===
            # 12. Check if we have email but no customer_id
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": "email-check",
                                "leftValue": "={{ $('Parse Payload').first().json.airtable_fields.Email }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "notEmpty"},
                            },
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-has-email",
                "name": "Has Email?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [1540, 640],
            },
            # 13. Search Shopify customer by email
            {
                "parameters": {
                    "method": "GET",
                    "url": f"=https://{SHOPIFY_SHOP}/admin/api/2024-01/customers/search.json?query=email:{{{{$('Parse Payload').first().json.airtable_fields.Email}}}}",
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
                "name": "Search Shopify Customer",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1760, 640],
                "onError": "continueRegularOutput",
            },
            # 14. Build metafields and save to Shopify + update Airtable
            {
                "parameters": {
                    "jsCode": """// Find customer from search results and build metafields
const customers = $input.first().json.customers || [];
if (customers.length === 0) {
  return [{ json: { found: false } }];
}

const customer = customers[0];
const cid = customer.id;
const parsed = $('Parse Payload').first().json;
const fields = parsed.airtable_fields || {};
const sd = $('Webhook').first().json.body || $('Webhook').first().json;
const surveyData = sd.survey_data || {};
const coreData = sd.core_signup_data || {};

// Build metafields for both namespaces
const metafields = [];

// Core signup data -> onzenna_survey namespace
if (coreData.journey_stage) {
  metafields.push({ namespace: 'onzenna_survey', key: 'journey_stage', value: String(coreData.journey_stage), type: 'single_line_text_field' });
}
if (coreData.baby_birth_month) {
  metafields.push({ namespace: 'onzenna_survey', key: 'baby_birth_month', value: String(coreData.baby_birth_month), type: 'single_line_text_field' });
}
if (coreData.has_other_children !== null && coreData.has_other_children !== undefined) {
  metafields.push({ namespace: 'onzenna_survey', key: 'has_other_children', value: String(coreData.has_other_children), type: 'boolean' });
}
if (coreData.other_child_birth) {
  metafields.push({ namespace: 'onzenna_survey', key: 'other_child_birth', value: String(coreData.other_child_birth), type: 'single_line_text_field' });
}

// Creator signup data -> onzenna_creator namespace
if (surveyData.primary_platform) {
  metafields.push({ namespace: 'onzenna_creator', key: 'primary_platform', value: surveyData.primary_platform, type: 'single_line_text_field' });
}
if (surveyData.primary_handle) {
  metafields.push({ namespace: 'onzenna_creator', key: 'primary_handle', value: surveyData.primary_handle, type: 'single_line_text_field' });
}
if (surveyData.following_size) {
  metafields.push({ namespace: 'onzenna_creator', key: 'following_size', value: surveyData.following_size, type: 'single_line_text_field' });
}
if (surveyData.content_type && surveyData.content_type.length > 0) {
  metafields.push({ namespace: 'onzenna_creator', key: 'content_type', value: JSON.stringify(surveyData.content_type), type: 'json' });
}
if (surveyData.has_brand_partnerships) {
  metafields.push({ namespace: 'onzenna_creator', key: 'has_brand_partnerships', value: surveyData.has_brand_partnerships, type: 'single_line_text_field' });
}
if (surveyData.brand_names) {
  metafields.push({ namespace: 'onzenna_creator', key: 'brand_names', value: surveyData.brand_names, type: 'single_line_text_field' });
}

// Add completed_at timestamps
metafields.push({ namespace: 'onzenna_creator', key: 'creator_completed_at', value: new Date().toISOString(), type: 'date_time' });

// Get Airtable record ID for updating
let recordId = null;
try {
  const airtableResp = $('Create Airtable Record').first().json;
  recordId = (airtableResp.records && airtableResp.records[0]) ? airtableResp.records[0].id : null;
} catch(e) {}

return [{
  json: {
    found: true,
    customer_id: cid,
    record_id: recordId,
    metafields: metafields,
    shopify_body: { customer: { id: cid, metafields: metafields } },
  }
}];"""
                },
                "id": "code-build-save",
                "name": "Build Metafields",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1980, 640],
            },
            # 15. Check if customer was found
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
                "id": "if-customer-found",
                "name": "Customer Found?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [2200, 640],
            },
            # 16. Save metafields to Shopify
            {
                "parameters": {
                    "method": "PUT",
                    "url": f"=https://{SHOPIFY_SHOP}/admin/api/2024-01/customers/{{{{$json.customer_id}}}}.json",
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
                "id": "http-shopify-save-mf",
                "name": "Save Metafields",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2420, 580],
                "onError": "continueRegularOutput",
            },
            # 17. Update Airtable with found customer_id
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
                    "jsonBody": '={{ JSON.stringify({ "records": [{ "id": $("Build Metafields").first().json.record_id, "fields": { "Shopify Customer ID": $("Build Metafields").first().json.customer_id } }] }) }}',
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-update-cid",
                "name": "Update Airtable (CID)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2640, 580],
                "onError": "continueRegularOutput",
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Parse Payload", "type": "main", "index": 0}]]
            },
            "Parse Payload": {
                "main": [[{"node": "Need Shopify Metafields?", "type": "main", "index": 0}]]
            },
            "Need Shopify Metafields?": {
                "main": [
                    [{"node": "Fetch Shopify Metafields", "type": "main", "index": 0}],
                    [{"node": "Use Form Data", "type": "main", "index": 0}],
                ]
            },
            "Fetch Shopify Metafields": {
                "main": [[{"node": "Merge Core Data", "type": "main", "index": 0}]]
            },
            "Merge Core Data": {
                "main": [[{"node": "Create Airtable Record", "type": "main", "index": 0}]]
            },
            "Use Form Data": {
                "main": [[{"node": "Create Airtable Record", "type": "main", "index": 0}]]
            },
            "Create Airtable Record": {
                "main": [
                    [
                        {"node": "Respond OK", "type": "main", "index": 0},
                        {"node": "Has IG Handle?", "type": "main", "index": 0},
                        {"node": "Has Email?", "type": "main", "index": 0},
                    ]
                ]
            },
            "Has IG Handle?": {
                "main": [
                    [{"node": "Scrape Instagram", "type": "main", "index": 0}],
                    [],
                ]
            },
            "Scrape Instagram": {
                "main": [[{"node": "Extract IG Metrics", "type": "main", "index": 0}]]
            },
            "Extract IG Metrics": {
                "main": [[{"node": "Has IG Data?", "type": "main", "index": 0}]]
            },
            "Has IG Data?": {
                "main": [
                    [{"node": "Update Airtable (IG)", "type": "main", "index": 0}],
                    [],
                ]
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
                    [{"node": "Save Metafields", "type": "main", "index": 0}],
                    [],
                ]
            },
            "Save Metafields": {
                "main": [[{"node": "Update Airtable (CID)", "type": "main", "index": 0}]]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Creator Signup -> Airtable")
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
    if missing:
        print(f"[WARN] Missing env vars: {', '.join(missing)}")
        print("  Run setup_airtable_inbound.py first, then add the IDs to ~/.wat_secrets")
        if not args.dry_run:
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Airtable Base: {AIRTABLE_BASE_ID or '(not set)'}")
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

    webhook_url = f"{N8N_BASE_URL}/webhook/onzenna-creator-to-airtable"
    print(f"\n  Webhook URL: {webhook_url}")
    print(f"\n  Add to ~/.wat_secrets:")
    print(f"    N8N_CREATOR_AIRTABLE_WEBHOOK={webhook_url}")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
