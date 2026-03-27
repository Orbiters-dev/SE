"""One-time initial load: Apify Google Sheet -> PostgreSQL.

Reads existing Posts Master + D+60 Tracker data from Apify sheet
and pushes to gk_content_posts / gk_content_metrics_daily via orbitools API.

Usage:
    python tools/initial_load_content_to_pg.py              # full load (US + JP)
    python tools/initial_load_content_to_pg.py --region us  # US only
    python tools/initial_load_content_to_pg.py --dry-run    # preview only
"""

import os
import sys
import re
import argparse
from datetime import datetime, timedelta

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

import gspread
from google.oauth2.service_account import Credentials

from push_content_to_pg import push_posts, push_metrics


def detect_brand_from_text(hashtags, content, tagged_account):
    """Detect brand from hashtags + content + tagged account text."""
    text = f"{hashtags} {content} {tagged_account}".lower()
    if re.search(r'grosmimi|gros.?mimi|ppsu|straw.?cup|baby.?bottle|sippy|tumbler', text):
        return 'Grosmimi'
    if re.search(r'cha.?&.?mom|chaandmom|cha_mom|chamom|phytoseline|ps.?cream|baby.?lotion|baby.?cream|baby.?wash', text):
        return 'CHA&MOM'
    if re.search(r'naeiae|rice.?puff|rice.?snack|pop.?rice|baby.?snack', text):
        return 'Naeiae'
    if re.search(r'babyrabbit|baby.?rabbit', text):
        return 'Babyrabbit'
    if re.search(r'commemoi|book.?stand', text):
        return 'Commemoi'
    if re.search(r'goongbe', text):
        return 'Goongbe'
    if re.search(r'onzenna|zezebaebae', text):
        return 'Grosmimi'
    return ''

PROJECT_ROOT = os.path.dirname(DIR)
APIFY_SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"

REGION_TABS = {
    "us": {"posts": "US Posts Master", "d60": "US D+60 Tracker"},
    "jp": {"posts": "JP Posts Master", "d60": "JP D+60 Tracker"},
}


