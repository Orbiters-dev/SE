#!/usr/bin/env python3
"""
Weekly JP Reels Scraper — IG + TikTok combined
===============================================
DB에서 JP 크리에이터 목록 → IG reel-scraper + TikTok hashtag scraper
→ 5K+ views 필터 → gk_content_posts에 저장

Target: ~200 reels/week

Usage:
  python tools/weekly_reels_scraper.py                    # full run
  python tools/weekly_reels_scraper.py --platform ig      # IG only
  python tools/weekly_reels_scraper.py --platform tiktok  # TikTok only
  python tools/weekly_reels_scraper.py --min-views 10000  # higher threshold
  python tools/weekly_reels_scraper.py --dry-run           # no DB push
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

CACHE_DIR = PROJECT_ROOT / ".tmp" / "weekly_reels"
TODAY = datetime.now().strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Apify actors
# ---------------------------------------------------------------------------
IG_REEL_SCRAPER = "apify/instagram-reel-scraper"
IG_HASHTAG_SCRAPER = "apify/instagram-hashtag-scraper"
TT_HASHTAG_SCRAPER = "clockworks/free-tiktok-scraper"

# JP parenting hashtags for TikTok discovery
TIKTOK_HASHTAGS = [
    "育児",
    "赤ちゃん",
    "子育て",
    "離乳食",
    "育児ママ",
    "ベビー用品",
    "1歳",
    "2歳",
    "育児グッズ",
    "ベビーグッズ",
    "新米ママ",
    "ママライフ",
]

# Brand/store accounts to skip
EXCLUDE_ACCOUNTS = {
    "onzenna.official", "grosmimi_usa", "grosmimi_japan", "grosmimi_official",
    "grosmimi_korea", "onzenna", "grosmimi", "zezebaebae",
    "grosmimithailand", "grosmimi_thailand",
}


def get_client():
    load_env()
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("[ERROR] APIFY_API_TOKEN not found")
        sys.exit(1)
    from apify_client import ApifyClient
    return ApifyClient(token)


# ---------------------------------------------------------------------------
# Step 1: Get JP creator usernames from DB
# ---------------------------------------------------------------------------
def get_jp_creators_from_db(min_followers=3000):
    """Get JP creator usernames from gk_content_posts."""
    creators = []
    try:
        DB_HOST = os.getenv("DB_HOST", "172.31.13.240")
        DB_NAME = os.getenv("DB_NAME", "export_calculator_db")
        DB_USER = os.getenv("DB_USER", "es_db_user")
        DB_PASS = os.getenv("DB_PASSWORD", "orbit1234")

        import psycopg2
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT username, MAX(followers) as max_f, COUNT(*) as cnt
            FROM gk_content_posts
            WHERE region = 'jp' AND username != '' AND username IS NOT NULL
            GROUP BY username
            HAVING MAX(followers) >= %s OR MAX(views_30d) >= 5000
            ORDER BY MAX(followers) DESC NULLS LAST
        """, (min_followers,))
        for row in cur.fetchall():
            creators.append({"username": row[0], "followers": row[1] or 0, "posts": row[2]})
        conn.close()
        print(f"[DB] Found {len(creators)} JP creators (followers >= {min_followers:,})")
    except Exception as e:
        print(f"[DB WARN] {e}")
    return creators


def get_existing_urls_from_db():
    """Get existing post URLs to avoid duplicates."""
    urls = set()
    try:
        DB_HOST = os.getenv("DB_HOST", "172.31.13.240")
        DB_NAME = os.getenv("DB_NAME", "export_calculator_db")
        DB_USER = os.getenv("DB_USER", "es_db_user")
        DB_PASS = os.getenv("DB_PASSWORD", "orbit1234")

        import psycopg2
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()
        cur.execute("""
            SELECT url FROM gk_content_posts
            WHERE region = 'jp' AND source IN ('reel_scraper', 'tiktok_scraper')
        """)
        for row in cur.fetchall():
            if row[0]:
                urls.add(row[0])
        conn.close()
    except Exception:
        pass
    return urls


