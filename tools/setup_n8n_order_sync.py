"""Create n8n workflow: Shopify Order Webhook -> PostgreSQL.

Workflow nodes:
  Webhook (POST /shopify-order-sync)
    -> Parse Order Payload
    -> Upsert Order to PostgreSQL
    -> Insert Line Items to PostgreSQL
    -> Update Customer Metrics
    -> Respond 200 OK

Usage:
    python tools/setup_n8n_order_sync.py
    python tools/setup_n8n_order_sync.py --dry-run
    python tools/setup_n8n_order_sync.py --credential-id <id>

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

from n8n_api_client import n8n_request

N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")

WORKFLOW_NAME = "Shopify: Order Sync -> PostgreSQL"



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
                    "path": "shopify-order-sync",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "id": "webhook-trigger",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [200, 300],
                "webhookId": "shopify-order-sync",
            },
            # 2. Parse order payload
            {
                "parameters": {
                    "jsCode": """// Parse Shopify order webhook payload
const raw = $input.first().json.body || $input.first().json;
const order = raw.order || raw;

const shopifyId = order.id;
const orderNumber = order.name || '';
const customerId = order.customer ? order.customer.id : null;
const email = (order.email || '').toLowerCase().trim();
const totalPrice = parseFloat(order.total_price || '0');
const subtotalPrice = parseFloat(order.subtotal_price || '0');
const totalTax = parseFloat(order.total_tax || '0');
const totalDiscounts = parseFloat(order.total_discounts || '0');
const currency = order.currency || 'USD';
const financialStatus = order.financial_status || '';
const fulfillmentStatus = order.fulfillment_status || null;
const tags = order.tags || '';
const note = order.note || '';
const createdAt = order.created_at || null;
const updatedAt = order.updated_at || null;

// Discount codes
const discountCodes = (order.discount_codes || []).map(d => ({
  code: d.code, amount: d.amount, type: d.type
}));

// Shipping address
const shipping = order.shipping_address || {};
const shippingCountry = shipping.country_code || '';
const shippingCity = shipping.city || '';
const shippingProvince = shipping.province || '';

// Line items
const lineItems = (order.line_items || []).map(li => ({
  shopify_line_id: li.id,
  order_id: shopifyId,
  product_id: li.product_id,
  variant_id: li.variant_id,
  title: li.title || '',
  variant_title: li.variant_title || '',
  sku: li.sku || '',
  quantity: li.quantity || 1,
  price: parseFloat(li.price || '0'),
  total_discount: parseFloat(li.total_discount || '0'),
}));

return [{
  json: {
    order: {
      shopify_id: shopifyId,
      order_number: orderNumber,
      customer_id: customerId,
      email,
      total_price: totalPrice,
      subtotal_price: subtotalPrice,
      total_tax: totalTax,
      total_discounts: totalDiscounts,
      currency,
      financial_status: financialStatus,
      fulfillment_status: fulfillmentStatus,
      tags,
      note,
      discount_codes: JSON.stringify(discountCodes),
      shipping_country: shippingCountry,
      shipping_city: shippingCity,
      shipping_province: shippingProvince,
      shopify_created_at: createdAt,
      shopify_updated_at: updatedAt,
    },
    line_items: lineItems,
    customer_id: customerId,
  }
}];"""
                },
                "id": "code-parse",
                "name": "Parse Order",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [420, 300],
            },
            # 3. Upsert order to PostgreSQL
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """INSERT INTO orders (
  shopify_id, order_number, customer_id, email,
  total_price, subtotal_price, total_tax, total_discounts,
  currency, financial_status, fulfillment_status,
  tags, note, discount_codes,
  shipping_country, shipping_city, shipping_province,
  shopify_created_at, shopify_updated_at, synced_at
) VALUES (
  {{ $json.order.shopify_id }},
  '{{ $json.order.order_number }}',
  {{ $json.order.customer_id || 'NULL' }},
  '{{ $json.order.email }}',
  {{ $json.order.total_price }},
  {{ $json.order.subtotal_price }},
  {{ $json.order.total_tax }},
  {{ $json.order.total_discounts }},
  '{{ $json.order.currency }}',
  '{{ $json.order.financial_status }}',
  {{ $json.order.fulfillment_status ? "'" + $json.order.fulfillment_status + "'" : 'NULL' }},
  '{{ $json.order.tags.replace(/'/g, "''") }}',
  '{{ $json.order.note.replace(/'/g, "''") }}',
  '{{ $json.order.discount_codes.replace(/'/g, "''") }}'::jsonb,
  '{{ $json.order.shipping_country }}',
  '{{ $json.order.shipping_city.replace(/'/g, "''") }}',
  '{{ $json.order.shipping_province.replace(/'/g, "''") }}',
  {{ $json.order.shopify_created_at ? "'" + $json.order.shopify_created_at + "'" : 'NULL' }},
  {{ $json.order.shopify_updated_at ? "'" + $json.order.shopify_updated_at + "'" : 'NULL' }},
  NOW()
)
ON CONFLICT (shopify_id) DO UPDATE SET
  order_number = EXCLUDED.order_number,
  customer_id = EXCLUDED.customer_id,
  email = EXCLUDED.email,
  total_price = EXCLUDED.total_price,
  subtotal_price = EXCLUDED.subtotal_price,
  total_tax = EXCLUDED.total_tax,
  total_discounts = EXCLUDED.total_discounts,
  financial_status = EXCLUDED.financial_status,
  fulfillment_status = EXCLUDED.fulfillment_status,
  tags = EXCLUDED.tags,
  note = EXCLUDED.note,
  discount_codes = EXCLUDED.discount_codes,
  shipping_country = EXCLUDED.shipping_country,
  shipping_city = EXCLUDED.shipping_city,
  shipping_province = EXCLUDED.shipping_province,
  shopify_updated_at = EXCLUDED.shopify_updated_at,
  synced_at = NOW();""",
                    "options": {},
                },
                "id": "pg-upsert-order",
                "name": "Upsert Order",
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
            # 4. Build line item queries
            {
                "parameters": {
                    "jsCode": """// Build line item insert queries
