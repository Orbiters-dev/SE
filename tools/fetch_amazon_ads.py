"""
WAT Tool: Fetch Amazon Advertising campaign performance data.

Uses the Amazon Advertising API (Reporting v3) to pull campaign-level
performance including spend, impressions, clicks, attributed sales, and ACOS.

Prerequisites:
    - Amazon Advertising API developer access approved
    - OAuth credentials in .env (see workflows/weekly_dashboard_report.md)

Usage:
    python tools/fetch_amazon_ads.py                 # fetch last 7 days
    python tools/fetch_amazon_ads.py --days 14        # fetch last 14 days
    python tools/fetch_amazon_ads.py --check-token    # check credentials only

Output:
    .tmp/amazon_ads_weekly.json

Setup guide: workflows/weekly_dashboard_report.md
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

AMAZON_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
AMAZON_ADS_API_BASE = "https://advertising-api-fe.amazon.com"  # Far East (JP)
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp"
OUTPUT_PATH = OUTPUT_DIR / "amazon_ads_weekly.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Auth ─────────────────────────────────────────────────────────────

def check_credentials() -> dict:
    """Validate that all required .env variables are present."""
    required = {
        "AMAZON_ADS_CLIENT_ID": os.getenv("AMAZON_ADS_CLIENT_ID"),
        "AMAZON_ADS_CLIENT_SECRET": os.getenv("AMAZON_ADS_CLIENT_SECRET"),
        "AMAZON_ADS_REFRESH_TOKEN": os.getenv("AMAZON_ADS_REFRESH_TOKEN"),
        "AMAZON_ADS_PROFILE_ID": os.getenv("AMAZON_ADS_PROFILE_ID"),
    }
    missing = [k for k, v in required.items() if not v]
    return {"ok": len(missing) == 0, "missing": missing, "values": required}


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange refresh token for a new access token."""
    resp = requests.post(AMAZON_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Reporting API ────────────────────────────────────────────────────

def create_report(access_token: str, profile_id: str, since: str, until: str) -> str:
    """
    Create an async Sponsored Products campaign report.
    Returns the report ID.
    """
    url = f"{AMAZON_ADS_API_BASE}/reporting/reports"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Amazon-Advertising-API-ClientId": os.getenv("AMAZON_ADS_CLIENT_ID"),
        "Amazon-Advertising-API-Scope": profile_id,
        "Content-Type": "application/vnd.createasyncreportrequest.v3+json",
    }

    payload = {
        "name": f"Weekly SP Campaign Report {since} to {until}",
        "startDate": since,
        "endDate": until,
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": ["campaign"],
            "columns": [
                "campaignId",
                "campaignName",
                "campaignStatus",
                "impressions",
                "clicks",
                "cost",
                "purchases7d",
                "sales7d",
            ],
            "reportTypeId": "spCampaigns",
            "timeUnit": "SUMMARY",
            "format": "GZIP_JSON",
        },
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    report_id = resp.json().get("reportId")
    logger.info(f"Report created: {report_id}")
    return report_id


def poll_report(access_token: str, profile_id: str, report_id: str, max_wait: int = 300) -> str:
    """
    Poll report status until complete. Returns download URL.
    """
    url = f"{AMAZON_ADS_API_BASE}/reporting/reports/{report_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Amazon-Advertising-API-ClientId": os.getenv("AMAZON_ADS_CLIENT_ID"),
        "Amazon-Advertising-API-Scope": profile_id,
    }

    elapsed = 0
    interval = 10

    while elapsed < max_wait:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")

        if status == "COMPLETED":
            return data.get("url")
        elif status == "FAILED":
            raise RuntimeError(f"Report failed: {data}")

        logger.info(f"  Report status: {status} (waiting {interval}s...)")
        time.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"Report not ready after {max_wait}s")


