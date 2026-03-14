"""
Grosmimi US SNS Tab Sync (Apify-based)
=======================================
Shopify 인플루언서 오더 기반으로 US SNS탭을 자동 동기화.
컨텐츠 링크/메트릭은 Apify test 시트(US Posts Master)에서만 참조.

필터 조건:
  - 2026-01-01 이후 shipped
  - Grosmimi 제품 포함
  - 금액 $0 또는 PR/influencer 태그
  - giveaway/valentine/event 제외

Logic:
  1. Shopify 오더 → 인플루언서 목록 추출
  2. Apify test 시트(US Posts Master)에서 username 매칭 → 최신 포스트 URL + 메트릭
  3. US SNS탭에:
     - 신규 인플루언서 행 추가
     - 기존 인플루언서 컨텐츠 링크/메트릭 업데이트

Usage:
  python tools/sync_sns_tab_grosmimi.py
  python tools/sync_sns_tab_grosmimi.py --dry-run
"""

import argparse
import json
import re
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
SNS_TAB        = "US SNS"

ORDERS_PATH = PROJECT_ROOT / ".tmp" / "polar_data" / "q10_influencer_orders.json"

EXCLUDE_TAGS  = {"giveaway", "valentine", "event"}
PR_TAGS       = {"pr", "influencer", "influencer-gifting", "igf", "free shipping (creator)"}
CUTOFF_DATE   = datetime(2026, 1, 1)


# ---------------------------------------------------------------------------
# Shopify 오더 파싱
# ---------------------------------------------------------------------------

def load_shopify_orders():
    data = json.loads(ORDERS_PATH.read_text(encoding="utf-8"))
    return data.get("orders", [])


def is_grosmimi_order(order):
    return any(
        "grosmimi" in (item.get("title") or "").lower()
        for item in order.get("line_items", [])
    )


def is_pr_order(order):
    tags  = (order.get("tags") or "").lower()
    price = float(order.get("total_price") or 0)
    return price == 0.0 or any(t in tags for t in PR_TAGS)


def is_excluded(order):
    tags = (order.get("tags") or "").lower()
    note = (order.get("note") or "").lower()
    return any(x in tags or x in note for x in EXCLUDE_TAGS)


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def extract_influencers(orders):
    """Shopify 오더 → {account_key: {name, ig_account, ship_date, product_types}}"""
    influencers = {}
    for o in orders:
        # 날짜 필터
        dt = parse_date(o.get("fulfilled_at") or o.get("created_at"))
        if not dt or dt.replace(tzinfo=None) < CUTOFF_DATE:
            continue

        if not is_grosmimi_order(o):
            continue
        if not is_pr_order(o):
            continue
        if is_excluded(o):
            continue

        # fulfillment 확인
        if not o.get("fulfilled_at") and o.get("fulfillment_status") not in ("fulfilled", "partial"):
            continue

        note     = o.get("note") or ""
        cname    = (o.get("customer_name") or "").strip()
        accounts = re.findall(r"@([\w.]+)", note)
        ig_acc   = accounts[0].lower() if accounts else ""
        key      = ig_acc if ig_acc else cname.lower()
        SKIP_KEYS = {"wj test", "flowtest", "william choi (test)"}
        if not key or any(s in key for s in SKIP_KEYS):
            continue

        # 제품 타입
        product_types = []
        for item in o.get("line_items", []):
            title = (item.get("title") or "").lower()
            if "straw cup" in title:
                pt = "PPSU Straw Cup" if "ppsu" in title else "Stainless Straw Cup"
            elif "tumbler" in title:
                pt = "PPSU Tumbler" if "ppsu" in title else "Stainless Tumbler"
            elif "bottle" in title:
                pt = "PPSU Baby Bottle"
            elif "accessory" in title or "replacement" in title or "straw" in title:
                pt = "Accessory"
            else:
                pt = ""
            if pt and pt not in product_types:
                product_types.append(pt)

        ship_date = dt.strftime("%Y-%m-%d") if dt else ""

        if key not in influencers:
            influencers[key] = {
                "name":     cname,
                "ig":       ig_acc,
                "ship_date": ship_date,
                "products": product_types,
            }
        else:
            # 최신 ship_date 유지
            if ship_date > influencers[key]["ship_date"]:
                influencers[key]["ship_date"] = ship_date
            for pt in product_types:
                if pt not in influencers[key]["products"]:
                    influencers[key]["products"].append(pt)

    return influencers


# ---------------------------------------------------------------------------
# Apify 시트에서 컨텐츠 조회
# ---------------------------------------------------------------------------

