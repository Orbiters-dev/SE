"""
WAT Tool: Twitter/X OAuth setup and credential verification.
Handles initial authentication setup and ongoing credential checks.

Usage:
    py -3 tools/twitter_auth.py --setup         # interactive OAuth setup
    py -3 tools/twitter_auth.py --verify        # verify stored credentials
    py -3 tools/twitter_auth.py --check-limits  # show rate limit status
"""

import os
import sys
import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def verify_credentials() -> dict | None:
    """Verify stored OAuth credentials by calling GET /2/users/me.

    Returns:
        dict with user info, or None on failure.
    """
    from twitter_utils import check_credentials

    missing = check_credentials()
    if missing:
        print(f"Missing credentials: {', '.join(missing)}")
        print("Run: py -3 tools/twitter_auth.py --setup")
        return None

    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=os.getenv("TWITTER_API_KEY"),
            consumer_secret=os.getenv("TWITTER_API_SECRET"),
            access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
            access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
        )

        me = client.get_me(
            user_fields=["public_metrics", "description", "created_at"]
        )

        if me.data is None:
            print("Authentication failed: could not retrieve user data.")
            return None

        user = me.data
        metrics = user.public_metrics or {}

        info = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "followers": metrics.get("followers_count", 0),
            "following": metrics.get("following_count", 0),
            "tweets": metrics.get("tweet_count", 0),
        }

        print(f"Authenticated as: @{info['username']} (ID: {info['id']})")
        print(f"Account: {info['name']}")
        print(f"Followers: {info['followers']} | Following: {info['following']} | Tweets: {info['tweets']}")
        print(f"API Tier: Free")
        return info

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        if "401" in str(e):
            print("401 Unauthorized — check your API keys and access tokens.")
        elif "403" in str(e):
            print("403 Forbidden — check app permissions (need Read and Write).")
        return None


def interactive_setup():
    """Guide user through interactive credential setup."""
    from twitter_utils import update_env_file

    print("=" * 50)
    print("Twitter/X API Setup for Grosmimi Japan")
    print("=" * 50)
    print()
    print("Before starting, complete these steps:")
    print("1. Go to https://developer.x.com")
    print("2. Create a Free developer account")
    print("3. Create a Project and App")
    print("4. Set app permissions to 'Read and Write'")
    print("5. Generate all required keys and tokens")
    print()
    print("See workflows/twitter_setup_guide.md for detailed instructions.")
    print()

    keys = {
        "TWITTER_API_KEY": "API Key (Consumer Key)",
        "TWITTER_API_SECRET": "API Key Secret (Consumer Secret)",
        "TWITTER_BEARER_TOKEN": "Bearer Token",
        "TWITTER_ACCESS_TOKEN": "Access Token",
        "TWITTER_ACCESS_TOKEN_SECRET": "Access Token Secret",
        "TWITTER_CLIENT_ID": "OAuth 2.0 Client ID (optional, press Enter to skip)",
        "TWITTER_CLIENT_SECRET": "OAuth 2.0 Client Secret (optional, press Enter to skip)",
    }

    saved_count = 0
    for env_key, label in keys.items():
        current = os.getenv(env_key, "")
        if current:
            masked = current[:4] + "..." + current[-4:] if len(current) > 8 else "***"
            print(f"\n{label}")
            print(f"  Current: {masked}")
            overwrite = input("  Overwrite? (y/N): ").strip().lower()
            if overwrite != "y":
                continue

        value = input(f"\n{label}: ").strip()
        if not value:
            if "optional" in label.lower():
                print(f"  Skipped {env_key}")
                continue
            else:
                print(f"  {env_key} is required. Skipping for now.")
                continue

        update_env_file(env_key, value)
        os.environ[env_key] = value
        saved_count += 1
        print(f"  Saved {env_key}")

    print(f"\n{saved_count} credential(s) saved to .env")

    if saved_count > 0:
        print("\nVerifying credentials...")
        verify_credentials()


def check_rate_limits():
    """Check current rate limit status (limited info on Free tier)."""
    from twitter_utils import BudgetTracker

    tracker = BudgetTracker()
    tracker.print_budget()

    print()
    print("Note: Detailed rate limit info requires Basic tier or higher.")
    print("Free tier limits:")
    print("  - Write: 1,500 tweets/month")
    print("  - Read:  ~1 request per 15 minutes")


def main():
    parser = argparse.ArgumentParser(description="Twitter/X OAuth setup and verification")
    parser.add_argument("--setup", action="store_true", help="Interactive credential setup")
    parser.add_argument("--verify", action="store_true", help="Verify stored credentials")
    parser.add_argument("--check-limits", action="store_true", help="Show rate limit status")
    args = parser.parse_args()

    if args.setup:
        interactive_setup()
    elif args.verify:
        verify_credentials()
    elif args.check_limits:
        check_rate_limits()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
