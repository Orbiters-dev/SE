"""
sync_wl_codes_notion.py — WL code + 게시물 URL Google Sheets → Notion UPDATE

기존 Notion 페이지(인스타 핸들로 pre-made 슬롯)를 찾아서
WL code + 링크 칸만 업데이트한다. 새 페이지 생성 안 함.

매칭 키: Notion 'instagram handle ' (email 필드, '@xxx' 형식)
      ↔ Sheet Creator ID ('xxx', @ 없음)

Source:
  Google Sheet 1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU, tab "Grosmimi"
  Col 2 = Creator name, Col 3 = Creator ID, Col 15 = WL code, Col 16 = URL

Target:
  Notion DB f4586c6dc04683e4bd0a01cfbdd39771 (Meta Ads JP)
  Data source 23f86c6d-c046-8393-ac65-078ed9ebee05 (Ads Campaign List)

Usage:
  python tools/sync_wl_codes_notion.py --dry-run
  python tools/sync_wl_codes_notion.py --sync
"""

import argparse
import io
import os
import re
import sys

import gspread
import requests
from apify_client import ApifyClient
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_API_TOKEN")
NOTION_VERSION = "2025-09-03"
DATA_SOURCE_ID = "23f86c6d-c046-8393-ac65-078ed9ebee05"

SHEET_ID = "1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU"
TAB_GID = 386147805

GOOGLE_SA_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")

COL_CREATOR_ID = 3
COL_PRODUCT = 6
COL_STATUS = 8
COL_WL = 15
COL_URL = 16

HANDLE_PROP = "instagram handle "  # 뒤에 공백 있음
WL_PROP = "WL code"
LINK_PROP = "링크"
POST_DATE_PROP = "Post Date"
GASI_PROP = "게시일(지선) "  # 뒤에 공백 있음


def extract_wl_codes(s: str) -> list[str]:
    """셀에서 모든 adcode-* 패턴 추출. ①②③ 마커나 개행으로 분리됐어도 모두 캡처."""
    return re.findall(r"adcode-[A-Za-z0-9_\-]+", s or "")


def extract_urls(s: str) -> list[str]:
    """셀에서 모든 https?:// URL 추출."""
    return re.findall(r"https?://\S+", s or "")


def map_product(product_text: str) -> list[str]:
    """Sheet Product 텍스트 → Notion 다중 선택 (1) 값 리스트."""
    p = product_text.lower()
    result = []
    if "ppsu" in p:
        result.append("PPSU")
    if "flip" in p:
        result.append("Flip top")
    if "stain" in p:
        result.append("Stainless")
    if "빨대" in product_text or "straw" in p:
        result.append("빨대")
    return result


