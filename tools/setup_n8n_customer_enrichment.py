"""Create n8n workflow: Customer Enrichment (daily RFM + metrics calculation).

Scheduled workflow that:
  1. Calculates LTV, AOV, purchase frequency for all customers
  2. Assigns RFM scores (Recency, Frequency, Monetary)
  3. Tags customer segments and consumption patterns
  4. Updates customer_metrics table in PostgreSQL

Usage:
    python tools/setup_n8n_customer_enrichment.py
    python tools/setup_n8n_customer_enrichment.py --dry-run
    python tools/setup_n8n_customer_enrichment.py --credential-id <pg_id>

Prerequisites:
    .wat_secrets: N8N_API_KEY, N8N_BASE_URL
    n8n: PostgreSQL credential configured
    PostgreSQL: shopify_db_schema.sql already executed
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

WORKFLOW_NAME = "Shopify: Customer Enrichment (Daily)"



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
    return {
        "name": WORKFLOW_NAME,
        "nodes": [
            # 1. Schedule trigger (daily 01:00 UTC = 10:00 KST, after airtable sync)
            {
                "parameters": {
                    "rule": {
                        "interval": [
                            {
                                "field": "cronExpression",
                                "expression": "0 1 * * *",
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
            # 2. Calculate base metrics for all customers
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """-- Step 1: Calculate base metrics for all customers with orders
INSERT INTO customer_metrics (
  customer_id, lifetime_value, order_count, avg_order_value,
  first_order_date, last_order_date, days_since_last,
  purchase_frequency, calculated_at
)
SELECT
  c.shopify_id,
  COALESCE(SUM(o.total_price), 0) as lifetime_value,
  COUNT(o.shopify_id) as order_count,
  CASE WHEN COUNT(o.shopify_id) > 0
    THEN ROUND(SUM(o.total_price) / COUNT(o.shopify_id), 2)
    ELSE 0 END as avg_order_value,
  MIN(o.shopify_created_at) as first_order_date,
  MAX(o.shopify_created_at) as last_order_date,
  EXTRACT(DAY FROM NOW() - MAX(o.shopify_created_at))::int as days_since_last,
  CASE
    WHEN COUNT(o.shopify_id) <= 1 THEN 0
    WHEN EXTRACT(EPOCH FROM MAX(o.shopify_created_at) - MIN(o.shopify_created_at)) < 86400 THEN 0
    ELSE ROUND(
      COUNT(o.shopify_id)::numeric /
      GREATEST(EXTRACT(EPOCH FROM MAX(o.shopify_created_at) - MIN(o.shopify_created_at)) / 2592000, 1),
      4
    )
  END as purchase_frequency,
  NOW()
FROM customers c
LEFT JOIN orders o ON c.shopify_id = o.customer_id
  AND o.financial_status NOT IN ('refunded', 'voided')
GROUP BY c.shopify_id
ON CONFLICT (customer_id) DO UPDATE SET
  lifetime_value = EXCLUDED.lifetime_value,
  order_count = EXCLUDED.order_count,
  avg_order_value = EXCLUDED.avg_order_value,
  first_order_date = EXCLUDED.first_order_date,
  last_order_date = EXCLUDED.last_order_date,
  days_since_last = EXCLUDED.days_since_last,
  purchase_frequency = EXCLUDED.purchase_frequency,
  calculated_at = NOW();""",
                    "options": {},
                },
                "id": "pg-base-metrics",
                "name": "Calculate Base Metrics",
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
            # 3. Calculate RFM scores using NTILE
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """-- Step 2: Calculate RFM scores (1-5 scale, 5 = best)
WITH rfm_raw AS (
  SELECT
    customer_id,
    days_since_last,
    order_count,
    lifetime_value,
    -- Recency: lower days = higher score
    NTILE(5) OVER (ORDER BY days_since_last DESC) as recency_score,
    -- Frequency: more orders = higher score
    NTILE(5) OVER (ORDER BY order_count ASC) as frequency_score,
    -- Monetary: higher LTV = higher score
    NTILE(5) OVER (ORDER BY lifetime_value ASC) as monetary_score
  FROM customer_metrics
  WHERE order_count > 0
)
UPDATE customer_metrics cm SET
  recency_score = r.recency_score,
  frequency_score = r.frequency_score,
  monetary_score = r.monetary_score,
  rfm_segment = CASE
    -- Champions: high R, high F, high M
    WHEN r.recency_score >= 4 AND r.frequency_score >= 4 AND r.monetary_score >= 4
      THEN 'Champions'
    -- Loyal: high F
    WHEN r.frequency_score >= 4 AND r.monetary_score >= 3
      THEN 'Loyal'
    -- Potential Loyalist: high R, medium F
    WHEN r.recency_score >= 4 AND r.frequency_score >= 2 AND r.frequency_score <= 3
      THEN 'Potential Loyalist'
    -- Recent: high R, low F (new customers)
    WHEN r.recency_score >= 4 AND r.frequency_score <= 1
      THEN 'Recent'
    -- Promising: medium R, low-medium F
    WHEN r.recency_score >= 3 AND r.frequency_score <= 2
      THEN 'Promising'
    -- Need Attention: medium across all
    WHEN r.recency_score >= 2 AND r.recency_score <= 3 AND r.frequency_score >= 2
      THEN 'Need Attention'
    -- At Risk: low R, high F (used to buy often)
    WHEN r.recency_score <= 2 AND r.frequency_score >= 3
      THEN 'At Risk'
    -- Hibernating: low R, low F
    WHEN r.recency_score <= 2 AND r.frequency_score <= 2 AND r.monetary_score >= 2
      THEN 'Hibernating'
    -- Lost
    ELSE 'Lost'
  END,
  calculated_at = NOW()
