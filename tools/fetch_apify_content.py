"""
Apify Content Pipeline - Daily IG + TikTok tracker
===================================================
6-tab Google Sheet: Posts Master / D+60 Tracker / Influencer Tracker x US, JP

Usage:
  # Full daily pipeline (IG tagged + TikTok + sheet update + email)
  python tools/fetch_apify_content.py --daily

  # US only
  python tools/fetch_apify_content.py --daily --region us

  # Skip email
  python tools/fetch_apify_content.py --daily --no-email

  # Dry run (no API calls, use cached JSON)
  python tools/fetch_apify_content.py --daily --dry-run
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
SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
TODAY = datetime.now().strftime("%Y-%m-%d")

# Apify actors
IG_SCRAPER = "apify/instagram-scraper"
IG_PROFILE_SCRAPER = "apify/instagram-profile-scraper"
TT_SCRAPER = "clockworks/free-tiktok-scraper"

# Brand tagged pages
US_TAGGED_URLS = [
    "https://www.instagram.com/onzenna.official/tagged/",
    "https://www.instagram.com/grosmimi_usa/tagged/",
]
JP_TAGGED_URLS = [
    "https://www.instagram.com/grosmimi_japan/tagged/",
]

# TikTok search queries (US only)
TT_QUERIES = ["onzenna", "grosmimi", "grosmimi_usa", "onzenna.official"]
TT_KEYWORDS = {
    "grosmimi", "onzenna", "zezebaebae", "chaandmom", "naeiae",
    "commemoi", "alpremio", "zzbb", "straw cup", "gros mimi",
}

# Exclude brand/store accounts
EXCLUDE = {
    "onzenna.official", "grosmimi_usa", "grosmimi_japan", "grosmimi_official",
    "grosmimi.id", "grosmimi_thailand", "grosmimi_cambodia", "grosmimi_uae",
    "grosmimiofficial_sg", "zezebaebae", "baby.boutique.official",
    "grosmimi_korea", "onzenna", "grosmimi",
}


# ---------------------------------------------------------------------------
# Apify fetch functions
# ---------------------------------------------------------------------------

def get_client():
    load_env()
    token = os.environ.get("APIFY_API_TOKEN", "")
    if not token:
        print("[ERROR] APIFY_API_TOKEN not found")
        sys.exit(1)
    from apify_client import ApifyClient
    return ApifyClient(token)


def fetch_ig_tagged(client, urls, limit=2000):
    """Fetch IG tagged posts per brand account."""
    all_items = []
    for url in urls:
        acct = url.rstrip("/").split("/")[-2]
        print(f"[IG] @{acct}/tagged/ (limit={limit})...")
        try:
            run = client.actor(IG_SCRAPER).call(
                run_input={
                    "directUrls": [url],
                    "resultsLimit": limit,
                    "searchType": "user",
                },
                timeout_secs=600,
            )
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            for item in items:
                item["_tagged_account"] = acct
            print(f"  @{acct}: {len(items)} posts")
            all_items.extend(items)
        except Exception as e:
            print(f"  [WARN] @{acct} failed: {e}")
    return all_items


def fetch_tiktok(client):
    """Search TikTok for brand mentions."""
    print(f"[TT] Searching: {TT_QUERIES}")
    try:
        run = client.actor(TT_SCRAPER).call(
            run_input={
                "searchQueries": TT_QUERIES,
                "resultsPerPage": 100,
                "maxProfilesPerQuery": 1,
                "shouldDownloadCovers": False,
                "shouldDownloadVideos": False,
                "shouldDownloadSubtitles": False,
            },
            timeout_secs=300,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"[TT] Raw: {len(items)} results")
        return items
    except Exception as e:
        print(f"[TT] Failed: {e}")
        return []


def fetch_ig_profiles(client, usernames):
    """Fetch follower counts for username list."""
    if not usernames:
        return {}
    print(f"[PROFILE] Fetching {len(usernames)} profiles...")
    try:
        run = client.actor(IG_PROFILE_SCRAPER).call(
            run_input={"usernames": list(usernames)},
            timeout_secs=300,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        fmap = {}
        for item in items:
            u = (item.get("username", "") or "").lower()
            fc = item.get("followersCount", item.get("followedByCount", 0)) or 0
            if u:
                fmap[u] = fc
        print(f"[PROFILE] Got {len(fmap)} profiles")
        return fmap
    except Exception as e:
        print(f"[PROFILE] Failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Normalize raw data to common format
# ---------------------------------------------------------------------------

def normalize_ig(items, fmap=None):
    fmap = fmap or {}
    result, seen = [], set()
    for item in items:
        sc = item.get("shortCode", item.get("id", ""))
        uname = (item.get("ownerUsername", "") or "").lower()
        if not sc or sc in seen or not uname or uname in EXCLUDE:
            continue
        seen.add(sc)
        ts = str(item.get("timestamp", "") or "")[:10]
        hashtags = item.get("hashtags", []) or []
        result.append({
            "post_id": sc,
            "url": item.get("url", "") or f"https://www.instagram.com/p/{sc}/",
            "platform": "instagram",
            "username": uname,
            "nickname": item.get("ownerFullName", "") or "",
            "followers": fmap.get(uname, 0),
            "caption": (item.get("caption", "") or "")[:500],
            "hashtags": ", ".join(
                h if isinstance(h, str) else h.get("name", "") for h in hashtags
            ),
            "tagged_account": item.get("_tagged_account", ""),
            "post_date": ts,
            "comments": item.get("commentsCount", 0) or 0,
            "likes": item.get("likesCount", 0) or 0,
            "views": item.get("videoViewCount", 0) or 0,
        })
    return result


def normalize_tt(items):
    result, seen = [], set()
    for item in items:
        vid = str(item.get("id", ""))
        am = item.get("authorMeta", {}) or {}
        uname = (am.get("name", "") or "").lower()
        if not vid or vid in seen or not uname or uname in EXCLUDE:
            continue
        # Relevance filter
        text = (item.get("text", "") or "").lower()
        ht_names = [h.get("name", "").lower() for h in (item.get("hashtags", []) or [])]
        all_text = text + " " + " ".join(ht_names)
        if not any(kw in all_text for kw in TT_KEYWORDS):
            continue
        seen.add(vid)
        result.append({
            "post_id": vid,
            "url": item.get("webVideoUrl", "") or f"https://www.tiktok.com/@{uname}/video/{vid}",
            "platform": "tiktok",
            "username": uname,
            "nickname": am.get("nickName", "") or "",
            "followers": am.get("fans", 0) or 0,
            "caption": (item.get("text", "") or "")[:500],
            "hashtags": ", ".join(h.get("name", "") for h in (item.get("hashtags", []) or [])),
            "tagged_account": "",
            "post_date": (item.get("createTimeISO", "") or "")[:10],
            "comments": item.get("commentCount", 0) or 0,
            "likes": item.get("diggCount", 0) or 0,
            "views": item.get("playCount", 0) or 0,
        })
    return result


# ---------------------------------------------------------------------------
# Google Sheets update (6-tab structure)
# ---------------------------------------------------------------------------

def get_sheets():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh, creds


def safe_hl(url, display):
    d = str(display).replace('"', "'")[:100]
    return f'=HYPERLINK("{url}", "{d}")'


def profile_url(username, platform):
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{username}"
    return f"https://www.instagram.com/{username}/"


def update_posts_master(sh, data, tab_name):
    """Add new posts, update metrics for existing."""
    headers = [
        "Post ID", "URL", "Platform", "Username", "Nickname", "Followers",
        "Content", "Hashtags", "Tagged Account", "Post Date",
        "Comments", "Likes", "Views",
    ]
    try:
        ws = sh.worksheet(tab_name)
        existing = ws.get_all_values()
        existing_ids = set(r[0] for r in existing[1:]) if len(existing) > 1 else set()
    except Exception:
        existing = []
        existing_ids = set()

    new_posts = [d for d in data if d["post_id"] not in existing_ids]
    if not new_posts and existing:
        # Just update metrics for existing posts
        _update_pm_metrics(ws, existing, data)
        print(f"[{tab_name}] Metrics updated, 0 new posts")
        return 0

    if not existing or len(existing) <= 1:
        # First run: write everything
        rows = []
        for d in data:
            rows.append([
                d["post_id"],
                safe_hl(d["url"], d["url"]),
                d["platform"],
                safe_hl(profile_url(d["username"], d["platform"]), d["username"]),
                d["nickname"], d["followers"], d["caption"], d["hashtags"],
                d["tagged_account"], d["post_date"],
                d["comments"], d["likes"], d["views"],
            ])
        try:
            ws = sh.worksheet(tab_name)
            ws.clear()
        except Exception:
            ws = sh.add_worksheet(tab_name, rows=len(rows) + 5, cols=len(headers))
        ws.update(range_name="A1", values=[headers])
        for i in range(0, len(rows), 80):
            ws.update(range_name=f"A{i + 2}", values=rows[i:i+80],
                      value_input_option="USER_ENTERED")
            time.sleep(1)
        print(f"[{tab_name}] Full write: {len(rows)} rows")
        return len(rows)

    # Append new posts
    new_rows = []
    for d in new_posts:
        new_rows.append([
            d["post_id"],
            safe_hl(d["url"], d["url"]),
            d["platform"],
            safe_hl(profile_url(d["username"], d["platform"]), d["username"]),
            d["nickname"], d["followers"], d["caption"], d["hashtags"],
            d["tagged_account"], d["post_date"],
            d["comments"], d["likes"], d["views"],
        ])
    if new_rows:
        next_row = len(existing) + 1
        required_rows = next_row + len(new_rows) - 1
        if required_rows > ws.row_count:
            ws.add_rows(required_rows - ws.row_count + 100)
        ws.update(range_name=f"A{next_row}", values=new_rows,
                  value_input_option="USER_ENTERED")
    _update_pm_metrics(ws, existing, data)
    print(f"[{tab_name}] +{len(new_rows)} new, metrics updated")
    return len(new_rows)


def _update_pm_metrics(ws, existing, data):
    """Update Comments/Likes/Views columns for existing posts."""
    if len(existing) <= 1:
        return
    lookup = {d["post_id"]: d for d in data}
    updates = []
    for row_idx, row in enumerate(existing[1:], start=2):
        pid = row[0]
        if pid in lookup:
            d = lookup[pid]
            # K=Comments(11), L=Likes(12), M=Views(13) -- 1-indexed: K,L,M
            updates.append({
                "range": f"'{ws.title}'!K{row_idx}:M{row_idx}",
                "values": [[d["comments"], d["likes"], d["views"]]],
            })
    if updates:
        for i in range(0, len(updates), 200):
            ws.spreadsheet.values_batch_update(
                {"valueInputOption": "RAW", "data": updates[i:i+200]}
            )
            time.sleep(1)


def update_d60_tracker(sh, data, tab_name):
    """Update D+60 tracker: fill today's D+N column for each post."""
    try:
        ws = sh.worksheet(tab_name)
        existing = ws.get_all_values()
    except Exception:
        existing = []

    if len(existing) <= 2:
        print(f"[{tab_name}] Empty, skipping D+60 update")
        return

    # Build lookup: post_id -> row index (0-based in existing)
    pid_to_row = {}
    for i, row in enumerate(existing[2:], start=2):  # skip 2 header rows
        pid = row[0] if row else ""
        if pid:
            pid_to_row[pid] = i

    data_lookup = {d["post_id"]: d for d in data}
    updates = []

    for pid, row_idx in pid_to_row.items():
        d = data_lookup.get(pid)
        if not d:
            continue

        post_date = d["post_date"]
        if not post_date:
            continue
        try:
            pd = datetime.strptime(post_date, "%Y-%m-%d")
            d_plus = (datetime.now() - pd).days
        except ValueError:
            continue

        # Update current status columns (G=7, H=8, I=9, J=10 -- 1-indexed)
        # Fixed: A=PostID, B=URL, C=Platform, D=Username, E=PostDate, F=TaggedAccount
        # Status: G=D+Days, H=CurrComment, I=CurrLike, J=CurrView
        updates.append({
            "range": f"'{tab_name}'!G{row_idx + 1}:J{row_idx + 1}",
            "values": [[d_plus, d["comments"], d["likes"], d["views"]]],
        })

        # Fill D+N column if within range
        if 0 <= d_plus <= 60:
            # Fixed cols: A-F (6) + Status: G-J (4) = 10 total fixed columns
            # D+0 starts at col index 10 (K), D+1 at 13, etc.
            col_start = 10 + d_plus * 3  # 0-based
            col_letter_1 = _col_letter(col_start)
            col_letter_3 = _col_letter(col_start + 2)
            updates.append({
                "range": f"'{tab_name}'!{col_letter_1}{row_idx + 1}:{col_letter_3}{row_idx + 1}",
                "values": [[d["comments"], d["likes"], d["views"]]],
            })

    # Also append new posts not yet in tracker
    existing_pids = set(pid_to_row.keys())
    new_posts = [d for d in data if d["post_id"] not in existing_pids]
    if new_posts:
        next_row = len(existing) + 1
        new_rows = []
        for d in new_posts:
            d_plus = ""
            if d["post_date"]:
                try:
                    pd = datetime.strptime(d["post_date"], "%Y-%m-%d")
                    d_plus = (datetime.now() - pd).days
                except ValueError:
                    pass

            row = [
                d["post_id"],
                safe_hl(d["url"], d["url"]),
                d["platform"],
                safe_hl(profile_url(d["username"], d["platform"]), d["username"]),
                d["post_date"],
                d["tagged_account"],
                str(d_plus) if d_plus != "" else "",
                str(d["comments"]), str(d["likes"]), str(d["views"]),
            ]
            for dn in range(61):
                if isinstance(d_plus, int) and dn == d_plus and d_plus <= 60:
                    row += [str(d["comments"]), str(d["likes"]), str(d["views"])]
                else:
                    row += ["", "", ""]
            new_rows.append(row)

        # Auto-expand sheet if needed
        required_rows = next_row + len(new_rows) - 1
        current_rows = ws.row_count
        if required_rows > current_rows:
            ws.add_rows(required_rows - current_rows + 100)
            print(f"[{tab_name}] Expanded sheet to {current_rows + (required_rows - current_rows + 100)} rows")

        for i in range(0, len(new_rows), 40):
            ws.update(range_name=f"A{next_row + i}", values=new_rows[i:i+40],
                      value_input_option="USER_ENTERED")
            time.sleep(1)
        print(f"[{tab_name}] +{len(new_rows)} new posts appended")

    if updates:
        for i in range(0, len(updates), 200):
            ws.spreadsheet.values_batch_update(
                {"valueInputOption": "RAW", "data": updates[i:i+200]}
            )
            time.sleep(1)
        print(f"[{tab_name}] D+N updated for {len(updates)//2} posts")
    else:
        print(f"[{tab_name}] No D+N updates needed")


