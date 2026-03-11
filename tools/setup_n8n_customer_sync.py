"""Create n8n workflow: Shopify Customer Webhook -> PostgreSQL.

Workflow nodes:
  Webhook (POST /shopify-customer-sync)
    -> Parse Customer Payload
    -> Upsert Customer to PostgreSQL
    -> Upsert Addresses to PostgreSQL
    -> Respond 200 OK

Usage:
    python tools/setup_n8n_customer_sync.py
    python tools/setup_n8n_customer_sync.py --dry-run
    python tools/setup_n8n_customer_sync.py --credential-id <id>

Prerequisites:
    .wat_secrets: N8N_API_KEY, N8N_BASE_URL
    n8n: PostgreSQL credential configured
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

WORKFLOW_NAME = "Shopify: Customer Sync -> PostgreSQL"


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
    """Auto-detect PostgreSQL credential ID from n8n."""
    try:
        result = n8n_request("GET", "/credentials")
        for cred in result.get("data", []):
            if cred.get("type") == "postgres":
                return cred["id"], cred.get("name", "")
    except Exception:
        pass
    return None, None


def build_workflow(pg_credential_id):
    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Webhook trigger
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "shopify-customer-sync",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "id": "webhook-trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "shopify-customer-sync",
            },
            # 2. Parse customer payload
            {
                "parameters": {
                    "jsCode": """// Parse Shopify customer webhook payload
const raw = $input.first().json.body || $input.first().json;

// Shopify sends different shapes depending on the event
const customer = raw.customer || raw;

const shopifyId = customer.id;
const email = (customer.email || '').toLowerCase().trim();
const firstName = customer.first_name || '';
const lastName = customer.last_name || '';
const phone = customer.phone || '';
const tags = customer.tags || '';
const note = customer.note || '';
const ordersCount = customer.orders_count || 0;
const totalSpent = parseFloat(customer.total_spent || '0');
const state = customer.state || 'enabled';
const verifiedEmail = customer.verified_email || false;
const taxExempt = customer.tax_exempt || false;
const acceptsMarketing = customer.accepts_marketing || false;
const createdAt = customer.created_at || null;
const updatedAt = customer.updated_at || null;

// Parse addresses
const addresses = (customer.addresses || []).map(addr => ({
  customer_id: shopifyId,
  shopify_address_id: addr.id,
  is_default: addr.default || false,
  first_name: addr.first_name || '',
  last_name: addr.last_name || '',
  company: addr.company || '',
  address1: addr.address1 || '',
  address2: addr.address2 || '',
  city: addr.city || '',
  province: addr.province || '',
  province_code: addr.province_code || '',
  country: addr.country || '',
  country_code: addr.country_code || '',
  zip: addr.zip || '',
  phone: addr.phone || '',
}));

// If no addresses array but default_address exists
if (addresses.length === 0 && customer.default_address) {
  const addr = customer.default_address;
  addresses.push({
    customer_id: shopifyId,
    shopify_address_id: addr.id,
    is_default: true,
    first_name: addr.first_name || '',
    last_name: addr.last_name || '',
    company: addr.company || '',
    address1: addr.address1 || '',
    address2: addr.address2 || '',
    city: addr.city || '',
    province: addr.province || '',
    province_code: addr.province_code || '',
    country: addr.country || '',
    country_code: addr.country_code || '',
    zip: addr.zip || '',
    phone: addr.phone || '',
  });
}

