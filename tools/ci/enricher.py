"""
CI Enricher — Fetch additional creator/content signals via Apify + GPT
======================================================================
Provides enrichment data for score_calculator v2:
  - Comment text scraping + quality classification (GPT)
  - Profile metadata (followers, posts count, bio)
  - Recent post history (posting frequency, collab detection)
  - Multi-platform detection

Enrichment cache: .tmp/ci_enrichment_cache.json
"""

import os, sys, json, re, time
from pathlib import Path

DIR = Path(__file__).resolve().parent
TOOLS_DIR = DIR.parent
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

CACHE_PATH = PROJECT_ROOT / ".tmp" / "ci_enrichment_cache.json"
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Apify actors
IG_COMMENT_SCRAPER = "apify/instagram-comment-scraper"
IG_PROFILE_SCRAPER = "apify/instagram-profile-scraper"
IG_POST_SCRAPER = "apify/instagram-scraper"
TT_SCRAPER = "GdWCkxBtKWOsKjdch"  # TikTok profile + posts (same as ViralLens)
TT_COMMENT_SCRAPER = "clockworks/tiktok-comments-scraper"

# Collab detection patterns in captions
COLLAB_PATTERNS = re.compile(
    r'#(?:ad|sponsored|gifted|collab|partnership|paid|ambassador|brandpartner|供給|PR|pr)\b'
    r'|(?:paid\s+partner|sponsored\s+by|gifted\s+by|in\s+collaboration\s+with)',
    re.IGNORECASE
)


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _apify_run(actor_id: str, run_input: dict, timeout_secs: int = 300) -> list:
    """Run an Apify actor and return dataset items."""
    import requests
    if not APIFY_TOKEN:
        print(f"  [enricher] APIFY_API_TOKEN not set, skipping {actor_id}")
        return []

    url = f"https://api.apify.com/v2/acts/{actor_id}/runs"
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}", "Content-Type": "application/json"}

    resp = requests.post(url, json=run_input, headers=headers, timeout=30)
    resp.raise_for_status()
    run_data = resp.json()["data"]
    run_id = run_data["id"]
    dataset_id = run_data.get("defaultDatasetId")

    # Poll for completion
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
    start = time.time()
    while time.time() - start < timeout_secs:
        time.sleep(5)
        sr = requests.get(status_url, headers=headers, timeout=15)
        status = sr.json()["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        print(f"  [enricher] {actor_id} run {run_id} ended with {status}")
        return []

    # Fetch results
    if not dataset_id:
        dataset_id = run_data.get("defaultDatasetId")
    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?format=json"
    items_resp = requests.get(items_url, headers=headers, timeout=60)
    return items_resp.json() if items_resp.ok else []


def fetch_ig_comments(post_url: str, max_comments: int = 50) -> list:
    """Fetch comments for an IG post via Apify. Returns list of comment dicts."""
    items = _apify_run(IG_COMMENT_SCRAPER, {
        "directUrls": [post_url],
        "resultsLimit": max_comments,
    })
    comments = []
    for item in items:
        text = item.get("text", "")
        if text:
            comments.append({
                "text": text,
                "username": item.get("ownerUsername", ""),
                "likes": item.get("likesCount", 0),
                "timestamp": item.get("timestamp", ""),
            })
    return comments


def fetch_ig_profile(username: str) -> dict:
    """Fetch IG profile metadata. Returns followers, posts count, bio etc."""
    items = _apify_run(IG_PROFILE_SCRAPER, {
        "usernames": [username],
    }, timeout_secs=120)

    if not items:
        return {}

    p = items[0]
    return {
        "followers": p.get("followersCount", 0),
        "following": p.get("followsCount", 0),
        "posts_count": p.get("postsCount", 0),
        "bio": p.get("biography", ""),
        "is_verified": p.get("verified", False),
        "is_business": p.get("isBusinessAccount", False),
        "external_url": p.get("externalUrl", ""),
    }


def fetch_ig_recent_posts(username: str, limit: int = 30) -> list:
    """Fetch recent posts for posting frequency + collab detection."""
    items = _apify_run(IG_POST_SCRAPER, {
        "usernames": [username],
        "resultsLimit": limit,
        "resultsType": "posts",
    }, timeout_secs=180)

    posts = []
    for item in items:
        caption = item.get("caption", "") or ""
        posts.append({
            "url": item.get("url", ""),
            "timestamp": item.get("timestamp", ""),
            "likes": item.get("likesCount", 0),
            "comments": item.get("commentsCount", 0),
            "views": item.get("videoViewCount") or item.get("videoPlayCount") or 0,
            "caption": caption,
            "is_video": item.get("type") == "Video",
            "is_collab": bool(COLLAB_PATTERNS.search(caption)),
            "duration": item.get("videoDuration", 0),
        })
    return posts


def fetch_tt_profile(username: str) -> dict:
    """Fetch TikTok profile metadata via Apify."""
    items = _apify_run(TT_SCRAPER, {
        "profiles": [username],
        "resultsPerPage": 0,  # profile only, no posts
    }, timeout_secs=120)

    if not items:
        return {}

    p = items[0]
    return {
        "followers": p.get("authorMeta", {}).get("fans", 0) or p.get("fans", 0),
        "following": p.get("authorMeta", {}).get("following", 0) or p.get("following", 0),
        "posts_count": p.get("authorMeta", {}).get("video", 0) or p.get("videoCount", 0),
        "bio": p.get("authorMeta", {}).get("signature", "") or p.get("signature", ""),
        "is_verified": p.get("authorMeta", {}).get("verified", False) or p.get("verified", False),
        "likes_total": p.get("authorMeta", {}).get("heart", 0) or p.get("hearts", 0),
    }


def fetch_tt_recent_posts(username: str, limit: int = 30) -> list:
    """Fetch recent TikTok posts for frequency + collab detection."""
    items = _apify_run(TT_SCRAPER, {
        "profiles": [username],
        "resultsPerPage": limit,
    }, timeout_secs=180)

    posts = []
    for item in items:
        caption = item.get("text", "") or item.get("desc", "") or ""
        posts.append({
            "url": item.get("webVideoUrl", "") or item.get("url", ""),
            "timestamp": item.get("createTimeISO", "") or item.get("createTime", ""),
            "likes": item.get("diggCount", 0) or item.get("likes", 0),
            "comments": item.get("commentCount", 0) or item.get("comments", 0),
            "views": item.get("playCount", 0) or item.get("plays", 0),
            "caption": caption,
            "is_video": True,
            "is_collab": bool(COLLAB_PATTERNS.search(caption)),
            "duration": item.get("videoMeta", {}).get("duration", 0) or item.get("duration", 0),
        })
    return posts


def fetch_tt_comments(post_url: str, max_comments: int = 50) -> list:
    """Fetch comments for a TikTok post via Apify."""
    items = _apify_run(TT_COMMENT_SCRAPER, {
        "postURLs": [post_url],
        "maxComments": max_comments,
    }, timeout_secs=120)

    comments = []
    for item in items:
        text = item.get("text", "") or item.get("comment", "")
        if text:
            comments.append({
                "text": text,
                "username": item.get("uniqueId", "") or item.get("user", {}).get("uniqueId", ""),
                "likes": item.get("diggCount", 0) or item.get("likes", 0),
                "timestamp": item.get("createTimeISO", ""),
            })
    return comments


def classify_comments_gpt(comments: list) -> dict:
    """Use GPT-4o-mini to classify comments as meaningful/bot/emoji-only.

    Returns:
        {"meaningful": int, "bot": int, "emoji_only": int, "total": int}
    """
    if not comments or not OPENAI_KEY:
        return {"meaningful": 0, "bot": 0, "emoji_only": 0, "total": len(comments or [])}

    import requests

    # Batch comments into a single prompt
    comment_texts = [c["text"][:100] for c in comments[:50]]  # cap at 50
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(comment_texts))

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": (
                    "Classify each comment as: meaningful (real engagement, >3 words, "
                    "asks question or shares experience), emoji_only (just emojis/tags), "
                    "or bot (generic spam, 'nice pic', single word). "
                    "Return JSON: {\"meaningful\": count, \"emoji_only\": count, \"bot\": count}"
                )},
                {"role": "user", "content": numbered},
            ],
            "max_tokens": 100,
        },
        timeout=30,
    )

    if not resp.ok:
        return {"meaningful": 0, "bot": 0, "emoji_only": 0, "total": len(comment_texts)}

    try:
        result = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(result)
        parsed["total"] = len(comment_texts)
        return parsed
    except Exception:
        return {"meaningful": 0, "bot": 0, "emoji_only": 0, "total": len(comment_texts)}


