"""Check if an influencer posted content with a specific hashtag on Instagram.

Uses Meta Graph API business_discovery to fetch an influencer's recent posts
and check whether they contain a given hashtag.

Usage:
    python tools/check_influencer_hashtag.py --handle "influencer_name" --hashtag "grosmimi"
    python tools/check_influencer_hashtag.py --handle "influencer_name" --hashtag "#grosmimi" --limit 50
    python tools/check_influencer_hashtag.py --handle "influencer_name" --hashtag "grosmimi" --days 30
    python tools/check_influencer_hashtag.py --handle "influencer_name" --hashtag "grosmimi" --output json

Prerequisites:
    .wat_secrets: META_ACCESS_TOKEN, INSTAGRAM_BUSINESS_USER_ID
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
load_env()

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("INSTAGRAM_BUSINESS_USER_ID", "")
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def graph_request(url):
    """Make a GET request to the Meta Graph API."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [API ERROR] {e.code}: {error_body[:500]}")
        raise


def build_url(path, params):
    qs = urllib.parse.urlencode(params)
    return f"{GRAPH_API_BASE}{path}?{qs}"


def fetch_posts_with_hashtag(handle, hashtag, max_posts=50, days=None):
    """Fetch an influencer's recent posts and filter by hashtag."""
    handle = handle.lstrip("@").strip()
    hashtag_lower = hashtag.lstrip("#").strip().lower()

    if not IG_USER_ID:
        print("  [ERROR] INSTAGRAM_BUSINESS_USER_ID not set in ~/.wat_secrets")
        print("  Run: python tools/fetch_instagram_metrics.py --find-ig-id")
        return None

    cutoff = None
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Fetch in batches via pagination
    per_page = min(max_posts, 50)
    fields = (
        f"business_discovery.username({handle}){{"
        f"id,username,name,followers_count,"
        f"media.limit({per_page}){{id,timestamp,like_count,comments_count,media_type,caption,permalink}}"
        f"}}"
    )

    url = build_url(f"/{IG_USER_ID}", {
        "fields": fields,
        "access_token": META_ACCESS_TOKEN,
    })

    result = graph_request(url)
    bd = result.get("business_discovery")
    if not bd:
        print(f"  [WARN] Could not find business account for @{handle}")
        print("  Note: Only Instagram Business/Creator accounts are discoverable.")
        return None

    profile = {
        "username": bd.get("username"),
        "name": bd.get("name"),
        "followers_count": bd.get("followers_count", 0),
    }

    all_posts = []
    media_data = bd.get("media", {})
    posts = media_data.get("data", [])
    all_posts.extend(posts)

    # Paginate if needed
    fetched = len(posts)
    while fetched < max_posts:
        next_cursor = (media_data.get("paging") or {}).get("cursors", {}).get("after")
        if not next_cursor:
            break

        page_fields = (
            f"business_discovery.username({handle}){{"
            f"media.limit({per_page}).after({next_cursor})"
            f"{{id,timestamp,like_count,comments_count,media_type,caption,permalink}}"
            f"}}"
        )
        url = build_url(f"/{IG_USER_ID}", {
            "fields": page_fields,
            "access_token": META_ACCESS_TOKEN,
        })

        page_result = graph_request(url)
        page_bd = page_result.get("business_discovery", {})
        media_data = page_bd.get("media", {})
        posts = media_data.get("data", [])
        if not posts:
            break
        all_posts.extend(posts)
        fetched += len(posts)

    # Filter by hashtag and optional date cutoff
    matched = []
    for post in all_posts:
        caption = (post.get("caption") or "").lower()
        timestamp_str = post.get("timestamp", "")

        # Date filter
        if cutoff and timestamp_str:
            try:
                post_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if post_dt < cutoff:
                    continue
            except ValueError:
                pass

        # Hashtag check: look for #hashtag in caption
        if f"#{hashtag_lower}" in caption:
            matched.append({
                "id": post.get("id"),
                "timestamp": timestamp_str,
                "media_type": post.get("media_type"),
                "likes": post.get("like_count", 0),
                "comments": post.get("comments_count", 0),
                "permalink": post.get("permalink"),
                "caption": (post.get("caption") or "")[:200],
            })

    return {
        "profile": profile,
        "hashtag": f"#{hashtag_lower}",
        "posts_scanned": len(all_posts),
        "posts_matched": len(matched),
        "found": len(matched) > 0,
        "matched_posts": matched,
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(
        description="Check if an influencer posted with a specific hashtag on Instagram"
    )
    parser.add_argument("--handle", required=True, help="Instagram handle to check")
    parser.add_argument("--hashtag", required=True, help="Hashtag to look for (with or without #)")
    parser.add_argument("--limit", type=int, default=50, help="Max posts to scan (default: 50)")
    parser.add_argument("--days", type=int, default=None, help="Only check posts from the last N days")
    parser.add_argument("--output", choices=["json", "pretty"], default="pretty", help="Output format")
    args = parser.parse_args()

    if not META_ACCESS_TOKEN:
        print("[ERROR] META_ACCESS_TOKEN not set in ~/.wat_secrets")
        sys.exit(1)

    handle = args.handle.lstrip("@")
    hashtag_display = args.hashtag if args.hashtag.startswith("#") else f"#{args.hashtag}"
    print(f"\n  Checking @{handle} for {hashtag_display} posts...")
    if args.days:
        print(f"  (looking at posts from the last {args.days} days)")

    result = fetch_posts_with_hashtag(args.handle, args.hashtag, args.limit, args.days)

    if not result:
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Pretty output
    p = result["profile"]
    print(f"\n{'=' * 60}")
    print(f"  @{p['username']} ({p['name'] or 'N/A'}) | Followers: {p['followers_count']:,}")
    print(f"  Hashtag: {result['hashtag']}")
    print(f"  Posts scanned: {result['posts_scanned']}")
    print(f"{'=' * 60}")

    if result["found"]:
        print(f"\n  FOUND: {result['posts_matched']} post(s) with {result['hashtag']}\n")
        for i, post in enumerate(result["matched_posts"], 1):
            date_str = post["timestamp"][:10] if post["timestamp"] else "N/A"
            print(f"  [{i}] {date_str} | {post['media_type'] or 'POST'}")
            print(f"      Likes: {post['likes']:,} | Comments: {post['comments']:,}")
            if post.get("permalink"):
                print(f"      Link: {post['permalink']}")
            print(f"      Caption: {post['caption'][:120]}...")
            print()
    else:
        print(f"\n  NOT FOUND: No posts with {result['hashtag']} in the last {result['posts_scanned']} posts.\n")


if __name__ == "__main__":
    main()
