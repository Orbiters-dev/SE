"""
Create n8n WF: "Onzenna: Accept -> Complete Draft Order"
Poll AT Creators for Accepted status → PG lookup → Shopify complete.json → AT update

Usage:
    python tools/create_accept_complete_wf.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

# ── env ──────────────────────────────────────────────────────────────────────
def load_env(path=None):
    env = {}
    for fp in [path or os.path.expanduser("~/.wat_secrets"), ".env"]:
        if os.path.exists(fp):
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip()
    return env

ENV = load_env()
N8N_BASE = ENV.get("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
N8N_KEY  = ENV.get("N8N_API_KEY", "")

AT_KEY            = ENV.get("AT_API_KEY_PATHLIGHT", "")
AT_BASE_CREATORS  = "app3Vnmh7hLAVsevE"   # Pathlight CRM
AT_TABLE_CREATORS = "tblRkxdILAVnR0ONX"   # Creators table

ORBITOOLS_URL     = ENV.get("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER    = ENV.get("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS    = ENV.get("ORBITOOLS_PASS", "admin")

SHOPIFY_SHOP      = ENV.get("SHOPIFY_SHOP", "mytoddie.myshopify.com")
SHOPIFY_TOKEN     = ENV.get("SHOPIFY_ACCESS_TOKEN", "")

# ── WF JSON ───────────────────────────────────────────────────────────────────
def build_workflow():
    wf = {
        "name": "Onzenna: Accept -> Complete Draft Order",
        "nodes": [
            # 0. Schedule trigger (every 5 min)
            {
                "id": "node-schedule",
                "name": "Every 5 Minutes",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [240, 300],
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": 5}]
                    }
                }
            },
            # 1. Get Accepted creators from Airtable
            {
                "id": "node-at-get",
                "name": "AT: Get Accepted Creators",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [460, 300],
                "parameters": {
                    "method": "GET",
                    "url": f"https://api.airtable.com/v0/{AT_BASE_CREATORS}/{AT_TABLE_CREATORS}",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpHeaderAuth",
                    "sendQuery": True,
                    "queryParameters": {
                        "parameters": [
                            {
                                "name": "filterByFormula",
                                "value": "AND({Outreach Status}='Accepted',OR({Partnership Status}='',{Partnership Status}!='Order Placed'))"
                            },
                            {"name": "fields[]", "value": "Name"},
                            {"name": "fields[]", "value": "Email"},
                            {"name": "fields[]", "value": "Outreach Status"},
                            {"name": "fields[]", "value": "Partnership Status"},
                            {"name": "maxRecords", "value": "50"}
                        ]
                    },
                    "options": {}
                },
                "credentials": {
                    "httpHeaderAuth": {
                        "id": "at-pathlight-auth",
                        "name": "Airtable Pathlight"
                    }
                }
            },
            # 2. Split into items
            {
                "id": "node-split",
                "name": "Split Records",
                "type": "n8n-nodes-base.splitInBatches",
                "typeVersion": 3,
                "position": [680, 300],
                "parameters": {
                    "batchSize": 1,
                    "options": {}
                }
            },
            # 3. Check if any records found
            {
                "id": "node-if-records",
                "name": "Has Records?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [900, 300],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "conditions": [
                            {
                                "leftValue": "={{ $json.records.length }}",
                                "rightValue": 0,
                                "operator": {"type": "number", "operation": "gt"}
                            }
                        ],
                        "combinator": "and"
                    }
                }
            },
            # 4. Extract email + record id from AT response
            {
                "id": "node-extract",
                "name": "Extract Creator Info",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [1120, 200],
                "parameters": {
                    "mode": "manual",
                    "duplicateItem": True,
                    "include": "none",
                    "assignments": {
                        "assignments": [
                            {"name": "at_record_id", "value": "={{ $json.id }}", "type": "string"},
                            {"name": "creator_email", "value": "={{ $json.fields.Email }}", "type": "string"},
                            {"name": "creator_name", "value": "={{ $json.fields.Name }}", "type": "string"}
                        ]
                    }
                }
            },
            # Note: For the split approach, after AT response we iterate records array
            # 4b. Loop over records array
            {
                "id": "node-code-extract",
                "name": "Prepare Records",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1120, 200],
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": (
                        "const records = $input.first().json.records || [];\n"
                        "return records.map(r => ({\n"
                        "  json: {\n"
                        "    at_record_id: r.id,\n"
                        "    creator_email: r.fields['Email'] || '',\n"
                        "    creator_name: r.fields['Name'] || ''\n"
                        "  }\n"
                        "}));"
                    )
                }
            },
            # 5. Query PG for draft_order_id
            {
                "id": "node-pg-lookup",
                "name": "PG: Get Draft Order ID",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1340, 200],
                "parameters": {
                    "method": "GET",
                    "url": f"{ORBITOOLS_URL}/api/onzenna/gifting/list/",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpBasicAuth",
                    "sendQuery": True,
                    "queryParameters": {
                        "parameters": [
                            {"name": "email", "value": "={{ $json.creator_email }}"}
                        ]
                    },
                    "options": {}
                },
                "credentials": {
                    "httpBasicAuth": {
                        "id": "orbitools-basic",
                        "name": "Orbitools Basic Auth"
                    }
                }
            },
            # 6. Extract draft_order_id
            {
                "id": "node-code-draft",
                "name": "Extract Draft Order ID",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1560, 200],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": (
                        "const prev = $('Prepare Records').item.json;\n"
                        "const apps = $input.item.json;\n"
                        "// PG returns list, find latest with shopify_draft_order_id\n"
                        "const list = Array.isArray(apps) ? apps : (apps.results || []);\n"
                        "const match = list.find(a => a.shopify_draft_order_id);\n"
                        "return {\n"
                        "  json: {\n"
                        "    at_record_id: prev.at_record_id,\n"
                        "    creator_email: prev.creator_email,\n"
                        "    creator_name: prev.creator_name,\n"
                        "    draft_order_id: match ? match.shopify_draft_order_id : null\n"
                        "  }\n"
                        "};"
                    )
                }
            },
            # 7. Check if draft_order_id found
            {
                "id": "node-if-draft",
                "name": "Has Draft Order?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [1780, 200],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True},
                        "conditions": [
                            {
                                "leftValue": "={{ $json.draft_order_id }}",
                                "rightValue": "",
                                "operator": {"type": "string", "operation": "notEmpty"}
                            }
                        ],
                        "combinator": "and"
                    }
                }
            },
            # 8. Shopify: complete the draft order
            {
                "id": "node-shopify-complete",
                "name": "Shopify: Complete Draft Order",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2000, 100],
                "parameters": {
                    "method": "POST",
                    "url": f"https://{SHOPIFY_SHOP}/admin/api/2023-10/draft_orders/={{{{$json.draft_order_id}}}}/complete.json",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpHeaderAuth",
                    "sendBody": True,
                    "contentType": "json",
                    "body": {
                        "mode": "raw",
                        "raw": "{\"payment_pending\": false}"
                    },
                    "options": {}
                },
                "credentials": {
                    "httpHeaderAuth": {
                        "id": "shopify-admin-auth",
                        "name": "Shopify Admin API Token"
                    }
                }
            },
            # 9. AT: Update Partnership Status = Order Placed
            {
                "id": "node-at-update",
                "name": "AT: Set Order Placed",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [2220, 100],
                "parameters": {
                    "method": "PATCH",
                    "url": f"https://api.airtable.com/v0/{AT_BASE_CREATORS}/{AT_TABLE_CREATORS}/={{{{$('Extract Draft Order ID').item.json.at_record_id}}}}",
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpHeaderAuth",
                    "sendBody": True,
                    "contentType": "json",
                    "body": {
                        "mode": "raw",
                        "raw": "{\"fields\": {\"Partnership Status\": \"Order Placed\"}}"
                    },
                    "options": {}
                },
                "credentials": {
                    "httpHeaderAuth": {
                        "id": "at-pathlight-auth",
                        "name": "Airtable Pathlight"
                    }
                }
            },
            # 10. No draft order found - log
            {
                "id": "node-no-draft",
                "name": "No Draft Order (Skip)",
                "type": "n8n-nodes-base.noOp",
                "typeVersion": 1,
                "position": [2000, 320],
                "parameters": {}
            }
        ],
        "connections": {
            "Every 5 Minutes": {
                "main": [[{"node": "AT: Get Accepted Creators", "type": "main", "index": 0}]]
            },
            "AT: Get Accepted Creators": {
                "main": [[{"node": "Has Records?", "type": "main", "index": 0}]]
            },
            "Has Records?": {
                "main": [
                    [{"node": "Prepare Records", "type": "main", "index": 0}],
                    []
                ]
            },
            "Prepare Records": {
                "main": [[{"node": "PG: Get Draft Order ID", "type": "main", "index": 0}]]
            },
            "PG: Get Draft Order ID": {
                "main": [[{"node": "Extract Draft Order ID", "type": "main", "index": 0}]]
            },
            "Extract Draft Order ID": {
                "main": [[{"node": "Has Draft Order?", "type": "main", "index": 0}]]
            },
            "Has Draft Order?": {
                "main": [
                    [{"node": "Shopify: Complete Draft Order", "type": "main", "index": 0}],
                    [{"node": "No Draft Order (Skip)", "type": "main", "index": 0}]
                ]
            },
            "Shopify: Complete Draft Order": {
                "main": [[{"node": "AT: Set Order Placed", "type": "main", "index": 0}]]
            }
        },
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "callerPolicy": "workflowsFromSameOwner",
            "errorWorkflow": ""
        }
    }
    return wf


def n8n_post(path, payload):
    url = f"{N8N_BASE}/api/v1{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "X-N8N-API-KEY": N8N_KEY,
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[HTTP {e.code}] {body[:400]}")
        raise


def main():
    if not N8N_KEY:
        print("N8N_API_KEY not found in ~/.wat_secrets")
        sys.exit(1)

    print("Building WF JSON...")
    wf = build_workflow()

    print("Posting to n8n PROD...")
    result = n8n_post("/workflows", wf)

    wf_id   = result.get("id", "?")
    wf_name = result.get("name", "?")
    print(f"\n✅ Created WF: {wf_id}")
    print(f"   Name: {wf_name}")
    print(f"   URL:  {N8N_BASE}/workflow/{wf_id}")
    print()
    print("NOTE: WF is created as INACTIVE (draft).")
    print("Activate manually after verifying credentials are set:")
    print("  - 'Airtable Pathlight' credential (HTTP Header: Authorization: Bearer <AT_KEY>)")
    print("  - 'Orbitools Basic Auth' credential (user/pass)")
    print("  - 'Shopify Admin API Token' credential (X-Shopify-Access-Token: <token>)")
    print()
    print(f"Activate: POST {N8N_BASE}/api/v1/workflows/{wf_id}/activate")


if __name__ == "__main__":
    main()
