"""Deep Crawler — discover recent posts from creator handles via Apify.

Scrapes IG/TikTok profiles + their latest posts, exports to Excel,
optionally syncs to PG via push_content_to_pg.

Usage:
    # Comma-separated handles
    python tools/deep_crawler.py --handles "user1,user2,user3"

    # From file (one handle per line)
    python tools/deep_crawler.py --handles-file creators.txt

    # From Syncly cache
    python tools/deep_crawler.py --from-syncly
    python tools/deep_crawler.py --from-syncly --min-views 5000

    # Filters
    python tools/deep_crawler.py --handles "user1" --max-posts 10 --min-post-views 1000

    # Dry run
    python tools/deep_crawler.py --handles "user1" --dry-run

    # PG sync
    python tools/deep_crawler.py --handles "user1" --pg-sync

    # Custom output
    python tools/deep_crawler.py --handles "user1" --output "my_crawl.xlsx"

    # Platform filter
    python tools/deep_crawler.py --handles "user1" --platform tiktok
"""

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows cp949
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DIR.parent
sys.path.insert(0, str(DIR))

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

# ── Constants ────────────────────────────────────────────────────────

TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "deep_crawler" / "output"
CACHE_FILE = PROJECT_ROOT / ".tmp" / "deep_crawler" / "profile_cache.json"
SYNCLY_CACHE = PROJECT_ROOT / ".tmp" / "data_crawler" / "cache" / "cache_1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o_Creators_updated.json"

ILLEGAL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')

# Apify actors
IG_PROFILE_SCRAPER = "apify/instagram-profile-scraper"
TT_SCRAPER = "clockworks/free-tiktok-scraper"

BATCH_SIZE = 20
COOLDOWN_SECS = 5
CACHE_TTL = 86400  # 24 hours


# ── Helpers ──────────────────────────────────────────────────────────

def safe_num(val):
    """Parse numeric value from string (handles commas, blanks, #DIV/0!)."""
    if not val or val in ("", "#DIV/0!", "#REF!", "#N/A", "#VALUE!"):
        return 0
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def clean(val):
    """Clean cell value for Excel."""
    if val is None:
        return ""
    s = str(val).strip()
    return ILLEGAL_CHARS.sub("", s)


def load_cache() -> dict:
    """Load profile cache from disk."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_cache(cache: dict):
    """Save profile cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def is_cache_fresh(entry: dict) -> bool:
    """Check if a cache entry is within TTL."""
    crawled_at = entry.get("crawled_at", 0)
    return (time.time() - crawled_at) < CACHE_TTL


# ── Input Loaders ────────────────────────────────────────────────────

def load_handles_csv(raw: str) -> list[str]:
    """Parse comma-separated handles."""
    handles = []
    for h in raw.split(","):
        h = h.strip().lstrip("@")
        if h:
            handles.append(h)
    return handles


def load_handles_file(filepath: str) -> list[str]:
    """Load handles from file, one per line."""
    p = Path(filepath)
    if not p.exists():
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)
    handles = []
    for line in p.read_text(encoding="utf-8").splitlines():
        h = line.strip().lstrip("@")
        if h and not h.startswith("#"):
            handles.append(h)
    return handles


