"""
fetch_google_ads_daily.py - Google Ads daily aggregated data collector (Q13d)

Output: .tmp/polar_data/q13d_google_ads_daily.json
Format: {"tableData": [{"googleads_campaign_and_device.raw.cost": X,
                        "googleads_campaign_and_device.raw.clicks": X,
                        "googleads_campaign_and_device.raw.impressions": X,
                        "date": "YYYY-MM-DD"}]}

Aggregates all campaigns per day (no campaign-level breakdown).
Reuses Google Ads client setup from fetch_google_ads_monthly.py.

Usage:
    python tools/no_polar/fetch_google_ads_daily.py --start 2024-01 --end 2026-03
"""

import os
import sys
import json
import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List
from collections import defaultdict
from pathlib import Path

from dateutil.relativedelta import relativedelta

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUTPUT_PATH = ROOT / ".tmp" / "polar_data" / "q13d_google_ads_daily.json"

MICROS = Decimal("1000000")
MCC_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "8625697405")


def _build_client():
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("[ERROR] google-ads package not installed.")
        print("        Run: pip install google-ads")
        sys.exit(1)

    dev_token     = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
    client_id     = os.getenv("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
    login_cid     = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")

    if not all([dev_token, client_id, client_secret, refresh_token]):
        print("[ERROR] GOOGLE_ADS_* env vars not set")
        sys.exit(1)

    config = {
        "developer_token": dev_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    if login_cid:
        config["login_customer_id"] = login_cid

    return GoogleAdsClient.load_from_dict(config)


def list_client_accounts(client, mcc_customer_id: str) -> List[Dict]:
    ga = client.get_service("GoogleAdsService")
    query = """
        SELECT
          customer_client.client_customer,
          customer_client.descriptive_name,
          customer_client.level,
          customer_client.manager
        FROM customer_client
        WHERE customer_client.level <= 1
          AND customer_client.status = 'ENABLED'
    """
    out = []
    try:
        resp = ga.search(customer_id=mcc_customer_id, query=query)
        for row in resp:
            cid = str(row.customer_client.client_customer).replace("customers/", "")
            out.append({
                "client_customer_id": cid,
                "name": row.customer_client.descriptive_name,
                "is_manager": row.customer_client.manager,
            })
    except Exception as e:
        print(f"  [WARN] MCC account list failed: {e}")
    return out


def fetch_campaign_daily(client, customer_id: str, start_date: str, end_date: str) -> List[Dict]:
    ga = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          segments.date,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
          AND campaign.status != 'REMOVED'
        ORDER BY segments.date
    """
    out = []
    try:
        stream = ga.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            for r in batch.results:
                out.append({
                    "date":        r.segments.date,
                    "impressions": int(r.metrics.impressions or 0),
                    "clicks":      int(r.metrics.clicks or 0),
                    "spend":       float(Decimal(int(r.metrics.cost_micros or 0)) / MICROS),
                })
    except Exception as e:
        print(f"  [WARN] customer {customer_id} query failed: {e}")
    return out


def fetch_all_clients(client, mcc_id: str, start_date: str, end_date: str) -> List[Dict]:
    clients = list_client_accounts(client, mcc_id)
    target_ids = [c["client_customer_id"] for c in clients if not c["is_manager"]]
    if not target_ids:
        target_ids = [mcc_id]

    print(f"  [Google Ads] {len(target_ids)} accounts to fetch")
    all_rows = []
    for cid in target_ids:
        try:
            rows = fetch_campaign_daily(client, cid, start_date, end_date)
            print(f"    account {cid}: {len(rows)} rows")
            all_rows.extend(rows)
        except Exception as e:
            print(f"    [WARN] account {cid} failed: {e}")
    return all_rows


def aggregate_daily(rows: List[Dict]) -> List[Dict]:
    """Aggregate all campaigns into per-day totals."""
    bucket = defaultdict(lambda: {"cost": 0.0, "clicks": 0, "impressions": 0})
    for r in rows:
        d = str(r.get("date", ""))[:10]
        if not d:
            continue
        bucket[d]["cost"]        += float(r.get("spend", 0) or 0)
        bucket[d]["clicks"]      += int(r.get("clicks", 0) or 0)
        bucket[d]["impressions"] += int(r.get("impressions", 0) or 0)

    out = []
    for date_key in sorted(bucket.keys()):
        v = bucket[date_key]
        out.append({
            "googleads_campaign_and_device.raw.cost":        round(v["cost"], 6),
            "googleads_campaign_and_device.raw.clicks":      v["clicks"],
            "googleads_campaign_and_device.raw.impressions": v["impressions"],
            "date": date_key,
        })
    return out


def main():
    parser = argparse.ArgumentParser(description="Fetch Google Ads daily data (Q13d)")
    parser.add_argument("--start", default="2024-01", help="Start month YYYY-MM")
    parser.add_argument("--end",   default=None,      help="End month YYYY-MM (default: current month)")
    args = parser.parse_args()

    today = date.today()
    start_date = datetime.strptime(args.start, "%Y-%m").date().replace(day=1)
    end_str    = args.end or today.strftime("%Y-%m")
    end_first  = datetime.strptime(end_str, "%Y-%m").date().replace(day=1)
    end_date   = (end_first + relativedelta(months=1)) - timedelta(days=1)
    if end_date > today:
        end_date = today

    print(f"[Google Ads Daily] {start_date} ~ {end_date} | MCC: {MCC_ID}")

    client = _build_client()
    rows = fetch_all_clients(client, MCC_ID, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    print(f"[Google Ads Daily] Total raw rows: {len(rows)}")

    daily = aggregate_daily(rows)
    print(f"[Google Ads Daily] Daily aggregated rows: {len(daily)}")

    total_cost = sum(r["googleads_campaign_and_device.raw.cost"] for r in daily)
    print(f"[Google Ads Daily] Total spend: ${total_cost:,.0f}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"tableData": daily}, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Q13d -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
