#!/usr/bin/env python3
"""
JP Discovery Caption/Hashtag Enricher
======================================
Reads the Discovery tab from Apify Master Sheet, fetches IG post captions
and hashtags via RapidAPI Instagram Scraper Stable API, and writes back.

Usage:
  # Dry run (preview, no sheet writes)
  python tools/enrich_discovery_captions.py --dry-run

  # Enrich all empty Caption rows
  python tools/enrich_discovery_captions.py

  # Specific tab
  python tools/enrich_discovery_captions.py --tab "Discovery Mar23-30"

  # Limit to N rows (for testing)
  python tools/enrich_discovery_captions.py --limit 5

  # Force re-fetch even if Caption exists
  python tools/enrich_discovery_captions.py --force
"""

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Force UTF-8 on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

# ── Config ────────────────────────────────────────────────────────────────── #
SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
DEFAULT_TAB = "Discovery Mar23-30"

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_IG_HOST", "instagram-scraper-stable-api.p.rapidapi.com")

# Rate limiting: PRO plan, be conservative
DELAY_BETWEEN_REQUESTS = 1.5  # seconds
MAX_RETRIES = 2

# Column mapping (0-indexed)
COL_MAP = {
    "Handle": 0,
    "Full Name": 1,
    "Platform": 2,
    "URL": 3,
    "Date": 4,
    "Type": 5,
    "Source": 6,
    "Followers": 7,
    "Views": 8,
    "Likes": 9,
    "Comments Count": 10,
    "Hashtags": 11,
    "Mentions": 12,
    "Email": 13,
    "Is Parent": 14,
    "Syncly KW": 15,
    "Extended KW": 16,
    "Transcript": 17,
    "Duration (s)": 18,
    "Whisper Cost ($)": 19,
    "Top Comments": 20,
    "Comments Scraped": 21,
    "Caption": 22,
}


# ── RapidAPI Client ──────────────────────────────────────────────────────── #
def extract_shortcode(url: str) -> str | None:
    """Extract IG shortcode from URL like /p/ABC123/ or /reel/ABC123/."""
    m = re.search(r"instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def extract_username(url: str) -> str | None:
    """Extract username from IG profile URL."""
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)/?", url)
    return m.group(1) if m else None