return [{
  json: {
    customer: {
      shopify_id: shopifyId,
      email,
      first_name: firstName,
      last_name: lastName,
      phone,
      tags,
      note,
      orders_count: ordersCount,
      total_spent: totalSpent,
      state,
      verified_email: verifiedEmail,
      tax_exempt: taxExempt,
      accepts_marketing: acceptsMarketing,
      shopify_created_at: createdAt,
      shopify_updated_at: updatedAt,
    },
    addresses,
    has_addresses: addresses.length > 0,
  }
}];"""
                },
                "id": "code-parse",
                "name": "Parse Customer",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [420, 300],
            },
            # 3. Upsert customer to PostgreSQL
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """INSERT INTO customers (
  shopify_id, email, first_name, last_name, phone, tags, note,
  orders_count, total_spent, state, verified_email, tax_exempt,
  accepts_marketing, shopify_created_at, shopify_updated_at, synced_at
) VALUES (
  {{ $json.customer.shopify_id }},
  '{{ $json.customer.email }}',
  '{{ $json.customer.first_name.replace(/'/g, "''") }}',
  '{{ $json.customer.last_name.replace(/'/g, "''") }}',
  '{{ $json.customer.phone }}',
  '{{ $json.customer.tags.replace(/'/g, "''") }}',
  '{{ $json.customer.note.replace(/'/g, "''") }}',
  {{ $json.customer.orders_count }},
  {{ $json.customer.total_spent }},
  '{{ $json.customer.state }}',
  {{ $json.customer.verified_email }},
  {{ $json.customer.tax_exempt }},
  {{ $json.customer.accepts_marketing }},
  {{ $json.customer.shopify_created_at ? "'" + $json.customer.shopify_created_at + "'" : 'NULL' }},
  {{ $json.customer.shopify_updated_at ? "'" + $json.customer.shopify_updated_at + "'" : 'NULL' }},
  NOW()
)
ON CONFLICT (shopify_id) DO UPDATE SET
  email = EXCLUDED.email,
  first_name = EXCLUDED.first_name,
  last_name = EXCLUDED.last_name,
  phone = EXCLUDED.phone,
  tags = EXCLUDED.tags,
  note = EXCLUDED.note,
  orders_count = EXCLUDED.orders_count,
  total_spent = EXCLUDED.total_spent,
  state = EXCLUDED.state,
  verified_email = EXCLUDED.verified_email,
  tax_exempt = EXCLUDED.tax_exempt,
  accepts_marketing = EXCLUDED.accepts_marketing,
  shopify_created_at = EXCLUDED.shopify_created_at,
  shopify_updated_at = EXCLUDED.shopify_updated_at,
  synced_at = NOW();""",
                    "options": {},
                },
                "id": "pg-upsert-customer",
                "name": "Upsert Customer",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [660, 200],
                "credentials": {
                    "postgres": {
                        "id": str(pg_credential_id),
                        "name": "PostgreSQL",
                    }
                },
            },
            # 4. Check if has addresses
            {
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "conditions": [
                            {
                                "id": "addr-check",
                                "leftValue": "={{ $('Parse Customer').first().json.has_addresses }}",
                                "rightValue": True,
                                "operator": {"type": "boolean", "operation": "true"},
                            }
                        ],
                        "combinator": "and",
                    },
                },
                "id": "if-has-addresses",
                "name": "Has Addresses?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [660, 440],
            },
            # 5. Upsert addresses (Code node that builds and runs queries)
            {
                "parameters": {
                    "jsCode": """// Build address upsert queries
const addresses = $('Parse Customer').first().json.addresses || [];
const queries = [];

for (const addr of addresses) {
  const q = `INSERT INTO addresses (
    customer_id, shopify_address_id, is_default, first_name, last_name,
    company, address1, address2, city, province, province_code,
    country, country_code, zip, phone, synced_at
  ) VALUES (
    ${addr.customer_id},
    ${addr.shopify_address_id || 'NULL'},
    ${addr.is_default},
    '${(addr.first_name || '').replace(/'/g, "''")}',
    '${(addr.last_name || '').replace(/'/g, "''")}',
    '${(addr.company || '').replace(/'/g, "''")}',
    '${(addr.address1 || '').replace(/'/g, "''")}',
    '${(addr.address2 || '').replace(/'/g, "''")}',
    '${(addr.city || '').replace(/'/g, "''")}',
    '${(addr.province || '').replace(/'/g, "''")}',
    '${(addr.province_code || '')}',
    '${(addr.country || '').replace(/'/g, "''")}',
    '${(addr.country_code || '')}',
    '${(addr.zip || '')}',
    '${(addr.phone || '')}',
    NOW()
  )
  ON CONFLICT (customer_id, shopify_address_id) DO UPDATE SET
    is_default = EXCLUDED.is_default,
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    company = EXCLUDED.company,
    address1 = EXCLUDED.address1,
    address2 = EXCLUDED.address2,
    city = EXCLUDED.city,
    province = EXCLUDED.province,
    province_code = EXCLUDED.province_code,
    country = EXCLUDED.country,
    country_code = EXCLUDED.country_code,
    zip = EXCLUDED.zip,
    phone = EXCLUDED.phone,
    synced_at = NOW();`;
  queries.push(q);
}