def get_gc():
    creds = Credentials.from_service_account_file(
        os.path.join(PROJECT_ROOT, "credentials", "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


def load_posts_master(sh, tab_name, region):
    """Read Posts Master tab -> list of dicts for content_posts + today's metrics."""
    print(f"\n=== Reading {tab_name} ===")
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        print(f"  [SKIP] Tab '{tab_name}' not found")
        return [], []

    rows = ws.get_all_values()
    if len(rows) <= 1:
        print(f"  [SKIP] Empty tab")
        return [], []

    headers = rows[0]
    print(f"  Headers: {headers}")
    print(f"  Total rows: {len(rows) - 1}")

    posts = []
    metrics = []
    today = datetime.now().strftime("%Y-%m-%d")

    for row in rows[1:]:
        if not row or not row[0]:
            continue

        # Posts Master columns: PostID, URL, Platform, Username, Nickname, Followers,
        # Content, Hashtags, TaggedAccount, PostDate, Comments, Likes, Views, Brand(13)
        post_id = row[0].strip()

        # URL might be =HYPERLINK("url", "display") — extract actual URL
        url = _extract_url(row[1]) if len(row) > 1 else ""
        platform = row[2] if len(row) > 2 else ""
        username = _extract_display(row[3]) if len(row) > 3 else ""
        nickname = row[4] if len(row) > 4 else ""
        followers = _safe_int(row[5]) if len(row) > 5 else 0
        caption = row[6] if len(row) > 6 else ""
        hashtags = row[7] if len(row) > 7 else ""
        tagged_account = row[8] if len(row) > 8 else ""
        post_date = (row[9] if len(row) > 9 else "")[:10]  # strip time part
        comments = _safe_int(row[10]) if len(row) > 10 else 0
        likes = _safe_int(row[11]) if len(row) > 11 else 0
        views = _safe_int(row[12]) if len(row) > 12 else 0

        posts.append({
            "post_id": post_id,
            "url": url,
            "platform": platform.lower() if platform else "instagram",
            "username": username,
            "nickname": nickname,
            "followers": followers,
            "caption": caption[:500] if caption else "",
            "hashtags": hashtags,
            "tagged_account": tagged_account,
            "post_date": post_date,
            "brand": row[13].strip() if len(row) > 13 and row[13].strip() else detect_brand_from_text(hashtags, caption, tagged_account),
            "region": region,
            "source": "apify",
        })

        # Current metrics as today's snapshot
        if comments or likes or views:
            metrics.append({
                "post_id": post_id,
                "date": today,
                "comments": comments,
                "likes": likes,
                "views": views,
            })

    print(f"  Parsed: {len(posts)} posts, {len(metrics)} metric rows")
    return posts, metrics


def load_d60_tracker(sh, tab_name):
    """Read D+60 Tracker tab -> list of dicts for content_metrics_daily.

    Structure: 10 fixed cols + (D+0..D+60/90) x 3 metrics each.
    Fixed: A=PostID, B=URL, C=Platform, D=Username, E=PostDate, F=TaggedAccount,
           G=D+Days, H=CurrComment, I=CurrLike, J=CurrView
    D+N starts at col 10: (comments, likes, views) triplets.
    """
    print(f"\n=== Reading {tab_name} ===")
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        print(f"  [SKIP] Tab '{tab_name}' not found")
        return []

    rows = ws.get_all_values()
    if len(rows) <= 2:
        print(f"  [SKIP] Empty tab (header rows only)")
        return []

    print(f"  Total rows: {len(rows) - 2} (excl 2 header rows)")
    print(f"  Columns per row: {len(rows[0]) if rows else 0}")

    metrics = []
    for row in rows[2:]:  # skip 2 header rows
        if not row or not row[0]:
            continue

        post_id = row[0].strip()
        # Extract post_id from HYPERLINK formula if present
        if post_id.startswith("=HYPERLINK"):
            post_id = _extract_display(post_id)

        post_date_str = row[4] if len(row) > 4 else ""
        if not post_date_str:
            continue

        try:
            post_date = datetime.strptime(post_date_str, "%Y-%m-%d")
        except ValueError:
            continue

        # Scan D+N triplets starting at col 10
        for d_plus in range(91):  # D+0 to D+90
            col_start = 10 + d_plus * 3
            if col_start + 2 >= len(row):
                break

            c_val = row[col_start]
            l_val = row[col_start + 1]
            v_val = row[col_start + 2]

            # Skip empty cells
            if not c_val and not l_val and not v_val:
                continue

            metric_date = (post_date + timedelta(days=d_plus)).strftime("%Y-%m-%d")
            metrics.append({
                "post_id": post_id,
                "date": metric_date,
                "comments": _safe_int(c_val),
                "likes": _safe_int(l_val),
                "views": _safe_int(v_val),
            })

    print(f"  Parsed: {len(metrics)} historical metric rows")
    return metrics


def _extract_url(cell):
    """Extract URL from =HYPERLINK("url", "display") or plain text."""
    if not cell:
        return ""
    if cell.startswith("=HYPERLINK"):
        try:
            return cell.split('"')[1]
        except (IndexError, ValueError):
            return cell
    return cell


def _extract_display(cell):
    """Extract display text from =HYPERLINK("url", "display") or plain text."""
    if not cell:
        return ""
    if cell.startswith("=HYPERLINK"):
        try:
            parts = cell.split('"')
            return parts[3] if len(parts) > 3 else parts[1]
        except (IndexError, ValueError):
            return cell
    return cell


def _safe_int(val):
    """Parse int from string, handling commas and empty strings."""
    if not val:
        return 0
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def main():
    parser = argparse.ArgumentParser(description="Initial load: Apify Sheet -> PG")
    parser.add_argument("--region", choices=["us", "jp", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no push")
    args = parser.parse_args()

    regions = ["us", "jp"] if args.region == "all" else [args.region]

    print("=" * 60)
    print("Initial Load: Apify Google Sheet -> PostgreSQL")
    print(f"Regions: {regions}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 60)

    gc = get_gc()
    sh = gc.open_by_key(APIFY_SHEET_ID)

    total_posts = 0
    total_pm_metrics = 0
    total_d60_metrics = 0

    for region in regions:
        tabs = REGION_TABS[region]

        # 1. Posts Master -> content_posts + today's metrics
        posts, pm_metrics = load_posts_master(sh, tabs["posts"], region)
        total_posts += len(posts)
        total_pm_metrics += len(pm_metrics)

        # 2. D+60 Tracker -> historical metrics
        d60_metrics = load_d60_tracker(sh, tabs["d60"])
        total_d60_metrics += len(d60_metrics)

        if args.dry_run:
            print(f"\n[DRY RUN] {region.upper()}: {len(posts)} posts, "
                  f"{len(pm_metrics)} current metrics, {len(d60_metrics)} D+60 metrics")
            if posts:
                print(f"  Sample post: {posts[0]['post_id']} - {posts[0]['username']} ({posts[0]['platform']})")
            if d60_metrics:
                print(f"  Sample D+60: {d60_metrics[0]['post_id']} date={d60_metrics[0]['date']} "
                      f"views={d60_metrics[0]['views']}")
            continue

        # Push posts
        if posts:
            print(f"\n--- Pushing {len(posts)} posts ({region.upper()}) ---")
            r = push_posts(posts)
            print(f"  Result: {r}")

        # Merge PM + D+60 metrics (D+60 has more granular data)
        # D+60 metrics take priority (historical snapshots)
        all_metrics = d60_metrics + pm_metrics  # push D+60 first, PM metrics will be upserted
        if all_metrics:
            print(f"\n--- Pushing {len(all_metrics)} metrics ({region.upper()}) ---")
            r = push_metrics(all_metrics)
            print(f"  Result: {r}")

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total_posts} posts, {total_pm_metrics} current metrics, "
          f"{total_d60_metrics} D+60 historical metrics")
    print("=" * 60)


if __name__ == "__main__":
    main()