def fetch_post_by_user(username: str, amount: int = 12) -> list[dict]:
    """Fetch user posts via RapidAPI. Returns list of post nodes."""
    url = f"https://{RAPIDAPI_HOST}/get_ig_user_posts.php"
    data = urllib.parse.urlencode({
        "username_or_url": username,
        "amount": str(amount),
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("x-rapidapi-host", RAPIDAPI_HOST)
    req.add_header("x-rapidapi-key", RAPIDAPI_KEY)

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            posts = result.get("posts", [])
            return [p.get("node", p) for p in posts]
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limited
                wait = 5 * (attempt + 1)
                print(f"    ⚠ Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 500 and attempt < MAX_RETRIES:
                time.sleep(2)
            else:
                raise
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(2)
            else:
                raise
    return []


def fetch_user_reels(username: str, amount: int = 12) -> list[dict]:
    """Fetch user reels via RapidAPI."""
    url = f"https://{RAPIDAPI_HOST}/get_ig_user_reels.php"
    data = urllib.parse.urlencode({
        "username_or_url": username,
        "amount": str(amount),
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("x-rapidapi-host", RAPIDAPI_HOST)
    req.add_header("x-rapidapi-key", RAPIDAPI_KEY)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        reels = result.get("reels", [])
        return [r.get("node", {}).get("media", r.get("node", r)) for r in reels]
    except Exception:
        return []


def match_post_by_shortcode(posts: list[dict], shortcode: str) -> dict | None:
    """Find a specific post by shortcode in a list of post nodes."""
    for p in posts:
        if p.get("code") == shortcode:
            return p
    return None


def extract_caption_and_hashtags(node: dict) -> tuple[str, list[str]]:
    """Extract caption text and hashtags from a post node."""
    caption_obj = node.get("caption", {})
    if isinstance(caption_obj, dict):
        text = caption_obj.get("text", "")
    elif isinstance(caption_obj, str):
        text = caption_obj
    else:
        text = ""

    hashtags = re.findall(r"#[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+", text)
    return text, hashtags


# ── Main Logic ────────────────────────────────────────────────────────────── #
def enrich_discovery(tab_name: str, dry_run: bool, limit: int | None, force: bool):
    """Enrich Discovery tab with captions and hashtags from RapidAPI."""
    import gspread
    from google.oauth2.service_account import Credentials

    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
    sa_full = PROJECT_ROOT / sa_path

    creds = Credentials.from_service_account_file(
        str(sa_full),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(tab_name)

    all_data = ws.get_all_values()
    header = all_data[0]
    rows = all_data[1:]

    print(f"Tab: {tab_name}")
    print(f"Total rows: {len(rows)}")
    print(f"Columns: {len(header)}")

    # Find column indices
    url_col = COL_MAP["URL"]
    caption_col = COL_MAP["Caption"]
    hashtag_col = COL_MAP["Hashtags"]
    handle_col = COL_MAP["Handle"]
    platform_col = COL_MAP["Platform"]
    type_col = COL_MAP["Type"]

    # Filter to IG rows needing enrichment
    to_enrich = []
    for i, row in enumerate(rows):
        # Pad row if shorter than expected
        while len(row) <= caption_col:
            row.append("")

        platform = row[platform_col].strip().lower() if len(row) > platform_col else ""
        url = row[url_col].strip() if len(row) > url_col else ""
        caption = row[caption_col].strip() if len(row) > caption_col else ""
        hashtags = row[hashtag_col].strip() if len(row) > hashtag_col else ""

        if "instagram" not in platform and "instagram.com" not in url:
            continue  # Skip non-IG

        if not url:
            continue

        if not force and caption:
            continue  # Already has caption

        to_enrich.append((i, row))

    print(f"Rows to enrich: {len(to_enrich)}")
    if limit:
        to_enrich = to_enrich[:limit]
        print(f"Limited to: {limit}")

    if not to_enrich:
        print("Nothing to enrich!")
        return

    # Group by username for batch API calls
    username_posts_cache: dict[str, list[dict]] = {}
    updates = []  # (row_num_1indexed, col_letter, value)
    enriched = 0
    failed = 0
    api_calls = 0

    for idx, (row_idx, row) in enumerate(to_enrich):
        sheet_row = row_idx + 2  # 1-indexed + header
        url = row[url_col].strip()
        handle = row[handle_col].strip()
        content_type = row[type_col].strip().lower() if len(row) > type_col else ""

        shortcode = extract_shortcode(url)
        username = handle or extract_username(url)

        if not username and not shortcode:
            print(f"  [{idx+1}/{len(to_enrich)}] Row {sheet_row}: no username/shortcode, skip")
            failed += 1
            continue

        print(f"  [{idx+1}/{len(to_enrich)}] Row {sheet_row}: @{username} ({shortcode or 'no code'})", end="")

        # Fetch posts for this username (cached)
        if username and username not in username_posts_cache:
            try:
                time.sleep(DELAY_BETWEEN_REQUESTS)
                posts = fetch_post_by_user(username, amount=30)
                api_calls += 1
                # Also try reels if content is reel/video type
                if "reel" in content_type or "video" in content_type:
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    reels = fetch_user_reels(username, amount=12)
                    api_calls += 1
                    posts.extend(reels)
                username_posts_cache[username] = posts
                print(f" → fetched {len(posts)} posts", end="")
            except Exception as e:
                print(f" → API error: {e}")
                username_posts_cache[username] = []
                failed += 1
                continue

        all_posts = username_posts_cache.get(username, [])

        # Find matching post by shortcode
        matched = None
        if shortcode:
            matched = match_post_by_shortcode(all_posts, shortcode)

        if not matched and all_posts:
            # If no shortcode match, use most recent post as fallback? No, skip.
            print(f" → shortcode not found in {len(all_posts)} posts")
            failed += 1
            continue

        if not matched:
            print(f" → no posts available")
            failed += 1
            continue

        # Extract caption and hashtags
        caption_text, hashtag_list = extract_caption_and_hashtags(matched)

        if not caption_text:
            print(f" → empty caption")
            failed += 1
            continue

        # Prepare updates
        # Caption column (W = col 23 = index 22)
        caption_cell = f"W{sheet_row}"
        hashtag_cell = f"L{sheet_row}"  # Hashtags = col 12 = L
        hashtag_str = " ".join(hashtag_list)

        if dry_run:
            print(f" → [DRY RUN] caption: {caption_text[:80]}...")
            print(f"             hashtags: {hashtag_str[:80]}")
        else:
            updates.append({
                "range": caption_cell,
                "values": [[caption_text]],
            })
            if not row[hashtag_col].strip():  # Only fill if empty
                updates.append({
                    "range": hashtag_cell,
                    "values": [[hashtag_str]],
                })
            print(f" → ✓ caption ({len(caption_text)} chars, {len(hashtag_list)} tags)")

        enriched += 1

    # Batch update
    if updates and not dry_run:
        print(f"\nWriting {len(updates)} cell updates to sheet...")
        ws.batch_update(updates, value_input_option="RAW")
        print("✓ Sheet updated!")

    # Summary
    print(f"\n{'=' * 50}")
    print(f"  ENRICHMENT SUMMARY")
    print(f"  Tab: {tab_name}")
    print(f"  Enriched: {enriched}/{len(to_enrich)}")
    print(f"  Failed: {failed}")
    print(f"  API calls: {api_calls}")
    print(f"  Dry run: {dry_run}")
    print(f"{'=' * 50}")

    return {"enriched": enriched, "failed": failed, "api_calls": api_calls}


# ── CLI ───────────────────────────────────────────────────────────────────── #
def main():
    parser = argparse.ArgumentParser(description="Enrich Discovery tab captions via RapidAPI")
    parser.add_argument("--tab", default=DEFAULT_TAB, help="Sheet tab name")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--limit", type=int, help="Limit rows to process")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if caption exists")
    args = parser.parse_args()

    if not RAPIDAPI_KEY:
        print("ERROR: RAPIDAPI_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    enrich_discovery(
        tab_name=args.tab,
        dry_run=args.dry_run,
        limit=args.limit,
        force=args.force,
    )


if __name__ == "__main__":
    main()
