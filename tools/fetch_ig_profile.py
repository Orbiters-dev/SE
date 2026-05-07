"""
Fetch Instagram profile (bio, name, follower count) via Apify.

Used by DM reachout flow to determine:
- Display name (for ○○様)
- Child age from bio (for product link routing)
- Follower count (for paid collab threshold)

Usage:
    python tools/fetch_ig_profile.py --handle waaku_110
    python tools/fetch_ig_profile.py --handle waaku_110 --output json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_loader import load_env

load_env()

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
ACTOR_ID = "apify~instagram-profile-scraper"


def run_apify_actor(handle: str) -> dict | None:
    """Run Apify Instagram Profile Scraper and return profile data."""
    handle = handle.lstrip("@").strip()
    url = (
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
        f"?token={urllib.parse.quote(APIFY_TOKEN)}&timeout=120"
    )
    payload = json.dumps({
        "usernames": [handle],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            items = json.loads(r.read())
            if items and len(items) > 0:
                return items[0]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[ERROR] Apify API {e.code}: {body[:300]}", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)

    return None


def _normalize_numbers(text: str) -> str:
    """Convert full-width digits to ASCII digits."""
    table = str.maketrans("０１２３４５６７８９", "0123456789")
    return text.translate(table)


def parse_child_age(bio: str) -> dict:
    """Parse child age/birth info from bio. Returns youngest child's age."""
    result = {"raw_matches": [], "estimated_months": None, "age_text": None}

    if not bio:
        return result

    from datetime import datetime
    normalized = _normalize_numbers(bio)
    now = datetime.now()
    all_ages: list[int] = []

    # Pattern: 令和N年M月生まれ (findall for multiple children)
    for m in re.finditer(r"令和(\d{1,2})[年./](\d{1,2})月?生まれ?", normalized):
        year = 2018 + int(m.group(1))
        month = int(m.group(2))
        result["raw_matches"].append(m.group())
        try:
            months = (now.year - year) * 12 + (now.month - month)
            all_ages.append(months)
        except (ValueError, OverflowError):
            pass

    # Pattern: 2024年3月生まれ
    for m in re.finditer(r"(\d{4})[年./](\d{1,2})月?生まれ", normalized):
        year, month = int(m.group(1)), int(m.group(2))
        result["raw_matches"].append(m.group())
        try:
            months = (now.year - year) * 12 + (now.month - month)
            all_ages.append(months)
        except (ValueError, OverflowError):
            pass

    # Pattern: R6.3生まれ
    for m in re.finditer(r"R(\d{1,2})[年./](\d{1,2})月?生まれ?", normalized):
        year = 2018 + int(m.group(1))
        month = int(m.group(2))
        result["raw_matches"].append(m.group())
        try:
            months = (now.year - year) * 12 + (now.month - month)
            all_ages.append(months)
        except (ValueError, OverflowError):
            pass

    # Pattern: N歳 / N歳Mヶ月 (findall for multiple)
    for m in re.finditer(r"(\d+)歳(\d+)?ヶ?月?", normalized):
        years = int(m.group(1))
        extra = int(m.group(2)) if m.group(2) else 0
        result["raw_matches"].append(m.group())
        all_ages.append(years * 12 + extra)

    if all_ages:
        # Pick youngest (smallest positive age)
        positive = [a for a in all_ages if a > 0]
        youngest = min(positive) if positive else min(all_ages)
        result["estimated_months"] = youngest
        result["age_text"] = f"{youngest}ヶ月 (youngest of {len(all_ages)} children)"

    return result


def recommend_product(months: int | None) -> dict:
    """Return product recommendation based on child age in months."""
    if months is None:
        return {
            "product": "unknown",
            "link": None,
            "note": "月齢不明 - 세은에게 확인 필요",
        }
    if months > 24:
        return {
            "product": "out_of_range",
            "link": None,
            "note": "24ヶ月超 - 対象外",
        }
    if months >= 12:
        return {
            "product": "onetouch",
            "link": "https://item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_onetouch_srawcup/",
            "note": "12~24ヶ月 → ワンタッチ式ストローマグ",
        }
    return {
        "product": "ppsu",
        "link": "https://item.rakuten.co.jp/littlefingerusa/grosmimi_ppsu_strawcup300/",
        "note": "~12ヶ月 → PPSU ストローマグ",
    }


def main():
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Fetch IG profile for DM reachout")
    parser.add_argument("--handle", required=True, help="Instagram handle")
    parser.add_argument("--output", choices=["json", "pretty"], default="pretty")
    args = parser.parse_args()

    if not APIFY_TOKEN:
        print("[ERROR] APIFY_API_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    handle = args.handle.lstrip("@").strip()
    print(f"Fetching @{handle} via Apify...")

    profile = run_apify_actor(handle)
    if not profile:
        print(f"[ERROR] Could not fetch profile for @{handle}")
        sys.exit(1)

    bio = profile.get("biography", "") or ""
    name = profile.get("fullName", "") or profile.get("full_name", "") or ""
    followers = profile.get("followersCount", 0) or profile.get("followers_count", 0) or 0

    age_info = parse_child_age(bio)
    product = recommend_product(age_info["estimated_months"])

    result = {
        "handle": handle,
        "name": name,
        "bio": bio,
        "followers": followers,
        "child_age": age_info,
        "product_recommendation": product,
    }

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'=' * 50}")
        print(f"  @{handle}")
        print(f"  Name: {name}")
        print(f"  Followers: {followers:,}")
        print(f"  Bio: {bio[:120]}")
        print(f"  Child Age: {age_info['age_text'] or '不明'}")
        print(f"  Product: {product['note']}")
        if product["link"]:
            print(f"  Link: {product['link']}")
        print(f"{'=' * 50}")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
