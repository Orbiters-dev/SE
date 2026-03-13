"""
USA_LLM Tab Updater
====================
Apify test 시트의 US Posts Master 데이터를 읽어
Grosmimi SNS 시트의 USA_LLM 탭을 갱신.

하이라이트 감지:
  - 전일 대비 조회수 30%+ 증가한 콘텐츠
  - 총 10만 뷰 이상 달성한 콘텐츠

결과를 .tmp/usa_llm_highlights.json 에 저장 → 이메일 보고에 포함.

Usage:
  python tools/update_usa_llm.py
  python tools/update_usa_llm.py --dry-run
"""

import argparse
import json
import sys
import time
from datetime import datetime
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

VIEW_INCREASE_THRESHOLD = 0.30   # 30%
VIEW_ABSOLUTE_THRESHOLD = 100000  # 10만


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

    url_col  = ci("URL")
    user_col = ci("Username")
    nick_col = ci("Nickname")
    date_col = ci("Post Date")
    comm_col = ci("Comments")
    like_col = ci("Likes")
    view_col = ci("Views")
    foll_col = ci("Followers")

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


def detect_highlights(aggregated, prev_metrics):
    highlights = []
    for row in aggregated:
        u = row["username"]
        cur_views = row["total_views"]
        prev_views = prev_metrics.get(u, {}).get("total_views", 0)

        reasons = []
        if cur_views >= VIEW_ABSOLUTE_THRESHOLD:
            reasons.append(f"100K+ 뷰 ({cur_views:,})")
        if prev_views > 0:
            change = (cur_views - prev_views) / prev_views
            if change >= VIEW_INCREASE_THRESHOLD:
                reasons.append(f"전일대비 +{change*100:.0f}% 조회수 증가 ({prev_views:,} → {cur_views:,})")

        if reasons:
            highlights.append({
                "username":    u,
                "nickname":    row["nickname"],
                "url":         row["latest_url"],
                "total_views": cur_views,
                "prev_views":  prev_views,
                "reasons":     reasons,
            })

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

    # 이전 메트릭 로드
    prev_metrics = {}
    if PREV_METRICS_PATH.exists():
        try:
            prev_metrics = json.loads(PREV_METRICS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    print("[3] 하이라이트 감지...")
    highlights = detect_highlights(aggregated, prev_metrics)
    print(f"    하이라이트: {len(highlights)}건")
    for h in highlights:
        print(f"    @{h['username']}: {', '.join(h['reasons'])}")

    print("[4] USA_LLM 탭 업데이트...")
    write_llm_tab(sh_sns, aggregated, dry_run=dry_run)

    # 현재 메트릭 저장 (다음 날 비교용)
    if not dry_run:
        new_prev = {row["username"]: {"total_views": row["total_views"]} for row in aggregated}
        PREV_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREV_METRICS_PATH.write_text(json.dumps(new_prev, ensure_ascii=False, indent=2), encoding="utf-8")

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
