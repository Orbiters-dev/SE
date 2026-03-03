"""
run_amazon_ppc_daily.py - Amazon PPC 일간 분석 에이전트

Amazon Ads API -> 30일 일별 데이터 수집 -> Claude PPC 전문가 분석 -> HTML 이메일 발송

Usage:
    python tools/run_amazon_ppc_daily.py
    python tools/run_amazon_ppc_daily.py --days 30 --to wj.choi@orbiters.co.kr
    python tools/run_amazon_ppc_daily.py --dry-run   # 이메일 발송 없이 분석만
"""

import argparse
import base64
import concurrent.futures
import gzip
import json
import os
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent

# --- credentials ---
AD_CLIENT_ID     = os.getenv("AMZ_ADS_CLIENT_ID")
AD_CLIENT_SECRET = os.getenv("AMZ_ADS_CLIENT_SECRET")
AD_REFRESH_TOKEN = os.getenv("AMZ_ADS_REFRESH_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

API_BASE = "https://advertising-api.amazon.com"

# --- brand by account (seller name from Amazon Ads profile) ---
PROFILE_BRAND_MAP = {
    "GROSMIMI USA": "Grosmimi",
    "Fleeters Inc": "Naeiae",
    "Orbitool": "CHA&MOM",
}


# ===========================================================================
# Amazon Ads Auth
# ===========================================================================

def get_access_token() -> str:
    resp = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": AD_REFRESH_TOKEN,
            "client_id": AD_CLIENT_ID,
            "client_secret": AD_CLIENT_SECRET,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


class TokenManager:
    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def get(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        self._token = get_access_token()
        self._expires_at = time.time() + 3600
        return self._token


TM = TokenManager()


def _headers_reporting(profile_id: int) -> Dict:
    return {
        "Authorization": f"Bearer {TM.get()}",
        "Amazon-Advertising-API-ClientId": AD_CLIENT_ID,
        "Amazon-Advertising-API-Scope": str(profile_id),
        "Accept": "application/vnd.adreporting.v3+json",
        "Content-Type": "application/vnd.adreporting.v3+json",
    }


def get_us_profiles() -> List[Dict]:
    resp = requests.get(
        f"{API_BASE}/v2/profiles",
        headers={
            "Authorization": f"Bearer {TM.get()}",
            "Amazon-Advertising-API-ClientId": AD_CLIENT_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()
    out = []
    for p in resp.json():
        if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller":
            out.append({
                "profile_id": p["profileId"],
                "seller": p["accountInfo"].get("name", ""),
            })
    return out


def fetch_campaign_names(profile_id: int) -> Dict[int, str]:
    tok = TM.get()
    headers = {
        "Authorization": f"Bearer {tok}",
        "Amazon-Advertising-API-ClientId": AD_CLIENT_ID,
        "Amazon-Advertising-API-Scope": str(profile_id),
        "Accept": "application/vnd.spCampaign.v3+json",
        "Content-Type": "application/vnd.spCampaign.v3+json",
    }
    out: Dict[int, str] = {}
    start_index = 0
    while True:
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{API_BASE}/sp/campaigns/list",
                    headers=headers,
                    json={"stateFilter": {"include": ["ENABLED", "PAUSED", "ARCHIVED"]},
                          "startIndex": start_index, "count": 1000},
                    timeout=20,
                )
                if resp.status_code in (401, 403):
                    raise PermissionError(f"Auth failed ({resp.status_code}) for profile {profile_id}")
                resp.raise_for_status()
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                if attempt < 2:
                    wait = 10 * (attempt + 1)
                    print(f"    [WARN] campaign list 연결 에러, {wait}s 후 재시도 ({attempt+1}/3)")
                    time.sleep(wait)
                else:
                    raise
        data = resp.json()
        camps = data.get("campaigns", []) if isinstance(data, dict) else data
        items = camps if isinstance(camps, list) else camps.get("items", [])
        for c in items:
            cid = c.get("campaignId")
            if cid:
                out[int(cid)] = c.get("name", str(cid))
        if len(items) < 1000:
            break
        start_index += 1000
    return out


def _parse_gzip(resp: requests.Response) -> List[Dict]:
    raw = resp.content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    obj = json.loads(raw.decode("utf-8"))
    if isinstance(obj, list):
        return obj
    for k in ("data", "results", "records"):
        if k in obj:
            return obj[k]
    return [obj]


def fetch_sp_daily(profile_id: int, start: date, end: date) -> List[Dict]:
    """Fetch SP campaign daily rows for a date range (max 28d per request)."""
    campaign_names = fetch_campaign_names(profile_id)
    all_rows: List[Dict] = []

    cur = start
    first_chunk = True
    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=6))  # 7-day windows (smaller = faster report gen)
        if not first_chunk:
            time.sleep(5)  # Brief gap between chunks to avoid 425 rate limits
        first_chunk = False
        print(f"  [Amazon Ads] {cur} ~ {chunk_end} (profile {profile_id})")

        body = {
            "name": f"PPC daily {cur}~{chunk_end}",
            "startDate": cur.strftime("%Y-%m-%d"),
            "endDate": chunk_end.strftime("%Y-%m-%d"),
            "configuration": {
                "adProduct": "SPONSORED_PRODUCTS",
                "groupBy": ["campaign"],
                "columns": ["date", "campaignId", "impressions", "clicks",
                            "cost", "sales14d", "purchases14d"],
                "reportTypeId": "spCampaigns",
                "timeUnit": "DAILY",
                "format": "GZIP_JSON",
            },
        }
        headers = _headers_reporting(profile_id)
        # Retry on 425 (Too Early / rate limit) with backoff
        for attempt in range(3):
            resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
            if resp.status_code == 425:
                wait = 30 * (attempt + 1)
                print(f"  [425] Rate limited, waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            print(f"  [WARN] Report submission failed after 3 retries for profile {profile_id}")
            cur = chunk_end + timedelta(days=1)
            continue
        report_id = resp.json()["reportId"]

        # poll — max 600s (reports can take 5-10 min during peak hours)
        deadline = time.time() + 600
        timed_out = True
        while time.time() < deadline:
            time.sleep(15)
            st = requests.get(f"{API_BASE}/reporting/reports/{report_id}",
                              headers=_headers_reporting(profile_id), timeout=30)
            st.raise_for_status()
            status = st.json().get("status")
            if status == "COMPLETED":
                url = st.json().get("url")
                if url:
                    dl = requests.get(url, timeout=300)
                    dl.raise_for_status()
                    rows = _parse_gzip(dl)
                    for r in rows:
                        cid = r.get("campaignId")
                        r["campaignName"] = campaign_names.get(int(cid), str(cid)) if cid else ""
                    all_rows.extend(rows)
                timed_out = False
                break
            if status == "FAILED":
                print(f"  [WARN] Report {report_id} failed for profile {profile_id}")
                timed_out = False
                break
        if timed_out:
            print(f"  [WARN] Report {report_id} timed out (600s) for profile {profile_id} - skipping chunk")

        cur = chunk_end + timedelta(days=1)

    return all_rows


# ===========================================================================
# Metrics computation
# ===========================================================================

def compute_metrics(rows: List[Dict], profile_brand: Optional[str] = None) -> List[Dict]:
    """Add ROAS, ACOS, CPC, CTR to each row. Brand is set from profile_brand."""
    out = []
    for r in rows:
        cost = float(r.get("cost", 0) or 0)
        sales = float(r.get("sales14d", 0) or 0)
        clicks = int(r.get("clicks", 0) or 0)
        impressions = int(r.get("impressions", 0) or 0)

        roas = round(sales / cost, 2) if cost > 0 else 0
        acos = round(cost / sales * 100, 1) if sales > 0 else None
        cpc = round(cost / clicks, 2) if clicks > 0 else 0
        ctr = round(clicks / impressions * 100, 2) if impressions > 0 else 0

        out.append({
            "date": r.get("date", ""),
            "campaignId": r.get("campaignId"),
            "campaignName": r.get("campaignName", ""),
            "brand": profile_brand or "기타",
            "impressions": impressions,
            "clicks": clicks,
            "cost": round(cost, 2),
            "sales": round(sales, 2),
            "roas": roas,
            "acos": acos,
            "cpc": cpc,
            "ctr": ctr,
        })
    return out


def aggregate_by_campaign(rows: List[Dict]) -> Dict[str, Dict]:
    """Sum metrics by campaign name."""
    bucket: Dict[str, Dict] = defaultdict(lambda: {
        "cost": 0.0, "sales": 0.0, "clicks": 0, "impressions": 0, "brand": ""
    })
    for r in rows:
        name = r["campaignName"]
        b = bucket[name]
        b["cost"]        += r["cost"]
        b["sales"]       += r["sales"]
        b["clicks"]      += r["clicks"]
        b["impressions"] += r["impressions"]
        b["brand"]        = r["brand"]

    out = {}
    for name, v in bucket.items():
        cost = v["cost"]; sales = v["sales"]; clicks = v["clicks"]; impr = v["impressions"]
        out[name] = {
            **v,
            "cost":   round(cost, 2),
            "sales":  round(sales, 2),
            "roas":   round(sales / cost, 2) if cost > 0 else 0,
            "acos":   round(cost / sales * 100, 1) if sales > 0 else None,
            "cpc":    round(cost / clicks, 2) if clicks > 0 else 0,
            "ctr":    round(clicks / impr * 100, 2) if impr > 0 else 0,
        }
    return out


def build_analysis_payload(rows: List[Dict], analysis_date: date) -> Dict:
    """Build structured data for Claude to analyze — 30d + 7d dual analysis."""
    yesterday = analysis_date - timedelta(days=1)
    last7_start  = analysis_date - timedelta(days=7)
    last30_start = analysis_date - timedelta(days=30)

    def filter_rows(from_d: date, to_d: date):
        return [r for r in rows if from_d <= datetime.strptime(r["date"][:10], "%Y-%m-%d").date() <= to_d]

    yesterday_rows = filter_rows(yesterday, yesterday)
    last7_rows     = filter_rows(last7_start, yesterday)
    last30_rows    = filter_rows(last30_start, yesterday)

    def totals(rs):
        cost  = sum(r["cost"]   for r in rs)
        sales = sum(r["sales"]  for r in rs)
        clicks= sum(r["clicks"] for r in rs)
        impr  = sum(r["impressions"] for r in rs)
        return {
            "spend": round(cost, 2),
            "sales": round(sales, 2),
            "roas":  round(sales / cost, 2) if cost > 0 else 0,
            "acos":  round(cost / sales * 100, 1) if sales > 0 else None,
            "cpc":   round(cost / clicks, 2) if clicks > 0 else 0,
            "ctr":   round(clicks / impr * 100, 2) if impr > 0 else 0,
            "clicks": clicks,
            "impressions": impr,
        }

    def brand_breakdown(rs):
        bd: Dict[str, Dict] = defaultdict(lambda: {"cost": 0.0, "sales": 0.0, "clicks": 0, "impressions": 0})
        for r in rs:
            b = bd[r["brand"]]
            b["cost"] += r["cost"]; b["sales"] += r["sales"]
            b["clicks"] += r["clicks"]; b["impressions"] += r["impressions"]
        result = []
        for brand, v in sorted(bd.items()):
            cost = v["cost"]; sales = v["sales"]
            result.append({
                "brand": brand,
                "spend": round(cost, 2),
                "sales": round(sales, 2),
                "roas":  round(sales / cost, 2) if cost > 0 else 0,
                "acos":  round(cost / sales * 100, 1) if sales > 0 else None,
            })
        return result

    # 30d brand with 7d comparison
    bd_30d = {b["brand"]: b for b in brand_breakdown(last30_rows)}
    bd_7d  = {b["brand"]: b for b in brand_breakdown(last7_rows)}
    brand_summary = []
    for brand, v30 in sorted(bd_30d.items()):
        v7 = bd_7d.get(brand, {})
        roas_30 = v30["roas"]; roas_7 = v7.get("roas", 0)
        trend = round((roas_7 - roas_30) / roas_30 * 100, 1) if roas_30 > 0 else None
        brand_summary.append({
            "brand": brand,
            "spend_30d": v30["spend"], "sales_30d": v30["sales"], "roas_30d": roas_30,
            "spend_7d":  v7.get("spend", 0), "sales_7d": v7.get("sales", 0), "roas_7d": roas_7,
            "roas_7d_vs_30d_pct": trend,
        })

    # campaign rankings — 30d and 7d
    camp_30d = aggregate_by_campaign(last30_rows)
    camp_7d  = aggregate_by_campaign(last7_rows)

    sorted_30d = sorted(camp_30d.items(), key=lambda x: x[1]["roas"], reverse=True)
    sorted_7d  = sorted(camp_7d.items(),  key=lambda x: x[1]["roas"], reverse=True)

    top5_30d = [{"campaign": n, **v} for n, v in sorted_30d[:5] if v["cost"] > 0]
    bot5_30d = [{"campaign": n, **v} for n, v in sorted_30d[-5:] if v["cost"] > 0]
    top5_7d  = [{"campaign": n, **v} for n, v in sorted_7d[:5]  if v["cost"] > 0]
    bot5_7d  = [{"campaign": n, **v} for n, v in sorted_7d[-5:]  if v["cost"] > 0]

    zero_sales_30d = [{"campaign": n, **v} for n, v in camp_30d.items()
                      if v["cost"] > 10 and v["sales"] == 0]
    zero_sales_7d  = [{"campaign": n, **v} for n, v in camp_7d.items()
                      if v["cost"] > 5 and v["sales"] == 0]

    # anomalies: yesterday vs 7d
    camp_yesterday = aggregate_by_campaign(yesterday_rows)
    anomalies = []
    for name, yd in camp_yesterday.items():
        avg = camp_7d.get(name)
        if not avg or avg["cost"] == 0:
            continue
        daily_avg_cost = avg["cost"] / 7
        roas_drop   = (avg["roas"] - yd["roas"]) / avg["roas"] * 100 if avg["roas"] > 0 else 0
        spend_spike = (yd["cost"] - daily_avg_cost) / daily_avg_cost * 100 if daily_avg_cost > 0 else 0
        if roas_drop >= 20:
            anomalies.append(f"ROAS 급락: {name} (7일평균 {avg['roas']} -> 어제 {yd['roas']}, -{roas_drop:.0f}%)")
        if spend_spike >= 100:
            anomalies.append(f"광고비 급증: {name} (7일일평균 ${daily_avg_cost:.1f} -> 어제 ${yd['cost']:.1f}, +{spend_spike:.0f}%)")
        if yd["clicks"] > 10 and yd["sales"] == 0:
            anomalies.append(f"클릭있는데 매출0: {name} (클릭 {yd['clicks']}회, 지출 ${yd['cost']:.1f})")

    # Per-brand campaign breakdown (yesterday + 7d + 30d)
    all_brands = sorted(set(r["brand"] for r in last30_rows))
    by_brand_campaigns: Dict[str, List[Dict]] = {}
    for brand in all_brands:
        b30 = aggregate_by_campaign([r for r in last30_rows  if r["brand"] == brand])
        b7  = aggregate_by_campaign([r for r in last7_rows   if r["brand"] == brand])
        byd = aggregate_by_campaign([r for r in yesterday_rows if r["brand"] == brand])
        camps = []
        for name, v30 in b30.items():
            if v30["cost"] < 3:
                continue
            v7  = b7.get(name, {})
            vyd = byd.get(name, {})
            camps.append({
                "campaign":   name,
                "spend_yd":   round(vyd.get("cost", 0), 2),
                "sales_yd":   round(vyd.get("sales", 0), 2),
                "roas_yd":    vyd.get("roas", 0),
                "acos_yd":    vyd.get("acos"),
                "spend_7d":   round(v7.get("cost", 0), 2),
                "sales_7d":   round(v7.get("sales", 0), 2),
                "roas_7d":    v7.get("roas", 0),
                "acos_7d":    v7.get("acos"),
                "spend_30d":  round(v30["cost"], 2),
                "sales_30d":  round(v30["sales"], 2),
                "roas_30d":   v30["roas"],
                "acos_30d":   v30["acos"],
            })
        camps.sort(key=lambda x: x["roas_7d"], reverse=True)
        by_brand_campaigns[brand] = camps

    return {
        "analysis_date": analysis_date.strftime("%Y-%m-%d"),
        "yesterday": yesterday.strftime("%Y-%m-%d"),
        "summary": {
            "yesterday": totals(yesterday_rows),
            "7d":        totals(last7_rows),
            "30d":       totals(last30_rows),
        },
        "brand_breakdown": brand_summary,
        "by_brand_campaigns": by_brand_campaigns,
        "campaigns_30d": {"top5": top5_30d, "bottom5": bot5_30d, "zero_sales": zero_sales_30d[:10]},
        "campaigns_7d":  {"top5": top5_7d,  "bottom5": bot5_7d,  "zero_sales": zero_sales_7d[:10]},
        "anomalies_detected": anomalies[:15],
        "total_active_30d": len([c for c, v in camp_30d.items() if v["cost"] > 0]),
        "total_active_7d":  len([c for c, v in camp_7d.items()  if v["cost"] > 0]),
    }


# ===========================================================================
# Claude API - PPC Expert Analysis
# ===========================================================================

SYSTEM_PROMPT = """당신은 10년 경력의 아마존 PPC 전문 마케터입니다.
아마존 스폰서드 광고(SP/SB/SD)에 대한 깊은 이해를 갖고 있으며,
데이터 기반으로 정확하고 실행 가능한 인사이트를 제공합니다.

분석 원칙:
1. 숫자만 나열하지 않는다. 반드시 의미와 액션을 함께 제시한다
2. ROAS 기준: 3.0 이상 우수 / 2.0~3.0 보통 / 2.0 미만 위험
3. ACOS 기준: 15% 미만 효율적 / 15~25% 보통 / 25% 초과 비효율
4. 어제(yd) + 7일 + 30일 세 기간을 모두 분석한다. 어제가 7일 평균 대비 얼마나 좋고 나쁜지 반드시 진단한다
5. 브랜드별로 구분하여 분석한다
6. 결론은 항상 "이번 주 해야 할 액션 3가지"로 마무리한다

캠페인 조정 강도 기준 (campaign_adjustments에서 반드시 적용):
- 7일 ROAS < 1.0: action=pause, priority=urgent (광고비만 나가고 매출 없음, 즉시 일시중단)
- 7일 ROAS 1.0~1.5: action=reduce_bid, bid_change_pct=-30, priority=urgent (심각 비효율, 대폭 인하)
- 7일 ROAS 1.5~2.0: action=reduce_bid, bid_change_pct=-15, priority=high (비효율, 입찰가 인하 필요)
- 7일 ROAS 2.0~3.0: action=monitor, priority=medium (보통, 더 관찰)
- 7일 ROAS 3.0~5.0: action=increase_budget, budget_change_pct=+20, priority=medium (우수, 스케일업)
- 7일 ROAS > 5.0: action=increase_budget, budget_change_pct=+30, bid_change_pct=+10, priority=high (최우수, 공격적 확장 + 키워드 추가 권고)
- 클릭 있는데 7일 매출 $0: action=pause, priority=urgent (전환없는 클릭 낭비, 즉시 중단)
- 어제(yd) ROAS가 7일 평균 대비 30% 이상 급락: reduce_bid -20% 추가 조치
- 어제(yd) 광고비가 7일 일평균 대비 100% 이상 급등: 즉시 확인 후 예산 캡 설정 권고

출력 형식: JSON (아래 구조 엄격히 준수, 모든 필드 필수)
{
  "executive_summary": "3줄 이내 핵심 요약 (어제 vs 7일 vs 30일 트렌드 포함)",
  "overall_assessment": "good | warning | danger",
  "period_comparison": {
    "trend_30d_vs_7d": "30일 대비 최근 7일 전반적 트렌드 해석",
    "yesterday_vs_7d": "어제 성과가 7일 평균 대비 어떤 상태인지 해석",
    "improving_brands": ["7일이 30일보다 좋아진 브랜드"],
    "declining_brands": ["7일이 30일보다 나빠진 브랜드"]
  },
  "brand_insights": [
    {"brand": "브랜드명", "status": "good|warning|danger", "insight": "어제/7일/30일 비교 인사이트", "action": "브랜드 레벨 즉각 액션"}
  ],
  "brand_campaign_analysis": [
    {
      "brand": "브랜드명",
      "top_campaigns": [
        {"campaign": "캠페인명", "roas_7d": 5.2, "roas_yd": 4.8, "why_good": "잘 되는 구체적 이유", "action": "예산 30% 증액 + 키워드 확장"}
      ],
      "problem_campaigns": [
        {"campaign": "캠페인명", "roas_7d": 0.8, "roas_yd": 0.5, "issue": "구체적 문제점", "action": "즉시 일시중단 (7일 ROAS 0.8, 광고비 낭비)"}
      ],
      "brand_strategy": "이 브랜드 이번 주 예산/입찰 전략 한 줄 요약"
    }
  ],
  "campaign_adjustments": [
    {
      "campaign": "캠페인명",
      "brand": "브랜드명",
      "current_roas_7d": 1.2,
      "current_roas_yd": 0.9,
      "action": "pause | reduce_bid | reduce_budget | increase_bid | increase_budget | monitor",
      "bid_change_pct": -30,
      "budget_change_pct": null,
      "keyword_action": "없음 | 키워드 추가 권고 | 부정키워드 추가 | 키워드 일시중단",
      "reason": "7일 ROAS 1.2로 위험 + 어제 0.9로 추가 악화. 입찰가 30% 인하 즉시 적용",
      "priority": "urgent | high | medium"
    }
  ],
  "anomaly_analysis": "이상 감지 항목에 대한 전문가 해석 및 즉각 조치",
  "weekly_actions": [
    {"priority": 1, "action": "구체적 액션 (예: XX 캠페인 입찰가 30% 인하)", "expected_result": "기대 효과 (예: ACOS 35%->20% 개선)", "campaign": "대상 캠페인명"},
    {"priority": 2, "action": "구체적 액션", "expected_result": "기대 효과", "campaign": "대상 캠페인"},
    {"priority": 3, "action": "구체적 액션", "expected_result": "기대 효과", "campaign": "대상 캠페인"}
  ]
}"""


def analyze_with_claude(payload: Dict) -> Dict:
    """Call Claude API with PPC expert role and return structured analysis."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    user_message = f"""다음은 PST 기준 어제({payload['yesterday']}) Amazon PPC 광고 성과 데이터입니다.
어제(yd) + 7일 + 30일 세 기간을 모두 활용하여 전문가 시각으로 분석하고 JSON 형식으로 응답해주세요.

=== 분석 데이터 ===
{json.dumps(payload, ensure_ascii=False, indent=2)}

중요:
- summary.yesterday(어제) vs summary.7d vs summary.30d 세 기간 모두 비교하세요
- by_brand_campaigns의 각 캠페인에는 spend_yd/roas_yd(어제), spend_7d/roas_7d(7일), spend_30d/roas_30d(30일) 포함
- 캠페인 조정 강도는 시스템 프롬프트의 ROAS 구간 기준을 반드시 따르세요 (ROAS<1.0=pause, 1.0~1.5=-30%, 등)
- campaign_adjustments에는 current_roas_yd(어제 ROAS)도 포함하고, keyword_action 필드도 반드시 채우세요
- campaigns_7d.zero_sales는 최근 7일 매출 없는 캠페인으로 즉시 pause 또는 -40% 입찰가 조치
- anomalies_detected는 전날 이상 감지 항목입니다
- JSON만 출력하세요 (코드블록 없이 순수 JSON)"""

    for attempt in range(3):
        max_tok = 16384 if attempt == 0 else 32768
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": max_tok,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=180,
        )
        resp.raise_for_status()
        body = resp.json()
        text = body["content"][0]["text"].strip()
        stop = body.get("stop_reason", "")

        # strip code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip().rstrip("```").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if stop == "max_tokens" or attempt < 2:
                print(f"  [WARN] Claude JSON 파싱 실패 (stop={stop}, max_tokens={max_tok}), 재시도 {attempt+1}/3")
                continue
            raise


# ===========================================================================
# HTML Email Builder
# ===========================================================================

def status_color(status: str) -> str:
    return {"good": "#2e7d32", "warning": "#f57c00", "danger": "#d32f2f"}.get(status, "#555")


def fmt_usd(v) -> str:
    return f"${v:,.2f}" if v is not None else "-"


def fmt_roas(v) -> str:
    if v is None:
        return "-"
    color = "#2e7d32" if v >= 3.0 else ("#d32f2f" if v < 2.0 else "#f57c00")
    return f'<span style="color:{color};font-weight:bold">{v:.2f}x</span>'


def fmt_acos(v) -> str:
    if v is None:
        return "-"
    color = "#2e7d32" if v < 15 else ("#d32f2f" if v > 25 else "#f57c00")
    return f'<span style="color:{color};font-weight:bold">{v:.1f}%</span>'


def build_html_email(payload: Dict, analysis: Dict) -> str:
    d   = payload["analysis_date"]
    yd  = payload["yesterday"]
    s   = payload["summary"]
    s_yd = s["yesterday"]
    s_7d = s["7d"]
    s_30d = s["30d"]

    oa = analysis.get("overall_assessment", "warning")
    oa_label = {"good": "양호", "warning": "주의", "danger": "위험"}.get(oa, "주의")
    oa_color = status_color(oa)

    # period comparison from Claude
    pc = analysis.get("period_comparison", {})
    trend_html = ""
    if pc:
        impr_brands = ", ".join(pc.get("improving_brands", [])) or "-"
        decl_brands = ", ".join(pc.get("declining_brands", [])) or "-"
        trend_html = f"""
        <div style="background:#e3f2fd;border-left:4px solid #1565c0;padding:12px 16px;margin:16px 0;border-radius:0 6px 6px 0">
          <strong style="color:#1565c0">30일 vs 7일 트렌드</strong>
          <p style="margin:6px 0;color:#333">{pc.get('trend_30d_vs_7d', '')}</p>
          <p style="margin:4px 0;font-size:13px">
            <span style="color:#2e7d32">&#8593; 개선: {impr_brands}</span> &nbsp;|&nbsp;
            <span style="color:#d32f2f">&#8595; 악화: {decl_brands}</span>
          </p>
        </div>"""

    # brand table — 30d + 7d side by side
    brand_rows = ""
    for b in payload.get("brand_breakdown", []):
        r7  = b.get("roas_7d", 0)
        r30 = b.get("roas_30d", 0)
        pct = b.get("roas_7d_vs_30d_pct")
        pct_str = (f'+{pct:.1f}%' if pct >= 0 else f'{pct:.1f}%') if pct is not None else "-"
        pct_color = "#2e7d32" if (pct or 0) >= 0 else "#d32f2f"
        brand_rows += f"""
        <tr>
          <td style="padding:8px 12px;font-weight:500">{b['brand']}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(b.get('spend_30d'))}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_roas(r30)}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(b.get('spend_7d'))}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_roas(r7)}</td>
          <td style="padding:8px 12px;text-align:right;font-weight:bold;color:{pct_color}">{pct_str}</td>
        </tr>"""

    # brand insights
    brand_insight_html = ""
    for bi in analysis.get("brand_insights", []):
        sc = status_color(bi.get("status", "warning"))
        brand_insight_html += f"""
        <div style="border-left:4px solid {sc};padding:10px 16px;margin:8px 0;background:#fafafa;border-radius:0 6px 6px 0">
          <strong style="color:{sc}">{bi['brand']}</strong>
          <p style="margin:4px 0;color:#333">{bi['insight']}</p>
          <p style="margin:4px 0;color:#555;font-size:13px">&#8594; {bi['action']}</p>
        </div>"""

    # 7d top/bottom campaigns (data-level)
    def camp_table_rows(camps):
        rows = ""
        for c in camps:
            rows += f"""<tr>
              <td style="padding:7px 12px;font-size:12px">{c['campaign']}</td>
              <td style="padding:7px 12px;text-align:right">{fmt_roas(c.get('roas'))}</td>
              <td style="padding:7px 12px;text-align:right">{fmt_usd(c.get('spend'))}</td>
              <td style="padding:7px 12px;text-align:right">{fmt_usd(c.get('sales'))}</td>
            </tr>"""
        return rows

    top7_rows = camp_table_rows(payload.get("campaigns_7d", {}).get("top5", []))
    bot7_rows = camp_table_rows(payload.get("campaigns_7d", {}).get("bottom5", []))
    top30_rows = camp_table_rows(payload.get("campaigns_30d", {}).get("top5", []))

    # winners/losers from Claude (7d)
    ch = analysis.get("campaign_highlights", {})
    winners_html = ""
    for c in ch.get("winners_7d", ch.get("winners", [])):
        winners_html += f"""<tr>
          <td style="padding:7px 12px">{c['campaign']}</td>
          <td style="padding:7px 12px">{c.get('reason', '')}</td>
        </tr>"""
    losers_html = ""
    for c in ch.get("losers_7d", ch.get("losers", [])):
        losers_html += f"""<tr>
          <td style="padding:7px 12px">{c['campaign']}</td>
          <td style="padding:7px 12px;color:#d32f2f">{c.get('issue', '')}</td>
          <td style="padding:7px 12px">{c.get('action', '')}</td>
        </tr>"""

    # zero sales 7d
    zero7 = payload.get("campaigns_7d", {}).get("zero_sales", [])
    zero7_html = ""
    for z in zero7:
        zero7_html += f"""<tr style="background:#fff3f3">
          <td style="padding:7px 12px;font-size:12px">{z['campaign']}</td>
          <td style="padding:7px 12px;text-align:right">{fmt_usd(z.get('cost'))}</td>
          <td style="padding:7px 12px;text-align:right;color:#d32f2f">$0</td>
        </tr>"""

    # anomalies
    anomaly_items = "".join(f'<li style="margin:6px 0">{a}</li>' for a in payload.get("anomalies_detected", []))
    anomaly_analysis_html = ""
    if analysis.get("anomaly_analysis"):
        anomaly_analysis_html = f"""
        <div style="background:#fff3e0;border-left:4px solid #f57c00;padding:12px 16px;margin-top:10px">
          <strong>전문가 해석:</strong>
          <p style="margin:6px 0;color:#444">{analysis['anomaly_analysis']}</p>
        </div>"""

    # brand-level campaign sections
    brand_section_html = ""
    for bca in analysis.get("brand_campaign_analysis", []):
        brand = bca.get("brand", "")
        b_insight = next((bi for bi in analysis.get("brand_insights", []) if bi.get("brand") == brand), {})
        bsc = status_color(b_insight.get("status", "warning"))

        # data rows for this brand
        camps_data = payload.get("by_brand_campaigns", {}).get(brand, [])
        data_rows = ""
        for c in camps_data:
            r30 = c.get("roas_30d", 0); r7 = c.get("roas_7d", 0); ryd = c.get("roas_yd", 0)
            row_bg = "#fff9f9" if r7 < 2.0 else ("#f9fff9" if r7 >= 3.0 else "white")
            data_rows += f"""<tr style="background:{row_bg}">
              <td style="padding:6px 10px;font-size:12px">{c['campaign']}</td>
              <td style="padding:6px 10px;text-align:right;background:#fff8e1">{fmt_usd(c.get('spend_yd'))}</td>
              <td style="padding:6px 10px;text-align:right;background:#fff8e1">{fmt_roas(ryd) if c.get('spend_yd', 0) > 0 else '-'}</td>
              <td style="padding:6px 10px;text-align:right;background:#f0fff0">{fmt_usd(c.get('spend_7d'))}</td>
              <td style="padding:6px 10px;text-align:right;background:#f0fff0">{fmt_roas(r7)}</td>
              <td style="padding:6px 10px;text-align:right">{fmt_usd(c.get('spend_30d'))}</td>
              <td style="padding:6px 10px;text-align:right">{fmt_roas(r30)}</td>
              <td style="padding:6px 10px;text-align:right">{fmt_acos(c.get('acos_7d'))}</td>
            </tr>"""

        # top/problem rows from Claude
        top_rows = "".join(f"""<tr>
          <td style="padding:6px 10px;font-size:12px">{t['campaign']}</td>
          <td style="padding:6px 10px;text-align:right;background:#fff3cd">{t.get('roas_yd','')}</td>
          <td style="padding:6px 10px;text-align:right;color:#2e7d32">{t.get('roas_7d','')}</td>
          <td style="padding:6px 10px;color:#555">{t.get('why_good','')}</td>
          <td style="padding:6px 10px;color:#2e7d32;font-weight:bold">{t.get('action','')}</td>
        </tr>""" for t in bca.get("top_campaigns", []))

        prob_rows = "".join(f"""<tr>
          <td style="padding:6px 10px;font-size:12px">{p['campaign']}</td>
          <td style="padding:6px 10px;text-align:right;background:#fff3cd">{p.get('roas_yd','')}</td>
          <td style="padding:6px 10px;text-align:right;color:#d32f2f">{p.get('roas_7d','')}</td>
          <td style="padding:6px 10px;color:#d32f2f">{p.get('issue','')}</td>
          <td style="padding:6px 10px;color:#f57c00;font-weight:bold">{p.get('action','')}</td>
        </tr>""" for p in bca.get("problem_campaigns", []))

        brand_section_html += f"""
        <div style="border:1px solid #e0e0e0;border-radius:8px;margin-bottom:24px;overflow:hidden">
          <div style="background:#232F3E;padding:12px 16px;display:flex;align-items:center;gap:12px">
            <span style="background:{bsc};padding:3px 10px;border-radius:12px;font-size:12px;color:white">
              {b_insight.get('status','').upper() or 'BRAND'}
            </span>
            <strong style="color:white;font-size:16px">{brand}</strong>
            <span style="color:#aaa;font-size:12px;margin-left:auto">{bca.get('brand_strategy','')}</span>
          </div>

          <div style="padding:12px 16px">
            <p style="margin:0 0 10px;color:#555;font-size:13px">{b_insight.get('insight','')}</p>

            <!-- Campaign data table for this brand -->
            <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:12px">
              <thead>
                <tr style="background:#f5f5f5">
                  <th style="padding:6px 10px;text-align:left">캠페인</th>
                  <th style="padding:6px 10px;text-align:right;background:#fff3cd">어제 광고비</th>
                  <th style="padding:6px 10px;text-align:right;background:#fff3cd">어제 ROAS</th>
                  <th style="padding:6px 10px;text-align:right;background:#e8f5e9">7일 광고비</th>
                  <th style="padding:6px 10px;text-align:right;background:#e8f5e9">7일 ROAS</th>
                  <th style="padding:6px 10px;text-align:right">30일 광고비</th>
                  <th style="padding:6px 10px;text-align:right">30일 ROAS</th>
                  <th style="padding:6px 10px;text-align:right">7일 ACOS</th>
                </tr>
              </thead>
              <tbody>{data_rows}</tbody>
            </table>

            {"" if not top_rows else f'''
            <p style="margin:10px 0 6px;font-weight:bold;color:#2e7d32;font-size:13px">잘된 캠페인</p>
            <table style="width:100%;border-collapse:collapse;font-size:12px">
              <thead><tr style="background:#e8f5e9">
                <th style="padding:5px 10px;text-align:left">캠페인</th>
                <th style="padding:5px 10px;text-align:right;background:#fff3cd">어제 ROAS</th>
                <th style="padding:5px 10px;text-align:right">7일 ROAS</th>
                <th style="padding:5px 10px;text-align:left">잘 되는 이유</th>
                <th style="padding:5px 10px;text-align:left">권장 액션</th>
              </tr></thead>
              <tbody>{top_rows}</tbody>
            </table>'''}

            {"" if not prob_rows else f'''
            <p style="margin:10px 0 6px;font-weight:bold;color:#d32f2f;font-size:13px">문제 캠페인</p>
            <table style="width:100%;border-collapse:collapse;font-size:12px">
              <thead><tr style="background:#ffebee">
                <th style="padding:5px 10px;text-align:left">캠페인</th>
                <th style="padding:5px 10px;text-align:right;background:#fff3cd">어제 ROAS</th>
                <th style="padding:5px 10px;text-align:right">7일 ROAS</th>
                <th style="padding:5px 10px;text-align:left">문제점</th>
                <th style="padding:5px 10px;text-align:left">조치</th>
              </tr></thead>
              <tbody>{prob_rows}</tbody>
            </table>'''}
          </div>
        </div>"""

    # campaign adjustments table
    ACTION_LABELS = {
        "pause": ("일시중단", "#d32f2f"),
        "reduce_bid": ("입찰가 인하", "#f57c00"),
        "reduce_budget": ("예산 감소", "#f57c00"),
        "increase_bid": ("입찰가 증액", "#2e7d32"),
        "increase_budget": ("예산 증액", "#2e7d32"),
        "monitor": ("모니터링", "#555"),
    }
    PRIORITY_COLORS = {"urgent": "#d32f2f", "high": "#f57c00", "medium": "#1565c0", "low": "#555"}

    adj_rows = ""
    for adj in analysis.get("campaign_adjustments", []):
        action_key = adj.get("action", "monitor")
        action_label, action_color = ACTION_LABELS.get(action_key, ("조치필요", "#555"))
        prio = adj.get("priority", "medium")
        prio_color = PRIORITY_COLORS.get(prio, "#555")
        bid_chg = adj.get("bid_change_pct")
        bud_chg = adj.get("budget_change_pct")
        kw_action = adj.get("keyword_action", "")
        chg_str = ""
        if bid_chg is not None:
            chg_str += f"입찰가 {'+' if bid_chg > 0 else ''}{bid_chg}%"
        if bud_chg is not None:
            chg_str += f" 예산 {'+' if bud_chg > 0 else ''}{bud_chg}%"
        if kw_action and kw_action != "없음":
            chg_str += f" / {kw_action}"
        adj_rows += f"""<tr>
          <td style="padding:7px 10px">
            <span style="background:{prio_color};color:white;padding:2px 7px;border-radius:10px;font-size:11px">{prio.upper()}</span>
          </td>
          <td style="padding:7px 10px;font-size:12px">{adj.get('brand','')}</td>
          <td style="padding:7px 10px;font-size:12px">{adj.get('campaign','')}</td>
          <td style="padding:7px 10px;text-align:right;background:#fff3cd">{fmt_roas(adj.get('current_roas_yd'))}</td>
          <td style="padding:7px 10px;text-align:right">{fmt_roas(adj.get('current_roas_7d'))}</td>
          <td style="padding:7px 10px;font-weight:bold;color:{action_color}">{action_label}</td>
          <td style="padding:7px 10px;color:#555;font-size:12px">{chg_str}</td>
          <td style="padding:7px 10px;color:#444;font-size:12px">{adj.get('reason','')}</td>
        </tr>"""

    # weekly actions
    action_html = ""
    for wa in analysis.get("weekly_actions", []):
        action_html += f"""
        <div style="display:flex;align-items:flex-start;margin:12px 0">
          <div style="background:#232F3E;color:white;border-radius:50%;min-width:28px;height:28px;
                      display:flex;align-items:center;justify-content:center;
                      font-weight:bold;margin-right:14px;font-size:14px">{wa['priority']}</div>
          <div>
            <strong style="color:#232F3E">{wa['action']}</strong>
            <p style="margin:3px 0;color:#666;font-size:13px">대상: {wa.get('campaign', '-')}</p>
            <p style="margin:3px 0;color:#2e7d32;font-size:13px">&#8594; {wa.get('expected_result', '')}</p>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Amazon PPC 일간 리포트</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:720px;margin:0 auto;background:white">

  <!-- Header -->
  <div style="background:#232F3E;padding:24px 30px;color:white">
    <div style="font-size:12px;color:#aaa;margin-bottom:6px">Amazon PPC 일간 리포트</div>
    <div style="font-size:22px;font-weight:bold">{d} 기준 분석 (30일 + 7일)</div>
    <div style="margin-top:10px">
      <span style="background:{oa_color};padding:4px 12px;border-radius:20px;font-size:13px">
        전체 상태: {oa_label}
      </span>
    </div>
    <div style="margin-top:14px;font-size:14px;color:#ddd;line-height:1.6">
      {analysis.get('executive_summary', '')}
    </div>
  </div>

  <div style="padding:24px 30px">

    {trend_html}

    <!-- Summary Table -->
    <h2 style="color:#232F3E;border-bottom:2px solid #232F3E;padding-bottom:8px">전체 성과 요약</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      <thead>
        <tr style="background:#232F3E;color:white">
          <th style="padding:10px 12px;text-align:left">지표</th>
          <th style="padding:10px 12px;text-align:right">어제 ({yd})</th>
          <th style="padding:10px 12px;text-align:right;background:#1a3a2a">최근 7일</th>
          <th style="padding:10px 12px;text-align:right">최근 30일</th>
        </tr>
      </thead>
      <tbody>
        <tr style="background:#f9f9f9">
          <td style="padding:8px 12px">광고비</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(s_yd['spend'])}</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{fmt_usd(s_7d['spend'])}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(s_30d['spend'])}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px">광고 매출</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(s_yd['sales'])}</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{fmt_usd(s_7d['sales'])}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(s_30d['sales'])}</td>
        </tr>
        <tr style="background:#f9f9f9">
          <td style="padding:8px 12px">ROAS</td>
          <td style="padding:8px 12px;text-align:right">{fmt_roas(s_yd['roas'])}</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{fmt_roas(s_7d['roas'])}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_roas(s_30d['roas'])}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px">ACOS</td>
          <td style="padding:8px 12px;text-align:right">{fmt_acos(s_yd['acos'])}</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{fmt_acos(s_7d['acos'])}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_acos(s_30d['acos'])}</td>
        </tr>
        <tr style="background:#f9f9f9">
          <td style="padding:8px 12px">CPC</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(s_yd['cpc'])}</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{fmt_usd(s_7d['cpc'])}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(s_30d['cpc'])}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px">CTR</td>
          <td style="padding:8px 12px;text-align:right">{s_yd['ctr']:.2f}%</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{s_7d['ctr']:.2f}%</td>
          <td style="padding:8px 12px;text-align:right">{s_30d['ctr']:.2f}%</td>
        </tr>
      </tbody>
    </table>

    <!-- Brand Performance 30d vs 7d -->
    <h2 style="color:#232F3E;border-bottom:2px solid #232F3E;padding-bottom:8px;margin-top:30px">브랜드별 성과 (30일 vs 7일)</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#232F3E;color:white">
          <th style="padding:10px 12px;text-align:left">브랜드</th>
          <th style="padding:10px 12px;text-align:right">30일 광고비</th>
          <th style="padding:10px 12px;text-align:right">30일 ROAS</th>
          <th style="padding:10px 12px;text-align:right;background:#1a3a2a">7일 광고비</th>
          <th style="padding:10px 12px;text-align:right;background:#1a3a2a">7일 ROAS</th>
          <th style="padding:10px 12px;text-align:right">트렌드</th>
        </tr>
      </thead>
      <tbody>{brand_rows}</tbody>
    </table>

    <!-- Brand-by-Brand Detailed Analysis -->
    <h2 style="color:#232F3E;border-bottom:2px solid #232F3E;padding-bottom:8px;margin-top:30px">브랜드별 상세 분석</h2>
    {brand_section_html}

    <!-- Campaign Adjustment Table -->
    {"" if not adj_rows else f'''
    <h2 style="color:#232F3E;border-bottom:2px solid #232F3E;padding-bottom:8px;margin-top:30px">
      캠페인별 세부 조정 권고
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead>
        <tr style="background:#232F3E;color:white">
          <th style="padding:8px 10px;text-align:left">우선순위</th>
          <th style="padding:8px 10px;text-align:left">브랜드</th>
          <th style="padding:8px 10px;text-align:left">캠페인</th>
          <th style="padding:8px 10px;text-align:right;background:#5a4a00">어제 ROAS</th>
          <th style="padding:8px 10px;text-align:right">7일 ROAS</th>
          <th style="padding:8px 10px;text-align:left">조치</th>
          <th style="padding:8px 10px;text-align:left">변경폭/키워드</th>
          <th style="padding:8px 10px;text-align:left">이유</th>
        </tr>
      </thead>
      <tbody>{adj_rows}</tbody>
    </table>'''}

    {"" if not zero7_html else f'''
    <h2 style="color:#d32f2f;border-bottom:2px solid #d32f2f;padding-bottom:8px;margin-top:24px">
      경고: 7일간 광고비 지출 + 매출 $0 캠페인
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="background:#ffebee">
        <th style="padding:8px 12px;text-align:left">캠페인</th>
        <th style="padding:8px 12px;text-align:right">7일 광고비</th>
        <th style="padding:8px 12px;text-align:right">매출</th>
      </tr></thead>
      <tbody>{zero7_html}</tbody>
    </table>'''}

    {"" if not anomaly_items else f'''
    <h2 style="color:#f57c00;border-bottom:2px solid #f57c00;padding-bottom:8px;margin-top:30px">이상 감지 알림</h2>
    <div style="background:#fff8e1;border-radius:6px;padding:16px 20px">
      <ul style="margin:0;padding-left:18px;color:#555;line-height:1.8">{anomaly_items}</ul>
    </div>
    {anomaly_analysis_html}'''}

    <!-- Weekly Actions -->
    <h2 style="color:#232F3E;border-bottom:2px solid #232F3E;padding-bottom:8px;margin-top:30px">
      이번 주 반드시 해야 할 액션 3가지
    </h2>
    <div style="background:#f8f9fa;border-radius:8px;padding:20px 24px">
      {action_html}
    </div>

  </div>

  <!-- Footer -->
  <div style="background:#f0f0f0;padding:16px 30px;font-size:12px;color:#888;text-align:center">
    분석 기준일: {d} | 데이터: Amazon Ads API (SP Campaigns, 14d attribution) | 분석: Claude Sonnet 4.6
  </div>