def download_report(download_url: str) -> list[dict]:
    """Download and decompress the report."""
    import gzip

    resp = requests.get(download_url, timeout=60)
    resp.raise_for_status()

    decompressed = gzip.decompress(resp.content)
    return json.loads(decompressed)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch Amazon Ads campaign performance")
    parser.add_argument("--check-token", action="store_true", help="Check credentials only")
    parser.add_argument("--days", type=int, default=7, help="Fetch last N days (default: 7)")
    args = parser.parse_args()

    print("=== Amazon Ads Weekly Report ===\n")

    # ── Check credentials ────────────────────────────────────────
    print("[1/5] Checking credentials...")
    creds = check_credentials()

    if not creds["ok"]:
        print(f"\n[ERROR] Missing .env variables:")
        for key in creds["missing"]:
            print(f"  - {key}")
        print("\nSee workflows/weekly_dashboard_report.md for setup instructions.")
        sys.exit(1)

    print("  All credentials present.")

    if args.check_token:
        print("\n[OK] Credential check complete.")
        return

    # ── Refresh token ────────────────────────────────────────────
    print("\n[2/5] Refreshing access token...")
    access_token = refresh_access_token(
        client_id=creds["values"]["AMAZON_ADS_CLIENT_ID"],
        client_secret=creds["values"]["AMAZON_ADS_CLIENT_SECRET"],
        refresh_token=creds["values"]["AMAZON_ADS_REFRESH_TOKEN"],
    )
    print("  Token refreshed.")

    profile_id = creds["values"]["AMAZON_ADS_PROFILE_ID"]

    # ── Create report ────────────────────────────────────────────
    until_dt = datetime.now() - timedelta(days=1)  # yesterday (data delay)
    since_dt = until_dt - timedelta(days=args.days - 1)
    since_str = since_dt.strftime("%Y-%m-%d")
    until_str = until_dt.strftime("%Y-%m-%d")

    print(f"\n[3/5] Creating report ({since_str} to {until_str})...")
    report_id = create_report(access_token, profile_id, since_str, until_str)

    # ── Poll & download ──────────────────────────────────────────
    print("\n[4/5] Waiting for report...")
    download_url = poll_report(access_token, profile_id, report_id)
    print("  Report ready. Downloading...")

    raw_data = download_report(download_url)
    print(f"  Downloaded {len(raw_data)} campaign(s)")

    # ── Parse & save ─────────────────────────────────────────────
    print("\n[5/5] Saving results...")

    campaigns = []
    total_spend = 0.0
    total_sales = 0.0

    for row in raw_data:
        spend = float(row.get("cost", 0))
        sales = float(row.get("sales7d", 0))
        total_spend += spend
        total_sales += sales

        campaigns.append({
            "campaign_id": row.get("campaignId"),
            "campaign_name": row.get("campaignName"),
            "status": row.get("campaignStatus"),
            "spend": spend,
            "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("clicks", 0)),
            "attributed_sales_7d": sales,
            "purchases_7d": int(row.get("purchases7d", 0)),
            "acos": round(spend / sales * 100, 2) if sales > 0 else None,
            "roas": round(sales / spend, 2) if spend > 0 else None,
        })

    campaigns.sort(key=lambda c: c["spend"], reverse=True)

    output = {
        "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "profile_id": profile_id,
        "date_range": {"since": since_str, "until": until_str},
        "summary": {
            "total_campaigns": len(campaigns),
            "total_spend": round(total_spend, 2),
            "total_attributed_sales": round(total_sales, 2),
            "overall_acos": round(total_spend / total_sales * 100, 2) if total_sales > 0 else None,
            "overall_roas": round(total_sales / total_spend, 2) if total_spend > 0 else None,
            "currency": "JPY",
        },
        "campaigns": campaigns,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Total spend: ¥{total_spend:,.0f}")
    print(f"  Total sales (7d attr.): ¥{total_sales:,.0f}")
    if total_spend > 0:
        print(f"  ACOS: {total_spend / total_sales * 100:.1f}%" if total_sales > 0 else "  ACOS: N/A")
        print(f"  ROAS: {total_sales / total_spend:.2f}x")
    print(f"  Saved to: {OUTPUT_PATH}")
    print("\n[OK] Amazon Ads weekly report complete.")


if __name__ == "__main__":
    main()
