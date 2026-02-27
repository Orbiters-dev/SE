"""Create n8n workflow: PostgreSQL -> Airtable (daily customer sync).

Scheduled workflow that queries active customers + metrics from PostgreSQL
and upserts them to Airtable for team operations.

Workflow nodes:
  Schedule Trigger (daily 09:00 KST)
    -> Query PostgreSQL (customers + metrics)
    -> Transform for Airtable
    -> Batch Upsert to Airtable

Usage:
    python tools/setup_n8n_airtable_sync.py
    python tools/setup_n8n_airtable_sync.py --dry-run
    python tools/setup_n8n_airtable_sync.py --credential-id <pg_id>

Prerequisites:
    .wat_secrets: N8N_API_KEY, N8N_BASE_URL, AIRTABLE_API_KEY,
                  AIRTABLE_CUSTOMERS_BASE_ID, AIRTABLE_CUSTOMERS_TABLE_ID
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
load_env()

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_CUSTOMERS_BASE_ID", "")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_CUSTOMERS_TABLE_ID", "")

WORKFLOW_NAME = "Shopify: PostgreSQL -> Airtable Sync (Daily)"


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


def find_postgres_credential():
    try:
        result = n8n_request("GET", "/credentials")
        for cred in result.get("data", []):
            if cred.get("type") == "postgres":
                return cred["id"], cred.get("name", "")
    except Exception:
        pass
    return None, None


def build_workflow(pg_credential_id):
    airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"

    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Schedule trigger (daily 09:00 KST = 00:00 UTC)
            {
                "parameters": {
                    "rule": {
                        "interval": [
                            {
                                "field": "cronExpression",
                                "expression": "0 0 * * *",
                            }
                        ]
                    },
                },
                "id": "schedule-trigger",
                "name": "Daily Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [200, 300],
            },
            # 2. Query PostgreSQL - active customers with metrics
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """SELECT
  c.shopify_id,
  c.email,
  c.first_name,
  c.last_name,
  c.phone,
  c.tags,
  c.state,
  c.shopify_created_at,
  a.city,
  a.country,
  COALESCE(m.lifetime_value, 0) as ltv,
  COALESCE(m.order_count, 0) as order_count,
  COALESCE(m.avg_order_value, 0) as avg_order_value,
  m.last_order_date,
  m.days_since_last,
  m.rfm_segment,
  COALESCE(array_to_string(m.pattern_tags, ', '), '') as pattern_tags,
  m.top_product
FROM customers c
LEFT JOIN customer_metrics m ON c.shopify_id = m.customer_id
LEFT JOIN LATERAL (
  SELECT city, country FROM addresses
  WHERE customer_id = c.shopify_id AND is_default = true
  LIMIT 1
) a ON true
WHERE c.state = 'enabled'
ORDER BY COALESCE(m.lifetime_value, 0) DESC
LIMIT 50000;""",
                    "options": {},
                },
                "id": "pg-query",
                "name": "Query Customers",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [440, 300],
                "credentials": {
                    "postgres": {
                        "id": str(pg_credential_id),
                        "name": "PostgreSQL",
                    }
                },
            },
            # 3. Transform and batch for Airtable (10 records per request)
            {
                "parameters": {
                    "jsCode": """// Transform PostgreSQL rows into Airtable batch upsert format
const items = $input.all();
const batches = [];
let batch = [];

for (const item of items) {
  const row = item.json;
  const record = {
    fields: {
      "Shopify ID": row.shopify_id,
      "Email": row.email || '',
      "First Name": row.first_name || '',
      "Last Name": row.last_name || '',
      "Phone": row.phone || '',
      "Tags": row.tags || '',
      "State": row.state || '',
      "City": row.city || '',
      "Country": row.country || '',
      "Created At": row.shopify_created_at || null,
      "LTV": row.ltv || 0,
      "Order Count": row.order_count || 0,
      "Avg Order Value": row.avg_order_value || 0,
      "Last Order Date": row.last_order_date || null,
      "Days Since Last Order": row.days_since_last || null,
      "RFM Segment": row.rfm_segment || null,
      "Pattern Tags": row.pattern_tags || '',
      "Top Product": row.top_product || '',
      "Last Synced": new Date().toISOString(),
    }
  };
  batch.push(record);

  if (batch.length === 10) {
    batches.push({ records: batch });
    batch = [];
  }
}

