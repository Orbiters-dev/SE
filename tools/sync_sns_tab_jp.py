"""Sync SNS JP Tab - Syncly JP content metrics -> Google Sheet.

Content-only tracking for Grosmimi Japan influencers.
No Shopify orders — purely Syncly D+60 Tracker data.

Reads:
  - Syncly D+60 Tracker Google Sheet (JP Posts Master + JP D+60 Tracker tabs)

Writes:
  - Target Google Sheet -> "SNS JP" tab

Usage:
  python tools/sync_sns_tab_jp.py
  python tools/sync_sns_tab_jp.py --dry-run
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from env_loader import load_env

# ── Sheet IDs ──────────────────────────────────────────────────────────────
DEFAULT_SYNCLY_SHEET_ID = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"
DEFAULT_TARGET_SHEET_ID = "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
SNS_TAB = "SNS JP"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Headers ────────────────────────────────────────────────────────────────
SNS_JP_HEADERS = [
    "No", "Channel", "Name", "Account",
    "Content Link", "Post Date",
    "D+ Days", "Curr Comment", "Curr Like", "Curr View",
    "Profile URL",
]

# ── Helpers ────────────────────────────────────────────────────────────────

def get_credentials():
    load_env()
    sa_path = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json"
    )
    if not os.path.isabs(sa_path):
        sa_path = str(PROJECT_ROOT / sa_path)
    return Credentials.from_service_account_file(sa_path, scopes=SCOPES)


def safe_int(val):
    if not val or val in ("N/A", "TBU", ""):
        return 0
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return 0


def fmt_number(n):
    if n >= 1000:
        return f"{n:,}"
    return str(n)


def col_letter(idx):
    result = ""
    while True:
        result = chr(65 + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


# ── Data Loading ───────────────────────────────────────────────────────────

def load_syncly_jp(gc, sheet_id):
    """Read JP Posts Master + JP D+60 Tracker from Syncly sheet."""
    sh = gc.open_by_key(sheet_id)

    # JP Posts Master: platform/username mapping
    pm_ws = sh.worksheet("JP Posts Master")
    pm_rows = pm_ws.get_all_values()
    posts_master = []
    for row in pm_rows[1:]:
        if not row[0]:
            continue
        posts_master.append({
            "post_id": row[0],
            "url": row[1] if len(row) > 1 else "",
            "platform": row[2] if len(row) > 2 else "",
            "username": row[3] if len(row) > 3 else "",
            "nickname": row[4] if len(row) > 4 else "",
            "followers": row[5] if len(row) > 5 else "",
            "content": row[6] if len(row) > 6 else "",
            "hashtags": row[7] if len(row) > 7 else "",
            "brand": row[9] if len(row) > 9 else "",
            "post_date": row[12] if len(row) > 12 else "",
        })

    # JP D+60 Tracker: metrics
    tr_ws = sh.worksheet("JP D+60 Tracker")
    tr_rows = tr_ws.get_all_values()
    tracker = []
    for row in tr_rows[2:]:  # skip 2 header rows
        if not row[0]:
            continue
        tracker.append({
            "post_id": row[0],
            "url": row[1],
            "username": row[2],
            "post_date": row[3],
            "d_plus_days": safe_int(row[4]) if len(row) > 4 else 0,
            "curr_comment": safe_int(row[5]) if len(row) > 5 else 0,
            "curr_like": safe_int(row[6]) if len(row) > 6 else 0,
            "curr_view": safe_int(row[7]) if len(row) > 7 else 0,
        })

    return {"posts_master": posts_master, "tracker": tracker}


# ── Row building ───────────────────────────────────────────────────────────

def build_rows(syncly_data):
    """Build SNS JP tab rows from Syncly data only (no Shopify)."""
    posts_master = syncly_data["posts_master"]
    tracker = syncly_data["tracker"]

    # Build username -> platform map from Posts Master
    platform_map = {}
    nickname_map = {}  # username -> nickname
    for post in posts_master:
        uname = post["username"].lower().strip()
        if uname:
            platform_map[uname] = post["platform"].lower()
            if post["nickname"].strip():
                nickname_map[uname] = post["nickname"].strip()

    # Group tracker posts by username, pick best (latest) per user
    by_username = {}
    for post in tracker:
        uname = post["username"].lower().strip()
        if not uname:
            continue
        if uname not in by_username:
            by_username[uname] = []
        by_username[uname].append(post)

    rows = []
    stats = {"total": 0, "with_metrics": 0}

    # Sort usernames by latest post date desc
    sorted_users = sorted(
        by_username.keys(),
        key=lambda u: max(p.get("post_date", "") for p in by_username[u]),
        reverse=True,
    )

    for uname in sorted_users:
        user_posts = by_username[uname]

        # Best post = latest
        best = max(user_posts, key=lambda p: p.get("post_date", ""))

        # Channel from platform
        plat = platform_map.get(uname, "")
        if "instagram" in plat:
            channel = "Instagram"
        elif "tiktok" in plat:
            channel = "TikTok"
        elif "youtube" in plat:
            channel = "YouTube"
        else:
            channel = "Instagram"  # default for JP (mostly IG)

        # Name = nickname, Account = @username
        name = nickname_map.get(uname, uname)
        account = f"@{uname}"

        # Content link
        url = best["url"]
        post_count = len(user_posts)
        label = "View Post"
        if post_count > 1:
            label = f"View Post (+{post_count - 1})"
        content_link = f'=HYPERLINK("{url}","{label}")'

        # Override channel from content link URL (most accurate signal)
        if "tiktok.com" in url:
            channel = "TikTok"
        elif "instagram.com" in url:
            channel = "Instagram"
        elif "youtube.com" in url or "youtu.be" in url:
            channel = "YouTube"

        # Post date
        post_date = best.get("post_date", "")[:10]

        # Metrics
        d_days = best["d_plus_days"]
        cmt = best["curr_comment"]
        like = best["curr_like"]
        view = best["curr_view"]

        has_metrics = any(v > 0 for v in [d_days, cmt, like, view])
        if has_metrics:
            stats["with_metrics"] += 1

        # Profile URL (based on channel, which is already corrected by content link URL)
        profile_url = ""
        if "instagram" in channel.lower():
            profile_url = f"https://www.instagram.com/{uname}/"
        elif "tiktok" in channel.lower():
            profile_url = f"https://www.tiktok.com/@{uname}"

        stats["total"] += 1

        rows.append([
            "",             # A: No (filled later)
            channel,        # B: Channel
            name,           # C: Name (nickname)
            account,        # D: Account (@username)
            content_link,   # E: Content Link
            post_date,      # F: Post Date
            d_days,         # G: D+ Days
            cmt,            # H: Curr Comment
            like,           # I: Curr Like
            view,           # J: Curr View
            profile_url,    # K: Profile URL
        ])

    # Fill sequential No
    for i, row in enumerate(rows, 1):
        row[0] = i

    return rows, stats


# ── Cross-check validation ────────────────────────────────────────────────

def cross_check(rows):
    """Validate JP data integrity."""
    issues = {
        "link_no_metrics": [],
        "channel_link_mismatch": [],
    }

    for row in rows:
        row_no = row[0]
        channel = str(row[1]).strip()
        name = str(row[2]).strip()
        account = str(row[3]).strip()
        content_link = str(row[4]).strip()
        d_days = row[6]
        cmt = row[7]
        like = row[8]
        view = row[9]

        link_url = ""
        link_match = re.search(r'HYPERLINK\("([^"]+)"', content_link, re.IGNORECASE)
        if link_match:
            link_url = link_match.group(1)

        has_metrics = any(safe_int(v) > 0 for v in [d_days, cmt, like, view])
        info = {"row_no": row_no, "name": name, "account": account}

        # Content Link exists but all metrics zero
        if link_url and not has_metrics:
            issues["link_no_metrics"].append({
                **info, "detail": f"D+={d_days} cmt={cmt} like={like} view={view}"})

        # Channel vs Content Link domain mismatch
        if link_url and channel:
            ch_lower = channel.lower()
            if "instagram.com" in link_url and "instagram" not in ch_lower:
                issues["channel_link_mismatch"].append({
                    **info, "detail": f"channel={channel} but link is Instagram"})
            elif "tiktok.com" in link_url and "tiktok" not in ch_lower:
                issues["channel_link_mismatch"].append({
                    **info, "detail": f"channel={channel} but link is TikTok"})

    return issues


def print_cross_check(issues):
    labels = {
        "link_no_metrics": "Content Link exists but all metrics = 0",
        "channel_link_mismatch": "Channel vs Content Link domain mismatch",
    }
    total = sum(len(v) for v in issues.values())
    print("\n" + "=" * 60)
    print("  CROSS-CHECK VALIDATION (JP)")
    print("=" * 60)
    if total == 0:
        print("  All checks passed!")
        print("=" * 60 + "\n")
        return
    print(f"  Total issues: {total}\n")
    for key, label in labels.items():
        items = issues[key]
        if not items:
            continue
        print(f"  [{len(items)}] {label}")
        for item in items[:10]:
            print(f"    Row {item['row_no']}: {item['name']} ({item['account']}) - {item['detail']}")
        print()
    print("=" * 60 + "\n")


# ── Sheet writing ──────────────────────────────────────────────────────────

def write_to_sheet(gc, target_sheet_id, rows, dry_run=False):
    """Write rows to the SNS JP tab."""
    if dry_run:
        print(f"\n[DRY-RUN] Would write {len(rows)} rows to {SNS_TAB}")
        print(f"[DRY-RUN] Target sheet: {target_sheet_id}")
        print(f"\n--- Sample rows (first 10) ---")
        for row in rows[:10]:
            display = []
            for cell in row:
                s = str(cell)
                if len(s) > 50:
                    s = s[:47] + "..."
                display.append(s)
            print(f"  {display}")
        return

    sh = gc.open_by_key(target_sheet_id)

    try:
        ws = sh.worksheet(SNS_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SNS_TAB, rows=max(len(rows) + 10, 100), cols=len(SNS_JP_HEADERS))

    needed_rows = len(rows) + 3
    needed_cols = len(SNS_JP_HEADERS)
    if ws.row_count < needed_rows:
        ws.resize(rows=needed_rows)
    if ws.col_count < needed_cols:
        ws.resize(cols=needed_cols)

    # Headers in Row 2
    end_hdr = col_letter(len(SNS_JP_HEADERS) - 1)
    ws.update(values=[SNS_JP_HEADERS], range_name=f"A2:{end_hdr}2", value_input_option="RAW")

    # Clear data rows
    if ws.row_count > 2:
        end_col = col_letter(needed_cols - 1)
        ws.batch_clear([f"A3:{end_col}{ws.row_count}"])

    # Write data
    if rows:
        end_col = col_letter(len(rows[0]) - 1)
        data_range = f"A3:{end_col}{len(rows) + 2}"
        ws.update(values=rows, range_name=data_range, value_input_option="USER_ENTERED")

    # Format
    format_sns_jp_tab(sh, ws, len(rows))

    url = f"https://docs.google.com/spreadsheets/d/{target_sheet_id}/edit#gid={ws.id}"
    print(f"[DONE] {SNS_TAB} tab updated: {url}")
    return url


def format_sns_jp_tab(sh, ws, num_rows):
    """Apply formatting to the SNS JP tab."""
    requests = []

    # Header row: dark bg, white bold
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": ws.id,
                "startRowIndex": 1, "endRowIndex": 2,
                "startColumnIndex": 0, "endColumnIndex": len(SNS_JP_HEADERS),
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.11, "green": 0.15, "blue": 0.27},
                    "textFormat": {
                        "bold": True, "fontSize": 10,
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat",
        }
    })

    # Column widths
    col_widths = [40, 80, 150, 160, 160, 90, 65, 80, 80, 80, 200]
    for i, w in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "COLUMNS",
                    "startIndex": i, "endIndex": i + 1,
                },
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })

    # Freeze rows 1-2
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 2}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Alternating row colors
    if num_rows > 0:
        try:
            requests.append({
                "addBanding": {
                    "bandedRange": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 2, "endRowIndex": num_rows + 2,
                            "startColumnIndex": 0, "endColumnIndex": len(SNS_JP_HEADERS),
                        },
                        "rowProperties": {
                            "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                            "secondBandColor": {"red": 0.95, "green": 0.96, "blue": 0.98},
                        },
                    }
                }
            })
        except Exception:
            pass

    try:
        sh.batch_update({"requests": requests})
    except Exception as e:
        if "addBanding" in str(e) or "already" in str(e).lower():
            requests_no_band = [r for r in requests if "addBanding" not in r]
            if requests_no_band:
                sh.batch_update({"requests": requests_no_band})
        else:
            raise


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync SNS JP tab: Syncly JP content metrics"
    )
    parser.add_argument(
        "--target-sheet-id", default=DEFAULT_TARGET_SHEET_ID,
        help="Target Google Sheet ID"
    )
    parser.add_argument(
        "--syncly-sheet-id", default=DEFAULT_SYNCLY_SHEET_ID,
        help="Syncly D+60 Tracker Sheet ID"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    print("[1/2] Loading Syncly JP data...")
    creds = get_credentials()
    gc = gspread.authorize(creds)
    syncly_data = load_syncly_jp(gc, args.syncly_sheet_id)
    print(f"  JP Posts Master: {len(syncly_data['posts_master'])} posts")
    print(f"  JP D+60 Tracker: {len(syncly_data['tracker'])} posts")

    print("[2/2] Building SNS JP rows...")
    rows, stats = build_rows(syncly_data)
    print(f"  Total influencers: {stats['total']}")
    print(f"  With metrics: {stats['with_metrics']}")

    # Cross-check
    xc_issues = cross_check(rows)
    print_cross_check(xc_issues)

    write_to_sheet(gc, args.target_sheet_id, rows, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
