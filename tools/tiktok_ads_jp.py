"""TikTok Marketing API — JP 광고 실적 수집 (파이프라인 #1: 유료축).

US tt_spark 파이프라인을 JP로 이식하기 위한 첫 조각. 광고 실적(지출·노출·클릭·
유료뷰·전환)을 TikTok Marketing API 로 일별 수집해 원장(JSON)으로 저장한다.
오가닉 총뷰·잔차 분해(#2)는 별도 소스(영상 뷰 시계열)와 조인하는 빌더(#4)에서 처리.

METRICS 는 TikTok Marketing API v1.3 (BASE 도 v1.3) 표준 리포트 세트다. 공식 문서는
SPA/로그인 게이트라 전량 노출되지 않으므로, metric 명의 최종 검증은 문서가 아니라
**실호출**로 한다 — `--probe` 로 계정 접근 확인 후 `--start/--end` 실행 시 잘못된
metric 은 응답 code≠0 (get_ad_report 가 즉시 중단·메시지 표시) 로 드러난다. 즉 이
파일의 정합성 기준은 실 API 응답이며, 자격증명 확보 후 첫 실행이 곧 스펙 검증이다.

이 스크립트가 직접 읽는 .env (실행 필수):
  TIKTOK_ACCESS_TOKEN     long-lived access token (advertiser 승인 후 발급)
  TIKTOK_ADVERTISER_ID_JP JP 광고계정 advertiser_id
토큰 발급에만 쓰이는 값 (이 스크립트는 미사용 · 별도 발급 절차/스크립트용):
  TIKTOK_APP_ID           TikTok for Business 개발자 앱 ID
  TIKTOK_APP_SECRET       앱 시크릿

사용:
  PYTHONIOENCODING=utf-8 python tools/tiktok_ads_jp.py --start 2026-09-15 --end 2026-09-21
  PYTHONIOENCODING=utf-8 python tools/tiktok_ads_jp.py --probe        # 자격증명·계정 접근 점검만
"""
from __future__ import annotations
import os
import sys
import json
import time
import argparse
import datetime
import urllib.request
import urllib.parse
import urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # dotenv 없으면 프로세스 환경변수만 사용 (실제 에러는 마스킹하지 않음)

BASE = "https://business-api.tiktok.com/open_api/v1.3"

# 유료축 metric (video_* = 유료 재생, video_views_p100 = 완주, conversion·구매·매출)
METRICS = [
    "spend", "impressions", "clicks", "ctr", "cpc",
    "video_play_actions",       # 유료 재생수 = tt_spark 의 paid 뷰 대응
    "video_watched_2s", "video_watched_6s",
    "video_views_p25", "video_views_p50", "video_views_p75", "video_views_p100",
    "conversion", "cost_per_conversion",
    "complete_payment", "total_complete_payment_rate", "total_purchase_value",
]


def _need(key: str) -> str:
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ENV MISSING] {key} — .env 에 설정 필요 (docstring 참조)")
    return v


def _request(url: str, headers: dict, retries: int = 2) -> dict:
    """GET + transient/rate-limit 재시도. 실패 시 스택트레이스 대신 명확한 메시지."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 502, 503) and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"[HTTP {e.code}] {url.split('?')[0]}\n{body}")
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"[NETWORK] {e.reason}")
    return {}  # unreachable (루프는 항상 return/exit)


def _get(path: str, params: dict) -> dict:
    """Marketing API GET. Access-Token 은 헤더. list/dict 파라미터는 JSON 문자열."""
    token = _need("TIKTOK_ACCESS_TOKEN")
    q = {}
    for k, v in params.items():
        q[k] = json.dumps(v, separators=(",", ":")) if isinstance(v, (list, dict)) else v
    url = f"{BASE}{path}?{urllib.parse.urlencode(q)}"
    return _request(url, {"Access-Token": token})


def probe() -> dict:
    """자격증명 + JP 계정 접근 점검 (advertiser info)."""
    adv = _need("TIKTOK_ADVERTISER_ID_JP")
    res = _get("/advertiser/info/", {"advertiser_ids": [adv],
                                     "fields": ["name", "currency", "timezone", "status"]})
    return res


def get_ad_report(start_date: str, end_date: str) -> list[dict]:
    """광고(ad) × 일별 실적. dimensions=[ad_id, stat_time_day]."""
    adv = _need("TIKTOK_ADVERTISER_ID_JP")
    rows: list[dict] = []
    page = 1
    while True:
        res = _get("/report/integrated/get/", {
            "advertiser_id": adv,
            "report_type": "BASIC",
            "data_level": "AUCTION_AD",
            "dimensions": ["ad_id", "stat_time_day"],
            "metrics": METRICS,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "page_size": 1000,
        })
        if res.get("code") != 0:
            sys.exit(f"[API ERROR] code={res.get('code')} msg={res.get('message')}")
        data = res.get("data", {})
        rows.extend(data.get("list", []))
        info = data.get("page_info", {})
        if page >= info.get("total_page", 1):
            break
        page += 1
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--out", default=".tmp/tiktok_jp/ad_report.json")
    a = ap.parse_args()

    if a.probe:
        print(json.dumps(probe(), ensure_ascii=False, indent=2))
        return

    if not (a.start and a.end):
        end = datetime.date.fromisoformat(a.end) if a.end else datetime.date.today()
        a.end = end.isoformat()
        a.start = a.start or (end - datetime.timedelta(days=7)).isoformat()  # 항상 end 기준 7일

    rows = get_ad_report(a.start, a.end)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    payload = {"pulled_at": datetime.datetime.now().isoformat(timespec="minutes"),
               "window": [a.start, a.end], "n": len(rows), "rows": rows}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] {len(rows)} ad×day rows → {a.out}")


if __name__ == "__main__":
    main()