def load_handles_syncly(min_views: float = 0) -> list[str]:
    """Load handles from Syncly Creators_updated cache."""
    if not SYNCLY_CACHE.exists():
        print(f"[ERROR] Syncly cache not found: {SYNCLY_CACHE}")
        print("  Run data_crawler first to populate the cache.")
        sys.exit(1)

    data = json.loads(SYNCLY_CACHE.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("values", [])

    handles = []
    for row in rows[1:]:  # skip header
        if len(row) <= 3:
            continue
        username = str(row[3]).strip().lstrip("@")
        if not username:
            continue

        if min_views > 0:
            views_val = safe_num(row[21] if len(row) > 21 else 0)
            if views_val < min_views:
                continue

        handles.append(username)

    return handles


# ── Apify Scrapers ───────────────────────────────────────────────────

def scrape_ig_profiles(handles: list[str], client) -> list[dict]:
    """Scrape Instagram profiles in batches via Apify."""
    all_results = []
    total = len(handles)

    for i in range(0, total, BATCH_SIZE):
        batch = handles[i:i + BATCH_SIZE]
        chunk_num = i // BATCH_SIZE + 1
        total_chunks = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  [IG] Chunk {chunk_num}/{total_chunks}: {len(batch)} handles...")

        try:
            run_input = {
                "usernames": batch,
                "resultsLimit": 1,  # 1 profile per username
            }
            run = client.actor(IG_PROFILE_SCRAPER).call(run_input=run_input)
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            all_results.extend(items)
            print(f"    -> Got {len(items)} profiles")
        except Exception as e:
            print(f"    [ERROR] IG batch failed: {e}")

        if i + BATCH_SIZE < total:
            print(f"    Cooldown {COOLDOWN_SECS}s...")
            time.sleep(COOLDOWN_SECS)

    return all_results


def scrape_tiktok_profiles(handles: list[str], client) -> list[dict]:
    """Scrape TikTok profiles in batches via Apify."""
    all_results = []
    total = len(handles)

    for i in range(0, total, BATCH_SIZE):
        batch = handles[i:i + BATCH_SIZE]
        chunk_num = i // BATCH_SIZE + 1
        total_chunks = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  [TT] Chunk {chunk_num}/{total_chunks}: {len(batch)} handles...")

        try:
            queries = [f"@{h}" for h in batch]
            run_input = {
                "searchQueries": queries,
            }
            run = client.actor(TT_SCRAPER).call(run_input=run_input)
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            all_results.extend(items)
            print(f"    -> Got {len(items)} results")
        except Exception as e:
            print(f"    [ERROR] TT batch failed: {e}")

        if i + BATCH_SIZE < total:
            print(f"    Cooldown {COOLDOWN_SECS}s...")
            time.sleep(COOLDOWN_SECS)

    return all_results


# ── Data Extraction ──────────────────────────────────────────────────

def extract_ig_profile(item: dict) -> dict:
    """Extract profile data from IG profile scraper response."""
    return {
        "username": item.get("username", ""),
        "followers": safe_num(item.get("followersCount", 0)),
        "following": safe_num(item.get("followsCount", 0)),
        "bio": clean(item.get("biography", "")),
        "profile_pic_url": item.get("profilePicUrl", ""),
        "post_count": safe_num(item.get("postsCount", 0)),
        "is_verified": bool(item.get("verified", False)),
        "platform": "instagram",
    }


def extract_ig_posts(item: dict) -> list[dict]:
    """Extract posts from IG profile's latestPosts array."""
    username = item.get("username", "")
    posts = []

    for p in item.get("latestPosts", []):
        shortcode = p.get("shortCode", p.get("id", ""))
        views = safe_num(p.get("videoViewCount", 0))
        likes = safe_num(p.get("likesCount", 0))
        comments = safe_num(p.get("commentsCount", 0))

        er = 0.0
        if views > 0:
            er = (likes + comments) / views

        # Extract hashtags
        hashtags_raw = p.get("hashtags", [])
        if isinstance(hashtags_raw, list):
            hashtag_strs = []
            for tag in hashtags_raw:
                if isinstance(tag, dict):
                    hashtag_strs.append(tag.get("name", str(tag)))
                else:
                    hashtag_strs.append(str(tag))
            hashtags = ", ".join(hashtag_strs)
        else:
            hashtags = str(hashtags_raw)

        post_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else ""

        posts.append({
            "username": username,
            "post_url": post_url,
            "post_id": shortcode,
            "views": int(views),
            "likes": int(likes),
            "comments": int(comments),
            "caption": clean(p.get("caption", "")),
            "hashtags": clean(hashtags),
            "post_date": p.get("timestamp", ""),
            "media_type": p.get("type", ""),
            "engagement_rate": round(er, 6),
            "thumbnail_url": p.get("displayUrl", ""),
            "platform": "instagram",
        })

    return posts


def extract_tiktok_profile(item: dict) -> dict:
    """Extract profile data from TikTok scraper response."""
    author = item.get("authorMeta", item)
    return {
        "username": author.get("name", author.get("uniqueId", "")),
        "followers": safe_num(author.get("fans", author.get("followers", 0))),
        "following": safe_num(author.get("following", 0)),
        "bio": clean(author.get("signature", author.get("bio", ""))),
        "profile_pic_url": author.get("avatar", ""),
        "post_count": safe_num(author.get("video", author.get("videoCount", 0))),
        "is_verified": bool(author.get("verified", False)),
        "platform": "tiktok",
    }


def extract_tiktok_posts(items: list[dict], username: str) -> list[dict]:
    """Extract posts from TikTok scraper results for a given user."""
    posts = []

    for item in items:
        author = item.get("authorMeta", {})
        item_user = author.get("name", author.get("uniqueId", ""))
        if item_user.lower() != username.lower():
            continue

        views = safe_num(item.get("playCount", item.get("views", 0)))
        likes = safe_num(item.get("diggCount", item.get("likes", 0)))
        comments = safe_num(item.get("commentCount", item.get("comments", 0)))

        er = 0.0
        if views > 0:
            er = (likes + comments) / views

        hashtags_raw = item.get("hashtags", [])
        if isinstance(hashtags_raw, list):
            hashtag_strs = []
            for tag in hashtags_raw:
                if isinstance(tag, dict):
                    hashtag_strs.append(tag.get("name", str(tag)))
                else:
                    hashtag_strs.append(str(tag))
            hashtags = ", ".join(hashtag_strs)
        else:
            hashtags = str(hashtags_raw)

        post_url = item.get("webVideoUrl", item.get("url", ""))

        posts.append({
            "username": username,
            "post_url": post_url,
            "post_id": item.get("id", ""),
            "views": int(views),
            "likes": int(likes),
            "comments": int(comments),
            "caption": clean(item.get("text", "")),
            "hashtags": clean(hashtags),
            "post_date": item.get("createTimeISO", item.get("createTime", "")),
            "media_type": "video",
            "engagement_rate": round(er, 6),
            "thumbnail_url": item.get("videoMeta", {}).get("coverUrl", ""),
            "platform": "tiktok",
        })

    return posts


# ── Filters ──────────────────────────────────────────────────────────

def filter_posts(posts: list[dict], max_posts: int = 0,
                 min_views: int = 0, min_er: float = 0.0) -> list[dict]:
    """Apply post-level filters."""
    filtered = posts

    if min_views > 0:
        filtered = [p for p in filtered if p["views"] >= min_views]

    if min_er > 0:
        filtered = [p for p in filtered if p["engagement_rate"] >= min_er]

    if max_posts > 0:
        # Group by username, keep top N per creator (by views desc)
        from collections import defaultdict
        by_user = defaultdict(list)
        for p in filtered:
            by_user[p["username"]].append(p)

        result = []
        for username, user_posts in by_user.items():
            user_posts.sort(key=lambda x: x["views"], reverse=True)
            result.extend(user_posts[:max_posts])
        filtered = result

    return filtered


# ── Output ───────────────────────────────────────────────────────────

def write_excel(profiles: list[dict], posts: list[dict], output_path: Path):
    """Write profiles + posts to Excel with 2 sheets."""
    try:
        import openpyxl
    except ImportError:
        print("[ERROR] openpyxl not installed. Run: pip install openpyxl")
        sys.exit(1)

    wb = openpyxl.Workbook()

    # -- Profiles sheet --
    ws_profiles = wb.active
    ws_profiles.title = "Profiles"
    profile_headers = [
        "username", "platform", "followers", "following", "bio",
        "post_count", "is_verified", "crawled_posts_count",
    ]
    ws_profiles.append(profile_headers)

    # Count crawled posts per user
    from collections import Counter
    post_counts = Counter(p["username"] for p in posts)

    for prof in profiles:
        ws_profiles.append([
            clean(prof.get("username", "")),
            prof.get("platform", ""),
            int(prof.get("followers", 0)),
            int(prof.get("following", 0)),
            clean(prof.get("bio", "")),
            int(prof.get("post_count", 0)),
            str(prof.get("is_verified", False)),
            post_counts.get(prof.get("username", ""), 0),
        ])

    # -- Posts sheet --
    ws_posts = wb.create_sheet("Posts")
    post_headers = [
        "username", "post_url", "post_id", "views", "likes", "comments",
        "caption", "hashtags", "post_date", "media_type",
        "engagement_rate", "thumbnail_url", "platform",
    ]
    ws_posts.append(post_headers)

    for p in posts:
        ws_posts.append([
            clean(p.get("username", "")),
            p.get("post_url", ""),
            p.get("post_id", ""),
            p.get("views", 0),
            p.get("likes", 0),
            p.get("comments", 0),
            clean(p.get("caption", "")),
            clean(p.get("hashtags", "")),
            p.get("post_date", ""),
            p.get("media_type", ""),
            round(p.get("engagement_rate", 0), 6),
            p.get("thumbnail_url", ""),
            p.get("platform", ""),
        ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    print(f"\n[OK] Excel saved: {output_path}")
    print(f"     Profiles: {len(profiles)} | Posts: {len(posts)}")


def pg_sync(profiles: list[dict], posts: list[dict]):
    """Sync crawled data to PostgreSQL via push_content_to_pg."""
    try:
        from push_content_to_pg import push_posts, push_metrics
    except ImportError:
        print("[ERROR] push_content_to_pg not found. Skipping PG sync.")
        return

    # Build followers lookup from profiles
    followers_map = {p["username"]: int(p.get("followers", 0)) for p in profiles}

    # Map posts to content_posts format
    post_rows = []
    metric_rows = []

    for p in posts:
        post_rows.append({
            "post_id": p["post_id"],
            "url": p["post_url"],
            "platform": p.get("platform", "instagram"),
            "username": p["username"],
            "followers": followers_map.get(p["username"], 0),
            "caption": p.get("caption", ""),
            "hashtags": p.get("hashtags", ""),
            "post_date": p.get("post_date", ""),
            "region": "us",
            "source": "deep_crawler",
        })

        metric_rows.append({
            "post_id": p["post_id"],
            "date": TODAY,
            "views": p.get("views", 0),
            "likes": p.get("likes", 0),
            "comments": p.get("comments", 0),
        })

    print(f"\n[PG Sync] Pushing {len(post_rows)} posts + {len(metric_rows)} metrics...")
    post_result = push_posts(post_rows)
    metric_result = push_metrics(metric_rows)

    print(f"  Posts:   +{post_result.get('created', 0)} new, ~{post_result.get('updated', 0)} updated")
    print(f"  Metrics: +{metric_result.get('created', 0)} new, ~{metric_result.get('updated', 0)} updated")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Deep Crawler — Apify profile + post scraper")

    # Input modes
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--handles", type=str, help="Comma-separated handles")
    input_group.add_argument("--handles-file", type=str, help="File with one handle per line")
    input_group.add_argument("--from-syncly", action="store_true", help="Load from Syncly cache")

    # Syncly filter
    parser.add_argument("--min-views", type=float, default=0, help="Min views_30d filter (Syncly mode)")

    # Post filters
    parser.add_argument("--max-posts", type=int, default=0, help="Max posts per creator (0=all)")
    parser.add_argument("--min-post-views", type=int, default=0, help="Min views per post")
    parser.add_argument("--min-post-er", type=float, default=0.0, help="Min engagement rate per post")

    # Platform
    parser.add_argument("--platform", choices=["instagram", "tiktok"], default=None,
                        help="Only crawl one platform")

    # Output
    parser.add_argument("--dry-run", action="store_true", help="Print counts + sample, no file")
    parser.add_argument("--output", type=str, default=None, help="Custom output filename")
    parser.add_argument("--pg-sync", action="store_true", help="Sync to PostgreSQL")

    args = parser.parse_args()

    # ── Load handles ──
    if args.handles:
        handles = load_handles_csv(args.handles)
    elif args.handles_file:
        handles = load_handles_file(args.handles_file)
    elif args.from_syncly:
        handles = load_handles_syncly(min_views=args.min_views)
    else:
        handles = []

    handles = list(dict.fromkeys(handles))  # dedupe, preserve order

    if not handles:
        print("[ERROR] No handles to crawl.")
        sys.exit(1)

    print(f"[Deep Crawler] {len(handles)} handles to crawl")
    print(f"  Platform: {args.platform or 'all'}")
    print(f"  Filters: max_posts={args.max_posts}, min_post_views={args.min_post_views}, min_post_er={args.min_post_er}")

    # ── Init Apify client ──
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("[ERROR] apify-client not installed. Run: pip install apify-client")
        sys.exit(1)

    token = os.getenv("APIFY_TOKEN", "")
    if not token:
        print("[ERROR] APIFY_TOKEN not set in environment.")
        sys.exit(1)

    client = ApifyClient(token)

    # ── Load cache ──
    cache = load_cache()
    all_profiles = []
    all_posts = []

    # ── Scrape Instagram ──
    if args.platform in (None, "instagram"):
        # Split into cached vs uncached
        ig_to_scrape = []
        for h in handles:
            cache_key = f"ig:{h}"
            if cache_key in cache and is_cache_fresh(cache[cache_key]):
                print(f"  [CACHE HIT] {h} (IG)")
                entry = cache[cache_key]
                all_profiles.append(entry["profile"])
                all_posts.extend(entry["posts"])
            else:
                ig_to_scrape.append(h)

        if ig_to_scrape:
            print(f"\n[IG] Scraping {len(ig_to_scrape)} uncached profiles...")
            ig_results = scrape_ig_profiles(ig_to_scrape, client)

            for item in ig_results:
                profile = extract_ig_profile(item)
                posts = extract_ig_posts(item)
                all_profiles.append(profile)
                all_posts.extend(posts)

                # Update cache
                cache_key = f"ig:{profile['username']}"
                cache[cache_key] = {
                    "profile": profile,
                    "posts": posts,
                    "crawled_at": time.time(),
                }

            save_cache(cache)
        else:
            print("  [IG] All handles cached, skipping Apify calls.")

    # ── Scrape TikTok ──
    if args.platform in (None, "tiktok"):
        tt_to_scrape = []
        for h in handles:
            cache_key = f"tt:{h}"
            if cache_key in cache and is_cache_fresh(cache[cache_key]):
                print(f"  [CACHE HIT] {h} (TT)")
                entry = cache[cache_key]
                all_profiles.append(entry["profile"])
                all_posts.extend(entry["posts"])
            else:
                tt_to_scrape.append(h)

        if tt_to_scrape:
            print(f"\n[TT] Scraping {len(tt_to_scrape)} uncached profiles...")
            tt_results = scrape_tiktok_profiles(tt_to_scrape, client)

            # Group TT results by username
            for h in tt_to_scrape:
                profile = None
                user_posts = extract_tiktok_posts(tt_results, h)

                # Find profile info from results
                for item in tt_results:
                    author = item.get("authorMeta", item)
                    item_user = author.get("name", author.get("uniqueId", ""))
                    if item_user.lower() == h.lower():
                        profile = extract_tiktok_profile(item)
                        break

                if profile:
                    all_profiles.append(profile)
                    all_posts.extend(user_posts)

                    cache_key = f"tt:{h}"
                    cache[cache_key] = {
                        "profile": profile,
                        "posts": user_posts,
                        "crawled_at": time.time(),
                    }

            save_cache(cache)
        else:
            print("  [TT] All handles cached, skipping Apify calls.")

    # ── Apply filters ──
    all_posts = filter_posts(
        all_posts,
        max_posts=args.max_posts,
        min_views=args.min_post_views,
        min_er=args.min_post_er,
    )

    # ── Output ──
    print(f"\n[Results] {len(all_profiles)} profiles, {len(all_posts)} posts (after filters)")

    if args.dry_run:
        print("\n--- DRY RUN (no file written) ---")
        print(f"Profiles: {len(all_profiles)}")
        print(f"Posts:    {len(all_posts)}")

        if all_profiles:
            print("\nSample profile:")
            sample = all_profiles[0]
            for k, v in sample.items():
                val = str(v)[:80]
                print(f"  {k}: {val}")

        if all_posts:
            print("\nSample post:")
            sample = all_posts[0]
            for k, v in sample.items():
                val = str(v)[:80]
                print(f"  {k}: {val}")

        return

    # Write Excel
    filename = args.output or f"deep_crawl_{TODAY}.xlsx"
    output_path = OUTPUT_DIR / filename
    write_excel(all_profiles, all_posts, output_path)

    # PG sync
    if args.pg_sync:
        pg_sync(all_profiles, all_posts)

    print("\n[Done]")


if __name__ == "__main__":
    main()
