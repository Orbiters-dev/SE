"""
WAT Tool: Refresh Instagram Graph API long-lived access token.
Long-lived tokens expire after 60 days and must be refreshed periodically.
Updates the token in .env automatically.

Usage:
    python tools/refresh_ig_token.py            # refresh token
    python tools/refresh_ig_token.py --check    # check expiration only
"""

import os
import re
import argparse
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

IG_API_BASE = "https://graph.facebook.com/v21.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def check_token_info(access_token: str) -> dict:
    """Check token validity and expiration."""
    url = f"{IG_API_BASE}/debug_token"
    params = {"input_token": access_token, "access_token": access_token}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {
            "is_valid": data.get("is_valid", False),
            "expires_at": data.get("expires_at", 0),
            "scopes": data.get("scopes", []),
            "type": data.get("type", "unknown"),
        }
    except Exception as e:
        logger.error(f"Token check failed: {e}")
        return {"is_valid": False, "error": str(e)}


def refresh_long_lived_token(access_token: str, app_id: str, app_secret: str) -> str | None:
    """Exchange current token for a new long-lived token."""
    url = f"{IG_API_BASE}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": access_token,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        new_token = data.get("access_token")
        expires_in = data.get("expires_in", 0)
        days = expires_in // 86400
        logger.info(f"New token obtained (expires in {days} days)")
        return new_token
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text}")
        return None


def update_env_file(env_path: Path, key: str, new_value: str) -> None:
    """Update a key in the .env file."""
    content = env_path.read_text(encoding="utf-8")

    pattern = re.compile(rf'^{re.escape(key)}=.*$', re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(f"{key}={new_value}", content)
    else:
        content += f"\n{key}={new_value}\n"

    env_path.write_text(content, encoding="utf-8")
    logger.info(f"Updated {key} in {env_path}")


def main():
    parser = argparse.ArgumentParser(description="Refresh Instagram Graph API token")
    parser.add_argument("--check", action="store_true", help="Check expiration only")
    args = parser.parse_args()

    access_token = os.getenv("IG_ACCESS_TOKEN")
    if not access_token:
        raise EnvironmentError("IG_ACCESS_TOKEN not found in .env")

    # Check current token
    info = check_token_info(access_token)

    if info.get("is_valid"):
        import datetime
        expires_at = info.get("expires_at", 0)
        if expires_at:
            expires_dt = datetime.datetime.fromtimestamp(expires_at)
            days_left = (expires_dt - datetime.datetime.now()).days
            print(f"Token valid. Expires: {expires_dt.strftime('%Y-%m-%d')} ({days_left} days left)")

            if args.check:
                if days_left < 7:
                    print("WARNING: Token expires within 7 days! Run without --check to refresh.")
                return
        else:
            print("Token valid (no expiration info available)")
            if args.check:
                return
    else:
        print(f"Token invalid or expired: {info.get('error', 'unknown')}")
        if args.check:
            print("Run without --check to attempt refresh.")
            return

    # Refresh token
    app_id = os.getenv("FB_APP_ID")
    app_secret = os.getenv("FB_APP_SECRET")

    if not app_id or not app_secret:
        raise EnvironmentError(
            "FB_APP_ID and FB_APP_SECRET required for token refresh.\n"
            "Add them to .env file."
        )

    new_token = refresh_long_lived_token(access_token, app_id, app_secret)
    if new_token:
        update_env_file(env_path, "IG_ACCESS_TOKEN", new_token)
        print("Token refreshed and saved to .env")
    else:
        print("Token refresh failed. You may need to generate a new token manually.")
        print("See: https://developers.facebook.com/tools/explorer/")


if __name__ == "__main__":
    main()
