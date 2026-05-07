"""
WAT Tool: Fetch Meta (Facebook) Ads campaign performance data.

Uses the Meta Marketing API to pull weekly campaign-level insights
including spend, impressions, clicks, CTR, and conversions.

Usage:
    python tools/fetch_meta_ads.py                  # fetch last 7 days
    python tools/fetch_meta_ads.py --days 14         # fetch last 14 days
    python tools/fetch_meta_ads.py --since 2026-02-01 --until 2026-02-14
    python tools/fetch_meta_ads.py --check-token     # check token scopes only

Output:
    .tmp/meta_ads_weekly.json
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

META_API_BASE = "https://graph.facebook.com/v21.0"
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp"
OUTPUT_PATH = OUTPUT_DIR / "meta_ads_weekly.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Token & Account helpers ──────────────────────────────────────────

def check_token_scopes(access_token: str) -> dict:
    """Check token validity and whether it has ads_read scope."""
    url = f"{META_API_BASE}/debug_token"
    params = {"input_token": access_token, "access_token": access_token}

    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data", {})

    scopes = data.get("scopes", [])
    has_ads_read = "ads_read" in scopes

    return {
        "is_valid": data.get("is_valid", False),
        "scopes": scopes,
        "has_ads_read": has_ads_read,
        "expires_at": data.get("expires_at", 0),
        "type": data.get("type", "unknown"),
    }


def get_ad_accounts(access_token: str) -> list[dict]:
    """Fetch all ad accounts accessible to this token."""
    url = f"{META_API_BASE}/me/adaccounts"
    params = {
        "fields": "id,name,currency,account_status",
        "access_token": access_token,
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    accounts = resp.json().get("data", [])
    return accounts


def save_ad_account_to_env(account_id: str) -> None:
    """Save discovered ad account ID to .env for future use."""
    import re
    content = env_path.read_text(encoding="utf-8")

    key = "META_AD_ACCOUNT_ID"
    pattern = re.compile(rf'^{re.escape(key)}=.*$', re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(f"{key}={account_id}", content)
    else:
        content = content.rstrip() + f"\n{key}={account_id}\n"

    env_path.write_text(content, encoding="utf-8")
    logger.info(f"Saved {key}={account_id} to .env")


# ── Insights fetcher ─────────────────────────────────────────────────

def fetch_campaign_insights(
    access_token: str,
    ad_account_id: str,
    since: str | None = None,
    until: str | None = None,
    date_preset: str | None = None,
) -> list[dict]:
    """
    Fetch campaign-level insights from Meta Marketing API.

    Args:
        ad_account_id: Full ID including 'act_' prefix
        since/until: Date strings in YYYY-MM-DD format
        date_preset: Meta preset like 'last_7d', 'last_30d', 'this_month'
    """
    url = f"{META_API_BASE}/{ad_account_id}/insights"

    fields = [
        "campaign_id",
        "campaign_name",
        "objective",
        "spend",
        "impressions",
        "clicks",
        "cpc",
        "cpm",
        "ctr",
        "reach",
        "frequency",
        "actions",
        "action_values",
    ]

    params = {
        "level": "campaign",
        "fields": ",".join(fields),
        "access_token": access_token,
        "limit": 100,
    }

    if since and until:
        params["time_range"] = json.dumps({"since": since, "until": until})
    elif date_preset:
        params["date_preset"] = date_preset
    else:
        params["date_preset"] = "last_7d"

    all_data = []
    page_url = url

    while page_url:
        resp = requests.get(page_url, params=params if page_url == url else None, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        all_data.extend(result.get("data", []))

        # Handle pagination
        paging = result.get("paging", {})
        page_url = paging.get("next")

    return all_data


def parse_actions(actions: list[dict] | None) -> dict:
    """Extract key action types from Meta's actions array."""
    if not actions:
        return {}

    parsed = {}
    for action in actions:
        action_type = action.get("action_type", "")
        value = action.get("value", "0")
        if action_type in (
            "purchase",
            "add_to_cart",
            "initiate_checkout",
            "link_click",
            "landing_page_view",
            "view_content",
            "lead",
        ):
            parsed[action_type] = int(value)
    return parsed


