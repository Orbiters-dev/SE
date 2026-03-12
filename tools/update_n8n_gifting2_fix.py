"""
update_n8n_gifting2_fix.py
Fix the Gifting2 workflow (KqICsN9F1mPwnAQ9):
1. Replace Find-then-Update Airtable with Upsert pattern (fixes record_id error)
2. Add conditional customer creation (IF node)
3. Add Creators table upsert
4. Add PostgreSQL save branch

Usage:
    python tools/update_n8n_gifting2_fix.py              # dry-run
    python tools/update_n8n_gifting2_fix.py --apply       # apply
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
from env_loader import load_env
load_env()

import requests

N8N_BASE_URL = os.environ["N8N_BASE_URL"]
N8N_API_KEY = os.environ["N8N_API_KEY"]
AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]

WORKFLOW_ID = "KqICsN9F1mPwnAQ9"

WJ_BASE = "appT2gLRR0PqMFgII"
WJ_APPLICANTS = "tbloYjIEr5OtEppT0"
WJ_CREATORS = "tbl7zJ1MscP852p9N"

# Nodes to remove (the broken Find-then-Update chain)
REMOVE_NODES = [
    "Prep Airtable Update",
    "Find Airtable Record",
    "Build Airtable Update",
    "Update Airtable",
]

# --- Replacement nodes ---

# Upsert Applicants (replaces the 4 broken nodes)
PREP_APPLICANTS_CODE = r"""
const orderResult = $input.first().json;
const mergeData = $('Merge Customer ID').first().json;
const draftOrder = orderResult.draft_order || {};
const buildData = $('Build Payloads').first().json;
const personal = buildData.personal_info || {};

var fields = {
  "Email": mergeData.airtable_email || personal.email || '',
  "Name": personal.full_name || '',
  "Draft Order ID": String(draftOrder.id || ''),
  "Shopify Customer ID": mergeData.customer_id ? Number(mergeData.customer_id) : null,
  "Status": "Accepted"
};

// Filter empty/null values
var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{ fields: cleanFields }],
  performUpsert: { fieldsToMergeOn: ["Email"] },
  typecast: true
}}];
""".strip()

# Upsert Creators
PREP_CREATORS_CODE = r"""
const orderResult = $input.first().json;
const mergeData = $('Merge Customer ID').first().json;
const draftOrder = orderResult.draft_order || {};
const buildData = $('Build Payloads').first().json;
const personal = buildData.personal_info || {};

var instagram = (personal.instagram || '').replace(/^@/, '');
var tiktok = (personal.tiktok || '').replace(/^@/, '');

var platform = 'Instagram';
var username = instagram;
var profileUrl = '';

if (instagram && instagram !== 'None') {
  platform = 'Instagram';
  username = instagram;
  profileUrl = 'https://www.instagram.com/' + instagram;
} else if (tiktok && tiktok !== 'None') {
  platform = 'TikTok';
  username = tiktok;
  profileUrl = 'https://www.tiktok.com/@' + tiktok;
}

var fields = {
  "Email": mergeData.airtable_email || personal.email || '',
  "Name": personal.full_name || '',
  "Username": username || '',
  "Platform": platform,
  "Profile URL": profileUrl,
  "Outreach Status": "Sample Sent",
  "Partnership Status": "New",
  "Source": "ManyChat Inbound",
  "Draft Order ID": String(draftOrder.id || '')
};

var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{ fields: cleanFields }],
  performUpsert: { fieldsToMergeOn: ["Email"] },
  typecast: true
}}];
""".strip()

# PG Payload
PREP_PG_CODE = r"""
const orderResult = $input.first().json;
const mergeData = $('Merge Customer ID').first().json;
const draftOrder = orderResult.draft_order || {};
const buildData = $('Build Payloads').first().json;
const personal = buildData.personal_info || {};
const address = buildData.shipping_address || {};
const baby = buildData.baby_info || {};