def _col_letter(idx):
    result = ""
    while idx >= 0:
        result = chr(idx % 26 + 65) + result
        idx = idx // 26 - 1
    return result


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------

def send_email(summary):
    """Send completion email via send_gmail.py."""
    try:
        from send_gmail import send_email as gmail_send
        subject = f"[Apify Content Tracker] Daily Report {TODAY}"
        body = f"Apify Content Pipeline - {TODAY}\n\n"
        body += "== Pipeline Results ==\n"
        for region, info in summary.items():
            body += f"\n{region.upper()}:\n"
            body += f"  IG posts: {info.get('ig_count', 0)}\n"
            if "tt_count" in info:
                body += f"  TikTok posts: {info['tt_count']}\n"
            body += f"  Total: {info.get('total', 0)} posts, {info.get('creators', 0)} creators\n"
            body += f"  New posts added: {info.get('new_posts', 0)}\n"
            body += f"  D+60 updated: {info.get('d60_updated', True)}\n"
        body += f"\nSheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        gmail_send(
            to="wj.choi@orbiters.co.kr",
            subject=subject,
            body=body,
        )
        print(f"[EMAIL] Sent to wj.choi@orbiters.co.kr")
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def save_json(data, name):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{TODAY}_{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[SAVE] {path.name}")
    return path


def run_daily(region="all", dry_run=False, send_mail=True):
    summary = {}
    client = None if dry_run else get_client()

    # --- US ---
    if region in ("all", "us"):
        print("\n===== US Pipeline =====")

        # IG tagged
        if dry_run:
            ig_path = max(OUTPUT_DIR.glob("*_us_tagged*.json"), key=os.path.getmtime, default=None)
            ig_raw = json.load(open(ig_path, encoding="utf-8")) if ig_path else []
            print(f"[DRY] Loaded {len(ig_raw)} from {ig_path}")
        else:
            ig_raw = fetch_ig_tagged(client, US_TAGGED_URLS, limit=2000)
            save_json(ig_raw, "us_tagged_raw")

        # TikTok
        if dry_run:
            tt_path = max(OUTPUT_DIR.glob("*_us_tiktok*.json"), key=os.path.getmtime, default=None)
            tt_raw = json.load(open(tt_path, encoding="utf-8")) if tt_path else []
            print(f"[DRY] Loaded {len(tt_raw)} TikTok from {tt_path}")
        else:
            tt_raw = fetch_tiktok(client)
            save_json(tt_raw, "us_tiktok_raw")

        # IG profiles for follower data
        ig_norm = normalize_ig(ig_raw)
        ig_usernames = set(d["username"] for d in ig_norm)
        if not dry_run and ig_usernames:
            fmap = fetch_ig_profiles(client, ig_usernames)
            save_json(fmap, "us_follower_map")
        else:
            fmap_path = max(OUTPUT_DIR.glob("*_us_follower_map.json"), key=os.path.getmtime, default=None)
            fmap = json.load(open(fmap_path, encoding="utf-8")) if fmap_path else {}

        # Re-normalize with follower data
        ig_norm = normalize_ig(ig_raw, fmap)
        tt_norm = normalize_tt(tt_raw)

        us_data = ig_norm + tt_norm
        us_data.sort(key=lambda x: x["post_date"] or "", reverse=True)
        us_creators = set(d["username"] for d in us_data)
        print(f"[US] Total: {len(us_data)} posts ({len(ig_norm)} IG + {len(tt_norm)} TT), {len(us_creators)} creators")

        # Update sheets
        sh, creds = get_sheets()
        new_pm = update_posts_master(sh, us_data, "US Posts Master")
        time.sleep(1)
        update_d60_tracker(sh, us_data, "US D+60 Tracker")

        summary["us"] = {
            "ig_count": len(ig_norm), "tt_count": len(tt_norm),
            "total": len(us_data), "creators": len(us_creators),
            "new_posts": new_pm, "d60_updated": True,
        }

    # --- JP ---
    if region in ("all", "jp"):
        print("\n===== JP Pipeline =====")

        if dry_run:
            jp_path = max(OUTPUT_DIR.glob("*_jp_tagged*.json"), key=os.path.getmtime, default=None)
            jp_raw = json.load(open(jp_path, encoding="utf-8")) if jp_path else []
            print(f"[DRY] Loaded {len(jp_raw)} from {jp_path}")
        else:
            jp_raw = fetch_ig_tagged(client, JP_TAGGED_URLS, limit=500)
            save_json(jp_raw, "jp_tagged_raw")

        jp_norm = normalize_ig(jp_raw)
        jp_creators = set(d["username"] for d in jp_norm)
        print(f"[JP] Total: {len(jp_norm)} posts, {len(jp_creators)} creators")

        sh, creds = get_sheets()
        new_pm = update_posts_master(sh, jp_norm, "JP Posts Master")
        time.sleep(1)
        update_d60_tracker(sh, jp_norm, "JP D+60 Tracker")

        summary["jp"] = {
            "ig_count": len(jp_norm), "total": len(jp_norm),
            "creators": len(jp_creators), "new_posts": new_pm,
            "d60_updated": True,
        }

    # Summary
    print("\n===== Daily Summary =====")
    print(f"Date: {TODAY}")
    for k, v in summary.items():
        print(f"  {k.upper()}: {v['total']} posts, {v['creators']} creators, +{v['new_posts']} new")

    # Email
    if send_mail and summary:
        send_email(summary)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Apify Content Pipeline")
    parser.add_argument("--daily", action="store_true", help="Run daily pipeline")
    parser.add_argument("--region", default="all", choices=["all", "us", "jp"])
    parser.add_argument("--dry-run", action="store_true", help="Use cached JSON, no API calls")
    parser.add_argument("--no-email", action="store_true", help="Skip email notification")
    args = parser.parse_args()

    if args.daily:
        run_daily(region=args.region, dry_run=args.dry_run, send_mail=not args.no_email)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
