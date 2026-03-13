"""
Apify Content Fetcher - Syncly replacement
===========================================
Brand 계정의 Tagged 페이지에서 인플루언서 포스트를 수집하고,
Google Sheets에 메트릭을 업데이트한다.

사용법:
  # 전체 파이프라인 (수집 + 시트 업데이트)
  python tools/fetch_apify_content.py --daily

  # US만 수집
  python tools/fetch_apify_content.py --daily --region us

  # JP만 수집
  python tools/fetch_apify_content.py --daily --region jp

  # 수집만 (시트 업데이트 없이)
  python tools/fetch_apify_content.py --daily --no-sheet

  # 시트 메트릭만 업데이트 (수집 없이, 기존 JSON 사용)
  python tools/fetch_apify_content.py --update-metrics

  # 테스트 (소량)
  python tools/fetch_apify_content.py --test
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from apify_client import ApifyClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

OUTPUT_DIR = PROJECT_ROOT / "Data Storage" / "apify"
SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"

# Apify Actor IDs
IG_POST_SCRAPER = "apify/instagram-post-scraper"
IG_SCRAPER = "apify/instagram-scraper"
TT_SCRAPER = "clockworks/tiktok-profile-scraper"

# ---- Brand Tagged Pages ----
US_TAGGED = [
    "https://www.instagram.com/onzenna.official/tagged/",
    "https://www.instagram.com/grosmimi_usa/tagged/",
]
JP_TAGGED = [
    "https://www.instagram.com/grosmimi_japan/tagged/",
]

# ---- Exclude brand/store accounts ----
EXCLUDE_ACCOUNTS = {
    "onzenna.official", "grosmimi_usa", "grosmimi_japan", "grosmimi_official",
    "grosmimi.id", "grosmimi_thailand", "grosmimi_cambodia", "grosmimi_uae",
    "grosmimiofficial_sg", "zezebaebae", "baby.boutique.official",
    "grosmimi_korea",
}

# ---- Sheet tab names ----
TAB_US = "US Apify Tracker"
TAB_JP = "JP Apify Tracker"

HEADERS = [
    "Platform", "Username", "Followers", "Post URL", "Post ID", "Post Date",
    "Type", "Views", "Likes", "Comments", "Tagged Account",
    "Caption", "Hashtags",
]


def get_client():
    """Initialize Apify client."""
    load_env()
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("[ERROR] APIFY_API_TOKEN not found")
        sys.exit(1)
    return ApifyClient(token)


def fetch_tagged_posts(client, tagged_urls, limit=200):
    """Scrape tagged posts from brand account pages."""
    all_items = []
    for url in tagged_urls:
        account = url.rstrip("/").split("/")[-2]
        print(f"[TAG] @{account}/tagged/ (limit={limit})...")

        run_input = {
            "directUrls": [url],
            "resultsType": "posts",
            "resultsLimit": limit,
            "proxy": {"useApifyProxy": True},
        }
        run = client.actor(IG_SCRAPER).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        for item in items:
            item["_tagged_account"] = account
        print(f"  Got {len(items)} posts")
        all_items.extend(items)

    return all_items


def fetch_ig_posts(client, usernames, results_limit=30):
    """Fetch Instagram posts by username list."""
    print(f"[IG] Fetching {len(usernames)} accounts (limit={results_limit})...")
    run_input = {"username": usernames, "resultsLimit": results_limit}
    run = client.actor(IG_POST_SCRAPER).call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"[IG] Got {len(items)} posts")
    return items


def fetch_ig_hashtag(client, hashtag, results_limit=50):
    """Search Instagram hashtag via explore page."""
    print(f"[IG] #{hashtag} (limit={results_limit})...")
    run_input = {
        "directUrls": [f"https://www.instagram.com/explore/tags/{hashtag}/"],
        "resultsType": "posts",
        "resultsLimit": results_limit,
        "proxy": {"useApifyProxy": True},
    }
    run = client.actor(IG_SCRAPER).call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"[IG] Got {len(items)} for #{hashtag}")
    return items


def fetch_tt_posts(client, usernames, results_limit=30):
    """Fetch TikTok videos by username list."""
    print(f"[TT] Fetching {len(usernames)} accounts (limit={results_limit})...")
    run_input = {"profiles": usernames, "resultsPerPage": results_limit}
    run = client.actor(TT_SCRAPER).call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"[TT] Got {len(items)} videos")
    return items


def dedup_and_filter(items):
    """Deduplicate by shortCode, exclude brand accounts."""
    seen = {}
    for item in items:
        sc = item.get("shortCode", item.get("id", ""))
        uname = (item.get("ownerUsername", "") or "").lower()
        if sc and sc not in seen and uname not in EXCLUDE_ACCOUNTS:
            seen[sc] = item
    result = list(seen.values())
    result.sort(key=lambda x: x.get("timestamp", "") or "", reverse=True)
    return result


def normalize_item(item):
    """Normalize raw Apify item to sheet row."""
    ts = item.get("timestamp", "")
    if ts and "T" in str(ts):
        ts = str(ts)[:10]

    hashtags_raw = item.get("hashtags", []) or []
    ht_str = ", ".join(
        [h if isinstance(h, str) else h.get("name", "") for h in hashtags_raw]
    )

    return [
        "instagram",
        item.get("ownerUsername", ""),
        item.get("ownerFollowerCount", 0) or 0,
        item.get("url", ""),
        item.get("shortCode", item.get("id", "")),
        ts,
        item.get("type", ""),
        item.get("videoViewCount", 0) or 0,
        item.get("likesCount", 0) or 0,
        item.get("commentsCount", 0) or 0,
        item.get("_tagged_account", ""),
        (item.get("caption", "") or "")[:300],
        ht_str,
    ]


def save_raw(items, prefix):
    """Save raw JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"{today}_{prefix}_raw.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2, default=str)
    print(f"[RAW] {path}")
    return path