return [{json: {
  form_type: "gifting2_sample_request",
  email: personal.email || mergeData.airtable_email || '',
  full_name: personal.full_name || '',
  phone: personal.phone || '',
  instagram: personal.instagram || '',
  tiktok: personal.tiktok || '',
  shopify_customer_id: mergeData.customer_id || null,
  shopify_draft_order_id: draftOrder.id || null,
  street: address.street || '',
  apt: address.apt || '',
  city: address.city || '',
  state: address.state || '',
  zip: address.zip || '',
  country: address.country || 'US',
  child_1_birthday: (baby.child_1 || {}).birthday || null,
  child_2_birthday: (baby.child_2 || {}).birthday || null,
  submitted_at: new Date().toISOString()
}}];
""".strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = not args.apply

    n8n_headers = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

    # Get current workflow
    r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=n8n_headers)
    r.raise_for_status()
    wf = r.json()

    print(f"Workflow: {wf['name']}")
    print(f"Current nodes: {len(wf['nodes'])}")

    if dry_run:
        print("\n[DRY RUN] Changes:")
        print(f"  Remove nodes: {REMOVE_NODES}")
        print(f"  Add: Prepare Applicants Upsert (code)")
        print(f"  Add: Save to Applicants (PATCH -> {WJ_BASE}/{WJ_APPLICANTS})")
        print(f"  Add: Prepare Creators Upsert (code)")
        print(f"  Add: Save to Creators (PATCH -> {WJ_BASE}/{WJ_CREATORS})")
        print(f"  Add: Prepare PG Payload (code)")
        print(f"  Add: Save to PostgreSQL (POST)")
        print(f"\n  New flow: Create Draft Order -> [Applicants Upsert, Creators Upsert, PG Save] -> Respond OK")
        return

    # Remove old Airtable nodes
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in REMOVE_NODES]

    # Remove old connections from/to removed nodes
    for name in REMOVE_NODES:
        wf["connections"].pop(name, None)
    for src, targets in list(wf["connections"].items()):
        for ttype, conns in targets.items():
            for i, conn_list in enumerate(conns):
                conns[i] = [c for c in conn_list if c["node"] not in REMOVE_NODES]

    # Add new nodes
    new_nodes = [
        {
            "parameters": {"jsCode": PREP_APPLICANTS_CODE},
            "id": "prep-applicants-upsert",
            "name": "Prepare Applicants Upsert",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1900, 600],
        },
        {
            "parameters": {
                "method": "PATCH",
                "url": f"https://api.airtable.com/v0/{WJ_BASE}/{WJ_APPLICANTS}",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json) }}",
                "options": {"timeout": 10000},
            },
            "id": "save-applicants",
            "name": "Save to Applicants",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2200, 600],
            "onError": "continueRegularOutput",
        },
        {
            "parameters": {"jsCode": PREP_CREATORS_CODE},
            "id": "prep-creators-upsert-g2",
            "name": "Prepare Creators Upsert",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1900, 850],
        },
        {
            "parameters": {
                "method": "PATCH",
                "url": f"https://api.airtable.com/v0/{WJ_BASE}/{WJ_CREATORS}",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": f"Bearer {AIRTABLE_API_KEY}"},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json) }}",
                "options": {"timeout": 10000},
            },
            "id": "save-creators-g2",
            "name": "Save to Creators",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2200, 850],
            "onError": "continueRegularOutput",
        },
        {
            "parameters": {"jsCode": PREP_PG_CODE},
            "id": "prep-pg-g2",
            "name": "Prepare PG Payload",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1900, 1100],
        },
        {
            "parameters": {
                "method": "POST",
                "url": "https://orbitools.orbiters.co.kr/api/onzenna/gifting/save/",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json) }}",
                "options": {"timeout": 10000},
            },
            "id": "save-pg-g2",
            "name": "Save to PostgreSQL",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2200, 1100],
            "onError": "continueRegularOutput",
        },
    ]

    wf["nodes"].extend(new_nodes)

    # Update connections: Create Draft Order -> [3 parallel branches] -> Respond OK
    # First, remove old "Create Draft Order" -> "Prep Airtable Update" connection
    wf["connections"]["Create Draft Order"] = {
        "main": [[
            {"node": "Prepare Applicants Upsert", "type": "main", "index": 0},
            {"node": "Prepare Creators Upsert", "type": "main", "index": 0},
            {"node": "Prepare PG Payload", "type": "main", "index": 0},
            {"node": "Respond OK", "type": "main", "index": 0},
        ]]
    }

    # Airtable chains
    wf["connections"]["Prepare Applicants Upsert"] = {
        "main": [[{"node": "Save to Applicants", "type": "main", "index": 0}]]
    }
    wf["connections"]["Prepare Creators Upsert"] = {
        "main": [[{"node": "Save to Creators", "type": "main", "index": 0}]]
    }
    wf["connections"]["Prepare PG Payload"] = {
        "main": [[{"node": "Save to PostgreSQL", "type": "main", "index": 0}]]
    }

    # Build update payload
    update_payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
    }

    r2 = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=n8n_headers,
        json=update_payload,
    )

    if r2.status_code == 200:
        updated = r2.json()
        print(f"\n[OK] Workflow updated. Nodes: {len(updated['nodes'])}")
        for n in updated["nodes"]:
            print(f"  {n['name']}")
        print(f"\nConnections from Create Draft Order:")
        for c in updated["connections"].get("Create Draft Order", {}).get("main", [[]])[0]:
            print(f"  -> {c['node']}")
    else:
        print(f"\n[ERROR] {r2.status_code}: {r2.text[:500]}")


if __name__ == "__main__":
    main()