def load_apify_content(sh_apify):
    """US Posts Master → {username: [post_dicts sorted by date desc]}"""
    ws = sh_apify.worksheet("US Posts Master")
    vals = ws.get_all_values()
    if not vals:
        return {}

    h = vals[0]
    def ci(name):
        try: return h.index(name)
        except ValueError: return None

    url_col  = ci("URL")
    user_col = ci("Username")
    date_col = ci("Post Date")
    comm_col = ci("Comments")
    like_col = ci("Likes")
    view_col = ci("Views")

    by_user = {}
    for row in vals[1:]:
        def get(col):
            return row[col] if col is not None and col < len(row) else ""

        username = get(user_col).lower().strip()
        if not username:
            continue

        url = get(url_col)
        # HYPERLINK 수식에서 URL 추출
        if url.startswith("=HYPERLINK("):
            try:
                url = url.split('"')[1]
            except Exception:
                pass

        if username not in by_user:
            by_user[username] = []
        by_user[username].append({
            "url":      url,
            "date":     get(date_col),
            "comments": get(comm_col),
            "likes":    get(like_col),
            "views":    get(view_col),
        })

    # 날짜 내림차순 정렬
    for posts in by_user.values():
        posts.sort(key=lambda x: x["date"] or "", reverse=True)

    return by_user


# ---------------------------------------------------------------------------
# US SNS탭 읽기/쓰기
# ---------------------------------------------------------------------------

def load_sns_tab(sh_sns):
    ws = sh_sns.worksheet(SNS_TAB)
    vals = ws.get_all_values()
    # 헤더는 2번째 행 (1번째 행은 병합된 빈 행)
    header = vals[1] if len(vals) > 1 else []
    return ws, vals, header


def col_idx(header, name):
    try:
        return header.index(name)
    except ValueError:
        return None


