"""
Meta JP Grosmimi 광고 1차 분석 (read-only)

캠페인 + 광고 14일 인사이트 fetch → 핵심 지표 + 문제 진단.
이메일 발송 X. 콘솔 출력 + JSON 저장만.
"""

import io
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from env_loader import load_env  # noqa
load_env()

TOKEN = os.getenv("META_JP_ACCESS_TOKEN")
ACCT = os.getenv("META_JP_AD_ACCOUNT_ID")
BASE = "https://graph.facebook.com/v18.0"


def api_get(path, params=None):
    params = params or {}
    params["access_token"] = TOKEN
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    out = []
    while True:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        out.extend(data.get("data", []))
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            break
        req = urllib.request.Request(nxt)
    return out


def fetch_insights(level, date_preset="last_14d"):
    fields = ",".join([
        "campaign_id", "campaign_name", "adset_id", "adset_name",
        "ad_id", "ad_name", "spend", "impressions", "clicks",
        "ctr", "cpc", "cpm", "frequency", "actions", "action_values",
    ])
    params = {
        "fields": fields,
        "level": level,
        "date_preset": date_preset,
        "limit": 500,
    }
    return api_get(f"{ACCT}/insights", params)


def extract_purchases(actions, action_values):
    purchases = 0
    revenue = 0.0
    for a in actions or []:
        if a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"):
            try:
                purchases += int(float(a.get("value", 0)))
            except Exception:
                pass
    for a in action_values or []:
        if a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"):
            try:
                revenue = max(revenue, float(a.get("value", 0)))
            except Exception:
                pass
    return purchases, revenue