def get_sheets_client():
    """Get gspread client + Credentials."""
    import gspread
    from google.oauth2.service_account import Credentials

    cred_path = PROJECT_ROOT / "credentials" / "google_service_account.json"
    creds = Credentials.from_service_account_file(
        str(cred_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    return gc, creds


def write_tab(gc, creds, tab_name, rows):
    """Write rows to a sheet tab with formatting + hyperlinks."""
    import requests as req
    from google.auth.transport.requests import Request

    sh = gc.open_by_key(SHEET_ID)

    # Create or clear tab
    try:
        ws = sh.worksheet(tab_name)
        ws.clear()
    except Exception:
        ws = sh.add_worksheet(tab_name, rows=len(rows) + 5, cols=len(HEADERS))

    ws.update(range_name="A1", values=[HEADERS] + rows)
    print(f"[SHEET] {tab_name}: {len(rows)} rows written")

    # Format via Sheets API
    if creds.expired:
        creds.refresh(Request())
    auth = {"Authorization": f"Bearer {creds.token}"}
    ws_id = ws.id
    total = len(rows) + 1
    nc = len(HEADERS)

    fmt = []
    # Header style
    fmt.append({"repeatCell": {
        "range": {"sheetId": ws_id, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 0, "endColumnIndex": nc},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.3},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1},
                           "bold": True, "fontSize": 10},
            "horizontalAlignment": "CENTER",
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
    }})
    # Freeze header
    fmt.append({"updateSheetProperties": {
        "properties": {"sheetId": ws_id, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount",
    }})
    # Auto-resize
    fmt.append({"autoResizeDimensions": {
        "dimensions": {"sheetId": ws_id, "dimension": "COLUMNS",
                       "startIndex": 0, "endIndex": 7},
    }})
    # Caption/Hashtags width
    for ci, w in [(11, 350), (12, 200)]:
        fmt.append({"updateDimensionProperties": {
            "range": {"sheetId": ws_id, "dimension": "COLUMNS",
                      "startIndex": ci, "endIndex": ci + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize",
        }})
    # Number format for Followers/Views/Likes/Comments
    for ci in [2, 7, 8, 9]:
        fmt.append({"repeatCell": {
            "range": {"sheetId": ws_id, "startRowIndex": 1, "endRowIndex": total,
                      "startColumnIndex": ci, "endColumnIndex": ci + 1},
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
            "fields": "userEnteredFormat.numberFormat",
        }})
    # Hyperlinks (Post URL = col 3)
    for ri, row in enumerate(rows, start=1):
        url = row[3]
        if url and url.startswith("http"):
            fmt.append({"updateCells": {
                "rows": [{"values": [{
                    "userEnteredValue": {"formulaValue": f'=HYPERLINK("{url}", "{url}")'},
                    "userEnteredFormat": {"textFormat": {
                        "foregroundColor": {"red": 0.07, "green": 0.34, "blue": 0.73},
                        "underline": True,
                    }},
                }]}],
                "range": {"sheetId": ws_id, "startRowIndex": ri, "endRowIndex": ri + 1,
                          "startColumnIndex": 3, "endColumnIndex": 4},
                "fields": "userEnteredValue,userEnteredFormat.textFormat",
            }})
    # Filter
    fmt.append({"setBasicFilter": {
        "filter": {"range": {"sheetId": ws_id, "startRowIndex": 0, "endRowIndex": total,
                             "startColumnIndex": 0, "endColumnIndex": nc}},
    }})

    resp = req.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate",
        headers=auth, json={"requests": fmt},
    )
    if resp.status_code != 200:
        print(f"[SHEET] Format error: {resp.text[:300]}")
    else:
        print(f"[SHEET] {tab_name}: formatted OK")

    return ws


def update_metrics_only(gc, creds, tab_name, fresh_items):
    """Update Views/Likes/Comments for existing rows (metric refresh)."""
    import requests as req
    from google.auth.transport.requests import Request

    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        print(f"[METRICS] Tab '{tab_name}' not found, skipping")
        return 0

    all_values = ws.get_all_values()
    if len(all_values) < 2:
        print(f"[METRICS] Tab '{tab_name}' is empty")
        return 0

    header = all_values[0]
    pid_col = header.index("Post ID")
    views_col = header.index("Views")
    likes_col = header.index("Likes")
    comments_col = header.index("Comments")
    followers_col = header.index("Followers")

    # Build lookup from fresh data
    fresh_lookup = {}
    for item in fresh_items:
        sc = item.get("shortCode", item.get("id", ""))
        if sc:
            fresh_lookup[sc] = item

    # Find cells to update
    updates = []
    updated_count = 0
    for row_idx, row in enumerate(all_values[1:], start=2):
        pid = row[pid_col]
        if pid in fresh_lookup:
            item = fresh_lookup[pid]
            new_views = item.get("videoViewCount", 0) or 0
            new_likes = item.get("likesCount", 0) or 0
            new_comments = item.get("commentsCount", 0) or 0
            new_followers = item.get("ownerFollowerCount", 0) or 0

            # Check if anything changed
            old_views = int(row[views_col]) if row[views_col].replace(",", "").isdigit() else 0
            old_likes = int(row[likes_col]) if row[likes_col].replace(",", "").lstrip("-").isdigit() else 0

            if new_views != old_views or new_likes != old_likes:
                updates.append({
                    "range": f"'{tab_name}'!{chr(65+followers_col)}{row_idx}",
                    "values": [[new_followers]],
                })
                updates.append({
                    "range": f"'{tab_name}'!{chr(65+views_col)}{row_idx}:{chr(65+comments_col)}{row_idx}",
                    "values": [[new_views, new_likes, new_comments]],
                })
                updated_count += 1

    if not updates:
        print(f"[METRICS] {tab_name}: no changes detected")
        return 0

    # Batch update
    sh.values_batch_update({"valueInputOption": "RAW", "data": updates})
    print(f"[METRICS] {tab_name}: updated {updated_count} rows")

    # Also add NEW posts not yet in the sheet
    existing_pids = set(row[pid_col] for row in all_values[1:])
    new_rows = []
    for item in fresh_items:
        sc = item.get("shortCode", item.get("id", ""))
        uname = (item.get("ownerUsername", "") or "").lower()
        if sc and sc not in existing_pids and uname not in EXCLUDE_ACCOUNTS:
            new_rows.append(normalize_item(item))
            existing_pids.add(sc)

    if new_rows:
        # Sort new rows by date desc
        new_rows.sort(key=lambda r: r[5] or "", reverse=True)
        next_row = len(all_values) + 1
        ws.update(range_name=f"A{next_row}", values=new_rows)
        print(f"[METRICS] {tab_name}: added {len(new_rows)} NEW posts")

        # Apply hyperlinks for new rows
        if creds.expired:
            creds.refresh(Request())
        auth = {"Authorization": f"Bearer {creds.token}"}
        ws_id = ws.id
        link_reqs = []
        for i, row in enumerate(new_rows):
            ri = next_row - 1 + i  # 0-based
            url = row[3]
            if url and url.startswith("http"):
                link_reqs.append({"updateCells": {
                    "rows": [{"values": [{
                        "userEnteredValue": {"formulaValue": f'=HYPERLINK("{url}", "{url}")'},
                        "userEnteredFormat": {"textFormat": {
                            "foregroundColor": {"red": 0.07, "green": 0.34, "blue": 0.73},
                            "underline": True,
                        }},
                    }]}],
                    "range": {"sheetId": ws_id, "startRowIndex": ri, "endRowIndex": ri + 1,
                              "startColumnIndex": 3, "endColumnIndex": 4},
                    "fields": "userEnteredValue,userEnteredFormat.textFormat",
                }})
        if link_reqs:
            req.post(
                f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate",
                headers=auth, json={"requests": link_reqs},
            )

    return updated_count + len(new_rows)


def run_daily(client, region="all", update_sheet=True):
    """Daily pipeline: fetch tagged posts + update sheet metrics."""
    today = datetime.now().strftime("%Y-%m-%d")
    results = {}

    if region in ("all", "us"):
        print("\n===== US Pipeline =====")
        us_items = fetch_tagged_posts(client, US_TAGGED, limit=200)
        save_raw(us_items, "us_tagged")
        us_filtered = dedup_and_filter(us_items)
        print(f"[US] {len(us_filtered)} posts from {len(set(i.get('ownerUsername','') for i in us_filtered))} creators")
        results["us"] = {"raw": us_items, "filtered": us_filtered}

    if region in ("all", "jp"):
        print("\n===== JP Pipeline =====")
        jp_items = fetch_tagged_posts(client, JP_TAGGED, limit=200)
        save_raw(jp_items, "jp_tagged")
        jp_filtered = dedup_and_filter(jp_items)
        print(f"[JP] {len(jp_filtered)} posts from {len(set(i.get('ownerUsername','') for i in jp_filtered))} creators")
        results["jp"] = {"raw": jp_items, "filtered": jp_filtered}

    if not update_sheet:
        print("\n[SKIP] Sheet update skipped (--no-sheet)")
        return results

    # Sheet update
    gc, creds = get_sheets_client()

    if "us" in results:
        us_rows = [normalize_item(item) for item in results["us"]["filtered"]]
        # Check if tab exists — if first run, write full; otherwise update metrics
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(TAB_US)
            existing = ws.get_all_values()
            if len(existing) > 1:
                print(f"[US] Existing tab found ({len(existing)-1} rows), updating metrics...")
                update_metrics_only(gc, creds, TAB_US, results["us"]["filtered"])
            else:
                write_tab(gc, creds, TAB_US, us_rows)
        except Exception:
            write_tab(gc, creds, TAB_US, us_rows)

    if "jp" in results:
        jp_rows = [normalize_item(item) for item in results["jp"]["filtered"]]
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(TAB_JP)
            existing = ws.get_all_values()
            if len(existing) > 1:
                print(f"[JP] Existing tab found ({len(existing)-1} rows), updating metrics...")
                update_metrics_only(gc, creds, TAB_JP, results["jp"]["filtered"])
            else:
                write_tab(gc, creds, TAB_JP, jp_rows)
        except Exception:
            write_tab(gc, creds, TAB_JP, jp_rows)

    # Summary
    print("\n===== Daily Summary =====")
    print(f"Date: {today}")
    for region_key, data in results.items():
        n = len(data["filtered"])
        creators = len(set(i.get("ownerUsername", "") for i in data["filtered"]))
        print(f"  {region_key.upper()}: {n} posts, {creators} creators")

    return results


def run_update_metrics_only(region="all"):
    """Re-read latest raw JSON and update sheet metrics (no API calls)."""
    gc, creds = get_sheets_client()
    today = datetime.now().strftime("%Y-%m-%d")

    if region in ("all", "us"):
        raw_path = OUTPUT_DIR / f"{today}_us_tagged_raw.json"
        if raw_path.exists():
            with open(raw_path, encoding="utf-8") as f:
                items = json.load(f)
            filtered = dedup_and_filter(items)
            update_metrics_only(gc, creds, TAB_US, filtered)
        else:
            print(f"[US] No raw file for today: {raw_path}")

    if region in ("all", "jp"):
        raw_path = OUTPUT_DIR / f"{today}_jp_tagged_raw.json"
        if raw_path.exists():
            with open(raw_path, encoding="utf-8") as f:
                items = json.load(f)
            filtered = dedup_and_filter(items)
            update_metrics_only(gc, creds, TAB_JP, filtered)
        else:
            print(f"[JP] No raw file for today: {raw_path}")


def run_test(client):
    """Quick test with sample accounts."""
    ig_items = fetch_ig_posts(client, ["pediatricdentalmom", "tulayclara_"], results_limit=5)
    save_raw(ig_items, "test_ig")
    for item in ig_items[:3]:
        print(f"  {item.get('ownerUsername','')}: {item.get('shortCode','')} views={item.get('videoViewCount',0)}")
    print(f"[TEST] {len(ig_items)} posts fetched")


def main():
    parser = argparse.ArgumentParser(description="Apify Content Fetcher (Syncly replacement)")
    parser.add_argument("--daily", action="store_true",
                        help="Run daily pipeline: fetch tagged + update sheet")
    parser.add_argument("--region", type=str, default="all", choices=["all", "us", "jp"],
                        help="Region to process (default: all)")
    parser.add_argument("--no-sheet", action="store_true",
                        help="Skip sheet update (collect only)")
    parser.add_argument("--update-metrics", action="store_true",
                        help="Update sheet metrics from today's raw JSON (no API)")
    parser.add_argument("--test", action="store_true",
                        help="Run quick test")
    parser.add_argument("--usernames", type=str,
                        help="Comma-separated IG usernames for manual fetch")
    parser.add_argument("--hashtag", type=str,
                        help="Search Instagram hashtag")
    parser.add_argument("--tiktok", action="store_true",
                        help="Use TikTok scraper")
    parser.add_argument("--limit", type=int, default=30,
                        help="Results limit per account (default: 30)")
    args = parser.parse_args()

    if args.daily:
        client = get_client()
        run_daily(client, region=args.region, update_sheet=not args.no_sheet)
    elif args.update_metrics:
        run_update_metrics_only(region=args.region)
    elif args.test:
        client = get_client()
        run_test(client)
    elif args.hashtag:
        client = get_client()
        items = fetch_ig_hashtag(client, args.hashtag, args.limit)
        save_raw(items, f"hashtag_{args.hashtag}")
    elif args.usernames:
        client = get_client()
        names = [n.strip() for n in args.usernames.split(",")]
        if args.tiktok:
            items = fetch_tt_posts(client, names, args.limit)
            save_raw(items, "tt_manual")
        else:
            items = fetch_ig_posts(client, names, args.limit)
            save_raw(items, "ig_manual")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