def sync(dry_run=False):
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "credentials" / "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)

    sh_apify = gc.open_by_key(APIFY_SHEET_ID)
    sh_sns   = gc.open_by_key(SNS_SHEET_ID)

    print("[1] Shopify 오더 로드...")
    orders      = load_shopify_orders()
    influencers = extract_influencers(orders)
    print(f"    필터 후 인플루언서: {len(influencers)}명")

    print("[2] Apify 컨텐츠 시트 로드...")
    apify_content = load_apify_content(sh_apify)
    print(f"    크리에이터: {len(apify_content)}명")

    print("[3] US SNS탭 로드...")
    ws_sns, sns_vals, header = load_sns_tab(sh_sns)

    # 컬럼 인덱스
    acc_col     = col_idx(header, "Account")
    name_col    = col_idx(header, "Name")
    ship_col    = col_idx(header, "Shipping Date")
    link_col    = col_idx(header, "Content Link")
    comm_col    = col_idx(header, "Curr Comment")
    like_col    = col_idx(header, "Curr Like")
    view_col    = col_idx(header, "Curr View")
    pt1_col     = col_idx(header, "Product Type1")
    pt2_col     = col_idx(header, "Product Type2")
    pt3_col     = col_idx(header, "Product Type3")
    ch_col      = col_idx(header, "Channel")
    no_col      = col_idx(header, "No")
    ddays_col   = col_idx(header, "D+Days") or col_idx(header, "D+days") or col_idx(header, "D+ Days")

    print(f"    현재 행수: {len(sns_vals)-2}")

    # 기존 인플루언서 맵 (account → row index 1-based)
    existing = {}
    for i, row in enumerate(sns_vals[2:], start=3):  # 1-based, 헤더2행 제외
        acc = row[acc_col].lstrip("@").lower() if acc_col is not None and acc_col < len(row) else ""
        if acc:
            existing[acc] = i

    # 신규/업데이트 분류
    to_add    = []
    to_update = []

    for key, info in influencers.items():
        ig    = info["ig"] or key
        posts = apify_content.get(ig, [])
        latest = posts[0] if posts else None

        content_url = latest["url"] if latest else ""
        comments    = latest["comments"] if latest else ""
        likes       = latest["likes"] if latest else ""
        views       = latest["views"] if latest else ""

        pts = info["products"]

        if ig in existing or key in existing:
            row_num = existing.get(ig) or existing.get(key)
            to_update.append({
                "row": row_num,
                "content_url": content_url,
                "comments": comments, "likes": likes, "views": views,
            })
        else:
            to_add.append({
                "name":        info["name"],
                "ig":          ig,
                "ship_date":   info["ship_date"],
                "products":    pts,
                "content_url": content_url,
                "comments":    comments, "likes": likes, "views": views,
            })

    print(f"    신규 추가: {len(to_add)}명 / 업데이트: {len(to_update)}명")
    with_content = sum(1 for x in to_add if x["content_url"])
    print(f"    신규 중 컨텐츠 링크 있음: {with_content}명")

    if dry_run:
        print("\n[DRY RUN] 실제 쓰기 스킵")
        print("신규 샘플 5명:")
        for x in to_add[:5]:
            print(f"  @{x['ig']} / {x['name']} / {x['ship_date']} / link={bool(x['content_url'])}")
        return

    # 업데이트: 컨텐츠 링크 + 메트릭 (컨텐츠 있는 경우만)
    batch_updates = []
    for upd in to_update:
        if not upd["content_url"]:
            continue
        row = upd["row"]
        if link_col is not None:
            batch_updates.append({
                "range": f"'{SNS_TAB}'!{chr(65+link_col)}{row}",
                "values": [[f'=HYPERLINK("{upd["content_url"]}","view post")']],
            })
        for col, val in [(comm_col, upd["comments"]), (like_col, upd["likes"]), (view_col, upd["views"])]:
            if col is not None and val:
                batch_updates.append({
                    "range": f"'{SNS_TAB}'!{chr(65+col)}{row}",
                    "values": [[val]],
                })

    if batch_updates:
        for i in range(0, len(batch_updates), 200):
            ws_sns.spreadsheet.values_batch_update({
                "valueInputOption": "USER_ENTERED",
                "data": batch_updates[i:i+200],
            })
            time.sleep(0.5)
        print(f"[UPDATE] {len(to_update)}명 메트릭/링크 업데이트 완료")

    # 신규 행 추가
    if to_add:
        # 현재 No 최대값
        max_no = 0
        for row in sns_vals[2:]:
            if no_col is not None and no_col < len(row) and row[no_col].isdigit():
                max_no = max(max_no, int(row[no_col]))

        next_row = len(sns_vals) + 1
        new_rows = []
        for x in to_add:
            row_data = [""] * len(header)
            pts = x["products"]

            def set_col(col, val):
                if col is not None and col < len(row_data):
                    row_data[col] = val

            max_no += 1
            set_col(no_col, str(max_no))
            set_col(ch_col, "Instagram" if x["ig"] else "")
            set_col(name_col, x["name"])
            set_col(acc_col, f"@{x['ig']}" if x["ig"] else "")
            set_col(pt1_col, pts[0] if len(pts) > 0 else "")
            set_col(pt2_col, pts[1] if len(pts) > 1 else "")
            set_col(pt3_col, pts[2] if len(pts) > 2 else "")
            set_col(ship_col, x["ship_date"])
            # D+days formula: days since ship date
            if ddays_col is not None and ship_col is not None and x["ship_date"]:
                ship_letter = chr(65 + ship_col)
                row_num_new = next_row + len(new_rows)
                set_col(ddays_col, f'=TODAY()-DATEVALUE({ship_letter}{row_num_new})')
            if x["content_url"]:
                set_col(link_col, f'=HYPERLINK("{x["content_url"]}","view post")')
            set_col(comm_col, x["comments"])
            set_col(like_col, x["likes"])
            set_col(view_col, x["views"])

            new_rows.append(row_data)

        if next_row + len(new_rows) > ws_sns.row_count:
            ws_sns.add_rows(len(new_rows) + 50)

        for i in range(0, len(new_rows), 50):
            ws_sns.update(
                range_name=f"A{next_row + i}",
                values=new_rows[i:i+50],
                value_input_option="USER_ENTERED",
            )
            time.sleep(0.5)
        print(f"[ADD] {len(to_add)}명 신규 추가 완료")

    print("\n[DONE] US SNS 동기화 완료")

    # 기간별 신규 카운트 (ship_date 기준)
    now = datetime.now(tz=timezone.utc)
    def count_new_within(days):
        cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        return sum(1 for info in influencers.values() if info.get("ship_date", "") >= cutoff)

    # 요약 저장
    summary = {
        "new_count":    len(to_add),
        "new_24h":      count_new_within(1),
        "new_7d":       count_new_within(7),
        "new_30d":      count_new_within(30),
        "update_count": len(to_update),
        "with_content": sum(1 for x in to_add if x["content_url"]),
        "total_influencers": len(influencers),
    }
    summary_path = PROJECT_ROOT / ".tmp" / "apify_sns_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