def main():
    print("=" * 60)
    print("  Meta JP Grosmimi 광고 1차 분석 (14일)")
    print(f"  Account: {ACCT}")
    print(f"  실행: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. 계정 메타데이터
    print("\n[1] 계정 정보 fetch...")
    acct_info = json.loads(urllib.request.urlopen(
        f"{BASE}/{ACCT}?fields=name,currency,timezone_name,account_status&access_token={TOKEN}",
        timeout=15
    ).read())
    print(f"  Name: {acct_info.get('name')}")
    print(f"  Currency: {acct_info.get('currency')} | TZ: {acct_info.get('timezone_name')}")

    # 2. 캠페인 인사이트 (14일)
    print("\n[2] 캠페인 인사이트 14일 fetch...")
    campaigns = fetch_insights("campaign", "last_14d")
    print(f"  활성 캠페인: {len(campaigns)}개")

    # 3. 광고 인사이트 (14일)
    print("\n[3] 광고 인사이트 14일 fetch...")
    ads = fetch_insights("ad", "last_14d")
    print(f"  활성 광고: {len(ads)}개")

    # 4. 7일 vs 14일 비교용
    print("\n[4] 캠페인 인사이트 7일 fetch...")
    camps_7d = fetch_insights("campaign", "last_7d")

    # 집계
    def agg(rows):
        spend = sum(float(r.get("spend", 0)) for r in rows)
        impr = sum(int(r.get("impressions", 0)) for r in rows)
        clicks = sum(int(r.get("clicks", 0)) for r in rows)
        purchases = 0
        revenue = 0.0
        for r in rows:
            p, v = extract_purchases(r.get("actions"), r.get("action_values"))
            purchases += p
            revenue += v
        return {
            "spend": spend, "impressions": impr, "clicks": clicks,
            "purchases": purchases, "revenue": revenue,
            "ctr": (clicks / impr * 100) if impr else 0,
            "cpc": (spend / clicks) if clicks else 0,
            "cpm": (spend / impr * 1000) if impr else 0,
            "cpa": (spend / purchases) if purchases else 0,
            "roas": (revenue / spend) if spend else 0,
        }

    total_14d = agg(campaigns)
    total_7d = agg(camps_7d)

    cur = acct_info.get("currency", "")
    print("\n" + "=" * 60)
    print(f"  요약 (14일 / 7일)")
    print("=" * 60)
    print(f"  지출:    {total_14d['spend']:>14,.0f} {cur}  /  {total_7d['spend']:>14,.0f}")
    print(f"  노출:    {total_14d['impressions']:>14,}      /  {total_7d['impressions']:>14,}")
    print(f"  클릭:    {total_14d['clicks']:>14,}      /  {total_7d['clicks']:>14,}")
    print(f"  CTR:     {total_14d['ctr']:>13.2f}%      /  {total_7d['ctr']:>13.2f}%")
    print(f"  CPC:     {total_14d['cpc']:>14,.0f}      /  {total_7d['cpc']:>14,.0f}")
    print(f"  CPM:     {total_14d['cpm']:>14,.0f}      /  {total_7d['cpm']:>14,.0f}")
    print(f"  구매:    {total_14d['purchases']:>14}      /  {total_7d['purchases']:>14}")
    print(f"  매출:    {total_14d['revenue']:>14,.0f}      /  {total_7d['revenue']:>14,.0f}")
    print(f"  ROAS:    {total_14d['roas']:>13.2f}x      /  {total_7d['roas']:>13.2f}x")
    print(f"  CPA:     {total_14d['cpa']:>14,.0f}      /  {total_7d['cpa']:>14,.0f}")

    # 캠페인별 정렬
    camp_data = []
    for c in campaigns:
        purchases, revenue = extract_purchases(c.get("actions"), c.get("action_values"))
        spend = float(c.get("spend", 0))
        camp_data.append({
            "campaign_id": c.get("campaign_id"),
            "campaign_name": c.get("campaign_name", "")[:60],
            "spend": spend,
            "impressions": int(c.get("impressions", 0)),
            "clicks": int(c.get("clicks", 0)),
            "ctr": float(c.get("ctr", 0)),
            "cpc": float(c.get("cpc", 0)),
            "cpm": float(c.get("cpm", 0)),
            "purchases": purchases,
            "revenue": revenue,
            "roas": (revenue / spend) if spend else 0,
        })
    camp_data.sort(key=lambda x: x["spend"], reverse=True)

    print("\n" + "=" * 60)
    print(f"  캠페인별 14일 (지출순 Top 10)")
    print("=" * 60)
    print(f"  {'name':<55} {'spend':>10} {'CTR':>6} {'CPC':>8} {'구매':>5} {'ROAS':>6}")
    print("  " + "-" * 95)
    for c in camp_data[:10]:
        print(f"  {c['campaign_name']:<55} {c['spend']:>10,.0f} {c['ctr']:>5.2f}% {c['cpc']:>8,.0f} {c['purchases']:>5} {c['roas']:>5.2f}x")

    # 광고별 정렬
    ad_data = []
    for a in ads:
        purchases, revenue = extract_purchases(a.get("actions"), a.get("action_values"))
        spend = float(a.get("spend", 0))
        ad_data.append({
            "ad_id": a.get("ad_id"),
            "ad_name": a.get("ad_name", "")[:60],
            "campaign_name": a.get("campaign_name", "")[:30],
            "spend": spend,
            "impressions": int(a.get("impressions", 0)),
            "clicks": int(a.get("clicks", 0)),
            "ctr": float(a.get("ctr", 0)),
            "cpc": float(a.get("cpc", 0)),
            "cpm": float(a.get("cpm", 0)),
            "frequency": float(a.get("frequency", 0)),
            "purchases": purchases,
            "revenue": revenue,
            "roas": (revenue / spend) if spend else 0,
        })
    ad_data.sort(key=lambda x: x["spend"], reverse=True)

    print("\n" + "=" * 60)
    print(f"  광고별 14일 (지출순 Top 10)")
    print("=" * 60)
    print(f"  {'ad_name':<60} {'spend':>10} {'CTR':>6} {'CPC':>8} {'구매':>5} {'ROAS':>6}")
    print("  " + "-" * 100)
    for a in ad_data[:10]:
        print(f"  {a['ad_name']:<60} {a['spend']:>10,.0f} {a['ctr']:>5.2f}% {a['cpc']:>8,.0f} {a['purchases']:>5} {a['roas']:>5.2f}x")

    # 문제 진단
    issues = []

    # 1. 전환 0건인데 지출 큰 광고 (>= 3000 KRW)
    no_conv_high_spend = [a for a in ad_data if a["purchases"] == 0 and a["spend"] >= 3000]
    no_conv_high_spend.sort(key=lambda x: x["spend"], reverse=True)
    if no_conv_high_spend:
        issues.append({
            "type": "no_conversion",
            "severity": "high",
            "count": len(no_conv_high_spend),
            "items": [(a["ad_name"], a["spend"], a["ctr"]) for a in no_conv_high_spend[:5]],
        })

    # 2. CTR 0.5% 미만 + impressions 1000+ (반응 X)
    low_ctr = [a for a in ad_data if a["impressions"] >= 1000 and a["ctr"] < 0.5]
    low_ctr.sort(key=lambda x: x["impressions"], reverse=True)
    if low_ctr:
        issues.append({
            "type": "low_ctr",
            "severity": "high",
            "count": len(low_ctr),
            "items": [(a["ad_name"], a["impressions"], a["ctr"]) for a in low_ctr[:5]],
        })

    # 3. Frequency 5+ (오디언스 소진)
    high_freq = [a for a in ad_data if a["frequency"] >= 5.0]
    high_freq.sort(key=lambda x: x["frequency"], reverse=True)
    if high_freq:
        issues.append({
            "type": "audience_burnout",
            "severity": "medium",
            "count": len(high_freq),
            "items": [(a["ad_name"], a["frequency"], a["spend"]) for a in high_freq[:5]],
        })

    # 4. CPC 너무 높음 (3000 KRW+) — JP 평균 대비
    high_cpc = [a for a in ad_data if a["cpc"] >= 3000 and a["clicks"] >= 5]
    high_cpc.sort(key=lambda x: x["cpc"], reverse=True)
    if high_cpc:
        issues.append({
            "type": "high_cpc",
            "severity": "medium",
            "count": len(high_cpc),
            "items": [(a["ad_name"], a["cpc"], a["clicks"]) for a in high_cpc[:5]],
        })

    print("\n" + "=" * 60)
    print(f"  ⚠️ 문제 진단")
    print("=" * 60)
    if not issues:
        print("  심각한 문제 없음")
    else:
        for iss in issues:
            print(f"\n  [{iss['severity'].upper()}] {iss['type']} — {iss['count']}건")
            for it in iss["items"]:
                if iss["type"] == "no_conversion":
                    name, spend, ctr = it
                    print(f"    - {name}  | spend={spend:,.0f} CTR={ctr:.2f}%")
                elif iss["type"] == "low_ctr":
                    name, impr, ctr = it
                    print(f"    - {name}  | impr={impr:,} CTR={ctr:.2f}%")
                elif iss["type"] == "audience_burnout":
                    name, freq, spend = it
                    print(f"    - {name}  | freq={freq:.2f} spend={spend:,.0f}")
                elif iss["type"] == "high_cpc":
                    name, cpc, clicks = it
                    print(f"    - {name}  | CPC={cpc:,.0f} clicks={clicks}")

    # JSON 저장
    out = {
        "executed_at": datetime.now().isoformat(),
        "account": acct_info,
        "summary_14d": total_14d,
        "summary_7d": total_7d,
        "campaigns": camp_data,
        "ads": ad_data,
        "issues": issues,
    }
    out_path = ROOT / ".tmp" / f"meta_jp_quick_{date.today().strftime('%Y%m%d')}.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  저장: {out_path}")

    print("\n" + "=" * 60)
    print("  완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
