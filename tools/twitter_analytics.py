"""
WAT Tool: Collect Twitter/X public metrics and analytics.
Free tier has limited API read access, so Firecrawl web scraping is the primary method.

Output: .tmp/twitter_analytics.json

Usage:
    py -3 tools/twitter_analytics.py                  # collect all available metrics
    py -3 tools/twitter_analytics.py --profile        # profile metrics only
    py -3 tools/twitter_analytics.py --tweets         # recent tweet metrics from log
    py -3 tools/twitter_analytics.py --scrape         # use Firecrawl fallback
    py -3 tools/twitter_analytics.py --report         # generate summary report
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, date

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from twitter_utils import (
    create_twitter_clients,
    RateLimiter,
    TWITTER_ANALYTICS_PATH,
    TWITTER_LOG_PATH,
    TMP_DIR,
)

read_limiter = RateLimiter(max_calls=1, period_seconds=900)


# ── Profile Metrics (API) ────────────────────────────────────────────────

def get_profile_metrics(client) -> dict | None:
    """Fetch own profile metrics via API."""
    read_limiter.wait_if_needed()

    try:
        me = client.get_me(user_fields=["public_metrics", "created_at", "description"])
        if not me.data:
            return None

        metrics = me.data.public_metrics or {}
        return {
            "username": me.data.username,
            "name": me.data.name,
            "followers": metrics.get("followers_count", 0),
            "following": metrics.get("following_count", 0),
            "tweet_count": metrics.get("tweet_count", 0),
            "listed_count": metrics.get("listed_count", 0),
            "collected_at": datetime.now().isoformat(),
            "source": "api",
        }
    except Exception as e:
        logger.error(f"Profile fetch failed: {e}")
        return None


# ── Tweet Metrics (from log) ─────────────────────────────────────────────

def get_tweet_metrics_from_log() -> list[dict]:
    """Get tweet posting stats from local log (no API needed)."""
    if not TWITTER_LOG_PATH.exists():
        return []

    with open(TWITTER_LOG_PATH, "r", encoding="utf-8") as f:
        log = json.load(f)

    tweets = log.get("tweets", [])
    today = date.today().isoformat()
    this_month = today[:7]

    published = [t for t in tweets if t.get("status") == "published"]

    return {
        "total_posted": len(published),
        "posted_today": sum(1 for t in published if t.get("posted_at", "").startswith(today)),
        "posted_this_month": sum(1 for t in published if t.get("posted_at", "").startswith(this_month)),
        "recent_tweets": [
            {
                "post_id": t.get("post_id"),
                "tweet_id": t.get("tweet_id"),
                "posted_at": t.get("posted_at"),
                "type": t.get("type"),
                "text_preview": t.get("text_preview", "")[:50],
            }
            for t in published[-10:]
        ],
    }


# ── Firecrawl Scraping (Free tier fallback) ──────────────────────────────

def scrape_profile_metrics(username: str) -> dict | None:
    """Scrape profile metrics via Firecrawl (Nitter/xcancel)."""
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    if not firecrawl_key:
        logger.warning("FIRECRAWL_API_KEY not set, skipping scrape")
        return None

    try:
        import requests

        # Try nitter/xcancel instance
        urls = [
            f"https://xcancel.com/{username}",
            f"https://nitter.privacydev.net/{username}",
        ]

        for url in urls:
            try:
                resp = requests.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={"Authorization": f"Bearer {firecrawl_key}"},
                    json={"url": url, "formats": ["markdown"]},
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    md = data.get("data", {}).get("markdown", "")
                    if md:
                        return _parse_profile_markdown(md, username)
            except Exception as e:
                logger.warning(f"Scrape failed for {url}: {e}")
                continue

    except Exception as e:
        logger.error(f"Firecrawl scrape failed: {e}")

    return None


def _parse_profile_markdown(md: str, username: str) -> dict:
    """Parse profile stats from scraped markdown."""
    import re

    stats = {
        "username": username,
        "source": "scrape",
        "collected_at": datetime.now().isoformat(),
    }

    # Common patterns in nitter/xcancel
    patterns = {
        "followers": [r"(\d[\d,\.]*)\s*(?:Followers|フォロワー)", r"Followers\s*(\d[\d,\.]*)"],
        "following": [r"(\d[\d,\.]*)\s*(?:Following|フォロー中)", r"Following\s*(\d[\d,\.]*)"],
        "tweet_count": [r"(\d[\d,\.]*)\s*(?:Tweets?|Posts?|ポスト)", r"Tweets?\s*(\d[\d,\.]*)"],
    }

    for key, pats in patterns.items():
        for pat in pats:
            match = re.search(pat, md, re.IGNORECASE)
            if match:
                val = match.group(1).replace(",", "").replace(".", "")
                try:
                    stats[key] = int(val)
                except ValueError:
                    pass
                break

    return stats


# ── Analytics Storage ────────────────────────────────────────────────────

def load_analytics() -> dict:
    """Load existing analytics history."""
    if TWITTER_ANALYTICS_PATH.exists():
        with open(TWITTER_ANALYTICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"snapshots": []}


def save_analytics(data: dict):
    """Save analytics data."""
    TWITTER_ANALYTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TWITTER_ANALYTICS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_snapshot(profile: dict, tweet_stats: dict):
    """Add a new analytics snapshot."""
    analytics = load_analytics()

    snapshot = {
        "date": date.today().isoformat(),
        **profile,
        "posting_stats": tweet_stats,
    }

    # Avoid duplicate snapshots for the same day
    today = date.today().isoformat()
    analytics["snapshots"] = [
        s for s in analytics["snapshots"] if s.get("date") != today
    ]
    analytics["snapshots"].append(snapshot)
    save_analytics(analytics)
    logger.info("Analytics snapshot saved")


# ── Report ───────────────────────────────────────────────────────────────

def generate_report():
    """Generate a summary analytics report."""
    analytics = load_analytics()
    snapshots = analytics.get("snapshots", [])

    if not snapshots:
        print("No analytics data yet. Run without --report first.")
        return

    latest = snapshots[-1]
    print("=" * 50)
    print("Twitter Analytics Report — Grosmimi Japan")
    print(f"Date: {latest.get('date', 'N/A')}")
    print("=" * 50)

    print(f"\nProfile: @{latest.get('username', 'N/A')}")
    print(f"  Followers:  {latest.get('followers', 'N/A')}")
    print(f"  Following:  {latest.get('following', 'N/A')}")
    print(f"  Tweets:     {latest.get('tweet_count', 'N/A')}")

    stats = latest.get("posting_stats", {})
    if stats:
        print(f"\nPosting Stats:")
        print(f"  Total posted:      {stats.get('total_posted', 0)}")
        print(f"  Posted today:      {stats.get('posted_today', 0)}")
        print(f"  Posted this month: {stats.get('posted_this_month', 0)}")

    # Growth trend
    if len(snapshots) >= 2:
        prev = snapshots[-2]
        follower_diff = latest.get("followers", 0) - prev.get("followers", 0)
        tweet_diff = latest.get("tweet_count", 0) - prev.get("tweet_count", 0)
        sign = "+" if follower_diff >= 0 else ""
        print(f"\nGrowth (since {prev.get('date', 'prev')}):")
        print(f"  Followers: {sign}{follower_diff}")
        print(f"  Tweets:    +{tweet_diff}")


def main():
    parser = argparse.ArgumentParser(description="Twitter analytics collector")
    parser.add_argument("--profile", action="store_true", help="Profile metrics only")
    parser.add_argument("--tweets", action="store_true", help="Tweet stats from log")
    parser.add_argument("--scrape", action="store_true", help="Use Firecrawl fallback")
    parser.add_argument("--report", action="store_true", help="Generate summary report")
    parser.add_argument("--username", type=str, help="Twitter username (without @)")
    args = parser.parse_args()

    if args.report:
        generate_report()
        return

    # Get tweet stats (always available, no API needed)
    tweet_stats = get_tweet_metrics_from_log()

    if args.tweets:
        print("Tweet Posting Stats:")
        print(json.dumps(tweet_stats, ensure_ascii=False, indent=2))
        return

    # Get profile metrics
    profile = None

    if args.scrape:
        username = args.username
        if not username:
            # Try to get from API first
            try:
                client, _ = create_twitter_clients()
                me = client.get_me()
                username = me.data.username
            except Exception:
                print("Provide --username for scrape mode")
                return
        profile = scrape_profile_metrics(username)
    else:
        try:
            client, _ = create_twitter_clients()
            profile = get_profile_metrics(client)
        except Exception as e:
            logger.warning(f"API fetch failed, trying scrape fallback: {e}")
            if args.username:
                profile = scrape_profile_metrics(args.username)

    if args.profile:
        if profile:
            print("Profile Metrics:")
            print(json.dumps(profile, ensure_ascii=False, indent=2))
        else:
            print("Could not fetch profile metrics.")
        return

    # Full collection: save snapshot
    if profile:
        add_snapshot(profile, tweet_stats)
        print(f"Analytics snapshot saved for @{profile.get('username', '?')}")
        print(f"  Followers: {profile.get('followers', 'N/A')}")
        print(f"  Tweets:    {profile.get('tweet_count', 'N/A')}")
    else:
        print("Could not collect profile metrics. Check credentials or use --scrape.")

    if tweet_stats:
        print(f"  Posted today: {tweet_stats.get('posted_today', 0)}")
        print(f"  Posted this month: {tweet_stats.get('posted_this_month', 0)}")


if __name__ == "__main__":
    main()
