"""
fetch_google_ads_monthly.py - Google Ads campaign daily data collector (Q7 replacement)

Source: Adapted from Orbiters11-dev/dashboard/google_datacollector.py
Output: .tmp/polar_data/q7_google_ads_campaign.json
Format: {"tableData": [{"googleads_campaign_and_device.raw.cost": X,
                        "googleads_campaign_and_device.raw.conversion_value": X,
                        "googleads_campaign_and_device.raw.clicks": X,
                        "googleads_campaign_and_device.raw.impressions": X,
                        "campaign": "name", "date": "YYYY-MM-01"}]}

Usage:
    python tools/no_polar/fetch_google_ads_monthly.py --start 2024-01 --end 2026-02
"""

import os
import sys
import json
import time
import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Iterable, Tuple
from collections import defaultdict
from pathlib import Path

from dateutil.relativedelta import relativedelta

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUTPUT_PATH = ROOT / ".tmp" / "polar_data" / "q7_google_ads_campaign.json"

MICROS = Decimal("1000000")
MCC_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "8625697405")


# ---------------------------------------------------------------------------
# Google Ads client (requires google-ads package)
# ---------------------------------------------------------------------------

def _build_client():
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("[ERROR] google-ads package not installed.")
        print("        Run: pip install google-ads")
        sys.exit(1)

    dev_token    = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
    client_id    = os.getenv("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
    login_cid    = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")

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


# ---------------------------------------------------------------------------
# Account discovery (MCC children)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Campaign daily metrics for one client
# ---------------------------------------------------------------------------

def fetch_campaign_daily(client, customer_id: str, start_date: str, end_date: str) -> List[Dict]:
    ga = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          segments.date,
          campaign.id,
          campaign.name,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
          AND campaign.status != 'REMOVED'
        ORDER BY segments.date, campaign.id
    """
    out = []
    try:
        # Use search_stream for efficiency (no page_size needed)
        stream = ga.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            for r in batch.results:
                date_val      = r.segments.date
                campaign_id   = str(r.campaign.id)
                campaign_name = r.campaign.name or ""
                impressions   = int(r.metrics.impressions or 0)
                clicks        = int(r.metrics.clicks or 0)
                cost_micros   = int(r.metrics.cost_micros or 0)
                conversions   = Decimal(str(r.metrics.conversions or 0))
                conv_value    = Decimal(str(r.metrics.conversions_value or 0))
                spend         = Decimal(cost_micros) / MICROS

                out.append({
                    "date":           date_val,
                    "campaign_id":    campaign_id,
                    "campaign_name":  campaign_name,
                    "impressions":    impressions,
                    "clicks":         clicks,
                    "spend":          float(spend),
                    "purchase_value": float(conv_value),
                    "purchases":      float(conversions),
                })
    except Exception as e:
        print(f"  [WARN] customer {customer_id} query failed: {e}")

    return out


# ---------------------------------------------------------------------------
# Fetch all clients under MCC
# ---------------------------------------------------------------------------

def fetch_all_clients(client, mcc_id: str, start_date: str, end_date: str) -> List[Dict]:
    clients = list_client_accounts(client, mcc_id)
    target_ids = [c["client_customer_id"] for c in clients if not c["is_manager"]]

    # If no sub-accounts, try MCC itself as a direct account
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


# ---------------------------------------------------------------------------
# Monthly aggregation → Q7 format
# ---------------------------------------------------------------------------

def aggregate_monthly(rows: List[Dict]) -> List[Dict]:
    bucket: Dict[Tuple, Dict] = defaultdict(lambda: {
        "cost": 0.0, "conversion_value": 0.0, "clicks": 0, "impressions": 0
    })

    for r in rows:
        d = r.get("date")
        if not d:
            continue
        try:
            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        month_key = date(dt.year, dt.month, 1).strftime("%Y-%m-%d")
        name = (r.get("campaign_name") or r.get("campaign_id", "")).lower().replace(" ", "_")
        key = (name, month_key)
        bucket[key]["cost"]             += float(r.get("spend", 0) or 0)
        bucket[key]["conversion_value"] += float(r.get("purchase_value", 0) or 0)
        bucket[key]["clicks"]           += int(r.get("clicks", 0) or 0)
        bucket[key]["impressions"]      += int(r.get("impressions", 0) or 0)

    out = []
    for (campaign, month_key), v in sorted(bucket.items()):
        out.append({
            "googleads_campaign_and_device.raw.cost":              round(v["cost"], 6),
            "googleads_campaign_and_device.raw.conversion_value":  round(v["conversion_value"], 6),
            "googleads_campaign_and_device.raw.clicks":            v["clicks"],
            "googleads_campaign_and_device.raw.impressions":       v["impressions"],
            "campaign":                                            campaign,
            "date":                                                month_key,
        })
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch Google Ads campaign data (Q7)")
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

    print(f"[Google Ads] {start_date} ~ {end_date} | MCC: {MCC_ID}")

    client = _build_client()
    rows = fetch_all_clients(client, MCC_ID, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    print(f"[Google Ads] Total daily rows: {len(rows)}")

    monthly = aggregate_monthly(rows)
    print(f"[Google Ads] Monthly rows: {len(monthly)}")

    total_cost  = sum(r["googleads_campaign_and_device.raw.cost"] for r in monthly)
    total_sales = sum(r["googleads_campaign_and_device.raw.conversion_value"] for r in monthly)
    print(f"[Google Ads] Total spend: ${total_cost:,.0f} | conversion value: ${total_sales:,.0f}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"tableData": monthly, "totalData": {}}, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