if (batch.length > 0) {
  batches.push({ records: batch });
}

return batches.map(b => ({ json: b }));"""
                },
                "id": "code-transform",
                "name": "Transform for Airtable",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [680, 300],
            },
            # 4. Upsert to Airtable (batch HTTP request)
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
                    "jsonBody": '={{ JSON.stringify({ ...$json, performUpsert: { fieldsToMergeOn: ["Shopify ID"] } }) }}',
                    "options": {
                        "timeout": 30000,
                        "batching": {"batch": {"batchSize": 1, "batchInterval": 250}},
                    },
                },
                "id": "http-airtable-upsert",
                "name": "Upsert to Airtable",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [920, 300],
            },
        ],
        "connections": {
            "Daily Trigger": {
                "main": [[{"node": "Query Customers", "type": "main", "index": 0}]]
            },
            "Query Customers": {
                "main": [[{"node": "Transform for Airtable", "type": "main", "index": 0}]]
            },
            "Transform for Airtable": {
                "main": [[{"node": "Upsert to Airtable", "type": "main", "index": 0}]]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: PostgreSQL -> Airtable sync")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--credential-id", type=str, help="PostgreSQL credential ID in n8n")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    missing = []
    if not AIRTABLE_API_KEY:
        missing.append("AIRTABLE_API_KEY")
    if not AIRTABLE_BASE_ID:
        missing.append("AIRTABLE_CUSTOMERS_BASE_ID")
    if not AIRTABLE_TABLE_ID:
        missing.append("AIRTABLE_CUSTOMERS_TABLE_ID")
    if missing:
        print(f"[WARN] Missing: {', '.join(missing)}")
        print("  Run setup_airtable_customers.py first, then add IDs to ~/.wat_secrets")
        if not args.dry_run:
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"  Airtable Base: {AIRTABLE_BASE_ID or '(not set)'}")
    print(f"{'=' * 60}\n")

    pg_cred_id = args.credential_id
    if not pg_cred_id:
        print("  Detecting PostgreSQL credential...")
        pg_cred_id, pg_cred_name = find_postgres_credential()
        if pg_cred_id:
            print(f"  [OK] Found: {pg_cred_name} (ID: {pg_cred_id})")
        else:
            print("  [ERROR] No PostgreSQL credential found in n8n.")
            sys.exit(1)

    existing = find_existing_workflow()
    if existing:
        wf_id = existing["id"]
        print(f"  [FOUND] Existing workflow (ID: {wf_id})")
        if args.dry_run:
            print(f"  [DRY RUN] Would update workflow {wf_id}")
            return
        wf_def = build_workflow(pg_cred_id)
        n8n_request("PUT", f"/workflows/{wf_id}", wf_def)
        print(f"  [OK] Updated workflow")
    else:
        print(f"  [NEW] Creating workflow: {WORKFLOW_NAME}")
        if args.dry_run:
            wf_def = build_workflow(pg_cred_id)
            print(f"  [DRY RUN] Would create new workflow")
            print(f"  Nodes: {len(wf_def['nodes'])}")
            for n in wf_def["nodes"]:
                print(f"    - {n['name']} ({n['type']})")
            return
        wf_def = build_workflow(pg_cred_id)
        result = n8n_request("POST", "/workflows", wf_def)
        wf_id = result.get("id")
        print(f"  [OK] Created workflow (ID: {wf_id})")

    try:
        n8n_request("POST", f"/workflows/{wf_id}/activate")
        print(f"  [OK] Workflow activated (runs daily at 00:00 UTC / 09:00 KST)")
    except Exception as e:
        print(f"  [WARN] Could not activate: {e}")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
