"""
Meta Ads 일별 데이터 수집 (campaign / adset / ad 레벨)
======================================================
Meta Graph API Insights 직접 호출.
campaign/adset/ad 레벨별 일별 집계 데이터를 수집하여 JSON 저장.

사용법:
  python tools/no_polar/fetch_meta_ads_daily.py --level campaign --days 60
  python tools/no_polar/fetch_meta_ads_daily.py --level adset --days 30
  python tools/no_polar/fetch_meta_ads_daily.py --level ad --days 30
  python tools/no_polar/fetch_meta_ads_daily.py --level all --days 30

출력:
  .tmp/meta_ads/campaign.json
  .tmp/meta_ads/adset.json
  .tmp/meta_ads/ad.json
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_loader import load_env

load_env()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")
API_VERSION = "v18.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / ".tmp" / "meta_ads"

# 레벨별 필드 정의
LEVEL_FIELDS = {
    "campaign": "campaign_id,campaign_name,spend,impressions,clicks,reach,frequency,actions,action_values",
    "adset":    "campaign_id,campaign_name,adset_id,adset_name,spend,impressions,clicks,reach,frequency,actions,action_values",
    "ad":       "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,spend,impressions,clicks,reach,frequency,actions,action_values",
}


def api_get(path, params):
    params["access_token"] = ACCESS_TOKEN
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            error_body = json.loads(e.read())
            msg = error_body.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        raise Exception(f"API 오류: {msg}")
    except urllib.error.URLError as e:
        raise Exception(f"Network 오류: {e.reason}")


def get_insights(since: str, until: str, level: str) -> list:
    """특정 기간의 레벨별 일별 데이터 반환."""
    params = {
        "fields": LEVEL_FIELDS[level],
        "level": level,
        "time_range": json.dumps({"since": since, "until": until}),
        "time_increment": 1,  # 일별 분해
        "limit": 500,
    }
    results = []
    url_path = f"/{AD_ACCOUNT_ID}/insights"

    while True:
        data = api_get(url_path, params)
        results.extend(data.get("data", []))

        next_page = data.get("paging", {}).get("next")
        if not next_page:
            break
        parsed = urllib.parse.urlparse(next_page)
        qs = urllib.parse.parse_qs(parsed.query)
        after = qs.get("after", [None])[0]
        if not after:
            break
        params = dict(params)
        params["after"] = after

    return results


def extract_purchase_metrics(actions, action_values):
    """purchases 수와 conversion value 추출."""
    purchases = 0
    purchases_value = 0.0

    for a in (actions or []):
        if a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
            purchases += int(float(a.get("value", 0)))

    for av in (action_values or []):
        if av.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
            purchases_value += float(av.get("value", 0))

    return purchases, purchases_value


def process_rows(raw_rows: list, level: str) -> list:
    """API 응답을 분석용 표준 포맷으로 변환."""
    rows = []
    for r in raw_rows:
        spend = float(r.get("spend", 0) or 0)
        if spend == 0:
            continue

        impressions = int(r.get("impressions", 0) or 0)
        clicks = int(r.get("clicks", 0) or 0)
        reach = int(r.get("reach", 0) or 0)
        frequency = float(r.get("frequency", 0) or 0)
        purchases, purchases_value = extract_purchase_metrics(
            r.get("actions"), r.get("action_values")
        )

        # 파생 지표
        roas = round(purchases_value / spend, 4) if spend > 0 else 0
        ctr = round(clicks / impressions * 100, 4) if impressions > 0 else 0
        cpc = round(spend / clicks, 4) if clicks > 0 else 0
        cpm = round(spend / impressions * 1000, 4) if impressions > 0 else 0
        cpa = round(spend / purchases, 4) if purchases > 0 else 0

        row = {
            "date": r.get("date_start"),
            "campaign_id": r.get("campaign_id", ""),
            "campaign_name": r.get("campaign_name", ""),
            "spend": spend,
            "impressions": impressions,
            "clicks": clicks,
            "reach": reach,
            "frequency": frequency,
            "purchases": purchases,
            "purchases_value": purchases_value,
            "roas": roas,
            "ctr": ctr,
            "cpc": cpc,
            "cpm": cpm,
            "cpa": cpa,
        }

        if level in ("adset", "ad"):
            row["adset_id"] = r.get("adset_id", "")
            row["adset_name"] = r.get("adset_name", "")

        if level == "ad":
            row["ad_id"] = r.get("ad_id", "")
            row["ad_name"] = r.get("ad_name", "")

        rows.append(row)

    return rows


def fetch_level(level: str, since: str, until: str) -> list:
    print(f"  [{level.upper()}] {since} ~ {until} 조회 중...", end=" ", flush=True)
    raw = get_insights(since, until, level)
    rows = process_rows(raw, level)
    print(f"{len(rows)}개 레코드")
    return rows


def main():
    parser = argparse.ArgumentParser(description="Meta Ads 일별 데이터 수집")
    parser.add_argument("--level", default="campaign",
                        choices=["campaign", "adset", "ad", "all"],
                        help="수집 레벨 (기본: campaign)")
    parser.add_argument("--days", type=int, default=30, help="최근 N일 (기본: 30)")
    parser.add_argument("--since", help="시작일 YYYY-MM-DD (--days 대신 사용)")
    parser.add_argument("--until", help="종료일 YYYY-MM-DD (기본: 어제)")
    args = parser.parse_args()

    if not ACCESS_TOKEN or not AD_ACCOUNT_ID:
        raise SystemExit("META_ACCESS_TOKEN / META_AD_ACCOUNT_ID 환경변수가 없습니다.")

    today = datetime.now().date()
    until = args.until or (today - timedelta(days=1)).strftime("%Y-%m-%d")
    if args.since:
        since = args.since
    else:
        since = (today - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"[Meta Ads] {since} ~ {until}\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    levels = ["campaign", "adset", "ad"] if args.level == "all" else [args.level]

    for level in levels:
        try:
            rows = fetch_level(level, since, until)
        except Exception as e:
            print(f"  [{level.upper()}] 오류: {e}")
            continue

        out_path = OUTPUT_DIR / f"{level}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"level": level, "since": since, "until": until, "data": rows},
                      f, ensure_ascii=False, indent=2)

        total_spend = sum(r["spend"] for r in rows)
        total_value = sum(r["purchases_value"] for r in rows)
        avg_roas = round(total_value / total_spend, 2) if total_spend > 0 else 0
        print(f"    -> {out_path.name} | spend ${total_spend:,.0f} | ROAS {avg_roas}")

    print("\n[완료]")


if __name__ == "__main__":
    main()
