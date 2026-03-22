"""Load Syncly Output spreadsheet → gk_content_posts (DataKeeper PG).

Reads the latest Output_updated tab from the Syncly Discovery spreadsheet
and upserts into gk_content_posts with full transcript, text, bio, and 30d metrics.

Usage:
    python tools/load_syncly_output_to_pg.py              # full load
    python tools/load_syncly_output_to_pg.py --dry-run     # preview only
    python tools/load_syncly_output_to_pg.py --limit 100   # first 100 rows
    python tools/load_syncly_output_to_pg.py --tab Output_updated_260318  # specific tab
"""

import os, sys, argparse, json, time
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

try:
    from env_loader import load_env
    load_env()
except Exception:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(DIR), ".env"))
    except:
        pass

import gspread
from google.oauth2.service_account import Credentials

PROJECT_ROOT = os.path.dirname(DIR)
SYNCLY_SHEET_ID = "1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o"

# Column mapping (0-indexed)
COL = {
    "update_date": 0,       # A: 업데이트 일자
    "username": 6,          # G: Username (id)
    "profile_url": 7,       # H: Profile URL
    "level": 8,             # I: Level
    "summary": 16,          # Q: Summary
    "theme": 17,            # R: Theme
    "text": 18,             # S: Text (full)
    "transcript": 19,       # T: Transcript (full 대사)
    "caption": 20,          # U: Caption
    "post_date": 21,        # V: date
    "nickname": 22,         # W: Nickname
    "bio_text": 23,         # X: Bio_text
    "email": 24,            # Y: Email
    "platform": 26,         # AA: Platform
    "post_url": 15,         # P: Post URL
    "syncly_url": 14,       # O: Syncly URL
    "followers": 32,        # AG: Followers
    "avg_view": 33,         # AH: Average view
    "videos_30d": 38,       # AM: 최근 30일 Video 수
    "views_30d": 39,        # AN: 최근 30일 조회 수 총합
    "likes_30d": 40,        # AO: 최근 30일 좋아요 수 총합
    "comments_30d": 41,     # AP: 최근 30일 댓글 수 총합
    "hashtags": -1,         # Not in sheet, derive from caption
    "brand": -1,            # Detect from keywords/content
    "is_blacklist": 5,      # F: 블랙리스트 여부
    "is_official": 25,      # Z: is_official
}