def detect_collab_in_captions(posts: list) -> dict:
    """Count #ad/#sponsored/#gifted in recent post captions."""
    total = len(posts)
    sponsored = sum(1 for p in posts if p.get("is_collab"))
    return {"sponsored_count": sponsored, "total_posts_checked": total}


def calc_posting_stats(posts: list) -> dict:
    """Calculate posting frequency from recent posts timestamps."""
    if not posts:
        return {"posts_last_30d": 0}

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    count_30d = 0
    for p in posts:
        ts = p.get("timestamp", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt >= cutoff:
                count_30d += 1
        except (ValueError, TypeError):
            continue

    return {"posts_last_30d": count_30d}


def detect_platforms(username: str, posts_data: dict = None) -> list:
    """Detect which platforms a creator is active on.
    Basic: check if we have IG data + search for TikTok handle match in cache.
    """
    platforms = []
    if posts_data and posts_data.get("ig_posts"):
        platforms.append("instagram")
    if posts_data and posts_data.get("tt_posts"):
        platforms.append("tiktok")
    # Could extend with YouTube, Twitter checks later
    return platforms or ["instagram"]  # default assumption


def enrich_creator(username: str, post_url: str = None,
                   platform: str = "instagram",
                   use_cache: bool = True) -> dict:
    """
    Full enrichment for one creator + one post.
    Returns dict ready for calculate_scores_v2(enrichment=...).

    Fetches:
    1. Profile metadata (followers, posts count)
    2. Recent posts (frequency, collab detection, avg engagement)
    3. Comments on target post (quality classification)
    4. Duration from recent posts data
    """
    cache = _load_cache() if use_cache else {}
    cache_key = f"{username}_{platform}"

    # Check if already enriched recently (within 7 days)
    if use_cache and cache_key in cache:
        cached = cache[cache_key]
        cached_ts = cached.get("_enriched_at", "")
        if cached_ts:
            from datetime import datetime, timedelta
            try:
                dt = datetime.fromisoformat(cached_ts)
                if (datetime.now() - dt).days < 7:
                    print(f"  [enricher] cache hit for {username} ({platform})")
                    return cached
            except Exception:
                pass

    print(f"  [enricher] enriching {username} ({platform})...")
    result = {}

    if platform == "instagram":
        # 1. Profile
        profile = fetch_ig_profile(username)
        result["followers"] = profile.get("followers", 0)
        result["posts_count"] = profile.get("posts_count", 0)
        result["bio"] = profile.get("bio", "")

        # 2. Recent posts
        recent = fetch_ig_recent_posts(username, limit=30)
        if recent:
            # Posting frequency
            freq = calc_posting_stats(recent)
            result["posts_last_30d"] = freq["posts_last_30d"]

            # Collab detection
            collab = detect_collab_in_captions(recent)
            result["sponsored_count"] = collab["sponsored_count"]
            result["total_posts_checked"] = collab["total_posts_checked"]

            # Avg engagement (for bot detection)
            avg_likes = sum(p.get("likes", 0) for p in recent) / len(recent)
            avg_comments = sum(p.get("comments", 0) for p in recent) / len(recent)
            result["avg_likes"] = round(avg_likes, 1)
            result["avg_comments"] = round(avg_comments, 1)

            # Duration from target post or first video
            for p in recent:
                if post_url and p.get("url") and post_url in p["url"]:
                    result["duration_seconds"] = p.get("duration", 0)
                    break
            if "duration_seconds" not in result:
                videos = [p for p in recent if p.get("is_video") and p.get("duration")]
                if videos:
                    result["duration_seconds"] = videos[0]["duration"]

            # Platforms
            result["platforms"] = ["instagram"]

        # 3. Comments on target post
        if post_url:
            raw_comments = fetch_ig_comments(post_url, max_comments=50)
            if raw_comments:
                classified = classify_comments_gpt(raw_comments)
                result["total_comments"] = classified.get("total", 0)
                result["meaningful_comments"] = classified.get("meaningful", 0)
                result["bot_comments"] = classified.get("bot", 0)

    else:
        # TikTok enrichment
        # 1. Profile
        profile = fetch_tt_profile(username)
        result["followers"] = profile.get("followers", 0)
        result["posts_count"] = profile.get("posts_count", 0)
        result["bio"] = profile.get("bio", "")
        result["likes_total"] = profile.get("likes_total", 0)

        # 2. Recent posts
        recent = fetch_tt_recent_posts(username, limit=30)
        if recent:
            freq = calc_posting_stats(recent)
            result["posts_last_30d"] = freq["posts_last_30d"]

            collab = detect_collab_in_captions(recent)
            result["sponsored_count"] = collab["sponsored_count"]
            result["total_posts_checked"] = collab["total_posts_checked"]

            avg_likes = sum(p.get("likes", 0) for p in recent) / len(recent)
            avg_comments = sum(p.get("comments", 0) for p in recent) / len(recent)
            result["avg_likes"] = round(avg_likes, 1)
            result["avg_comments"] = round(avg_comments, 1)

            # Duration from target post or first video
            for p in recent:
                if post_url and p.get("url") and post_url in p["url"]:
                    result["duration_seconds"] = p.get("duration", 0)
                    break
            if "duration_seconds" not in result:
                videos = [p for p in recent if p.get("duration")]
                if videos:
                    result["duration_seconds"] = videos[0]["duration"]

        result["platforms"] = ["tiktok"]

        # 3. Comments on target post
        if post_url:
            raw_comments = fetch_tt_comments(post_url, max_comments=50)
            if raw_comments:
                classified = classify_comments_gpt(raw_comments)
                result["total_comments"] = classified.get("total", 0)
                result["meaningful_comments"] = classified.get("meaningful", 0)
                result["bot_comments"] = classified.get("bot", 0)

    # Timestamp
    from datetime import datetime
    result["_enriched_at"] = datetime.now().isoformat()

    # Save to cache
    cache[cache_key] = result
    _save_cache(cache)

    return result


def enrich_batch(creators: list, use_cache: bool = True) -> dict:
    """
    Enrich a batch of creators.

    Args:
        creators: list of dicts with keys: username, post_url, platform
        use_cache: use cached results if fresh

    Returns:
        dict keyed by username → enrichment data
    """
    results = {}
    total = len(creators)

    for i, c in enumerate(creators, 1):
        username = c.get("username", "")
        post_url = c.get("post_url", "")
        platform = c.get("platform", "instagram")

        print(f"  [{i}/{total}] {username}...")
        try:
            data = enrich_creator(username, post_url, platform, use_cache)
            results[username] = data
        except Exception as e:
            print(f"    ERROR: {e}")
            results[username] = {"_error": str(e)}

        # Rate limit: 1 second between creators
        if i < total:
            time.sleep(1)

    print(f"  [enricher] Done: {len(results)} creators enriched")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CI Enricher — fetch creator signals via Apify")
    parser.add_argument("--username", help="Single username to enrich")
    parser.add_argument("--post-url", help="Target post URL")
    parser.add_argument("--platform", default="instagram")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    if args.username:
        result = enrich_creator(args.username, args.post_url, args.platform, not args.no_cache)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Usage: python ci/enricher.py --username <handle> [--post-url <url>]")
