"""Create n8n workflow: Airtable Creator Update -> PostgreSQL Enriched.

Polls Airtable every 5 minutes for recently modified records.
Calls orbitools API to upsert the enriched data into onzenna_creator_enriched table.

No Airtable automation setup required - fully automatic.

Usage:
    python tools/setup_n8n_airtable_to_postgres.py
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

WORKFLOW_NAME = "Onzenna: Airtable Update -> PostgreSQL Enriched"
ORBITOOLS_ENDPOINT = "https://orbitools.orbiters.co.kr/api/onzenna/creators/update/"
ORBITOOLS_CRED_ID = "mF9WJI64MUwl0gSU"
ORBITOOLS_CRED_NAME = "MVP module admin auth"

AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"


def n8n_request(method, path, body=None):
    url = f"{N8N_BASE_URL}/api/v1/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "X-N8N-API-KEY": N8N_API_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"n8n API error {e.code}: {err}")


def get_existing_workflow():
    resp = n8n_request("GET", "workflows?limit=50")
    for wf in resp.get("data", []):
        if wf["name"] == WORKFLOW_NAME:
            return wf["id"]
    return None


def build_workflow():
    # Airtable formula: records modified in last 10 minutes
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
                            {
                                "name": "Authorization",
                                "value": f"Bearer {AIRTABLE_API_KEY}",
                            }
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
            # 3. Split records and map to orbitools format
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
      status: f['Status'] || f['status'] || null,
      notes: f['Notes'] || f['notes'] || null,
      tags: f['Tags'] || f['tags'] || null,
      fields: f,
    }
  };
}).filter(item => item.json.email);""",
                },
                "id": "code-map-records",
                "name": "Map Records",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [680, 300],
            },
            # 4. Check if email exists (skip empty results)
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
            # 5. Save enriched data to orbitools -> PostgreSQL
            {
                "parameters": {
                    "method": "POST",
                    "url": ORBITOOLS_ENDPOINT,
                    "authentication": "genericCredentialType",
                    "genericAuthType": "httpBasicAuth",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json) }}",
                    "options": {"timeout": 15000},
                },
                "credentials": {
                    "httpBasicAuth": {
                        "id": ORBITOOLS_CRED_ID,
                        "name": ORBITOOLS_CRED_NAME,
                    }
                },
                "id": "http-orbitools-save-enriched",
                "name": "Save to Orbitools (Enriched)",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1120, 200],
                "onError": "continueRegularOutput",
            },
        ],
        "connections": {
            "Schedule Trigger": {
                "main": [[{"node": "Fetch Airtable Records", "type": "main", "index": 0}]]
            },
            "Fetch Airtable Records": {
                "main": [[{"node": "Map Records", "type": "main", "index": 0}]]
            },
            "Map Records": {
                "main": [[{"node": "Has Email?", "type": "main", "index": 0}]]
            },
            "Has Email?": {
                "main": [
                    [{"node": "Save to Orbitools (Enriched)", "type": "main", "index": 0}],
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Airtable -> PostgreSQL Enriched (polling)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set")
        sys.exit(1)
    if not AIRTABLE_API_KEY:
        print("[ERROR] AIRTABLE_API_KEY not set")
        sys.exit(1)
    if not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_ID:
        print("[ERROR] AIRTABLE_INBOUND_BASE_ID or AIRTABLE_INBOUND_TABLE_ID not set")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Mode: Polling (every 5 min, no Airtable automation needed)")
    print(f"{'=' * 60}\n")

    wf = build_workflow()

    if args.dry_run:
        print("[DRY RUN] Workflow JSON:")
        print(json.dumps(wf, indent=2, ensure_ascii=False))
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
    print(f"  Fetches: Airtable records modified in last 10 min")
    print(f"  Saves to: {ORBITOOLS_ENDPOINT}")
    print(f"\n{'=' * 60}")
    print("  DONE - No Airtable automation needed!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