def get_gc():
    creds = Credentials.from_service_account_file(
        os.path.join(PROJECT_ROOT, "credentials", "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


def safe_int(val, default=0):
    if not val:
        return default
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def detect_brand(text, username=""):
    """Detect brand from content text."""
    combined = (text or "").lower()
    if any(k in combined for k in ["grosmimi", "ppsu", "straw cup", "baby bottle", "그로미미"]):
        return "Grosmimi"
    if any(k in combined for k in ["cha&mom", "chaenmom", "차앤맘", "baby wash", "baby lotion"]):
        return "CHA&MOM"
    if any(k in combined for k in ["naeiae", "나이애", "rice puff", "baby snack", "pop rice"]):
        return "Naeiae"
    return ""


def extract_post_id(url):
    """Extract post ID from Instagram/TikTok URL."""
    if not url:
        return ""
    url = url.strip()
    # TikTok: /video/1234567890
    if "tiktok.com" in url:
        parts = url.split("/video/")
        if len(parts) > 1:
            return parts[1].split("/")[0].split("?")[0]
    # Instagram: /p/ABC123/ or /reel/ABC123/
    if "instagram.com" in url:
        for pattern in ["/p/", "/reel/", "/reels/"]:
            if pattern in url:
                parts = url.split(pattern)
                if len(parts) > 1:
                    return parts[1].strip("/").split("/")[0].split("?")[0]
    return url[-20:]  # fallback: last 20 chars


def load_and_push(args):
    gc = get_gc()
    sh = gc.open_by_key(SYNCLY_SHEET_ID)

    # Find target tab
    if args.tab:
        tab_name = args.tab
    else:
        output_tabs = [ws for ws in sh.worksheets() if ws.title.startswith("Output_updated")]
        if not output_tabs:
            print("No Output_updated tabs found!")
            return
        tab_name = sorted(output_tabs, key=lambda w: w.title)[-1].title

    print(f"Reading tab: {tab_name}")
    ws = sh.worksheet(tab_name)
    all_rows = ws.get_all_values()
    headers = all_rows[0]
    data_rows = all_rows[1:]

    print(f"  Total rows: {len(data_rows)}")
    if args.limit:
        data_rows = data_rows[:args.limit]
        print(f"  Limited to: {len(data_rows)}")

    # Parse rows
    posts = []
    skipped = {"blacklist": 0, "official": 0, "no_username": 0, "no_url": 0}

    for i, row in enumerate(data_rows):
        def col(key):
            idx = COL.get(key, -1)
            if idx < 0 or idx >= len(row):
                return ""
            return row[idx]

        username = col("username").strip().lstrip("@")
        if not username:
            skipped["no_username"] += 1
            continue

        # Skip blacklisted and official accounts
        if col("is_blacklist").upper() == "TRUE":
            skipped["blacklist"] += 1
            continue
        if col("is_official").upper() == "TRUE":
            skipped["official"] += 1
            continue

        post_url = col("post_url").strip()
        if not post_url:
            skipped["no_url"] += 1
            continue

        post_id = extract_post_id(post_url)
        if not post_id:
            post_id = f"syncly_{username}_{i}"

        platform = (col("platform") or "").strip().lower()
        if "tiktok" in platform or "tiktok" in post_url:
            platform = "tiktok"
        else:
            platform = "instagram"

        transcript = col("transcript")
        text = col("text")
        caption = col("caption")
        bio_text = col("bio_text")
        nickname = col("nickname")

        # Detect brand from all text
        all_text = " ".join([transcript or "", caption or "", text or ""])
        brand = detect_brand(all_text, username)

        # Parse date
        post_date_raw = col("post_date")
        try:
            if post_date_raw and len(post_date_raw) >= 10:
                post_date = post_date_raw[:10]
            else:
                post_date = col("update_date")[:10] if col("update_date") else datetime.now().strftime("%Y-%m-%d")
        except:
            post_date = datetime.now().strftime("%Y-%m-%d")

        post = {
            "post_id": post_id,
            "url": post_url,
            "platform": platform,
            "username": username,
            "nickname": nickname or "",
            "followers": safe_int(col("followers")),
            "caption": caption or "",
            "transcript": transcript or "",
            "text": text or "",
            "bio_text": bio_text or "",
            "hashtags": "",
            "tagged_account": "",
            "post_date": post_date,
            "brand": brand,
            "videos_30d": safe_int(col("videos_30d")),
            "views_30d": safe_int(col("views_30d")),
            "likes_30d": safe_int(col("likes_30d")),
            "comments_30d": safe_int(col("comments_30d")),
            "product_types": "",
            "region": "us",
            "source": "syncly_sheets",
        }
        posts.append(post)

    print(f"\n  Parsed: {len(posts)} posts")
    print(f"  Skipped: {json.dumps(skipped)}")

    if args.dry_run:
        print("\n[DRY RUN] Would push to PG:")
        for p in posts[:5]:
            print(f"  @{p['username']} | {p['platform']} | {p['post_date']} | transcript={len(p['transcript'])} chars | brand={p['brand']}")
        print(f"  ... and {len(posts) - 5} more")
        return

    # Push to PG via push_content_to_pg
    from push_content_to_pg import push_posts

    result = push_posts(posts)
    print(f"\n=== COMPLETE ===")
    print(f"  Created: {result.get('created', 0)}")
    print(f"  Updated: {result.get('updated', 0)}")
    print(f"  Errors: {result.get('errors', [])}")
    print(f"  Total in batch: {len(posts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Syncly Output → PG content_posts")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no push")
    parser.add_argument("--limit", type=int, default=0, help="Limit rows to process")
    parser.add_argument("--tab", type=str, default="", help="Specific tab name")
    args = parser.parse_args()
    load_and_push(args)
