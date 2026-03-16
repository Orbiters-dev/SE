"""Push crawler data (Syncly/Apify) to PostgreSQL via orbitools API.

Lightweight utility that crawlers call after their existing CSV/JSON output.
Reuses the same POST /api/datakeeper/save/ endpoint as data_keeper.py.

Usage (as library):
    from push_content_to_pg import push_posts, push_metrics, push_influencer_orders

    push_posts([{"post_id": "abc", "url": "...", ...}])
    push_metrics([{"post_id": "abc", "date": "2026-03-16", "comments": 10, ...}])
    push_influencer_orders([{"order_id": "123", ...}])

Usage (CLI test):
    python tools/push_content_to_pg.py --test
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

ORBITOOLS_BASE = "https://orbitools.orbiters.co.kr/api/datakeeper"
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

CHUNK_SIZE = 1000


def _push_to_pg(table: str, rows: list[dict]) -> dict:
    """Push rows to PostgreSQL via orbitools API. Returns {created, updated, errors}."""
    if not rows:
        return {"created": 0, "updated": 0, "errors": []}

    total_created = 0
    total_updated = 0
    all_errors = []

    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        try:
            resp = requests.post(
                f"{ORBITOOLS_BASE}/save/",
                json={"table": table, "rows": chunk},
                auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            total_created += result.get("created", 0)
            total_updated += result.get("updated", 0)
            if result.get("errors"):
                all_errors.extend(result["errors"][:5])
                print(f"  [PG WARN] {table}: {len(result['errors'])} errors in chunk {i // CHUNK_SIZE}")
        except Exception as e:
            msg = f"{table} chunk {i // CHUNK_SIZE}: {e}"
            print(f"  [PG ERROR] {msg}")
            all_errors.append(msg)

    print(f"  [PG] {table}: +{total_created} new, ~{total_updated} updated (total {len(rows)} rows)")
    return {"created": total_created, "updated": total_updated, "errors": all_errors}


def push_posts(posts: list[dict]) -> dict:
    """Upsert content posts to gk_content_posts.

    Expected fields per row:
        post_id, url, platform, username, nickname, followers,
        caption, hashtags, tagged_account, post_date, brand, region, source
    """
    return _push_to_pg("content_posts", posts)


def push_metrics(metrics: list[dict]) -> dict:
    """Upsert daily engagement metrics to gk_content_metrics_daily.

    Expected fields per row:
        post_id, date, comments, likes, views
    """
    return _push_to_pg("content_metrics_daily", metrics)


def push_influencer_orders(orders: list[dict]) -> dict:
    """Upsert influencer orders to gk_influencer_orders.

    Expected fields per row:
        order_id, order_name, customer_name, customer_email,
        account_handle, channel, product_types, product_names,
        influencer_fee, shipping_date, fulfillment_status, brand, tags
    """
    return _push_to_pg("influencer_orders", orders)


def _run_test():
    """Push a single test row to each table, then query to verify."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("=== Push Content to PG: Test Mode ===\n")

    # Test content_posts
    test_post = {
        "post_id": "_test_post_001",
        "url": "https://example.com/test",
        "platform": "instagram",
        "username": "test_user",
        "nickname": "Test User",
        "followers": 1000,
        "caption": "Test caption",
        "hashtags": "#test",
        "tagged_account": "onzenna.official",
        "post_date": today,
        "brand": "Grosmimi",
        "region": "us",
        "source": "test",
    }
    r1 = push_posts([test_post])
    print(f"  content_posts: {r1}\n")

    # Test content_metrics_daily
    test_metric = {
        "post_id": "_test_post_001",
        "date": today,
        "comments": 5,
        "likes": 100,
        "views": 2000,
    }
    r2 = push_metrics([test_metric])
    print(f"  content_metrics_daily: {r2}\n")

    # Test influencer_orders
    test_order = {
        "order_id": "_test_order_001",
        "order_name": "#TEST001",
        "customer_name": "Test Influencer",
        "customer_email": "test@example.com",
        "account_handle": "@test_influencer",
        "channel": "Instagram",
        "product_types": "PPSU Straw Cup",
        "product_names": "Grosmimi PPSU Straw Cup 10oz White",
        "influencer_fee": 0,
        "shipping_date": today,
        "fulfillment_status": "fulfilled",
        "brand": "Grosmimi",
        "tags": "pr, test",
    }
    r3 = push_influencer_orders([test_order])
    print(f"  influencer_orders: {r3}\n")

    # Verify by querying
    print("--- Verify: querying back ---")
    for table in ["content_posts", "content_metrics_daily", "influencer_orders"]:
        try:
            resp = requests.get(
                f"{ORBITOOLS_BASE}/query/",
                params={"table": table, "limit": 1},
                auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
                timeout=15,
            )
            data = resp.json()
            count = data.get("count", data.get("total", "?"))
            print(f"  {table}: {count} rows, latest: {json.dumps(data.get('rows', [{}])[0], default=str)[:120]}...")
        except Exception as e:
            print(f"  {table}: query failed - {e}")

    print("\n=== Test complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push crawler data to PostgreSQL")
    parser.add_argument("--test", action="store_true", help="Run test push + verify")
    args = parser.parse_args()

    if args.test:
        _run_test()
    else:
        print("Usage: python push_content_to_pg.py --test")
        print("Or import: from push_content_to_pg import push_posts, push_metrics, push_influencer_orders")