const lineItems = $('Parse Order').first().json.line_items || [];

if (lineItems.length === 0) {
  return [{ json: { query: '-- no line items', has_items: false } }];
}

const queries = [];
for (const li of lineItems) {
  const q = `INSERT INTO line_items (
    shopify_line_id, order_id, product_id, variant_id,
    title, variant_title, sku, quantity, price, total_discount, synced_at
  ) VALUES (
    ${li.shopify_line_id},
    ${li.order_id},
    ${li.product_id || 'NULL'},
    ${li.variant_id || 'NULL'},
    '${(li.title || '').replace(/'/g, "''")}',
    '${(li.variant_title || '').replace(/'/g, "''")}',
    '${(li.sku || '').replace(/'/g, "''")}',
    ${li.quantity},
    ${li.price},
    ${li.total_discount},
    NOW()
  )
  ON CONFLICT (order_id, shopify_line_id) DO UPDATE SET
    title = EXCLUDED.title,
    variant_title = EXCLUDED.variant_title,
    sku = EXCLUDED.sku,
    quantity = EXCLUDED.quantity,
    price = EXCLUDED.price,
    total_discount = EXCLUDED.total_discount,
    synced_at = NOW();`;
  queries.push(q);
}

return [{ json: { query: queries.join('\\n'), has_items: true } }];"""
                },
                "id": "code-line-items",
                "name": "Build Line Item Queries",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [660, 440],
            },
            # 5. Execute line item queries
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": "={{ $json.query }}",
                    "options": {},
                },
                "id": "pg-insert-lines",
                "name": "Insert Line Items",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [900, 440],
                "credentials": {
                    "postgres": {
                        "id": str(pg_credential_id),
                        "name": "PostgreSQL",
                    }
                },
            },
            # 6. Update customer metrics (if customer_id exists)
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """-- Recalculate customer metrics after new order
INSERT INTO customer_metrics (customer_id, lifetime_value, order_count, avg_order_value, first_order_date, last_order_date, days_since_last, calculated_at)
SELECT
  o.customer_id,
  SUM(o.total_price) as lifetime_value,
  COUNT(*) as order_count,
  ROUND(AVG(o.total_price), 2) as avg_order_value,
  MIN(o.shopify_created_at) as first_order_date,
  MAX(o.shopify_created_at) as last_order_date,
  EXTRACT(DAY FROM NOW() - MAX(o.shopify_created_at))::int as days_since_last,
  NOW()
FROM orders o
WHERE o.customer_id = {{ $('Parse Order').first().json.customer_id }}
  AND o.financial_status NOT IN ('refunded', 'voided')
GROUP BY o.customer_id
ON CONFLICT (customer_id) DO UPDATE SET
  lifetime_value = EXCLUDED.lifetime_value,
  order_count = EXCLUDED.order_count,
  avg_order_value = EXCLUDED.avg_order_value,
  first_order_date = EXCLUDED.first_order_date,
  last_order_date = EXCLUDED.last_order_date,
  days_since_last = EXCLUDED.days_since_last,
  calculated_at = NOW();""",
                    "options": {},
                },
                "id": "pg-update-metrics",
                "name": "Update Customer Metrics",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [1140, 300],
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
                    "responseBody": '={{ JSON.stringify({ success: true, synced: "order" }) }}',
                    "options": {},
                },
                "id": "respond-ok",
                "name": "Respond OK",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1380, 300],
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "Parse Order", "type": "main", "index": 0}]]
            },
            "Parse Order": {
                "main": [[
                    {"node": "Upsert Order", "type": "main", "index": 0},
                    {"node": "Build Line Item Queries", "type": "main", "index": 0},
                ]]
            },
            "Upsert Order": {
                "main": [[{"node": "Update Customer Metrics", "type": "main", "index": 0}]]
            },
            "Build Line Item Queries": {
                "main": [[{"node": "Insert Line Items", "type": "main", "index": 0}]]
            },
            "Update Customer Metrics": {
                "main": [[{"node": "Respond OK", "type": "main", "index": 0}]]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Shopify Order -> PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--credential-id", type=str, help="PostgreSQL credential ID in n8n")
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
            print("  Pass --credential-id <id> or add PostgreSQL credentials in n8n UI")
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

    # Activate
    try:
        n8n_request("POST", f"/workflows/{wf_id}/activate")
        print(f"  [OK] Workflow activated")
    except Exception as e:
        print(f"  [WARN] Could not activate: {e}")

    webhook_url = f"{N8N_BASE_URL}/webhook/shopify-order-sync"
    print(f"\n  Webhook URL: {webhook_url}")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
