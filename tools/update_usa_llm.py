"""
USA_LLM Tab Updater
====================
Apify test 시트의 US Posts Master 데이터를 읽어
Grosmimi SNS 시트의 USA_LLM 탭을 갱신.

하이라이트 감지:
  - 지난 24시간 내 업로드된 포스트 (뷰 순 정렬)

결과를 .tmp/usa_llm_highlights.json 에 저장 → 이메일 보고에 포함.

Usage:
  python tools/update_usa_llm.py
  python tools/update_usa_llm.py --dry-run
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

load_env()

import gspread
from google.oauth2.service_account import Credentials

APIFY_SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
SNS_SHEET_ID   = "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"
LLM_TAB        = "USA_LLM"

PREV_METRICS_PATH = PROJECT_ROOT / ".tmp" / "usa_llm_prev.json"
HIGHLIGHTS_PATH   = PROJECT_ROOT / ".tmp" / "usa_llm_highlights.json"

HIGHLIGHTS_WINDOW_HOURS = 24   # show posts uploaded within last N hours


def to_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0


def load_us_posts_master(sh_apify):
    ws = sh_apify.worksheet("US Posts Master")
    vals = ws.get_all_values()
    if not vals:
        return []

    h = vals[0]
    def ci(name):
        try: return h.index(name)
        except ValueError: return None

    url_col   = ci("URL")
    user_col  = ci("Username")
    nick_col  = ci("Nickname")
    date_col  = ci("Post Date")
    comm_col  = ci("Comments")
    like_col  = ci("Likes")
    view_col  = ci("Views")
    foll_col  = ci("Followers")
    hash_col  = ci("Hashtags")

    posts = []
    for row in vals[1:]:
        def get(col):
            return row[col] if col is not None and col < len(row) else ""

        username = get(user_col).lower().strip()
        if not username:
            continue

        url = get(url_col)
        if url.startswith("=HYPERLINK("):
            try: url = url.split('"')[1]
            except Exception: pass

        posts.append({
            "username":  username,
            "nickname":  get(nick_col),
            "followers": get(foll_col),
            "url":       url,
            "date":      get(date_col),
            "comments":  to_int(get(comm_col)),
            "likes":     to_int(get(like_col)),
            "views":     to_int(get(view_col)),
            "hashtags":  get(hash_col),
        })

    return posts


def aggregate_by_user(posts):
    """최신 포스트 기준으로 유저별 집계"""
    by_user = {}
    for p in posts:
        u = p["username"]
        if u not in by_user:
            by_user[u] = {
                "username":     u,
                "nickname":     p["nickname"],
                "followers":    p["followers"],
                "latest_date":  p["date"],
                "latest_url":   p["url"],
                "total_views":  0,
                "total_likes":  0,
                "total_comments": 0,
                "post_count":   0,
            }
        by_user[u]["total_views"]    += p["views"]
        by_user[u]["total_likes"]    += p["likes"]
        by_user[u]["total_comments"] += p["comments"]
        by_user[u]["post_count"]     += 1
        if p["date"] > by_user[u]["latest_date"]:
            by_user[u]["latest_date"] = p["date"]
            by_user[u]["latest_url"]  = p["url"]
            by_user[u]["nickname"]    = p["nickname"]

    return sorted(by_user.values(), key=lambda x: x["total_views"], reverse=True)


def detect_highlights(posts):
    """지난 24시간 내 업로드된 포스트만 뷰 순으로 반환."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=HIGHLIGHTS_WINDOW_HOURS)
    seen_urls = set()
    highlights = []

    for p in posts:
        url = p["url"]
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        date_str = p.get("date", "")
        if not date_str:
            continue

        # Parse post date — try several common formats
        date_obj = None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                date_obj = datetime.strptime(date_str[:len(fmt)], fmt).replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue

        if date_obj is None:
            continue

        if date_obj < cutoff:
            continue

        highlights.append({
            "username":   p["username"],
            "nickname":   p["nickname"],
            "url":        url,
            "date":       date_str,
            "views":      p["views"],
            "hashtags":   p.get("hashtags", ""),
        })

    # 뷰 높은 순 정렬
    highlights.sort(key=lambda x: x["views"], reverse=True)
    return highlights


def write_llm_tab(sh_sns, aggregated, dry_run=False):
    headers = [
        "Username", "Nickname", "Followers",
        "Latest Post Date", "Latest Post URL",
        "Total Views", "Total Likes", "Total Comments", "Post Count",
        "Updated At",
    ]
    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    rows = [headers]
    for row in aggregated:
        url = row["latest_url"]
        url_formula = f'=HYPERLINK("{url}","view post")' if url else ""
        rows.append([
            row["username"],
            row["nickname"],
            row["followers"],
            row["latest_date"],
            url_formula,
            row["total_views"],
            row["total_likes"],
            row["total_comments"],
            row["post_count"],
            today,
        ])

    if dry_run:
        print(f"[DRY RUN] Would write {len(rows)-1} rows to {LLM_TAB}")
        return

    try:
        ws = sh_sns.worksheet(LLM_TAB)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh_sns.add_worksheet(LLM_TAB, rows=len(rows) + 50, cols=len(headers))

    if len(rows) + 5 > ws.row_count:
        ws.add_rows(len(rows) - ws.row_count + 50)

    for i in range(0, len(rows), 100):
        ws.update(
            range_name=f"A{i+1}",
            values=rows[i:i+100],
            value_input_option="USER_ENTERED",
        )
        time.sleep(0.3)

    print(f"[USA_LLM] {len(rows)-1}명 업데이트 완료")


def run(dry_run=False):
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)

    sh_apify = gc.open_by_key(APIFY_SHEET_ID)
    sh_sns   = gc.open_by_key(SNS_SHEET_ID)

    print("[1] US Posts Master 로드...")
    posts = load_us_posts_master(sh_apify)
    print(f"    포스트: {len(posts)}개")

    print("[2] 유저별 집계...")
    aggregated = aggregate_by_user(posts)
    print(f"    크리에이터: {len(aggregated)}명")

    print("[3] 하이라이트 감지... (최근 24시간 업로드, 뷰 순)")
    highlights = detect_highlights(posts)
    print(f"    하이라이트: {len(highlights)}건")
    for h in highlights:
        print(f"    @{h['username']} ({h['date']}): {h['views']:,} views")

    print("[4] USA_LLM 탭 업데이트...")
    write_llm_tab(sh_sns, aggregated, dry_run=dry_run)


    # 하이라이트 저장
    HIGHLIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HIGHLIGHTS_PATH.write_text(json.dumps({
        "highlights": highlights,
        "total_creators": len(aggregated),
        "total_posts": len(posts),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return highlights, aggregated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