def parse_action_values(action_values: list[dict] | None) -> dict:
    """Extract monetary values from action_values."""
    if not action_values:
        return {}

    parsed = {}
    for av in action_values:
        action_type = av.get("action_type", "")
        value = av.get("value", "0")
        if action_type == "purchase":
            parsed["purchase_value"] = float(value)
    return parsed


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch Meta Ads campaign insights")
    parser.add_argument("--check-token", action="store_true", help="Check token scopes only")
    parser.add_argument("--days", type=int, help="Fetch last N days (default: 7)")
    parser.add_argument("--since", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    # Load token
    access_token = os.getenv("IG_ACCESS_TOKEN")
    if not access_token:
        logger.error("IG_ACCESS_TOKEN not found in .env")
        sys.exit(1)

    # ── Check token ──────────────────────────────────────────────
    print("=== Meta Ads Weekly Report ===\n")
    print("[1/4] Checking token...")

    token_info = check_token_scopes(access_token)

    if not token_info["is_valid"]:
        logger.error("Token is invalid or expired. Run: python tools/refresh_ig_token.py")
        sys.exit(1)

    print(f"  Token valid: {token_info['is_valid']}")
    print(f"  Scopes: {', '.join(token_info['scopes'])}")
    print(f"  ads_read: {'YES' if token_info['has_ads_read'] else 'NO — REQUIRED'}")

    if not token_info["has_ads_read"]:
        print("\n[ERROR] Token lacks 'ads_read' scope.")
        print("You need to regenerate the token with ads_read permission:")
        print("  1. Go to https://developers.facebook.com/tools/explorer/")
        print("  2. Select your app")
        print("  3. Add 'ads_read' permission")
        print("  4. Generate token and update IG_ACCESS_TOKEN in .env")
        sys.exit(1)

    if args.check_token:
        print("\n[OK] Token check complete.")
        return

    # ── Get ad account ───────────────────────────────────────────
    print("\n[2/4] Getting ad account...")

    ad_account_id = os.getenv("META_AD_ACCOUNT_ID")

    if not ad_account_id:
        accounts = get_ad_accounts(access_token)
        if not accounts:
            logger.error("No ad accounts found for this token.")
            sys.exit(1)

        # Use first active account
        for acc in accounts:
            print(f"  Found: {acc['id']} — {acc.get('name', 'N/A')} ({acc.get('currency', '?')})")

        ad_account_id = accounts[0]["id"]
        save_ad_account_to_env(ad_account_id)
    else:
        print(f"  Using saved account: {ad_account_id}")

    # ── Fetch insights ───────────────────────────────────────────
    print("\n[3/4] Fetching campaign insights...")

    since_date = args.since
    until_date = args.until
    date_preset = None

    if since_date and until_date:
        print(f"  Date range: {since_date} to {until_date}")
    elif args.days:
        until_dt = datetime.now()
        since_dt = until_dt - timedelta(days=args.days)
        since_date = since_dt.strftime("%Y-%m-%d")
        until_date = until_dt.strftime("%Y-%m-%d")
        print(f"  Last {args.days} days: {since_date} to {until_date}")
    else:
        date_preset = "last_7d"
        print("  Date range: last_7d")

    raw_insights = fetch_campaign_insights(
        access_token=access_token,
        ad_account_id=ad_account_id,
        since=since_date,
        until=until_date,
        date_preset=date_preset,
    )

    print(f"  Found {len(raw_insights)} campaign(s)")

    # ── Parse & save ─────────────────────────────────────────────
    print("\n[4/4] Saving results...")

    campaigns = []
    total_spend = 0.0

    for row in raw_insights:
        spend = float(row.get("spend", 0))
        total_spend += spend

        actions = parse_actions(row.get("actions"))
        action_values = parse_action_values(row.get("action_values"))

        campaigns.append({
            "campaign_id": row.get("campaign_id"),
            "campaign_name": row.get("campaign_name"),
            "objective": row.get("objective"),
            "spend": spend,
            "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("clicks", 0)),
            "cpc": float(row.get("cpc", 0)),
            "cpm": float(row.get("cpm", 0)),
            "ctr": float(row.get("ctr", 0)),
            "reach": int(row.get("reach", 0)),
            "frequency": float(row.get("frequency", 0)),
            "actions": actions,
            "purchase_value": action_values.get("purchase_value", 0),
        })

    # Sort by spend descending
    campaigns.sort(key=lambda c: c["spend"], reverse=True)

    output = {
        "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "ad_account_id": ad_account_id,
        "date_range": {
            "since": since_date,
            "until": until_date,
            "preset": date_preset,
        },
        "summary": {
            "total_campaigns": len(campaigns),
            "total_spend": round(total_spend, 2),
            "currency": "JPY",
        },
        "campaigns": campaigns,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Total spend: ¥{total_spend:,.0f}")
    print(f"  Campaigns: {len(campaigns)}")
    print(f"  Saved to: {OUTPUT_PATH}")

    # Print summary table
    if campaigns:
        print(f"\n  {'Campaign':<40} {'Spend':>12} {'Impr':>10} {'Clicks':>8} {'CTR':>6}")
        print(f"  {'-'*40} {'-'*12} {'-'*10} {'-'*8} {'-'*6}")
        for c in campaigns[:10]:
            name = c["campaign_name"][:38] if c["campaign_name"] else "N/A"
            print(f"  {name:<40} ¥{c['spend']:>10,.0f} {c['impressions']:>10,} {c['clicks']:>8,} {c['ctr']:>5.2f}%")

    print("\n[OK] Meta Ads weekly report complete.")


if __name__ == "__main__":
    main()
