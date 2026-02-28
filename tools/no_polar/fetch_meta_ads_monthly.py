"""
Meta Ads 월별 캠페인 데이터 수집 (Polar Q6 대체)
================================================
Polar MCP 없이 Meta Graph API 직접 호출.
Jan 2024 ~ 현재까지 월별 집계하여 q6_facebook_ads_campaign.json 생성.

사용법:
  python tools/no_polar/fetch_meta_ads_monthly.py
  python tools/no_polar/fetch_meta_ads_monthly.py --start 2024-01 --end 2026-02
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/
from env_loader import load_env

load_env()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
API_VERSION = "v18.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / ".tmp" / "polar_data" / "q6_facebook_ads_campaign.json"


def api_get(path, params):
    params["access_token"] = ACCESS_TOKEN
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = json.loads(e.read())
        raise Exception(f"API 오류: {error_body.get('error', {}).get('message', str(e))}")


def get_campaign_insights_monthly(since: str, until: str) -> list:
    """
    특정 기간의 캠페인별 집계 데이터 반환.
    Meta Insights API는 level=campaign + time_range로 월별 집계 가능.
    """
    params = {
        "fields": "campaign_name,spend,impressions,clicks,actions,action_values",
        "level": "campaign",
        "time_range": json.dumps({"since": since, "until": until}),
        "limit": 500,
    }
    results = []
    url_path = f"/{AD_ACCOUNT_ID}/insights"

    while True:
        data = api_get(url_path, params)
        results.extend(data.get("data", []))

        # 페이지네이션
        next_page = data.get("paging", {}).get("next")
        if not next_page:
            break
        # next URL에서 after cursor 추출
        parsed = urllib.parse.urlparse(next_page)
        qs = urllib.parse.parse_qs(parsed.query)
        after = qs.get("after", [None])[0]
        if not after:
            break
        params = dict(params)
        params["after"] = after

    return results


def extract_purchase_value(actions, action_values):
    """actions/action_values 배열에서 구매 전환 값 추출"""
    purchases_value = 0.0
    for av in (action_values or []):
        if av.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
            purchases_value += float(av.get("value", 0))
    return purchases_value


def month_range(start_ym: str, end_ym: str):
    """'YYYY-MM' 형식으로 월 범위 생성"""
    sy, sm = int(start_ym[:4]), int(start_ym[5:7])
    ey, em = int(end_ym[:4]), int(end_ym[5:7])
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def fetch_all_months(start_ym: str, end_ym: str) -> list:
    rows = []
    for y, m in month_range(start_ym, end_ym):
        since = f"{y:04d}-{m:02d}-01"
        last_day = monthrange(y, m)[1]
        until = f"{y:04d}-{m:02d}-{last_day:02d}"
        date_key = f"{y:04d}-{m:02d}-01"

        print(f"  {date_key} 조회 중...", end=" ")
        try:
            insights = get_campaign_insights_monthly(since, until)
        except Exception as e:
            print(f"오류 ({e}) — 건너뜀")
            continue

        for row in insights:
            spend = float(row.get("spend", 0) or 0)
            if spend == 0:
                continue  # 지출 없는 캠페인 제외

            purchase_value = extract_purchase_value(
                row.get("actions"), row.get("action_values")
            )
            rows.append({
                "facebookads_ad_platform_and_device.raw.spend": spend,
                "facebookads_ad_platform_and_device.raw.purchases_conversion_value": purchase_value,
                "facebookads_ad_platform_and_device.raw.clicks": int(row.get("clicks", 0) or 0),
                "facebookads_ad_platform_and_device.raw.impressions": int(row.get("impressions", 0) or 0),
                "campaign": row.get("campaign_name", ""),
                "date": date_key,
            })

        print(f"{len(insights)}개 캠페인")

    return rows


def build_totals(rows: list) -> list:
    totals = {
        "facebookads_ad_platform_and_device.raw.spend": 0.0,
        "facebookads_ad_platform_and_device.raw.purchases_conversion_value": 0.0,
        "facebookads_ad_platform_and_device.raw.clicks": 0,
        "facebookads_ad_platform_and_device.raw.impressions": 0,
    }
    for r in rows:
        for k in totals:
            totals[k] += r.get(k, 0)
    return [totals]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01", help="시작 월 (YYYY-MM)")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m"), help="종료 월 (YYYY-MM)")
    args = parser.parse_args()

    if not ACCESS_TOKEN or not AD_ACCOUNT_ID:
        raise SystemExit("❌ META_ACCESS_TOKEN / META_AD_ACCOUNT_ID 환경변수가 없습니다.")

    print(f"[Meta Ads] 월별 데이터 수집: {args.start} ~ {args.end}\n")
    rows = fetch_all_months(args.start, args.end)

    output = {
        "tableData": rows,
        "totalData": build_totals(rows),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] 저장: {OUTPUT_PATH}")
    print(f"   총 레코드: {len(rows)}개")
    total_spend = sum(r["facebookads_ad_platform_and_device.raw.spend"] for r in rows)
    print(f"   총 지출: ${total_spend:,.0f}")


if __name__ == "__main__":
    main()
