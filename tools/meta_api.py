"""
Meta Marketing API - Ad spend & performance data fetcher

Uses Ads Insights API to pull spend, impressions, clicks, CPC, CTR per campaign.
Auth: System User token with ads_read permission.
Endpoint: https://graph.facebook.com/v21.0/{ad_account_id}/insights
"""

import os, sys, io, json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests

def _setup_encoding():
    if hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")

BASE_URL = "https://graph.facebook.com/v21.0"


def get_account_insights(date_from, date_to, level="account"):
    """Get ad account level insights for a date range.

    Args:
        date_from: "YYYY-MM-DD"
        date_to:   "YYYY-MM-DD"
        level: "account", "campaign", or "ad"

    Returns: list of insight dicts
    """
    params = {
        "access_token": ACCESS_TOKEN,
        "time_range": json.dumps({"since": date_from, "until": date_to}),
        "fields": "spend,impressions,clicks,cpc,ctr,reach,frequency,actions",
        "level": level,
        "limit": 500,
    }

    if level in ("campaign", "ad", "adset"):
        params["fields"] += ",campaign_name,campaign_id"
    if level in ("adset", "ad"):
        params["fields"] += ",adset_name,adset_id"
    if level == "ad":
        params["fields"] += ",ad_name,ad_id"

    resp = requests.get(
        f"{BASE_URL}/{AD_ACCOUNT_ID}/insights",
        params=params,
        timeout=30,
    )

    # If 400 error with reach/frequency, retry without them
    if resp.status_code == 400 and "reach" in params["fields"]:
        print("  [WARN] Retrying without reach/frequency fields...")
        params["fields"] = params["fields"].replace(",reach,frequency", "")
        resp = requests.get(
            f"{BASE_URL}/{AD_ACCOUNT_ID}/insights",
            params=params,
            timeout=30,
        )

    resp.raise_for_status()
    data = resp.json()

    results = data.get("data", [])
    print(f"  Got {len(results)} {level}-level insight rows")
    return results


def get_campaign_insights(date_from, date_to):
    """Get campaign-level breakdown."""
    return get_account_insights(date_from, date_to, level="campaign")


def get_adset_insights(date_from, date_to):
    """Get ad set-level breakdown."""
    return get_account_insights(date_from, date_to, level="adset")


def get_ad_insights(date_from, date_to):
    """Get ad-level breakdown (includes adset_name for grouping)."""
    return get_account_insights(date_from, date_to, level="ad")


def weekly_ad_spend(date_from, date_to):
    """Get total ad spend and performance for a date range.

    Args:
        date_from: "YYYY-MM-DD"
        date_to:   "YYYY-MM-DD"

    Returns: dict with total_spend, impressions, clicks, cpc, ctr
    """
    print(f"\nFetching Meta ad data: {date_from} ~ {date_to}")
    insights = get_account_insights(date_from, date_to, level="account")

    if not insights:
        return {
            "total_spend": 0,
            "impressions": 0,
            "clicks": 0,
            "cpc": 0,
            "ctr": 0,
            "campaigns": [],
        }

    row = insights[0]
    total_spend = float(row.get("spend", 0))
    impressions = int(row.get("impressions", 0))
    clicks = int(row.get("clicks", 0))
    cpc = float(row.get("cpc", 0))
    ctr = float(row.get("ctr", 0))

    print(f"  Total spend: ¥{total_spend:,.0f}")
    print(f"  Impressions: {impressions:,}")
    print(f"  Clicks: {clicks:,}")
    print(f"  CPC: ¥{cpc:,.1f}")
    print(f"  CTR: {ctr:.2f}%")

    # Also fetch campaign breakdown
    campaigns = get_campaign_insights(date_from, date_to)

    return {
        "total_spend": total_spend,
        "impressions": impressions,
        "clicks": clicks,
        "cpc": cpc,
        "ctr": ctr,
        "campaigns": campaigns,
    }


def test_connection():
    """Quick test: fetch last 7 days of ad data."""
    print("=" * 50)
    print("Meta Marketing API Connection Test")
    print("=" * 50)
    print(f"Ad Account: {AD_ACCOUNT_ID}")
    print(f"Token: {ACCESS_TOKEN[:20]}... (loaded)")

    today = datetime.now()
    week_ago = today - timedelta(days=7)

    result = weekly_ad_spend(
        week_ago.strftime("%Y-%m-%d"),
        today.strftime("%Y-%m-%d"),
    )

    print(f"\n--- Result ---")
    print(f"Total Spend: ¥{result['total_spend']:,.0f}")
    print(f"Impressions: {result['impressions']:,}")
    print(f"Clicks: {result['clicks']:,}")

    if result["campaigns"]:
        print(f"\nCampaigns ({len(result['campaigns'])}):")
        for c in result["campaigns"]:
            name = c.get("campaign_name", "N/A")
            spend = float(c.get("spend", 0))
            impr = int(c.get("impressions", 0))
            print(f"  - {name}: ¥{spend:,.0f} / {impr:,} impr")

    return result


if __name__ == "__main__":
    _setup_encoding()
    test_connection()