</div>
</body>
</html>"""


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Amazon PPC 일간 분석 에이전트")
    parser.add_argument("--days", type=int, default=30,
                        help="수집 기간 (일) - 최근 N일 (기본 30일, 7일은 그 부분집합)")
    parser.add_argument("--to", default=os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr"),
                        help="수신 이메일")
    parser.add_argument("--dry-run", action="store_true",
                        help="이메일 발송 없이 HTML 파일만 저장")
    parser.add_argument("--from-payload", type=str, default=None,
                        help="기존 payload JSON 파일로 Step 1 스킵 (Claude 분석 + 이메일만)")
    args = parser.parse_args()

    # PST (UTC-8) 기준 어제 = 아마존 US 광고 날짜 기준
    PST = timezone(timedelta(hours=-8))
    pst_today = datetime.now(PST).date()
    analysis_date = pst_today           # build_analysis_payload의 기준일 (어제 = analysis_date-1)
    data_end = pst_today - timedelta(days=1)  # 어제까지 수집 (오늘 데이터 미완성)

    # --from-payload: skip Step 1+2 and use existing payload
    if args.from_payload:
        print(f"\n[PPC Agent] 기존 payload 사용: {args.from_payload}")
        with open(args.from_payload, "r", encoding="utf-8") as f:
            payload = json.load(f)
        # extract data_end from payload
        yd = payload.get("summary", {}).get("yesterday", {}).get("date")
        if yd:
            data_end = date.fromisoformat(yd)
        print(f"  어제(payload): {data_end}")
        print(f"  어제 광고비: ${payload['summary']['yesterday']['spend']:,.2f}")
        print(f"  30일 총 ROAS: {payload['summary']['30d']['roas']:.2f}x")
    else:
        if not all([AD_CLIENT_ID, AD_CLIENT_SECRET, AD_REFRESH_TOKEN]):
            print("[ERROR] AMZ_ADS_CLIENT_ID / AMZ_ADS_CLIENT_SECRET / AMZ_ADS_REFRESH_TOKEN 없음")
            sys.exit(1)

        start_date = pst_today - timedelta(days=args.days)

        print(f"\n[PPC Agent] PST 기준 오늘: {pst_today}")
        print(f"[PPC Agent] 분석 기준일: {analysis_date} / 어제(PST): {data_end}")
        print(f"[PPC Agent] 데이터 수집 기간: {start_date} ~ {data_end}")

        # Step 1: Fetch data
        print("\n[Step 1] Amazon Ads 데이터 수집 중...")
        profiles = get_us_profiles()
        if not profiles:
            print("[ERROR] US seller 프로필 없음")
            sys.exit(1)
        print(f"  프로필 수: {len(profiles)} - {[p['seller'] for p in profiles]}")

        all_rows: List[Dict] = []
        for prof in profiles:
            pid = prof["profile_id"]
            seller = prof["seller"]
            brand_name = PROFILE_BRAND_MAP.get(seller, seller)
            print(f"\n  프로필: {seller} ({pid}) -> 브랜드: {brand_name}")
            try:
                ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                fut = ex.submit(fetch_sp_daily, pid, start_date, data_end)
                try:
                    rows = fut.result(timeout=2400)
                    ex.shutdown(wait=False)
                except concurrent.futures.TimeoutError:
                    ex.shutdown(wait=False)
                    print(f"  [WARN] {seller} - 2400s wall-clock timeout, skipping profile")
                    continue
                rows = compute_metrics(rows, profile_brand=brand_name)
                print(f"  -> {len(rows)}개 일별 행")
                all_rows.extend(rows)
            except PermissionError as e:
                ex.shutdown(wait=False)
                print(f"  [SKIP] {seller} - 권한 없음 (401/403), 스킵합니다: {e}")
            except Exception as e:
                ex.shutdown(wait=False)
                print(f"  [WARN] 프로필 실패: {e}")
                traceback.print_exc()

        if not all_rows:
            print("[ERROR] 수집된 데이터 없음")
            sys.exit(1)

        # Step 2: Build payload
        print("\n[Step 2] 분석 페이로드 구성...")
        payload = build_analysis_payload(all_rows, analysis_date)
        print(f"  어제 광고비: ${payload['summary']['yesterday']['spend']:,.2f}")
        print(f"  30일 총 ROAS: {payload['summary']['30d']['roas']:.2f}x")
        print(f"  이상 감지: {len(payload['anomalies_detected'])}건")

    # Step 3: Claude analysis
    print("\n[Step 3] Claude PPC 전문가 분석 중...")
    analysis = analyze_with_claude(payload)
    print(f"  전체 평가: {analysis.get('overall_assessment', '?')}")
    print(f"  액션 {len(analysis.get('weekly_actions', []))}개 생성됨")

    # Step 4: Build HTML
    print("\n[Step 4] HTML 이메일 생성...")
    html = build_html_email(payload, analysis)

    tmp_dir = ROOT / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    html_path = tmp_dir / f"ppc_report_{data_end.strftime('%Y%m%d')}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"  저장됨: {html_path}")

    # Step 5: Send email
    subject = (
        f"[Amazon PPC] 일간 리포트 - {data_end.strftime('%Y-%m-%d')} PST | "
        f"ROAS {payload['summary']['yesterday']['roas']:.2f}x | "
        f"ACOS {payload['summary']['yesterday']['acos'] or '-'}%"
    )

    if args.dry_run:
        print(f"\n[Dry Run] 이메일 발송 건너뜀. HTML: {html_path}")
        print(f"  제목: {subject}")
    else:
        print(f"\n[Step 5] 이메일 발송 중...")
        send_gmail_path = TOOLS_DIR / "send_gmail.py"
        result = subprocess.run(
            [sys.executable, str(send_gmail_path),
             "--to", args.to,
             "--subject", subject,
             "--body-file", str(html_path)],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode == 0:
            print(result.stdout)
            print(f"[완료] {args.to}으로 발송 성공!")
        else:
            print(f"[ERROR] 이메일 발송 실패:\n{result.stderr}")
            sys.exit(1)

    # Save raw payload for debugging
    payload_path = tmp_dir / f"ppc_payload_{data_end.strftime('%Y%m%d')}.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[완료] 페이로드 저장: {payload_path}")


if __name__ == "__main__":
    main()
