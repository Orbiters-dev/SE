"""
JP Social Ambassador Discovery — Hashtag-based creator crawling
================================================================
일본어 육아 해시태그로 IG 검색 → 새 크리에이터 발굴 → PG 저장 + 시트 업데이트

Usage:
  # Tier 1 only (제품 관련 키워드)
  python tools/discover_jp_ambassadors.py --tier 1 --max-per-hashtag 30

  # All tiers
  python tools/discover_jp_ambassadors.py --tier all --max-per-hashtag 20

  # Dry run (no Apify calls, load cached)
  python tools/discover_jp_ambassadors.py --dry-run

  # Just show results, don't push to PG
  python tools/discover_jp_ambassadors.py --no-push
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "apify"
CACHE_DIR = PROJECT_ROOT / ".tmp" / "ambassador_discovery"

# Apify actors
IG_HASHTAG_SCRAPER = "apify/instagram-hashtag-scraper"
IG_PROFILE_SCRAPER = "apify/instagram-profile-scraper"

# ---------------------------------------------------------------------------
# JP parenting hashtags by tier
# ---------------------------------------------------------------------------
HASHTAGS_TIER1 = [
    "ストローマグ",       # straw mug
    "ベビーマグ",         # baby mug
    "ストローデビュー",   # straw debut
    "マグデビュー",       # mug debut
    "ストロー練習",       # straw practice
]

HASHTAGS_TIER2 = [
    "離乳食",             # baby food / weaning
    "離乳食レシピ",       # weaning recipe
    "育児グッズ",         # parenting goods
    "ベビー用品",         # baby products
    "ベビーグッズ",       # baby goods
]

HASHTAGS_TIER3 = [
    "育児ママ",           # parenting mom
    "新米ママ",           # new mom
    "子育て",             # child rearing
    "赤ちゃんのいる生活", # life with baby
    "ママライフ",         # mom life
]

# Already-collaborated brands to exclude
EXCLUDE_KEYWORDS = {
    "grosmimi", "グロスミミ", "grosmimi_japan", "onzenna",
    "grosmimi_usa", "grosmimi_official",
}

# Brand/store accounts to exclude
EXCLUDE_ACCOUNTS = {
    "onzenna.official", "grosmimi_usa", "grosmimi_japan", "grosmimi_official",
    "grosmimi_korea", "onzenna", "grosmimi", "zezebaebae",
    "grosmimithailand", "grosmimi_thailand", "grosmimi_cambodia", "grosmimi_uae",
    "grosmimi.id", "grosmimi.indo", "grosmimi_malaysia",
    "grosmimivietnam.official", "grosmimi.vietnam",
    "grosmimiofficial_sg", "grosmimi_sk", "grosmimi_hu",
    "chaandmom.vn", "commemoi.vietnam", "commemoi._.official",
    "naeiae.official", "naeiae",
    "baby.boutique.official", "baby.boutique.kh", "chez.gros.mimi",
}

TODAY = datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Apify hashtag search
# ---------------------------------------------------------------------------

def get_client():
    load_env()
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("[ERROR] APIFY_API_TOKEN not found")
        sys.exit(1)
    from apify_client import ApifyClient
    return ApifyClient(token)


def fetch_hashtag_posts(client, hashtags: list, max_per_hashtag: int = 30,
                        reels_only: bool = False) -> list:
    """Search IG by hashtag using Apify hashtag scraper.
    reels_only=False: JP parenting hashtags are mostly photo posts.
    Set True to filter to Video only (rare for these hashtags).
    """
    all_items = []

    for tag in hashtags:
        search_type = "reels" if reels_only else "hashtag"
        print(f"[HASHTAG] #{tag} (max={max_per_hashtag}, type={search_type})...")
        try:
            run = client.actor(IG_HASHTAG_SCRAPER).call(
                run_input={
                    "hashtags": [tag],
                    "resultsLimit": max_per_hashtag,
                    "searchType": search_type,
                },
                timeout_secs=300,
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            # Filter to video posts only (has videoUrl or type==Video)
            if reels_only:
                before = len(items)
                items = [it for it in items
                         if it.get("videoUrl") or it.get("type") == "Video"]
                if before != len(items):
                    print(f"  #{tag}: filtered {before} -> {len(items)} (video only)")
            for item in items:
                item["_search_hashtag"] = tag
            print(f"  #{tag}: {len(items)} posts")
            all_items.extend(items)
        except Exception as e:
            print(f"  [WARN] #{tag} failed: {e}")

        time.sleep(2)  # rate limit courtesy

    return all_items


def fetch_profiles(client, usernames: list) -> dict:
    """Fetch IG profile info for a list of usernames."""
    if not usernames:
        return {}

    print(f"[PROFILE] Fetching {len(usernames)} profiles...")
    profiles = {}

    # Batch in chunks of 50
    for i in range(0, len(usernames), 50):
        chunk = usernames[i:i+50]
        try:
            run = client.actor(IG_PROFILE_SCRAPER).call(
                run_input={
                    "usernames": chunk,
                },
                timeout_secs=300,
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            for item in items:
                uname = item.get("username", "").lower()
                profiles[uname] = {
                    "username": item.get("username", ""),
                    "full_name": item.get("fullName", ""),
                    "followers": item.get("followersCount", 0),
                    "following": item.get("followsCount", 0),
                    "posts_count": item.get("postsCount", 0),
                    "bio": item.get("biography", ""),
                    "is_verified": item.get("verified", False),
                    "is_business": item.get("isBusinessAccount", False),
                    "profile_url": f"https://www.instagram.com/{item.get('username', '')}/",
                    "profile_pic": item.get("profilePicUrl", ""),
                }
            print(f"  Batch {i//50+1}: {len(items)} profiles")
        except Exception as e:
            print(f"  [WARN] Profile batch failed: {e}")

        time.sleep(2)

    return profiles


# ---------------------------------------------------------------------------
# Filtering & scoring
# ---------------------------------------------------------------------------

def get_existing_creators() -> set:
    """Get set of usernames already in our pipeline (PG)."""
    existing = set()
    try:
        import psycopg2
        DB_HOST = os.getenv("DB_HOST", "172.31.13.240")
        DB_NAME = os.getenv("DB_NAME", "export_calculator_db")
        DB_USER = os.getenv("DB_USER", "es_db_user")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")

        if not DB_PASSWORD:
            print("[DB] No DB_PASSWORD, skipping existing creator check")
            return existing

        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        cur = conn.cursor()

        # From content_posts (already posted about grosmimi)
        cur.execute("SELECT DISTINCT LOWER(username) FROM gk_content_posts WHERE region='jp'")
        for row in cur.fetchall():
            if row[0]:
                existing.add(row[0])

        # From pipeline_creators
        cur.execute("SELECT DISTINCT LOWER(ig_handle) FROM onz_pipeline_creators WHERE country='jp'")
        for row in cur.fetchall():
            if row[0]:
                existing.add(row[0])

        conn.close()
        print(f"[DB] {len(existing)} existing JP creators in pipeline")
    except Exception as e:
        print(f"[DB WARN] Could not check existing creators: {e}")

    return existing


def filter_and_dedupe(raw_posts: list, existing_creators: set) -> dict:
    """Filter posts and dedupe by creator. Returns {username: best_post}."""
    creator_posts = defaultdict(list)

    for post in raw_posts:
        username = (post.get("ownerUsername") or post.get("username") or "").lower().strip()
        if not username:
            continue

        # Skip brand accounts
        if username in EXCLUDE_ACCOUNTS:
            continue

        # Skip existing creators
        if username in existing_creators:
            continue

        # Skip if caption mentions grosmimi (already collaborating)
        caption = (post.get("caption") or "").lower()
        if any(kw in caption for kw in EXCLUDE_KEYWORDS):
            continue

        # Normalize post data
        likes = post.get("likesCount") or post.get("likes") or 0
        comments = post.get("commentsCount") or post.get("comments") or 0
        views = post.get("videoViewCount") or post.get("videoPlayCount") or post.get("views") or 0
        media_type = post.get("type") or post.get("mediaType") or ""
        url = post.get("url") or post.get("permalink") or ""
        shortcode = post.get("shortCode") or post.get("shortcode") or ""
        timestamp = post.get("timestamp") or post.get("takenAt") or ""

        creator_posts[username].append({
            "username": username,
            "shortcode": shortcode,
            "url": url,
            "caption": post.get("caption", ""),
            "likes": likes,
            "comments": comments,
            "views": views,
            "media_type": media_type,
            "timestamp": str(timestamp),
            "hashtag_source": post.get("_search_hashtag", ""),
            "engagement": likes + comments,
        })

    # Pick best post per creator (highest engagement)
    best = {}
    for username, posts in creator_posts.items():
        posts.sort(key=lambda x: x["engagement"], reverse=True)
        best[username] = posts[0]
        best[username]["total_posts_found"] = len(posts)

    return best


def score_creator(post: dict, profile: dict) -> float:
    """Score a creator 0-100 based on discovery criteria."""
    score = 0.0
    followers = profile.get("followers", 0) if profile else 0
    bio = (profile.get("bio", "") or "").lower() if profile else ""

    # Followers range (15%)
    if 1000 <= followers <= 500000:
        if 5000 <= followers <= 100000:
            score += 15  # sweet spot: micro-influencer
        elif 1000 <= followers < 5000:
            score += 10  # nano
        else:
            score += 8   # macro

    # Engagement rate (20%)
    engagement = post.get("engagement", 0)
    if followers > 0:
        er = engagement / followers
        if er >= 0.05:
            score += 20
        elif er >= 0.03:
            score += 15
        elif er >= 0.01:
            score += 10
        else:
            score += 5

    # Content relevance — hashtag tier (30%)
    tag = post.get("hashtag_source", "")
    if tag in [h for h in HASHTAGS_TIER1]:
        score += 30  # product-related = highest
    elif tag in [h for h in HASHTAGS_TIER2]:
        score += 20  # category
    else:
        score += 10  # lifestyle

    # Bio relevance (10%)
    bio_keywords = ["ママ", "育児", "子育て", "赤ちゃん", "ベビー", "離乳食",
                     "mom", "baby", "mama", "主婦", "2児", "1児", "男の子", "女の子"]
    bio_hits = sum(1 for kw in bio_keywords if kw in bio)
    score += min(10, bio_hits * 3)

    # Video content bonus (10%)
    media_type = str(post.get("media_type", "")).lower()
    if "video" in media_type or "reel" in media_type:
        score += 10
    elif post.get("views", 0) > 0:
        score += 10  # has views = video

    # Posting activity (5%)
    posts_count = profile.get("posts_count", 0) if profile else 0
    if posts_count >= 100:
        score += 5
    elif posts_count >= 30:
        score += 3

    return round(score, 1)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_results(creators: list, limit: int = 30):
    """Pretty print discovery results."""
    print(f"\n{'='*80}")
    print(f"  JP AMBASSADOR DISCOVERY RESULTS — {TODAY}")
    print(f"  Found {len(creators)} new potential creators")
    print(f"{'='*80}\n")

    for i, c in enumerate(creators[:limit], 1):
        profile = c.get("profile", {})
        followers = profile.get("followers", 0)
        bio = (profile.get("bio", "") or "")[:60]
        print(f"  {i:2d}. @{c['username']:<25s} | score={c['score']:5.1f} | "
              f"followers={followers:>7,} | ER={c.get('engagement_rate', 0):.1%}")
        print(f"      hashtag=#{c['hashtag_source']:<15s} | "
              f"likes={c['likes']:>5,} comments={c['comments']:>3,} views={c['views']:>7,}")
        if bio:
            print(f"      bio: {bio}")
        print(f"      {c.get('url', '')}")
        print()


def save_results(creators: list):
    """Save results to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CACHE_DIR / f"discovery_{TODAY}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(creators, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] Results saved to {out_path}")
    return out_path


