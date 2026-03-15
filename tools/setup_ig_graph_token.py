"""
Instagram Graph API Token Setup & IG Business User ID Finder
============================================================
Run this after getting a fresh token from graph.facebook.com/explorer

Usage:
  python tools/setup_ig_graph_token.py --token "EAAU3Ur..."
  python tools/setup_ig_graph_token.py --token "EAAU3Ur..." --save

What it does:
  1. Verifies the token works
  2. Lists all FB Pages connected to the user
  3. Finds IG Business User IDs for each page
  4. Identifies grosmimi_usa / grosmimi_japan IDs
  5. --save: updates ~/.wat_secrets with the new token + IDs
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SECRETS_PATH = Path.home() / ".wat_secrets"

def graph_get(path, params, token):
    params["access_token"] = token
    url = f"https://graph.facebook.com/v21.0/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def find_ig_ids(token):
    print("[1] Verifying token...")
    me = graph_get("me", {"fields": "id,name"}, token)
    if "error" in me:
        print(f"  ERROR: {me['error']['message']}")
        sys.exit(1)
    print(f"  Authenticated as: {me.get('name')} (id={me.get('id')})")

    print("\n[2] Listing FB Pages...")
    pages_resp = graph_get("me/accounts", {"fields": "id,name,instagram_business_account"}, token)
    pages = pages_resp.get("data", [])
    if not pages:
        print("  No pages found. Make sure token has pages_show_list permission.")
        return {}

    results = {}
    for page in pages:
        pid = page["id"]
        name = page["name"]
        ig = page.get("instagram_business_account", {})
        ig_id = ig.get("id", "") if ig else ""
        print(f"  Page: {name} (fb={pid}) -> IG user ID: {ig_id or 'N/A'}")

        if ig_id:
            # Get IG username for this ID
            try:
                ig_info = graph_get(ig_id, {"fields": "username"}, token)
                username = ig_info.get("username", "")
                print(f"    -> @{username}")
                results[username] = ig_id
            except Exception as e:
                print(f"    -> Could not get username: {e}")
                results[f"page_{pid}"] = ig_id

    return results


def save_secrets(token, ig_ids):
    if not SECRETS_PATH.exists():
        print(f"[WARN] {SECRETS_PATH} not found")
        return

    content = SECRETS_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()

    def update_or_append(key, value):
        nonlocal lines
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                print(f"  Updated: {key}={value[:20]}...")
                return
        lines.append(f"{key}={value}")
        print(f"  Added: {key}={value[:20]}...")

    update_or_append("META_GRAPH_IG_TOKEN", token)

    for username, ig_id in ig_ids.items():
        if "onzenna" in username.lower():
            update_or_append("IG_BUSINESS_USER_ID_ONZENNA", ig_id)
        elif "grosmimi" in username.lower() and ("japan" in username.lower() or "jp" in username.lower()):
            update_or_append("IG_BUSINESS_USER_ID_GROSMIMI_JP", ig_id)
        elif "grosmimi" in username.lower():
            update_or_append("IG_BUSINESS_USER_ID_GROSMIMI_USA", ig_id)

    SECRETS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Saved to {SECRETS_PATH}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="Graph API access token")
    parser.add_argument("--save", action="store_true", help="Save token + IDs to ~/.wat_secrets")
    args = parser.parse_args()

    ig_ids = find_ig_ids(args.token)

    print("\n[3] Summary:")
    for username, ig_id in ig_ids.items():
        print(f"  @{username}: {ig_id}")

    if not ig_ids:
        print("\n  No IG accounts found. You may need pages_read_engagement permission.")
        print("  Try: graph.facebook.com/explorer -> Add permission -> pages_read_engagement")
        return

    if args.save:
        print("\n[4] Saving to ~/.wat_secrets...")
        save_secrets(args.token, ig_ids)
    else:
        print("\nRun with --save to update ~/.wat_secrets")
        print(f"\nCopy these to ~/.wat_secrets:")
        print(f"  META_GRAPH_IG_TOKEN={args.token}")
        for username, ig_id in ig_ids.items():
            if "onzenna" in username.lower():
                print(f"  IG_BUSINESS_USER_ID_ONZENNA={ig_id}")
            elif "grosmimi" in username.lower() and ("japan" in username.lower() or "jp" in username.lower()):
                print(f"  IG_BUSINESS_USER_ID_GROSMIMI_JP={ig_id}")
            elif "grosmimi" in username.lower():
                print(f"  IG_BUSINESS_USER_ID_GROSMIMI_USA={ig_id}")


if __name__ == "__main__":
    main()
