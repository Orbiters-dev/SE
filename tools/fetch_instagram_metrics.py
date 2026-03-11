"""Fetch Instagram metrics for a given handle using Meta Graph API.

Uses the business_discovery endpoint to look up public metrics of
Instagram Business/Creator accounts by username.

Usage:
    python tools/fetch_instagram_metrics.py --handle "grosmimi_usa"
    python tools/fetch_instagram_metrics.py --handle "@janedoe" --output json

Prerequisites:
    .wat_secrets: META_ACCESS_TOKEN, INSTAGRAM_BUSINESS_USER_ID
    (INSTAGRAM_BUSINESS_USER_ID = your brand's IG account ID for business_discovery)
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
load_env()

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("INSTAGRAM_BUSINESS_USER_ID", "")
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def graph_request(path, params=None):
    """Make a request to the Meta Graph API."""
    qs = urllib.parse.urlencode(params or {})
    url = f"{GRAPH_API_BASE}{path}?{qs}" if qs else f"{GRAPH_API_BASE}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {e.code}: {error_body[:500]}")
        raise


def lookup_own_ig_user_id():
    """Find the IG user ID connected to the current Meta access token.
    This is a one-time helper to find INSTAGRAM_BUSINESS_USER_ID.
    """
    print("  Looking up connected Instagram Business accounts...")

    # Get Facebook pages
    result = graph_request("/me/accounts", {
        "access_token": META_ACCESS_TOKEN,
        "fields": "id,name,instagram_business_account{id,username}",
    })

    ig_accounts = []
    for page in result.get("data", []):
        ig = page.get("instagram_business_account")
        if ig:
            ig_accounts.append({
                "page_name": page.get("name"),
                "page_id": page.get("id"),
                "ig_user_id": ig.get("id"),
                "ig_username": ig.get("username"),
            })

    if not ig_accounts:
        print("  [WARN] No Instagram Business accounts found connected to this token.")
        print("  Make sure your Meta access token has instagram_basic permission")
        print("  and a Facebook Page is connected to an Instagram Business account.")
        return None

    print(f"\n  Found {len(ig_accounts)} Instagram Business account(s):")
    for acc in ig_accounts:
        print(f"    - @{acc['ig_username']} (ID: {acc['ig_user_id']}) via Page: {acc['page_name']}")

    return ig_accounts[0]["ig_user_id"]


def fetch_metrics(handle):
    """Fetch Instagram metrics for a given handle using business_discovery."""
    # Clean handle
    handle = handle.lstrip("@").strip()

    if not IG_USER_ID:
        print("  [ERROR] INSTAGRAM_BUSINESS_USER_ID not set in ~/.wat_secrets")
        print("  Run: python tools/fetch_instagram_metrics.py --find-ig-id")
        return None

    fields = (
        "business_discovery.username({handle}){"
        "id,username,name,biography,followers_count,follows_count,"
        "media_count,profile_picture_url,"
        "media.limit(12){id,timestamp,like_count,comments_count,media_type,caption}"
        "}"
    ).replace("{handle}", handle)

    result = graph_request(f"/{IG_USER_ID}", {
        "fields": fields,
        "access_token": META_ACCESS_TOKEN,
    })

    bd = result.get("business_discovery")
    if not bd:
        print(f"  [WARN] Could not find business account for @{handle}")
        print("  Note: Only Instagram Business/Creator accounts are discoverable.")
        return None

    # Parse recent media
    recent_posts = []
    media_data = bd.get("media", {}).get("data", [])
    total_engagement = 0
    for post in media_data:
        likes = post.get("like_count", 0)
        comments = post.get("comments_count", 0)
        engagement = likes + comments
        total_engagement += engagement
        recent_posts.append({
            "id": post.get("id"),
            "timestamp": post.get("timestamp"),
            "media_type": post.get("media_type"),
            "likes": likes,
            "comments": comments,
            "engagement": engagement,
            "caption": (post.get("caption") or "")[:100],
        })

    avg_engagement = round(total_engagement / len(recent_posts)) if recent_posts else 0
    followers = bd.get("followers_count", 0)
    engagement_rate = round((avg_engagement / followers) * 100, 2) if followers > 0 else 0

    return {
        "username": bd.get("username"),
        "name": bd.get("name"),
        "biography": bd.get("biography"),
        "followers_count": followers,
        "follows_count": bd.get("follows_count", 0),
        "media_count": bd.get("media_count", 0),
        "profile_picture_url": bd.get("profile_picture_url"),
        "avg_engagement": avg_engagement,
        "engagement_rate_pct": engagement_rate,
        "recent_posts": recent_posts,
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Fetch Instagram metrics via Meta Graph API")
    parser.add_argument("--handle", type=str, help="Instagram handle to look up")
    parser.add_argument("--find-ig-id", action="store_true", help="Find your brand's IG Business User ID")
    parser.add_argument("--output", choices=["json", "pretty"], default="pretty", help="Output format")
    args = parser.parse_args()

    if not META_ACCESS_TOKEN:
        print("[ERROR] META_ACCESS_TOKEN not set in ~/.wat_secrets")
        sys.exit(1)

    if args.find_ig_id:
        ig_id = lookup_own_ig_user_id()
        if ig_id:
            print(f"\n  Add to ~/.wat_secrets:")
            print(f"    INSTAGRAM_BUSINESS_USER_ID={ig_id}")
        return

    if not args.handle:
        parser.print_help()
        sys.exit(1)

    print(f"\n  Fetching Instagram metrics for @{args.handle.lstrip('@')}...")
    metrics = fetch_metrics(args.handle)

    if not metrics:
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'=' * 50}")
        print(f"  @{metrics['username']} ({metrics['name'] or 'N/A'})")
        print(f"{'=' * 50}")
        print(f"  Followers:    {metrics['followers_count']:,}")
        print(f"  Following:    {metrics['follows_count']:,}")
        print(f"  Posts:        {metrics['media_count']:,}")
        print(f"  Avg Engage:   {metrics['avg_engagement']:,} per post")
        print(f"  Engage Rate:  {metrics['engagement_rate_pct']}%")
        print(f"  Bio:          {(metrics['biography'] or '')[:80]}")
        print(f"{'=' * 50}")
        print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