def _fix_timestamp(ts: str) -> str:
    """Convert ISO timestamp to YYYY-MM-DD for PG compatibility."""
    if not ts:
        return TODAY
    ts = str(ts)
    # Handle ISO format: 2026-04-06T10:59:20.000Z
    if "T" in ts:
        return ts.split("T")[0]
    # Handle unix timestamp
    if ts.isdigit() and len(ts) >= 10:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    return ts[:10] if len(ts) >= 10 else TODAY


def push_to_pg(creators: list):
    """Push discovered creators to gk_content_posts + onz_pipeline_creators."""
    # 1) Push posts to gk_content_posts
    try:
        from push_content_to_pg import push_posts
        posts = []
        for c in creators:
            posts.append({
                "post_id": c.get("shortcode", ""),
                "url": c.get("url", ""),
                "username": c.get("username", ""),
                "platform": "instagram",
                "region": "jp",
                "source": "ambassador_discovery",
                "caption": (c.get("caption", "") or "")[:2000],
                "likes": max(0, c.get("likes", 0)),
                "comments": max(0, c.get("comments", 0)),
                "views": max(0, c.get("views", 0)),
                "post_date": _fix_timestamp(c.get("timestamp", "")),
                "followers": c.get("profile", {}).get("followers", 0),
            })
        if posts:
            result = push_posts(posts)
            print(f"[PG] Pushed {len(posts)} discovery posts: {result}")
    except Exception as e:
        print(f"[PG WARN] Post push failed: {e}")

    # 2) Register to CRM pipeline via import-discovery endpoint
    # This reads gk_content_posts and creates missing pipeline_creators
    try:
        import requests
        load_env()
        ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
        ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "")

        payload = {
            "region": "jp",
            "source": "ambassador_discovery",
            "days": 90,
            "limit": len(creators),
        }
        resp = requests.post(
            "https://orbitools.orbiters.co.kr/api/onzenna/pipeline/creators/import-discovery/",
            json=payload,
            auth=(ORBITOOLS_USER, ORBITOOLS_PASS),
            timeout=30,
        )
        if resp.ok:
            r = resp.json()
            print(f"[CRM] Pipeline creators: +{r.get('created',0)} new, "
                  f"skipped={r.get('skipped',0)}")
        else:
            print(f"[CRM WARN] {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[CRM WARN] Pipeline import failed: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="JP Ambassador Discovery via IG Hashtags")
    parser.add_argument("--tier", default="1", choices=["1", "2", "3", "all"],
                        help="Hashtag tier to search (1=product, 2=category, 3=lifestyle, all)")
    parser.add_argument("--max-per-hashtag", type=int, default=30,
                        help="Max posts per hashtag (default: 30)")
    parser.add_argument("--min-followers", type=int, default=1000)
    parser.add_argument("--max-followers", type=int, default=500000)
    parser.add_argument("--top", type=int, default=30, help="Show top N results")
    parser.add_argument("--dry-run", action="store_true", help="Use cached data")
    parser.add_argument("--no-push", action="store_true", help="Don't push to PG")
    parser.add_argument("--no-profile", action="store_true", help="Skip profile lookup (faster)")
    args = parser.parse_args()

    # Select hashtags by tier
    hashtags = []
    if args.tier in ("1", "all"):
        hashtags.extend(HASHTAGS_TIER1)
    if args.tier in ("2", "all"):
        hashtags.extend(HASHTAGS_TIER2)
    if args.tier in ("3", "all"):
        hashtags.extend(HASHTAGS_TIER3)

    print(f"[CONFIG] tier={args.tier}, hashtags={len(hashtags)}, max/tag={args.max_per_hashtag}")
    print(f"[CONFIG] followers: {args.min_followers:,} ~ {args.max_followers:,}")
    print(f"[CONFIG] hashtags: {', '.join(f'#{h}' for h in hashtags)}")
    print()

    # Step 1: Fetch hashtag posts
    if args.dry_run:
        cache_path = CACHE_DIR / f"raw_{TODAY}.json"
        if cache_path.exists():
            raw_posts = json.loads(cache_path.read_text(encoding="utf-8"))
            print(f"[DRY] Loaded {len(raw_posts)} cached posts")
        else:
            print(f"[DRY] No cache at {cache_path}")
            return
    else:
        client = get_client()
        raw_posts = fetch_hashtag_posts(client, hashtags, args.max_per_hashtag)
        # Cache raw
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_DIR / f"raw_{TODAY}.json", "w", encoding="utf-8") as f:
            json.dump(raw_posts, f, ensure_ascii=False, indent=2)
        print(f"\n[TOTAL] {len(raw_posts)} raw posts from {len(hashtags)} hashtags")

    # Step 2: Get existing creators to exclude
    existing = get_existing_creators()

    # Step 3: Filter & dedupe
    best_posts = filter_and_dedupe(raw_posts, existing)
    print(f"[FILTER] {len(best_posts)} unique new creators after filtering")

    if not best_posts:
        print("[DONE] No new creators found")
        return

    # Step 4: Fetch profiles (optional)
    profiles = {}
    if not args.no_profile and not args.dry_run:
        usernames = list(best_posts.keys())[:100]  # cap at 100
        profiles = fetch_profiles(client, usernames)

    # Step 5: Score & rank
    results = []
    for username, post in best_posts.items():
        profile = profiles.get(username.lower(), {})
        followers = profile.get("followers", 0)

        # Filter by follower range
        if profile and (followers < args.min_followers or followers > args.max_followers):
            continue

        s = score_creator(post, profile)
        er = post["engagement"] / followers if followers > 0 else 0

        results.append({
            "username": username,
            "score": s,
            "shortcode": post["shortcode"],
            "url": post["url"],
            "caption": post["caption"],
            "likes": post["likes"],
            "comments": post["comments"],
            "views": post["views"],
            "engagement": post["engagement"],
            "engagement_rate": round(er, 4),
            "media_type": post["media_type"],
            "timestamp": post["timestamp"],
            "hashtag_source": post["hashtag_source"],
            "total_posts_found": post["total_posts_found"],
            "profile": profile,
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    # Step 6: Output
    print_results(results, args.top)
    out_path = save_results(results)

    # Step 7: Push to PG
    if not args.no_push and results:
        push_to_pg(results)

    print(f"\n[DONE] {len(results)} creators discovered, top {min(args.top, len(results))} shown")
    return results


if __name__ == "__main__":
    main()