def fetch_ig_post_date(url: str) -> str | None:
    """Instagram URL → 게시 날짜 (YYYY-MM-DD). Apify apify/instagram-scraper 사용."""
    token = os.getenv("APIFY_API_TOKEN")
    if not token or not url:
        return None
    try:
        client = ApifyClient(token)
        run = client.actor("apify/instagram-scraper").call(
            run_input={"directUrls": [url], "resultsLimit": 1, "resultsType": "posts"},
            timeout_secs=90,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if items:
            ts = items[0].get("timestamp", "")
            return ts[:10] if ts else None
    except Exception as e:
        print(f"  [IG date] 실패: {e}")
    return None


# 진행 상태 = 항상 "예정 또는 진행중"으로 고정 (세은 명시 규칙 2026-04-20)
FIXED_STATUS = "예정 또는 진행중"


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_sheet_rows():
    creds = Credentials.from_service_account_file(
        GOOGLE_SA_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = next(w for w in sh.worksheets() if w.id == TAB_GID)
    return ws.get_all_values()


def fetch_all_notion_pages() -> list[dict]:
    pages = []
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query",
            headers=notion_headers(),
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return pages


def normalize_handle(s: str) -> str:
    """'@creator_id' or 'creator_id' → 'creator_id' (lowercase, stripped)"""
    return (s or "").strip().lstrip("@").lower()


def index_pages_by_handle(pages: list[dict]) -> dict:
    """
    handle → list of page dicts (with existing wl_code, link)
    """
    idx = {}
    for p in pages:
        handle = p.get("properties", {}).get(HANDLE_PROP, {}).get("email", "") or ""
        key = normalize_handle(handle)
        if not key:
            continue
        wl = "".join(x.get("plain_text", "") for x in p.get("properties", {}).get(WL_PROP, {}).get("rich_text", []))
        link = p.get("properties", {}).get(LINK_PROP, {}).get("url", "") or ""
        idx.setdefault(key, []).append({
            "id": p["id"],
            "wl": wl.strip(),
            "link": link.strip(),
        })
    return idx


def update_page(page_id: str, wl_code: str, url: str, post_date: str | None = None):
    props = {
        WL_PROP: {"rich_text": [{"text": {"content": wl_code}}]},
        LINK_PROP: {"url": url},
    }
    if post_date:
        props[POST_DATE_PROP] = {"date": {"start": post_date}}
    r = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=notion_headers(),
        json={"properties": props},
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Notion update failed [{r.status_code}]: {r.text[:300]}")


def create_page(handle: str, wl_code: str, url: str, product: str = "", status: str = "", post_date: str | None = None):
    """새 슬롯 생성. 기존 Notion 슬롯 패턴 그대로 따라감.

    기본값:
      - 유형: 'Meta | JP'
      - 다중 선택: ['WL']
      - 다중 선택 (1): Product 컬럼 매핑 (PPSU/Flip top/Stainless/빨대)
      - 진행 상태: Sheet Status 매핑
      - 제목: ' ' (빈 칸)
    """
    product_tags = map_product(product)
    props = {
        "메타광고제목(지선)": {"title": [{"text": {"content": " "}}]},
        HANDLE_PROP: {"email": f"@{handle}"},
        WL_PROP: {"rich_text": [{"text": {"content": wl_code}}]},
        LINK_PROP: {"url": url},
        "유형": {"select": {"name": "Meta | JP"}},
        "다중 선택": {"multi_select": [{"name": "WL"}]},
        "진행 상태": {"status": {"name": FIXED_STATUS}},
    }
    if product_tags:
        props["다중 선택 (1)"] = {"multi_select": [{"name": t} for t in product_tags]}
    if post_date:
        props[POST_DATE_PROP] = {"date": {"start": post_date}}
    body = {
        "parent": {"type": "data_source_id", "data_source_id": DATA_SOURCE_ID},
        "properties": props,
    }
    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=notion_headers(),
        json=body,
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Notion create failed [{r.status_code}]: {r.text[:300]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    if not (args.dry_run or args.sync):
        parser.error("--dry-run 또는 --sync 필요")

    print("=" * 60)
    print("WL Code Sync — 기존 슬롯 UPDATE (새 페이지 생성 X)")
    print("=" * 60)

    print("\n[1] Google Sheet 읽는 중...")
    rows = fetch_sheet_rows()
    # rows[0] 빈 행, rows[1] 섹션, rows[2] 컬럼헤더, rows[3]+ 데이터
    data_rows = rows[3:]
    print(f"  데이터 행: {len(data_rows)}건")

    candidates = []
    for i, row in enumerate(data_rows, start=4):
        if len(row) <= COL_URL:
            continue
        wl_raw = row[COL_WL].strip() if len(row) > COL_WL else ""
        url_raw = row[COL_URL].strip() if len(row) > COL_URL else ""
        handle_key = normalize_handle(row[COL_CREATOR_ID] if len(row) > COL_CREATOR_ID else "")
        if not wl_raw or not url_raw or not handle_key:
            continue
        if wl_raw in ("×", "x", "X"):
            continue
        # 셀 하나에 ①/② 여러 코드 있을 수 있음 → 모두 추출해서 각각 후보로
        wl_list = extract_wl_codes(wl_raw)
        url_list = extract_urls(url_raw)
        if not wl_list or not url_list:
            continue
        pairs = list(zip(wl_list, url_list))
        for wl, url in pairs:
            candidates.append({
                "row": i,
                "handle": handle_key,
                "wl": wl,
                "url": url,
                "product": row[COL_PRODUCT] if len(row) > COL_PRODUCT else "",
                "status": row[COL_STATUS] if len(row) > COL_STATUS else "",
            })
    print(f"  WL code + URL + handle 있는 행: {len(candidates)}건")

    print("\n[2] Notion 페이지 전체 조회 중...")
    pages = fetch_all_notion_pages()
    print(f"  총 페이지: {len(pages)}건")
    idx = index_pages_by_handle(pages)
    print(f"  핸들 인덱스: {len(idx)}명")

    to_update = []
    to_create = []
    already_same = []
    for c in candidates:
        matched = idx.get(c["handle"], [])
        same = [m for m in matched if m["wl"] == c["wl"]]
        if same:
            already_same.append(c)
            continue
        empty = [m for m in matched if not m["wl"]]
        if empty:
            to_update.append({**c, "page_id": empty[0]["id"]})
        else:
            # 매칭 핸들 없음 OR 기존은 전부 다른 WL (신규 캠페인) → 새 슬롯 생성
            to_create.append(c)

    print(f"\n[3] 업데이트: {len(to_update)}건 / 신규 생성: {len(to_create)}건 / 이미 있음: {len(already_same)}건")

    if to_update:
        print("\n=== 업데이트 대상 (기존 빈 슬롯) ===")
        for u in to_update:
            print(f"  row{u['row']} @{u['handle']} | {u['wl'][:40]}... | {u['url'][:50]}")

    if to_create:
        print("\n=== 신규 슬롯 생성 대상 ===")
        for c in to_create:
            print(f"  row{c['row']} @{c['handle']} | {c['wl'][:40]}... | {c['url'][:50]}")

    if args.dry_run:
        print("\n[DRY-RUN] Notion 기록 안 함.")
        return 0

    ok, fail = 0, 0
    if to_update:
        print(f"\n[4a] 기존 슬롯 업데이트 중... ({len(to_update)}건)")
        for u in to_update:
            try:
                pd = fetch_ig_post_date(u["url"])
                update_page(u["page_id"], u["wl"], u["url"], pd)
                print(f"  ✓ UPDATE row{u['row']} @{u['handle']} (date={pd})")
                ok += 1
            except Exception as e:
                print(f"  ✗ UPDATE row{u['row']} @{u['handle']} 실패: {e}")
                fail += 1

    if to_create:
        print(f"\n[4b] 신규 슬롯 생성 중... ({len(to_create)}건)")
        for c in to_create:
            try:
                pd = fetch_ig_post_date(c["url"])
                create_page(c["handle"], c["wl"], c["url"], c.get("product", ""), c.get("status", ""), pd)
                print(f"  ✓ CREATE row{c['row']} @{c['handle']} (date={pd})")
                ok += 1
            except Exception as e:
                print(f"  ✗ CREATE row{c['row']} @{c['handle']} 실패: {e}")
                fail += 1

    print(f"\n=== 완료 ===\n  성공: {ok}건 / 실패: {fail}건")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