return [{ json: { query: queries.join('\\n') } }];"""
                },
                "id": "code-addr-queries",
                "name": "Build Address Queries",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [900, 440],
            },
            # 6. Execute address queries
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": "={{ $json.query }}",
                    "options": {},
                },
                "id": "pg-upsert-addresses",
                "name": "Upsert Addresses",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [1120, 440],
                "credentials": {
                    "postgres": {
                        "id": str(pg_credential_id),
                        "name": "PostgreSQL",
                    }
                },
            },
            # 7. Respond OK
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": '={{ JSON.stringify({ success: true, synced: "customer" }) }}',
                    "options": {},
                },
                "id": "respond-ok",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [900, 200],
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Parse Customer", "type": "main", "index": 0}]]
            },
            "Parse Customer": {
                "main": [[
                    {"node": "Upsert Customer", "type": "main", "index": 0},
                    {"node": "Has Addresses?", "type": "main", "index": 0},
                ]]
            },
            "Upsert Customer": {
                "main": [[{"node": "Respond OK", "type": "main", "index": 0}]]
            },
            "Has Addresses?": {
                "main": [
                    [{"node": "Build Address Queries", "type": "main", "index": 0}],
                    [],
                ]
            },
            "Build Address Queries": {
                "main": [[{"node": "Upsert Addresses", "type": "main", "index": 0}]]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Shopify Customer -> PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--credential-id", type=str, help="PostgreSQL credential ID in n8n (auto-detected if not set)")
    args = parser.parse_args()

    if not N8N_API_KEY:
        print("[ERROR] N8N_API_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  Setup n8n Workflow: {WORKFLOW_NAME}")
    print(f"  n8n: {N8N_BASE_URL}")
    print(f"{'=' * 60}\n")

    # Find PostgreSQL credential
    pg_cred_id = args.credential_id
    if not pg_cred_id:
        print("  Detecting PostgreSQL credential...")
        pg_cred_id, pg_cred_name = find_postgres_credential()
        if pg_cred_id:
            print(f"  [OK] Found: {pg_cred_name} (ID: {pg_cred_id})")
        else:
            print("  [ERROR] No PostgreSQL credential found in n8n.")
            print("  Either:")
            print("    1. Add PostgreSQL credentials in n8n UI (Settings -> Credentials)")
            print("    2. Pass --credential-id <id> manually")
            sys.exit(1)

    # Check existing
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
            print(f"  [DRY RUN] Would create new workflow")
            wf_def = build_workflow(pg_cred_id)
            print(f"  Nodes: {len(wf_def['nodes'])}")
            for n in wf_def["nodes"]:
                print(f"    - {n['name']} ({n['type']})")
            return

        wf_def = build_workflow(pg_cred_id)
        result = n8n_request("POST", "/workflows", wf_def)
        wf_id = result.get("id")
        print(f"  [OK] Created workflow (ID: {wf_id})")

    # Activate
    try:
        n8n_request("POST", f"/workflows/{wf_id}/activate")
        print(f"  [OK] Workflow activated")
    except Exception as e:
        print(f"  [WARN] Could not activate: {e}")

    webhook_url = f"{N8N_BASE_URL}/webhook/shopify-customer-sync"
    print(f"\n  Webhook URL: {webhook_url}")
    print(f"\n  Next: Run setup_shopify_webhooks.py to register Shopify -> n8n webhooks")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
