"""
Syncly → Apify test 시트 마이그레이션
======================================
Syncly US/JP Posts Master에 있는 포스트 중 Apify test 시트에 없는 것만 추가.
중복 기준: Post ID 또는 URL.
메트릭(Comments/Likes/Views)은 Syncly 값으로 초기화 (Apify daily가 이후 업데이트).

Usage:
  python tools/migrate_syncly_to_apify.py           # US + JP
  python tools/migrate_syncly_to_apify.py --region us
  python tools/migrate_syncly_to_apify.py --dry-run  # 확인만
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

load_env()

import gspread
from google.oauth2.service_account import Credentials

SYNCLY_SHEET_ID = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"
APIFY_SHEET_ID  = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"

# Apify Posts Master 컬럼 순서 (13개)
APIFY_HEADERS = [
    "Post ID", "URL", "Platform", "Username", "Nickname", "Followers",
    "Content", "Hashtags", "Tagged Account", "Post Date",
    "Comments", "Likes", "Views",
]

def get_sheets():
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh_syncly = gc.open_by_key(SYNCLY_SHEET_ID)
    sh_apify  = gc.open_by_key(APIFY_SHEET_ID)
    return sh_syncly, sh_apify


def migrate_region(sh_syncly, sh_apify, region="us", dry_run=False):
    prefix = region.upper()
    syncly_tab = f"{prefix} Posts Master"
    apify_tab  = f"{prefix} Posts Master"

    print(f"\n=== {prefix} Migration ===")

    # Syncly 읽기
    ws_s = sh_syncly.worksheet(syncly_tab)
    s_vals = ws_s.get_all_values()
    if not s_vals:
        print(f"[{prefix}] Syncly 시트 비어있음, 스킵")
        return 0

    s_header = s_vals[0]
    # 컬럼 인덱스 매핑
    def col(header, name):
        try:
            return header.index(name)
        except ValueError:
            return None

    s_pid_col  = col(s_header, "Post ID")
    s_url_col  = col(s_header, "URL")
    s_plat_col = col(s_header, "Platform")
    s_user_col = col(s_header, "Username")
    s_nick_col = col(s_header, "Nickname")
    s_foll_col = col(s_header, "Followers")
    s_cont_col = col(s_header, "Content")
    s_hash_col = col(s_header, "Hashtags")
    s_date_col = col(s_header, "Post Date")
    s_comm_col = col(s_header, "Comments")
    s_like_col = col(s_header, "Likes")
    s_view_col = col(s_header, "Views")

    def get(row, idx):
        return row[idx] if idx is not None and idx < len(row) else ""

    syncly_posts = []
    for row in s_vals[1:]:
        pid = get(row, s_pid_col)
        url = get(row, s_url_col)
        if not pid and not url:
            continue
        syncly_posts.append({
            "post_id":      pid,
            "url":          url,
            "platform":     get(row, s_plat_col),
            "username":     get(row, s_user_col),
            "nickname":     get(row, s_nick_col),
            "followers":    get(row, s_foll_col),
            "content":      get(row, s_cont_col),
            "hashtags":     get(row, s_hash_col),
            "tagged":       "",
            "post_date":    get(row, s_date_col),
            "comments":     get(row, s_comm_col),
            "likes":        get(row, s_like_col),
            "views":        get(row, s_view_col),
        })

    print(f"[{prefix}] Syncly 포스트: {len(syncly_posts)}개")

    # Apify 시트 읽기
    try:
        ws_a = sh_apify.worksheet(apify_tab)
        a_vals = ws_a.get_all_values()
    except gspread.WorksheetNotFound:
        print(f"[{prefix}] Apify 탭 없음, 스킵")
        return 0

    # 기존 post_id + url 세트
    existing_pids = set()
    existing_urls = set()
    for row in a_vals[1:]:
        if row and row[0]:
            existing_pids.add(row[0].strip())
        if len(row) > 1 and row[1]:
            # HYPERLINK 수식에서 URL 추출
            raw = row[1].strip()
            if raw.startswith('=HYPERLINK('):
                try:
                    url_part = raw.split('"')[1]
                    existing_urls.add(url_part)
                except:
                    pass
            else:
                existing_urls.add(raw)

    print(f"[{prefix}] Apify 기존: {len(a_vals)-1}행, {len(existing_pids)} post IDs")

    # 신규 포스트 필터
    new_posts = []
    for p in syncly_posts:
        pid = p["post_id"].strip()
        url = p["url"].strip()
        if pid and pid in existing_pids:
            continue
        if url and url in existing_urls:
            continue
        new_posts.append(p)

    print(f"[{prefix}] 신규 (Syncly only): {len(new_posts)}개")

    if not new_posts:
        print(f"[{prefix}] 추가할 포스트 없음")
        return 0

    if dry_run:
        print(f"[{prefix}] DRY RUN - skip actual write")
        for p in new_posts[:5]:
            print(f"  @{p['username']} | {p['url'][:60]}")
        if len(new_posts) > 5:
            print(f"  ... +{len(new_posts)-5}개 더")
        return len(new_posts)

    # Apify 시트에 append
    rows_to_add = []
    for p in new_posts:
        rows_to_add.append([
            p["post_id"],
            p["url"],
            p["platform"],
            p["username"],
            p["nickname"],
            p["followers"],
            p["content"],
            p["hashtags"],
            p["tagged"],
            p["post_date"],
            p["comments"],
            p["likes"],
            p["views"],
        ])

    next_row = len(a_vals) + 1
    required_rows = next_row + len(rows_to_add) - 1
    if required_rows > ws_a.row_count:
        ws_a.add_rows(required_rows - ws_a.row_count + 100)

    for i in range(0, len(rows_to_add), 80):
        ws_a.update(
            range_name=f"A{next_row + i}",
            values=rows_to_add[i:i+80],
            value_input_option="USER_ENTERED",
        )
        time.sleep(0.5)

    print(f"[{prefix}] {len(new_posts)}개 추가 완료 (행 {next_row}~{next_row+len(new_posts)-1})")
    return len(new_posts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="all", choices=["us", "jp", "all"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sh_syncly, sh_apify = get_sheets()

    total = 0
    if args.region in ("all", "us"):
        total += migrate_region(sh_syncly, sh_apify, "us", args.dry_run)
    if args.region in ("all", "jp"):
        total += migrate_region(sh_syncly, sh_apify, "jp", args.dry_run)

    print(f"\n총 {total}개 포스트 {'(dry run)' if args.dry_run else '추가됨'}")


if __name__ == "__main__":
    main()
