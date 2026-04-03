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
IG_POST_SCRAPER = "apify/instagram-scraper"  # for individual post URL scraping (gets videoViewCount)
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
def enrich_ig_posts(posts: list[dict], delay: float = 0.5) -> list[dict]:
    """Enrich ALL IG posts with views/likes/comments via RapidAPI.

    Apify hashtag scraper returns views=0 for IG posts. RapidAPI provides
    video_view_count, like_count, comment_count that we use to fill gaps.
    Also backfills captions/hashtags if missing.
    """
    if not RAPIDAPI_KEY:
        print("[ENRICH] No RAPIDAPI_KEY, skipping enrichment")
        return posts

    ig_posts = [p for p in posts if p["Platform"] == "instagram"]
    if not ig_posts:
        print("[ENRICH] No IG posts to enrich")
        return posts

    print(f"\n[ENRICH] Enriching {len(ig_posts)} IG posts via RapidAPI (delay={delay}s)")

    # Group by handle
    by_handle = {}
    for p in ig_posts:
        h = p["Handle"]
        if h not in by_handle:
            by_handle[h] = []
        by_handle[h].append(p)

    cache = {}
    enriched = 0
    api_calls = 0
    for handle, handle_posts in by_handle.items():
        if handle in cache:
            api_posts = cache[handle]
        else:
            try:
                time.sleep(delay)
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
                api_calls += 1
            except Exception as e:
                print(f"  ⚠ @{handle}: {e}")
                cache[handle] = []
                continue

        for p in handle_posts:
            sc = p["_post_id"]
            match = next((ap for ap in api_posts if ap.get("code") == sc), None)
            if match:
                # Views: video_view_count or view_count (Reels/Video only)
                views = match.get("video_view_count", 0) or match.get("view_count", 0) or 0
                if views > 0:
                    p["Views"] = views

                # Likes: edge_media_preview_like.count or like_count
                likes_edge = match.get("edge_media_preview_like", {})
                likes = likes_edge.get("count", 0) if isinstance(likes_edge, dict) else 0
                if not likes:
                    likes = match.get("like_count", 0) or 0
                if likes > 0:
                    p["Likes"] = likes

                # Comments: edge_media_to_comment.count or comment_count
                comments_edge = match.get("edge_media_to_comment", {})
                comments = comments_edge.get("count", 0) if isinstance(comments_edge, dict) else 0
                if not comments:
                    comments = match.get("comment_count", 0) or 0
                if comments > 0:
                    p["Comments Count"] = comments

                # Caption backfill (if Apify missed it)
                if not p.get("Caption"):
                    cap_obj = match.get("caption", {})
                    cap_text = cap_obj.get("text", "") if isinstance(cap_obj, dict) else str(cap_obj)
                    if cap_text:
                        p["Caption"] = cap_text
                        p["Hashtags"] = " ".join(re.findall(
                            r"#[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+", cap_text
                        ))

                enriched += 1

    print(f"[ENRICH] Enriched {enriched}/{len(ig_posts)} posts ({api_calls} API calls to {len(by_handle)} handles)")
    return posts


# ── Apify View Enrichment ───────────────────────────────────────────────── #
def enrich_ig_views(posts: list[dict]) -> list[dict]:
    """Scrape individual IG post URLs via apify/instagram-scraper to get videoViewCount.

    The hashtag scraper returns views=0 for IG. Individual post scraping gets real views.
    """
    if not APIFY_TOKEN:
        print("[VIEWS] No APIFY_API_TOKEN, skipping view enrichment")
        return posts

    ig_posts = [p for p in posts if p["Platform"] == "instagram" and (p.get("Views") or 0) == 0]
    if not ig_posts:
        print("[VIEWS] All IG posts already have views")
        return posts

    urls = [p["URL"] for p in ig_posts if p.get("URL")]
    if not urls:
        return posts

    print(f"\n[VIEWS] Scraping {len(urls)} IG post URLs for videoViewCount via Apify...")

    try:
        from apify_client import ApifyClient
        client = ApifyClient(APIFY_TOKEN)
        run = client.actor(IG_POST_SCRAPER).call(
            run_input={
                "directUrls": urls,
                "resultsLimit": len(urls),
                "resultsType": "posts",
            },
            timeout_secs=600,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"[VIEWS] Got {len(items)} results from Apify")
    except Exception as e:
        print(f"[VIEWS] Apify scrape failed: {e}")
        return posts

    # Build shortCode → views map
    views_map = {}
    for item in items:
        sc = item.get("shortCode", "")
        views = item.get("videoViewCount", 0) or 0
        likes = item.get("likesCount", 0) or 0
        comments = item.get("commentsCount", 0) or 0
        if sc:
            views_map[sc] = {"views": views, "likes": likes, "comments": comments}

    enriched = 0
    for p in ig_posts:
        sc = p.get("_post_id", "")
        if sc in views_map:
            v = views_map[sc]
            if v["views"] > 0:
                p["Views"] = v["views"]
            if v["likes"] > 0 and (p.get("Likes") or 0) == 0:
                p["Likes"] = v["likes"]
            if v["comments"] > 0 and (p.get("Comments Count") or 0) == 0:
                p["Comments Count"] = v["comments"]
            enriched += 1

    with_views = sum(1 for p in ig_posts if (p.get("Views") or 0) > 0)
    print(f"[VIEWS] Matched {enriched}/{len(ig_posts)}, {with_views} now have views>0")
    return posts