FROM rfm_raw r
WHERE cm.customer_id = r.customer_id;""",
                    "options": {},
                },
                "id": "pg-rfm-scores",
                "name": "Calculate RFM Scores",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [680, 300],
                "credentials": {
                    "postgres": {
                        "id": str(pg_credential_id),
                        "name": "PostgreSQL",
                    }
                },
            },
            # 4. Calculate pattern tags and top product
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """-- Step 3: Pattern tags and top product
WITH customer_patterns AS (
  SELECT
    cm.customer_id,
    ARRAY_REMOVE(ARRAY[
      CASE WHEN cm.order_count >= 3 THEN 'repeat_buyer' END,
      CASE WHEN cm.order_count = 1 THEN 'one_time' END,
      CASE WHEN cm.avg_order_value >= 100 THEN 'high_aov' END,
      CASE WHEN cm.avg_order_value < 30 THEN 'low_aov' END,
      CASE WHEN cm.purchase_frequency >= 1 THEN 'frequent' END,
      CASE WHEN cm.days_since_last <= 30 THEN 'active_30d' END,
      CASE WHEN cm.days_since_last > 180 THEN 'dormant_180d' END,
      CASE WHEN cm.lifetime_value >= 500 THEN 'vip' END
    ], NULL) as tags
  FROM customer_metrics cm
  WHERE cm.order_count > 0
),
top_products AS (
  SELECT DISTINCT ON (o.customer_id)
    o.customer_id,
    li.title as top_product
  FROM orders o
  JOIN line_items li ON o.shopify_id = li.order_id
  WHERE o.financial_status NOT IN ('refunded', 'voided')
  GROUP BY o.customer_id, li.title
  ORDER BY o.customer_id, COUNT(*) DESC, SUM(li.quantity) DESC
)
UPDATE customer_metrics cm SET
  pattern_tags = cp.tags,
  top_product = tp.top_product,
  calculated_at = NOW()
FROM customer_patterns cp
LEFT JOIN top_products tp ON cp.customer_id = tp.customer_id
WHERE cm.customer_id = cp.customer_id;""",
                    "options": {},
                },
                "id": "pg-pattern-tags",
                "name": "Calculate Patterns",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [920, 300],
                "credentials": {
                    "postgres": {
                        "id": str(pg_credential_id),
                        "name": "PostgreSQL",
                    }
                },
            },
            # 5. Log sync completion
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": """INSERT INTO sync_log (sync_type, source, records_processed, status, completed_at)
SELECT
  'enrichment',
  'scheduled',
  COUNT(*),
  'completed',
  NOW()
FROM customer_metrics WHERE calculated_at >= NOW() - INTERVAL '1 hour';""",
                    "options": {},
                },
                "id": "pg-log",
                "name": "Log Completion",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.5,
                "position": [1160, 300],
                "credentials": {
                    "postgres": {
                        "id": str(pg_credential_id),
                        "name": "PostgreSQL",
                    }
                },
            },
        ],
        "connections": {
            "Daily Trigger": {
                "main": [[{"node": "Calculate Base Metrics", "type": "main", "index": 0}]]
            },
            "Calculate Base Metrics": {
                "main": [[{"node": "Calculate RFM Scores", "type": "main", "index": 0}]]
            },
            "Calculate RFM Scores": {
                "main": [[{"node": "Calculate Patterns", "type": "main", "index": 0}]]
            },
            "Calculate Patterns": {
                "main": [[{"node": "Log Completion", "type": "main", "index": 0}]]
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

    parser = argparse.ArgumentParser(description="Create n8n workflow: Customer Enrichment")
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
        print(f"  [OK] Workflow activated (runs daily at 01:00 UTC / 10:00 KST)")
    except Exception as e:
        print(f"  [WARN] Could not activate: {e}")

    print(f"\n  Enrichment calculates:")
    print(f"    - LTV, AOV, purchase frequency")
    print(f"    - RFM scores (Recency/Frequency/Monetary 1-5)")
    print(f"    - RFM segments (Champions, Loyal, At Risk, etc.)")
    print(f"    - Pattern tags (repeat_buyer, vip, dormant, etc.)")
    print(f"    - Top purchased product")

    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
