"""Create n8n workflow: Poll Airtable for Accepted creators -> Send sample form email.

Workflow nodes:
  Schedule (every 3 min) -> Query Airtable (Accepted + not sent) -> Loop each
    -> Send Email -> Update Airtable (Sample Form Sent = true)

Usage:
    python tools/setup_n8n_accepted_email.py
    python tools/setup_n8n_accepted_email.py --dry-run

Prerequisites:
    .wat_secrets: N8N_API_KEY, N8N_BASE_URL, AIRTABLE_API_KEY,
                  AIRTABLE_INBOUND_BASE_ID, AIRTABLE_INBOUND_TABLE_ID
    n8n: SMTP credentials configured (or will use n8n default email)
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

WORKFLOW_NAME = "Onzenna: Accepted Creator -> Email Sample Form"
SAMPLE_FORM_BASE_URL = "https://onzenna.com/pages/creator-sample-form"



def find_existing_workflow():
    result = n8n_request("GET", "/workflows?limit=100")
    for wf in result.get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf
    return None


def build_workflow():
    import urllib.parse as _up
    filter_formula = 'AND(FIND("Accept",ARRAYJOIN({MKT action: Send Sample form})),{Status}!="Accepted")'
    airtable_base_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    airtable_query_url = (
        airtable_base_url
        + f"?filterByFormula={_up.quote(filter_formula)}&maxRecords=10"
    )

    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Schedule trigger - every 3 minutes
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": 3}]
                    },
                },
                "id": "schedule-trigger",
                "name": "Every 3 Minutes",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [200, 300],
            },
            # 2. Query Airtable for accepted + not sent
            {
                "parameters": {
                    "method": "GET",
                    "url": airtable_query_url,
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                        ]
                    },
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-query",
                "name": "Query Accepted Creators",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [420, 300],
            },
            # 3. Check if any records found
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "conditions": [
                            {
                                "id": "has-records",
                                "leftValue": "={{ $json.records.length }}",
                                "rightValue": 0,
                                "operator": {"type": "number", "operation": "gt"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-has-records",
                "name": "Has Records?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.2,
                "position": [640, 300],
            },
            # 4. Split into individual records
            {
                "parameters": {
                    "jsCode": """// Split Airtable records into individual items
const records = $input.first().json.records || [];
return records.map(rec => ({
  json: {
    record_id: rec.id,
    name: rec.fields['Name'] || 'Creator',
    email: rec.fields['Email'] || '',
    customer_id: rec.fields['Shopify Customer ID'] || '',
    ig_handle: rec.fields['Instagram Handle'] || '',
    platform: rec.fields['Primary Platform'] || '',
    baby_birth_month: rec.fields['Baby Birth Month'] || '',
  }
}));"""
                },
                "id": "code-split",
                "name": "Split Records",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [860, 240],
            },
            # 5. Send email via Gmail
            {
                "parameters": {
                    "sendTo": "={{ $json.email }}",
                    "subject": "You're an Onzenna Creator! Choose your free samples",
                    "message": f"""=<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <img src="https://cdn.shopify.com/s/files/1/0915/8367/5058/files/onzenna-logo-dark.png" alt="Onzenna" style="height: 40px; margin-bottom: 24px; display: block;" />

  <h2 style="color: #333; font-size: 22px;">Congratulations, {{{{ $json.name }}}}!</h2>

  <p style="color: #555; font-size: 15px; line-height: 1.6;">
    You've been selected as an <strong>Onzenna Creator</strong>!
  </p>

  <p style="color: #555; font-size: 15px; line-height: 1.6;">
    Please choose your free sample products by clicking the button below. It only takes a minute — just pick your samples and agree to the collaboration terms.
  </p>

  <div style="text-align: center; margin: 32px 0;">
    <a href="{SAMPLE_FORM_BASE_URL}?email={{{{ encodeURIComponent($json.email) }}}}&cid={{{{ $json.customer_id }}}}&age={{{{ encodeURIComponent($json.baby_birth_month) }}}}"
       style="display: inline-block; padding: 14px 36px; background: #333; color: #fff; text-decoration: none; border-radius: 5px; font-size: 15px; font-weight: 600;">
      Choose Your Samples
    </a>
  </div>

  <p style="color: #555; font-size: 14px; line-height: 1.6;">
    Products will be selected based on your child's age. Once submitted, we'll ship your samples right away!
  </p>

  <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />

  <p style="color: #999; font-size: 12px;">
    Welcome to the Onzenna family!<br/>
    - The Onzenna Team
  </p>
</div>""",
                    "options": {},
                },
                "id": "send-email",
                "name": "Send Sample Form Email",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [1080, 240],
                "credentials": {
                    "gmailOAuth2": {
                        "id": "ZSCspnGLmbDXJMBu",
                        "name": "Onzenna Gmail (affiliates@onzenna.com)"
                    }
                },
            },
            # 6. Update Airtable - mark as sent
            {
                "parameters": {
                    "method": "PATCH",
                    "url": airtable_base_url,
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify({ \"records\": [{ \"id\": $('Split Records').item.json.record_id, \"fields\": { \"Status\": \"Accepted\" } }] }) }}",
                    "options": {"timeout": 30000},
                },
                "id": "http-airtable-update",
                "name": "Mark as Sent",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1300, 240],
            },
        ],
        "connections": {
            "Every 3 Minutes": {
                "main": [[{"node": "Query Accepted Creators", "type": "main", "index": 0}]]
            },
            "Query Accepted Creators": {
                "main": [[{"node": "Has Records?", "type": "main", "index": 0}]]
            },
            "Has Records?": {
                "main": [
                    [{"node": "Split Records", "type": "main", "index": 0}],
                    [],
                ]
            },
            "Split Records": {
                "main": [[{"node": "Send Sample Form Email", "type": "main", "index": 0}]]
            },
            "Send Sample Form Email": {
                "main": [[{"node": "Mark as Sent", "type": "main", "index": 0}]]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Accepted -> Email")
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
            wf_def = build_workflow()
            print(f"  [DRY RUN] Would create new workflow")
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

    print(f"\n  How it works:")
    print(f"    1. Polls Airtable every 3 minutes")
    print(f"    2. Finds records: Status='Sample form sent' AND Sample Email Sent=false")
    print(f"    3. Sends email with link to {SAMPLE_FORM_BASE_URL}")
    print(f"    4. Updates Airtable: Sample Email Sent = true")
    print(f"\n  NOTE: n8n must have SMTP credentials configured.")
    print(f"  Go to n8n Settings > SMTP to configure email sending.")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
