"""
update_n8n_gifting_creators.py
Add Creators table upsert nodes to the Gifting workflow (F0sv8RsCS1v56Gkw).

Usage:
    python tools/update_n8n_gifting_creators.py              # dry-run
    python tools/update_n8n_gifting_creators.py --apply       # apply changes
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

WORKFLOW_ID = "F0sv8RsCS1v56Gkw"

# Creators table in WJ Test base
WJ_BASE = "appT2gLRR0PqMFgII"
WJ_CREATORS = "tbl7zJ1MscP852p9N"

PREPARE_CREATORS_CODE = r"""
var draftData = $('Create Draft Order').first().json;
var draftOrder = draftData.draft_order || {};
var formData = $('Process Form Data').first().json;
var body = $('Webhook').first().json.body || $('Webhook').first().json;
var personal = body.personal_info || {};

var instagram = (personal.instagram || '').replace(/^@/, '');
var tiktok = (personal.tiktok || '').replace(/^@/, '');

// Determine primary platform and username
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
  "Email": formData.email || personal.email || '',
  "Name": formData.firstName ? (formData.firstName + ' ' + (formData.lastName || '')).trim() : (personal.full_name || ''),
  "Username": username || '',
  "Platform": platform,
  "Profile URL": profileUrl,
  "Outreach Status": "Needs Review",
  "Partnership Status": "New",
  "Source": "ManyChat Inbound",
  "Initial Discovery Date": new Date().toISOString().split('T')[0],
  "Draft Order ID": String(draftOrder.id || '')
};

// Filter empty values
var cleanFields = {};
for (var key in fields) {
  if (fields[key] !== null && fields[key] !== undefined && fields[key] !== '') {
    cleanFields[key] = fields[key];
  }
}

return [{json: {
  records: [{
    fields: cleanFields
  }],
  performUpsert: {
    fieldsToMergeOn: ["Email"]
  },
  typecast: true
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

    # Check if already added
    existing_names = [n["name"] for n in wf["nodes"]]
    if "Save to Creators" in existing_names:
        print("Creators nodes already exist. Nothing to do.")
        return

    # New node 1: Prepare Creators Payload
    prepare_creators_node = {
        "parameters": {"jsCode": PREPARE_CREATORS_CODE},
        "id": "prepare-creators-payload",
        "name": "Prepare Creators Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2150, 1050],
    }

    # New node 2: Save to Creators
    save_creators_node = {
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
        "id": "save-to-creators",
        "name": "Save to Creators",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2450, 1050],
        "onError": "continueRegularOutput",
    }

    if dry_run:
        print("\n[DRY RUN] Would add nodes:")
        print(f"  - Prepare Creators Payload (code)")
        print(f"  - Save to Creators (HTTP PATCH -> {WJ_BASE}/{WJ_CREATORS})")
        print(f"\n[DRY RUN] Would add connections:")
        print(f"  Create Draft Order -> Prepare Creators Payload -> Save to Creators")
        return

    # Add nodes
    wf["nodes"].append(prepare_creators_node)
    wf["nodes"].append(save_creators_node)

    # Add connections
    if "Create Draft Order" not in wf["connections"]:
        wf["connections"]["Create Draft Order"] = {"main": [[]]}

    main_conns = wf["connections"]["Create Draft Order"]["main"]
    if len(main_conns) == 0:
        main_conns.append([])
    main_conns[0].append(
        {"node": "Prepare Creators Payload", "type": "main", "index": 0}
    )

    wf["connections"]["Prepare Creators Payload"] = {
        "main": [[{"node": "Save to Creators", "type": "main", "index": 0}]]
    }

    # Build update payload - only include required fields
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
            marker = " *NEW*" if n["name"] in ("Prepare Creators Payload", "Save to Creators") else ""
            print(f"  {n['name']}{marker}")
        print(f"\nConnections from Create Draft Order:")
        for c in updated["connections"].get("Create Draft Order", {}).get("main", [[]])[0]:
            print(f"  -> {c['node']}")
    else:
        print(f"\n[ERROR] {r2.status_code}: {r2.text[:500]}")


if __name__ == "__main__":
    main()