# ---------------------------------------------------------------------------
# Step 2: IG Reel Scraper (profile-based)
# ---------------------------------------------------------------------------
def scrape_ig_reels(client, creators, min_views=5000, max_per_creator=10):
    """Fetch reels from known JP creators via IG reel-scraper."""
    usernames = [c["username"] for c in creators if c["username"].lower() not in EXCLUDE_ACCOUNTS]
    print(f"\n[IG REELS] Scraping {len(usernames)} creators (max {max_per_creator}/each)...")

    all_reels = []
    one_week_ago = datetime.now() - timedelta(days=7)

    # Batch in chunks of 5
    for i in range(0, len(usernames), 5):
        chunk = usernames[i:i+5]
        print(f"  Batch {i//5+1}: {', '.join(f'@{u}' for u in chunk)}")
        try:
            run = client.actor(IG_REEL_SCRAPER).call(
                run_input={"username": chunk, "resultsLimit": max_per_creator},
                timeout_secs=300,
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            for item in items:
                username = item.get("ownerUsername", "") or ""
                views = (item.get("videoPlayCount", 0) or item.get("videoViewCount", 0)
                         or item.get("video_play_count", 0) or 0)
                if views < min_views:
                    continue

                likes = item.get("likesCount", 0) or 0
                comments = item.get("commentsCount", 0) or 0
                caption = (item.get("caption", "") or "")[:500]
                shortcode = item.get("shortCode", "") or ""
                taken = (item.get("timestamp", "") or "")[:10]
                post_url = f"https://www.instagram.com/reel/{shortcode}/" if shortcode else ""

                # Date filter: last 7 days for weekly
                try:
                    post_date = datetime.strptime(taken, "%Y-%m-%d")
                    if post_date < one_week_ago:
                        continue
                except ValueError:
                    pass

                all_reels.append({
                    "platform": "instagram",
                    "username": username,
                    "shortcode": shortcode,
                    "post_url": post_url,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "caption": caption,
                    "date": taken,
                    "source": "reel_scraper",
                })

            print(f"    → {len(items)} reels fetched")
        except Exception as e:
            print(f"    FAIL: {e}")

        time.sleep(2)

    print(f"[IG REELS] {len(all_reels)} reels with {min_views:,}+ views (last 7d)")
    return all_reels


# ---------------------------------------------------------------------------
# Step 3: TikTok Hashtag Scraper
# ---------------------------------------------------------------------------
def scrape_tiktok_hashtags(client, hashtags=None, min_views=5000, max_per_hashtag=30):
    """Fetch TikTok videos from JP parenting hashtags."""
    hashtags = hashtags or TIKTOK_HASHTAGS
    print(f"\n[TIKTOK] Scraping {len(hashtags)} hashtags (max {max_per_hashtag}/each)...")

    all_videos = []
    one_week_ago = datetime.now() - timedelta(days=7)

    for tag in hashtags:
        print(f"  #{tag}...")
        try:
            run = client.actor(TT_HASHTAG_SCRAPER).call(
                run_input={
                    "hashtags": [tag],
                    "resultsPerPage": max_per_hashtag,
                    "shouldDownloadVideos": False,
                },
                timeout_secs=180,
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            found = 0
            for item in items:
                views = item.get("playCount", 0) or 0
                if views < min_views:
                    continue

                author_meta = item.get("authorMeta", {})
                if isinstance(author_meta, str):
                    try:
                        author_meta = json.loads(author_meta.replace("'", '"'))
                    except Exception:
                        author_meta = {}

                username = author_meta.get("name", "") or ""
                if not username:
                    continue

                likes = item.get("diggCount", 0) or 0
                comments = item.get("commentCount", 0) or 0
                caption = (item.get("text", "") or "")[:500]
                video_id = item.get("id", "")
                web_url = item.get("webVideoUrl", "") or ""
                create_time = item.get("createTimeISO", "") or ""
                taken = create_time[:10] if create_time else ""

                # Date filter: last 7 days
                try:
                    post_date = datetime.strptime(taken, "%Y-%m-%d")
                    if post_date < one_week_ago:
                        continue
                except ValueError:
                    pass

                # JP content check (Japanese chars in caption)
                has_jp = any(ord(c) > 0x3000 and ord(c) < 0x9FFF for c in caption[:200])
                if not has_jp:
                    continue

                all_videos.append({
                    "platform": "tiktok",
                    "username": username,
                    "shortcode": video_id,
                    "post_url": web_url,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "caption": caption,
                    "date": taken,
                    "source": "tiktok_scraper",
                    "hashtag": tag,
                })
                found += 1

            print(f"    → {len(items)} videos, {found} passed filter")
        except Exception as e:
            print(f"    FAIL: {e}")

        time.sleep(2)

    # Dedupe by post_url
    seen_urls = set()
    deduped = []
    for v in all_videos:
        if v["post_url"] and v["post_url"] not in seen_urls:
            seen_urls.add(v["post_url"])
            deduped.append(v)

    print(f"[TIKTOK] {len(deduped)} unique videos with {min_views:,}+ views (last 7d, JP content)")
    return deduped


# ---------------------------------------------------------------------------
# Step 4: Push to DB
# ---------------------------------------------------------------------------
def push_to_db(reels, existing_urls):
    """Push reels/videos to gk_content_posts."""
    new_reels = [r for r in reels if r["post_url"] not in existing_urls]
    if not new_reels:
        print("[DB] No new reels to insert")
        return 0

    try:
        DB_HOST = os.getenv("DB_HOST", "172.31.13.240")
        DB_NAME = os.getenv("DB_NAME", "export_calculator_db")
        DB_USER = os.getenv("DB_USER", "es_db_user")
        DB_PASS = os.getenv("DB_PASSWORD", "orbit1234")

        import psycopg2
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()

        inserted = 0
        for r in new_reels:
            try:
                cur.execute("""
                    INSERT INTO gk_content_posts
                    (post_id, url, platform, username, caption, post_date, region, source,
                     collected_at, views_30d, likes_30d, comments_30d, videos_30d,
                     bio_text, text, transcript, product_types)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    r["shortcode"],
                    r["post_url"],
                    r["platform"],
                    r["username"],
                    r["caption"],
                    r["date"] if r["date"] else None,
                    "jp",
                    r["source"],
                    datetime.now().isoformat(),
                    r["views"],
                    r["likes"],
                    r["comments"],
                    0,   # videos_30d
                    "",  # bio_text
                    "",  # text
                    "",  # transcript — CI will fill
                    "",  # product_types
                ))
                inserted += 1
            except Exception as e:
                print(f"  ! @{r['username']} | ERROR: {e}")
                conn.rollback()
                conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
                cur = conn.cursor()

        conn.commit()
        cur.close()
        conn.close()
        print(f"[DB] Inserted {inserted} new reels/videos")
        return inserted
    except Exception as e:
        print(f"[DB ERROR] {e}")
        return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Weekly JP Reels Scraper (IG + TikTok)")
    parser.add_argument("--platform", default="all", choices=["all", "ig", "tiktok"])
    parser.add_argument("--min-views", type=int, default=5000)
    parser.add_argument("--min-followers", type=int, default=3000)
    parser.add_argument("--max-per-creator", type=int, default=10, help="Max reels per IG creator")
    parser.add_argument("--max-per-hashtag", type=int, default=30, help="Max videos per TT hashtag")
    parser.add_argument("--dry-run", action="store_true", help="Don't push to DB")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  Weekly JP Reels Scraper — {TODAY}")
    print(f"  Platform: {args.platform} | Min views: {args.min_views:,}")
    print(f"{'='*60}\n")

    load_env()
    client = get_client()
    all_results = []

    # IG Reels
    if args.platform in ("all", "ig"):
        creators = get_jp_creators_from_db(args.min_followers)
        if creators:
            ig_reels = scrape_ig_reels(client, creators, args.min_views, args.max_per_creator)
            all_results.extend(ig_reels)

    # TikTok
    if args.platform in ("all", "tiktok"):
        tt_videos = scrape_tiktok_hashtags(client, TIKTOK_HASHTAGS, args.min_views, args.max_per_hashtag)
        all_results.extend(tt_videos)

    # Summary
    ig_count = sum(1 for r in all_results if r["platform"] == "instagram")
    tt_count = sum(1 for r in all_results if r["platform"] == "tiktok")
    print(f"\n{'='*60}")
    print(f"  TOTAL: {len(all_results)} reels/videos")
    print(f"  IG: {ig_count} | TikTok: {tt_count}")
    print(f"{'='*60}")

    # Top results
    all_results.sort(key=lambda x: x["views"], reverse=True)
    print(f"\nTop 20 by views:")
    for r in all_results[:20]:
        icon = "IG" if r["platform"] == "instagram" else "TT"
        print(f"  [{icon}] @{r['username']:20s} | views={r['views']:>12,} | {r['date']} | {r['caption'][:40]}...")

    # Cache results
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"reels_{TODAY}.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nCached to {cache_path}")

    # Push to DB
    if not args.dry_run and all_results:
        existing_urls = get_existing_urls_from_db()
        pushed = push_to_db(all_results, existing_urls)
        print(f"[FINAL] {pushed} new entries pushed to gk_content_posts")
    elif args.dry_run:
        print("[DRY RUN] Skipping DB push")

    return all_results


if __name__ == "__main__":
    main()
