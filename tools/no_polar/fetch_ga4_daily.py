"""
fetch_ga4_daily.py - GA4 daily traffic & conversion collector (Q13b)

Fetches sessions and ecommerce_purchases from Google Analytics 4 Data API,
both total and by default channel grouping.

Outputs:
  .tmp/polar_data/q13b_ga4_daily.json            - total sessions + purchases per day
  .tmp/polar_data/q13b_ga4_by_channel_daily.json  - sessions + purchases by channel per day

Usage:
    python tools/no_polar/fetch_ga4_daily.py --start 2024-01 --end 2026-03
"""

import os
import sys
import json
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from dateutil.relativedelta import relativedelta

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUT_TOTAL   = ROOT / ".tmp" / "polar_data" / "q13b_ga4_daily.json"
OUT_CHANNEL = ROOT / ".tmp" / "polar_data" / "q13b_ga4_by_channel_daily.json"

PROPERTY_ID = os.getenv("GA4_PROPERTY_ID")


def _build_credentials():
    """Build OAuth credentials for GA4 Data API."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    client_id = os.getenv("GA4_CLIENT_ID")
    client_secret = os.getenv("GA4_CLIENT_SECRET")
    refresh_token = os.getenv("GA4_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("[ERROR] GA4_CLIENT_ID, GA4_CLIENT_SECRET, GA4_REFRESH_TOKEN required in .wat_secrets")
        print("        Run: python tools/no_polar/ga4_oauth_setup.py")
        sys.exit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    creds.refresh(Request())
    print("  Using GA4 OAuth credentials")
    return creds


def _build_client(creds):
    """Build GA4 Data API client."""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
    except ImportError:
        print("[ERROR] google-analytics-data package not installed.")
        print("        Run: pip install google-analytics-data")
        sys.exit(1)

    return BetaAnalyticsDataClient(credentials=creds)


def fetch_daily_totals(client, property_id, start_date, end_date):
    """Fetch daily sessions + ecommerce_purchases (total)."""
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
    )

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="ecommercePurchases"),
        ],
        limit=10000,
    )

    response = client.run_report(request)
    rows = []
    for row in response.rows:
        d = row.dimension_values[0].value  # "20260201"
        date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        rows.append({
            "ga_main.raw.sessions": int(row.metric_values[0].value),
            "ga_main.raw.ecommerce_purchases": int(row.metric_values[1].value),
            "date": date_str,
        })

    return sorted(rows, key=lambda r: r["date"])


def fetch_daily_by_channel(client, property_id, start_date, end_date):
    """Fetch daily sessions + purchases by default channel grouping."""
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
    )

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[
            Dimension(name="date"),
            Dimension(name="sessionDefaultChannelGroup"),
        ],
        metrics=[
            Metric(name="sessions"),
            Metric(name="ecommercePurchases"),
        ],
        limit=50000,
    )

    response = client.run_report(request)
    rows = []
    for row in response.rows:
        d = row.dimension_values[0].value
        channel = row.dimension_values[1].value
        date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        rows.append({
            "ga_main.raw.sessions": int(row.metric_values[0].value),
            "ga_main.raw.ecommerce_purchases": int(row.metric_values[1].value),
            "custom_internal-default-channel-grouping": channel,
            "date": date_str,
        })

    return sorted(rows, key=lambda r: (r["date"], r["custom_internal-default-channel-grouping"]))


def main():
    parser = argparse.ArgumentParser(description="Fetch GA4 daily data (Q13b)")
    parser.add_argument("--start", default="2024-01", help="Start month YYYY-MM")
    parser.add_argument("--end",   default=None,      help="End month YYYY-MM")
    args = parser.parse_args()

    if not PROPERTY_ID:
        print("[ERROR] GA4_PROPERTY_ID not set")
        sys.exit(1)

    today = date.today()
    start_date = datetime.strptime(args.start, "%Y-%m").date().replace(day=1)
    end_str = args.end or today.strftime("%Y-%m")
    end_date = datetime.strptime(end_str, "%Y-%m").date().replace(day=1)
    end_dt = (end_date + relativedelta(months=1)) - timedelta(days=1)
    if end_dt > today:
        end_dt = today

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    print(f"[GA4] Property: {PROPERTY_ID} | {start_str} ~ {end_str}")

    creds = _build_credentials()
    client = _build_client(creds)

    # Total daily
    print("[GA4] Fetching daily totals...")
    total_rows = fetch_daily_totals(client, PROPERTY_ID, start_str, end_str)
    total_sessions = sum(r["ga_main.raw.sessions"] for r in total_rows)
    total_purchases = sum(r["ga_main.raw.ecommerce_purchases"] for r in total_rows)
    print(f"  {len(total_rows)} days | {total_sessions:,} sessions, {total_purchases:,} purchases")

    # By channel daily
    print("[GA4] Fetching daily by channel...")
    channel_rows = fetch_daily_by_channel(client, PROPERTY_ID, start_str, end_str)
    channels = set(r["custom_internal-default-channel-grouping"] for r in channel_rows)
    print(f"  {len(channel_rows)} rows | {len(channels)} channels: {', '.join(sorted(channels))}")

    # Save
    for path, data, label in [
        (OUT_TOTAL,   {"tableData": total_rows},   "Q13b total"),
        (OUT_CHANNEL, {"tableData": channel_rows}, "Q13b by channel"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] {label} -> {path} ({len(data['tableData'])} rows)")


if __name__ == "__main__":
    main()