# ── RapidAPI Reels Discovery ─────────────────────────────────────────────── #
def discover_ig_reels(handles: list[str], max_reels_per_handle: int = 5, delay: float = 0.5) -> list[dict]:
    """Fetch Reels for discovered IG handles via RapidAPI.

    Apify hashtag scraper doesn't return Reels. This fills the gap by
    fetching Reels from each discovered creator's profile.
    """
    if not RAPIDAPI_KEY:
        print("[REELS] No RAPIDAPI_KEY, skipping Reels discovery")
        return []

    unique = list(dict.fromkeys(h.lower() for h in handles if h))
    unique = [h for h in unique if h.lower() not in EXCLUDE_ACCOUNTS]
    print(f"\n[REELS] Fetching Reels for {len(unique)} IG handles via RapidAPI")

    all_reels = []
    api_calls = 0
    for handle in unique:
        try:
            time.sleep(delay)
            url = f"https://{RAPIDAPI_HOST}/get_ig_user_reels.php"
            data = urllib.parse.urlencode({
                "username_or_url": handle,
                "amount": str(max_reels_per_handle),
            }).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            req.add_header("x-rapidapi-host", RAPIDAPI_HOST)
            req.add_header("x-rapidapi-key", RAPIDAPI_KEY)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
            api_calls += 1

            reels = result.get("reels", [])
            for r in reels:
                node = r.get("node", r)
                media = node.get("media", node)
                code = media.get("code", "")
                if not code:
                    continue
                cap_obj = media.get("caption", {})
                caption = cap_obj.get("text", "") if isinstance(cap_obj, dict) else str(cap_obj or "")
                hashtags = re.findall(r"#[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+", caption)
                play_count = media.get("play_count", 0) or 0
                like_count = media.get("like_count", 0) or 0
                comment_count = media.get("comment_count", 0) or 0

                all_reels.append({
                    "Handle": handle,
                    "Full Name": "",
                    "Platform": "instagram",
                    "URL": f"https://www.instagram.com/reel/{code}/",
                    "Date": "",
                    "Type": "Video",
                    "Source": "rapidapi/reels",
                    "Followers": 0,  # filled later if available
                    "Views": play_count,
                    "Likes": like_count,
                    "Comments Count": comment_count,
                    "Hashtags": " ".join(hashtags),
                    "Mentions": "",
                    "Caption": caption,
                    "_post_id": code,
                    "_source_tag": "reels",
                })

        except Exception as e:
            print(f"  ⚠ @{handle}: {e}")
            continue

    print(f"[REELS] Got {len(all_reels)} Reels from {api_calls} handles")
    return all_reels


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
        ig_posts = enrich_ig_posts(ig_posts)       # RapidAPI: likes + comments
        ig_posts = enrich_ig_views(ig_posts)        # Apify: videoViewCount
        save_raw(ig_posts, "jp_ig_discovery")
        all_posts.extend(ig_posts)

        # Reels Discovery: fetch Reels from discovered handles via RapidAPI
        ig_handles = list(set(p["Handle"] for p in ig_posts if p.get("Handle")))
        ig_reels = discover_ig_reels(ig_handles, max_reels_per_handle=5)
        if ig_reels:
            # Dedup against already-discovered posts
            existing_urls = set(p["URL"] for p in all_posts)
            ig_reels = [r for r in ig_reels if r["URL"] not in existing_urls]
            save_raw(ig_reels, "jp_ig_reels")
            all_posts.extend(ig_reels)
            print(f"[REELS] Added {len(ig_reels)} unique Reels to discovery")

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
    with_views = sum(1 for p in all_posts if (p.get("Views") or 0) > 0)
    with_likes = sum(1 for p in all_posts if (p.get("Likes") or 0) > 0)
    with_comments = sum(1 for p in all_posts if (p.get("Comments Count") or 0) > 0)
    print(f"  With caption: {with_caption}/{len(all_posts)} ({with_caption/max(len(all_posts),1)*100:.0f}%)")
    print(f"  With views:   {with_views}/{len(all_posts)} ({with_views/max(len(all_posts),1)*100:.0f}%)")
    print(f"  With likes:   {with_likes}/{len(all_posts)} ({with_likes/max(len(all_posts),1)*100:.0f}%)")
    print(f"  With comments:{with_comments}/{len(all_posts)} ({with_comments/max(len(all_posts),1)*100:.0f}%)")

    # Write to sheet
    if not args.no_sheet:
        write_to_sheet(all_posts, tab_name, dry_run=args.dry_run)

    print(f"\n✓ Done!")


if __name__ == "__main__":
    main()
