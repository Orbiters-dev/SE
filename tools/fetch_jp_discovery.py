#!/usr/bin/env python3
"""
JP Content Discovery Pipeline (Syncly Replacement)
====================================================
Apify(IG Hashtag + TikTok Search) + RapidAPI(IG Enrichment) 조합으로
일본 육아 컨텐츠를 포괄적으로 수집.

Syncly 대비 장점:
- 100건 제한 없음
- TikTok 포함
- 해시태그 다중 검색
- 전체 caption/hashtag/metrics 자동 수집

Usage:
  # Full discovery (IG + TikTok)
  python tools/fetch_jp_discovery.py

  # IG only
  python tools/fetch_jp_discovery.py --ig-only

  # TikTok only
  python tools/fetch_jp_discovery.py --tt-only

  # Specific hashtags
  python tools/fetch_jp_discovery.py --hashtags "育児,育児グッズ"

  # Dry run (no sheet writes)
  python tools/fetch_jp_discovery.py --dry-run

  # Custom date range (days back from today)
  python tools/fetch_jp_discovery.py --days 7
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
from datetime import datetime, timedelta
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

# ── Config ────────────────────────────────────────────────────────────────── #
SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "discovery"

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_IG_HOST", "instagram-scraper-stable-api.p.rapidapi.com")

# Apify actors
IG_HASHTAG_SCRAPER = "apify/instagram-hashtag-scraper"
TT_SCRAPER = "clockworks/free-tiktok-scraper"

# JP parenting keywords (core 3 — covers 90%+ of relevant posts)
JP_HASHTAGS_IG = [
    "育児", "ベビー用品", "子育て",
]
JP_KEYWORDS_TT = [
    "育児", "ベビー用品", "子育て",
]

# Exclude brand/store accounts
EXCLUDE_ACCOUNTS = {
    "grosmimi_japan", "grosmimi_usa", "onzenna.official", "grosmimi_official",
    "grosmimi", "onzenna", "zezebaebae",
}

TODAY = datetime.now().strftime("%Y-%m-%d")


# ── Apify Helpers ─────────────────────────────────────────────────────────── #
def apify_run_actor(actor_id: str, run_input: dict, timeout_secs: int = 120) -> list:
    """Run an Apify actor and return dataset items."""
    # Apify API uses ~ instead of / in actor IDs
    api_actor_id = actor_id.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{api_actor_id}/runs?token={APIFY_TOKEN}"
    body = json.dumps(run_input).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=30) as resp:
        run_data = json.loads(resp.read())

    run_id = run_data["data"]["id"]
    dataset_id = run_data["data"]["defaultDatasetId"]
    print(f"  Apify run started: {run_id}")

    # Poll for completion
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"
    start = time.time()
    while time.time() - start < timeout_secs:
        time.sleep(5)
        with urllib.request.urlopen(status_url, timeout=15) as resp:
            status = json.loads(resp.read())["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        print(f"  ⚠ Apify run {status}")
        return []

    # Fetch dataset
    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}&limit=1000"
    with urllib.request.urlopen(items_url, timeout=30) as resp:
        items = json.loads(resp.read())

    print(f"  ✓ Got {len(items)} items")
    return items


# ── IG Hashtag Discovery ──────────────────────────────────────────────────── #
def discover_ig_hashtags(hashtags: list[str], days: int = 7) -> list[dict]:
    """Search IG by hashtags via Apify, return normalized posts."""
    all_posts = []
    seen_ids = set()

    for tag in hashtags:
        print(f"\n[IG] Searching #{tag}...")
        try:
            items = apify_run_actor(IG_HASHTAG_SCRAPER, {
                "hashtags": [tag],
                "resultsLimit": 200,
                "resultsType": "posts",
            }, timeout_secs=180)
        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue

        cutoff = datetime.now() - timedelta(days=days)
        for item in items:
            post_id = item.get("id", item.get("shortCode", ""))
            if not post_id or post_id in seen_ids:
                continue

            # Parse timestamp
            ts = item.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.replace(tzinfo=None) < cutoff:
                        continue
                except:
                    pass

            username = item.get("ownerUsername", "")
            if username.lower() in EXCLUDE_ACCOUNTS:
                continue

            seen_ids.add(post_id)
            all_posts.append(_normalize_ig(item, source_tag=tag))

        print(f"  #{tag}: {len(items)} raw → kept {len([p for p in all_posts if p.get('_source_tag') == tag])}")

    print(f"\n[IG] Total unique posts: {len(all_posts)}")
    return all_posts


def _normalize_ig(item: dict, source_tag: str = "") -> dict:
    """Normalize Apify IG hashtag scraper output to Discovery format."""
    caption = item.get("caption", "") or ""
    hashtags = re.findall(r"#[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+", caption)

    ts = item.get("timestamp", "")
    post_date = ""
    if ts:
        try:
            post_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except:
            post_date = ts[:10]

    media_type = item.get("type", "")
    if not media_type:
        if item.get("videoUrl"):
            media_type = "Video"
        elif item.get("childPosts"):
            media_type = "Sidecar"
        else:
            media_type = "Image"

    shortcode = item.get("shortCode", item.get("id", ""))
    url = item.get("url", f"https://www.instagram.com/p/{shortcode}/")

    return {
        "Handle": item.get("ownerUsername", ""),
        "Full Name": item.get("ownerFullName", ""),
        "Platform": "instagram",
        "URL": url,
        "Date": post_date,
        "Type": media_type,
        "Source": f"apify/#{source_tag}",
        "Followers": item.get("ownerFollowerCount", 0) or 0,
        "Views": item.get("videoViewCount", 0) or 0,
        "Likes": item.get("likesCount", 0) or 0,
        "Comments Count": item.get("commentsCount", 0) or 0,
        "Hashtags": " ".join(hashtags),
        "Mentions": ", ".join(item.get("mentions", []) or []),
        "Caption": caption,
        "_post_id": shortcode,
        "_source_tag": source_tag,
    }


# ── TikTok Discovery ─────────────────────────────────────────────────────── #
def discover_tiktok(keywords: list[str], days: int = 7) -> list[dict]:
    """Search TikTok by keywords via Apify, return normalized posts."""
    all_posts = []
    seen_ids = set()

    for idx, kw in enumerate(keywords):
        if idx > 0:
            print(f"  [TT] Waiting 10s between keywords (rate limit)...")
            time.sleep(10)
        print(f"\n[TT] Searching '{kw}'...")
        try:
            items = apify_run_actor(TT_SCRAPER, {
                "searchQueries": [kw],
                "resultsPerPage": 100,
                "shouldDownloadVideos": False,
            }, timeout_secs=180)
        except Exception as e:
            print(f"  ✗ Error: {e}")
            if "403" in str(e):
                print(f"  [TT] Rate limited, waiting 30s before next keyword...")
                time.sleep(30)
            continue

        cutoff = datetime.now() - timedelta(days=days)
        for item in items:
            post_id = item.get("id", "")
            if not post_id or post_id in seen_ids:
                continue

            # Date filter
            create_time = item.get("createTime", 0)
            if create_time:
                dt = datetime.fromtimestamp(create_time)
                if dt < cutoff:
                    continue

            username = (item.get("authorMeta", {}) or {}).get("name", "")
            if username.lower() in EXCLUDE_ACCOUNTS:
                continue

            seen_ids.add(post_id)
            all_posts.append(_normalize_tt(item, source_kw=kw))

        print(f"  '{kw}': {len(items)} raw → kept {len([p for p in all_posts if p.get('_source_tag') == kw])}")

    print(f"\n[TT] Total unique posts: {len(all_posts)}")
    return all_posts


def _normalize_tt(item: dict, source_kw: str = "") -> dict:
    """Normalize Apify TikTok scraper output to Discovery format."""
    author = item.get("authorMeta", {}) or {}
    text = item.get("text", "") or ""
    hashtags = [f"#{h.get('name', '')}" for h in (item.get("hashtags", []) or [])]

    create_time = item.get("createTime", 0)
    post_date = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d") if create_time else ""

    url = item.get("webVideoUrl", "")
    if not url and author.get("name") and item.get("id"):
        url = f"https://www.tiktok.com/@{author['name']}/video/{item['id']}"

    return {
        "Handle": author.get("name", ""),
        "Full Name": author.get("nickName", ""),
        "Platform": "tiktok",
        "URL": url,
        "Date": post_date,
        "Type": "Video",
        "Source": f"apify/tt:{source_kw}",
        "Followers": author.get("fans", 0) or 0,
        "Views": item.get("playCount", 0) or 0,
        "Likes": item.get("diggCount", 0) or 0,
        "Comments Count": item.get("commentCount", 0) or 0,
        "Hashtags": " ".join(hashtags),
        "Mentions": "",
        "Caption": text,
        "_post_id": item.get("id", ""),
        "_source_tag": source_kw,
    }


# ── RapidAPI Enrichment ──────────────────────────────────────────────────── #
def enrich_ig_posts(posts: list[dict]) -> list[dict]:
    """Enrich IG posts with full captions via RapidAPI (for posts missing caption)."""
    if not RAPIDAPI_KEY:
        print("[ENRICH] No RAPIDAPI_KEY, skipping enrichment")
        return posts

    needs_enrich = [p for p in posts if not p.get("Caption") and p["Platform"] == "instagram"]
    if not needs_enrich:
        print("[ENRICH] All posts already have captions")
        return posts

    print(f"\n[ENRICH] {len(needs_enrich)} posts need caption enrichment via RapidAPI")

    # Group by handle
    by_handle = {}
    for p in needs_enrich:
        h = p["Handle"]
        if h not in by_handle:
            by_handle[h] = []
        by_handle[h].append(p)

    cache = {}
    enriched = 0
    for handle, handle_posts in by_handle.items():
        if handle in cache:
            api_posts = cache[handle]
        else:
            try:
                time.sleep(1.5)
                url = f"https://{RAPIDAPI_HOST}/get_ig_user_posts.php"
                data = urllib.parse.urlencode({
                    "username_or_url": handle,
                    "amount": "30",
                }).encode()
                req = urllib.request.Request(url, data=data, method="POST")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                req.add_header("x-rapidapi-host", RAPIDAPI_HOST)
                req.add_header("x-rapidapi-key", RAPIDAPI_KEY)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                api_posts = [p.get("node", p) for p in result.get("posts", [])]
                cache[handle] = api_posts
            except Exception as e:
                print(f"  ⚠ @{handle}: {e}")
                cache[handle] = []
                continue

        for p in handle_posts:
            sc = p["_post_id"]
            match = next((ap for ap in api_posts if ap.get("code") == sc), None)
            if match:
                cap_obj = match.get("caption", {})
                cap_text = cap_obj.get("text", "") if isinstance(cap_obj, dict) else str(cap_obj)
                p["Caption"] = cap_text
                p["Hashtags"] = " ".join(re.findall(
                    r"#[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+", cap_text
                ))
                enriched += 1

    print(f"[ENRICH] Enriched {enriched}/{len(needs_enrich)} posts")
    return posts


# ── Sheet Writer ──────────────────────────────────────────────────────────── #
DISCOVERY_HEADERS = [
    "Handle", "Full Name", "Platform", "URL", "Date", "Type", "Source",
    "Followers", "Views", "Likes", "Comments Count", "Hashtags", "Mentions",
    "Email", "Is Parent", "Syncly KW", "Extended KW", "Transcript",
    "Duration (s)", "Whisper Cost ($)", "Top Comments", "Comments Scraped",
    "Caption",
]


def write_to_sheet(posts: list[dict], tab_name: str, dry_run: bool = False):
    """Write discovery results to Google Sheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    sa_path = PROJECT_ROOT / "credentials" / "google_service_account.json"
    creds = Credentials.from_service_account_file(
        str(sa_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    # Check if tab exists
    existing_tabs = [ws.title for ws in sh.worksheets()]
    if tab_name in existing_tabs:
        ws = sh.worksheet(tab_name)
        existing = ws.get_all_values()
        existing_urls = set(r[3] for r in existing[1:] if len(r) > 3)
        print(f"[SHEET] Tab '{tab_name}' exists with {len(existing)-1} rows")
    else:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(DISCOVERY_HEADERS))
        ws.update(values=[DISCOVERY_HEADERS], range_name="A1")
        existing_urls = set()
        print(f"[SHEET] Created new tab '{tab_name}'")

    # Dedup against existing
    new_posts = [p for p in posts if p.get("URL") not in existing_urls]
    print(f"[SHEET] New posts: {len(new_posts)} (deduped from {len(posts)})")

    if not new_posts:
        print("[SHEET] Nothing to write")
        return

    # Build rows
    rows = []
    for p in new_posts:
        row = [str(p.get(h, "")) for h in DISCOVERY_HEADERS]
        rows.append(row)

    if dry_run:
        print(f"[DRY RUN] Would write {len(rows)} rows")
        for r in rows[:5]:
            print(f"  @{r[0]} | {r[2]} | {r[3][:50]}")
        return

    # Append rows
    next_row = len(existing_urls) + 2 if existing_urls else 2
    ws.update(values=rows, range_name=f"A{next_row}", value_input_option="RAW")
    print(f"[SHEET] ✓ Wrote {len(rows)} rows starting at row {next_row}")


# ── Save Raw Data ─────────────────────────────────────────────────────────── #
def save_raw(posts: list[dict], label: str):
    """Save raw data to Data Storage."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{TODAY}_{label}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False, default=str)
    print(f"[SAVE] {path.name} ({len(posts)} posts)")


# ── Main ──────────────────────────────────────────────────────────────────── #
def main():
    parser = argparse.ArgumentParser(description="JP Content Discovery Pipeline")
    parser.add_argument("--ig-only", action="store_true")
    parser.add_argument("--tt-only", action="store_true")
    parser.add_argument("--hashtags", help="Comma-separated IG hashtags")
    parser.add_argument("--tt-keywords", help="Comma-separated TikTok keywords")
    parser.add_argument("--days", type=int, default=1, help="Days back to search (default: 1 for daily runs)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tab", help="Sheet tab name (default: auto-generated)")
    parser.add_argument("--no-sheet", action="store_true", help="Skip sheet writes")
    args = parser.parse_args()

    if not APIFY_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set")
        sys.exit(1)

    hashtags = args.hashtags.split(",") if args.hashtags else JP_HASHTAGS_IG
    tt_keywords = args.tt_keywords.split(",") if args.tt_keywords else JP_KEYWORDS_TT

    # Calculate date range for tab name
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    tab_name = args.tab or f"Discovery {start_date.strftime('%b%d')}-{end_date.strftime('%b%d')}"

    print("╔══════════════════════════════════════════╗")
    print("║  JP Content Discovery Pipeline            ║")
    print(f"║  Period: {start_date.strftime('%m/%d')} ~ {end_date.strftime('%m/%d')} ({args.days} days)       ║")
    print(f"║  Tab: {tab_name:<35}║")
    print("╚══════════════════════════════════════════╝")

    all_posts = []

    # IG Discovery
    if not args.tt_only:
        print(f"\n{'━'*50}")
        print(f"  INSTAGRAM — {len(hashtags)} hashtags")
        print(f"{'━'*50}")
        ig_posts = discover_ig_hashtags(hashtags, days=args.days)
        ig_posts = enrich_ig_posts(ig_posts)
        save_raw(ig_posts, "jp_ig_discovery")
        all_posts.extend(ig_posts)

    # TikTok Discovery
    if not args.ig_only:
        print(f"\n{'━'*50}")
        print(f"  TIKTOK — {len(tt_keywords)} keywords")
        print(f"{'━'*50}")
        tt_posts = discover_tiktok(tt_keywords, days=args.days)
        save_raw(tt_posts, "jp_tt_discovery")
        all_posts.extend(tt_posts)

    # Summary
    from collections import Counter
    platforms = Counter(p["Platform"] for p in all_posts)
    print(f"\n{'═'*50}")
    print(f"  DISCOVERY SUMMARY")
    print(f"{'═'*50}")
    print(f"  Total: {len(all_posts)}")
    for plat, cnt in platforms.most_common():
        print(f"    {plat}: {cnt}")
    handles = set(p["Handle"] for p in all_posts)
    print(f"  Unique handles: {len(handles)}")
    with_caption = sum(1 for p in all_posts if p.get("Caption"))
    print(f"  With caption: {with_caption}/{len(all_posts)} ({with_caption/max(len(all_posts),1)*100:.0f}%)")

    # Write to sheet
    if not args.no_sheet:
        write_to_sheet(all_posts, tab_name, dry_run=args.dry_run)

    print(f"\n✓ Done!")


if __name__ == "__main__":
    main()
