# -*- coding: utf-8 -*-
"""심사 큐 릴스 영상 URL 프리페치 — Apify instagram-scraper 로 videoUrl(mp4) 취득 →
"Reel Video Cache" 탭에 캐시. meta-app 심사 화면이 이 캐시로 <video loop> 무한재생.

IG CDN URL 은 며칠 뒤 만료 → 매일(또는 심사 전) 재실행해 갱신.
사용: python tools/prefetch_reel_videos.py [--all] [shortcode ...]
      기본 = "JP Content Review" 시트의 미심사/전체 shortcode. 인자로 특정 shortcode 지정 가능.
"""
import os, sys, json, argparse, datetime as dt, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from env_loader import load_env; load_env()
except Exception:
    pass
from sheets_utils import get_sheets_client

SHEET = os.getenv("TAG_SHEET_ID") or "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
REVIEW_TAB = "JP Content Review"
CACHE_TAB = "Reel Video Cache"
CACHE_HEADER = ["shortcode", "video_url", "video_duration", "cached_at"]
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")


def apify_videos(shortcodes):
    """directUrls 배치 → {shortcode: (videoUrl, duration)}."""
    urls = [f"https://www.instagram.com/reel/{sc}/" for sc in shortcodes]
    ep = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    payload = {"directUrls": urls, "resultsType": "posts", "resultsLimit": len(urls), "addParentData": False}
    req = urllib.request.Request(ep, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            items = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Apify HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Apify 네트워크 오류: {e}")
    out = {}
    for it in items:
        sc = it.get("shortCode") or (it.get("url", "").rstrip("/").split("/")[-1])
        vurl = it.get("videoUrl") or it.get("videoUrlBackup")
        if sc and vurl:
            out[sc] = (vurl, it.get("videoDuration", ""))
    return out


def get_cache_ws(gc):
    sh = gc.open_by_key(SHEET)
    try:
        ws = sh.worksheet(CACHE_TAB)
    except Exception:
        ws = sh.add_worksheet(title=CACHE_TAB, rows=500, cols=len(CACHE_HEADER))
        ws.update(values=[CACHE_HEADER], range_name="A1")
    if (ws.get_all_values() or [[]])[0][:len(CACHE_HEADER)] != CACHE_HEADER:
        ws.update(values=[CACHE_HEADER], range_name="A1")
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shortcodes", nargs="*")
    ap.add_argument("--all", action="store_true", help="시트 전체(기본도 전체)")
    args = ap.parse_args()
    if not APIFY_TOKEN:
        sys.exit("APIFY_API_TOKEN 없음 (.env 확인)")

    gc = get_sheets_client()
    if args.shortcodes:
        targets = args.shortcodes
    else:
        rv = gc.open_by_key(SHEET).worksheet(REVIEW_TAB).get_all_values()
        i_sc = rv[0].index("shortcode")
        targets = [r[i_sc].strip() for r in rv[1:] if len(r) > i_sc and r[i_sc].strip()]
    targets = list(dict.fromkeys(targets))
    print(f"프리페치 대상 {len(targets)}건: {targets}")

    vids = apify_videos(targets)
    print(f"videoUrl 취득 {len(vids)}/{len(targets)}건")

    ws = get_cache_ws(gc)
    rows = ws.get_all_values()
    existing = {r[0].strip(): i + 2 for i, r in enumerate(rows[1:]) if r and r[0].strip()}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    from gspread.utils import rowcol_to_a1
    appended = 0
    for sc, (vurl, dur) in vids.items():
        row = [sc, vurl, str(dur), now]
        if sc in existing:
            ws.update(values=[row], range_name=f"A{existing[sc]}:D{existing[sc]}")
        else:
            ws.append_row(row, value_input_option="RAW")
            appended += 1
    miss = [sc for sc in targets if sc not in vids]
    print(f"캐시 갱신 완료 (신규 {appended}) → 탭 '{CACHE_TAB}'" + (f" · 취득실패 {miss}" if miss else ""))


if __name__ == "__main__":
    main()
