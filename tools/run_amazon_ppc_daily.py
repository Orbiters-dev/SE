"""
run_amazon_ppc_daily.py - Amazon PPC 일간 분석 에이전트

DataKeeper (PostgreSQL) -> 30일 캠페인 데이터 -> Claude PPC 전문가 분석 -> HTML 이메일 발송

Usage:
    python tools/run_amazon_ppc_daily.py
    python tools/run_amazon_ppc_daily.py --days 30 --to wj.choi@orbiters.co.kr
    python tools/run_amazon_ppc_daily.py --dry-run   # 이메일 발송 없이 분석만
"""

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


# ===========================================================================
# DataKeeper 수집
# ===========================================================================

def fetch_from_datakeeper(days: int) -> List[Dict]:
    """DataKeeper에서 amazon_ads_daily 데이터를 가져와 compute_metrics 형식으로 변환."""
    from data_keeper_client import DataKeeper

    dk = DataKeeper()
    rows = dk.get("amazon_ads_daily", days=days)
    if not rows:
        print("[ERROR] DataKeeper에서 amazon_ads_daily 데이터 없음")
        return []

    # DataKeeper 필드 -> compute_metrics 입력 형식 변환
    # DK: spend, sales, campaign_id, campaign_name, purchases
    # compute_metrics expects: cost, sales14d, campaignId, campaignName, purchases14d
    out = []
    for r in rows:
        out.append({
            "date": r.get("date", ""),
            "campaignId": r.get("campaign_id", ""),
            "campaignName": r.get("campaign_name", r.get("campaign_id", "")),
            "cost": float(r.get("spend", 0) or 0),
            "sales14d": float(r.get("sales", 0) or 0),
            "purchases14d": int(r.get("purchases", 0) or 0),
            "clicks": int(r.get("clicks", 0) or 0),
            "impressions": int(r.get("impressions", 0) or 0),
            "brand": r.get("brand", ""),
        })

    brands = set(r["brand"] for r in out)
    dates = sorted(set(r["date"] for r in out))
    print(f"  DataKeeper -> {len(out)}행 | 브랜드: {brands}")
    print(f"  기간: {dates[0]} ~ {dates[-1]}" if dates else "  기간: 없음")
    return out


# ===========================================================================
# Metrics computation
# ===========================================================================

def compute_metrics(rows: List[Dict], profile_brand: Optional[str] = None) -> List[Dict]:
    """Add ROAS, ACOS, CPC, CTR, CVR to each row. Brand is set from profile_brand."""
    out = []
    for r in rows:
        cost = float(r.get("cost", 0) or 0)
        sales = float(r.get("sales14d", 0) or 0)
        clicks = int(r.get("clicks", 0) or 0)
        impressions = int(r.get("impressions", 0) or 0)
        purchases = int(r.get("purchases14d", 0) or 0)

        roas = round(sales / cost, 2) if cost > 0 else 0
        acos = round(cost / sales * 100, 1) if sales > 0 else None
        cpc = round(cost / clicks, 2) if clicks > 0 else 0
        ctr = round(clicks / impressions * 100, 2) if impressions > 0 else 0
        cvr = round(purchases / clicks * 100, 2) if clicks > 0 else 0

        out.append({
            "date": r.get("date", ""),
            "campaignId": r.get("campaignId"),
            "campaignName": r.get("campaignName", ""),
            "brand": profile_brand or r.get("brand") or "기타",
            "impressions": impressions,
            "clicks": clicks,
            "purchases": purchases,
            "cost": round(cost, 2),
            "sales": round(sales, 2),
            "roas": roas,
            "acos": acos,
            "cpc": cpc,
            "ctr": ctr,
            "cvr": cvr,
        })
    return out


def aggregate_by_campaign(rows: List[Dict]) -> Dict[str, Dict]:
    """Sum metrics by campaign name."""
    bucket: Dict[str, Dict] = defaultdict(lambda: {
        "cost": 0.0, "sales": 0.0, "clicks": 0, "impressions": 0, "purchases": 0, "brand": ""
    })
    for r in rows:
        name = r["campaignName"]
        b = bucket[name]
        b["cost"]        += r["cost"]
        b["sales"]       += r["sales"]
        b["clicks"]      += r["clicks"]
        b["impressions"] += r["impressions"]
        b["purchases"]   += r.get("purchases", 0)
        b["brand"]        = r["brand"]

    out = {}
    for name, v in bucket.items():
        cost = v["cost"]; sales = v["sales"]; clicks = v["clicks"]; impr = v["impressions"]
        purchases = v["purchases"]
        out[name] = {
            **v,
            "cost":      round(cost, 2),
            "sales":     round(sales, 2),
            "purchases": purchases,
            "roas":      round(sales / cost, 2) if cost > 0 else 0,
            "acos":      round(cost / sales * 100, 1) if sales > 0 else None,
            "cpc":       round(cost / clicks, 2) if clicks > 0 else 0,
            "ctr":       round(clicks / impr * 100, 2) if impr > 0 else 0,
            "cvr":       round(purchases / clicks * 100, 2) if clicks > 0 else 0,
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
        purchases = sum(r.get("purchases", 0) for r in rs)
        return {
            "spend": round(cost, 2),
            "sales": round(sales, 2),
            "purchases": purchases,
            "roas":  round(sales / cost, 2) if cost > 0 else 0,
            "acos":  round(cost / sales * 100, 1) if sales > 0 else None,
            "cpc":   round(cost / clicks, 2) if clicks > 0 else 0,
            "ctr":   round(clicks / impr * 100, 2) if impr > 0 else 0,
            "cvr":   round(purchases / clicks * 100, 2) if clicks > 0 else 0,
            "clicks": clicks,
            "impressions": impr,
        }

    def brand_breakdown(rs):
        bd: Dict[str, Dict] = defaultdict(lambda: {"cost": 0.0, "sales": 0.0, "clicks": 0, "impressions": 0, "purchases": 0})
        for r in rs:
            b = bd[r["brand"]]
            b["cost"] += r["cost"]; b["sales"] += r["sales"]
            b["clicks"] += r["clicks"]; b["impressions"] += r["impressions"]
            b["purchases"] += r.get("purchases", 0)
        result = []
        for brand, v in sorted(bd.items()):
            cost = v["cost"]; sales = v["sales"]; clicks = v["clicks"]; purchases = v["purchases"]
            result.append({
                "brand": brand,
                "spend": round(cost, 2),
                "sales": round(sales, 2),
                "purchases": purchases,
                "roas":  round(sales / cost, 2) if cost > 0 else 0,
                "acos":  round(cost / sales * 100, 1) if sales > 0 else None,
                "cvr":   round(purchases / clicks * 100, 2) if clicks > 0 else 0,
                "cpc":   round(cost / clicks, 2) if clicks > 0 else 0,
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
                "cvr_7d":     v7.get("cvr", 0),
                "cpc_7d":     v7.get("cpc", 0),
                "clicks_7d":  v7.get("clicks", 0),
                "purchases_7d": v7.get("purchases", 0),
                "spend_30d":  round(v30["cost"], 2),
                "sales_30d":  round(v30["sales"], 2),
                "roas_30d":   v30["roas"],
                "acos_30d":   v30["acos"],
                "cvr_30d":    v30.get("cvr", 0),
                "cpc_30d":    v30.get("cpc", 0),
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

SYSTEM_PROMPT = """당신은 아마존 PPC 전문 에이전시의 시니어 전략가입니다 (10년+ 경력).
SP/SB/SD 캠페인 최적화, 입찰 전략, 키워드 확장, 예산 배분에 특화되어 있습니다.
e-커머스 Baby/Kids 카테고리 (Grosmimi=유아식기, CHA&MOM=스킨케어, Naeiae=스낵) 전문입니다.

=== 분석 프레임워크 ===

1단계: 계정 건전성 스코어링
- SPEND EFFICIENCY: (매출 / 지출) 비율 — 전체 광고 ROI의 핵심
- CVR (전환율): 클릭 -> 구매 전환율. 이커머스 벤치마크 중앙값: 9.47% (Amazon SP 2025 기준)
  CVR < 5%: 리스팅 문제 의심 | CVR 5-10%: 정상 | CVR > 15%: 고효율 (스케일업 대상)
- CTR: 노출 -> 클릭 비율. SP 벤치마크: 0.40% (전체), Baby Products: 0.30-0.45%
  CTR < 0.20%: 타겟팅/크리에이티브 문제 | CTR 0.30-0.50%: 정상 | CTR > 0.60%: 우수
- CPC: Baby Products 평균 $0.75-1.20. CPC > $1.50이면 입찰 과다 의심

2단계: ROAS/ACOS 판단 기준
- ROAS >= 5.0: 최우수 (ACOS 20% 이하) -> 공격적 스케일업
- ROAS 3.0~5.0: 우수 (ACOS 20-33%) -> 점진적 스케일업
- ROAS 2.0~3.0: 보통 (ACOS 33-50%) -> 최적화 필요, 모니터링
- ROAS 1.5~2.0: 위험 (ACOS 50-67%) -> 입찰가 인하 필요
- ROAS 1.0~1.5: 심각 (ACOS 67-100%) -> 대폭 인하 또는 중단
- ROAS < 1.0: 적자 (ACOS >100%) -> 즉시 중단

3단계: 트렌드 진단 (가장 중요)
- 3기간 비교: 어제(yd) vs 7일 vs 30일
- 7일이 30일보다 좋으면 "개선 중" (모멘텀 유지/강화)
- 7일이 30일보다 나쁘면 "악화 중" (원인 파악 + 즉시 조치)
- 어제가 7일 평균 대비 30%+ 변동: 이상 신호 (일시적 vs 구조적 판단)
- 연속 하락 (30d > 7d > yd): 빨간불 — 구조적 문제 진단 필수

4단계: 캠페인별 심층 진단
- WASTED SPEND 분석: 클릭 있는데 매출 $0 = 전환 실패 (리스팅 문제 or 타겟팅 미스매치)
- CPC vs CVR 매트릭스:
  높은CPC + 높은CVR = 수익성 확인 후 유지
  높은CPC + 낮은CVR = 즉시 입찰 인하 (가장 위험)
  낮은CPC + 높은CVR = 최적 — 스케일업 대상
  낮은CPC + 낮은CVR = 타겟팅 리뷰 필요
- 신규 캠페인 (7일 미만): learning phase로 분류, 14일 데이터 전까지는 급한 조정 자제

5단계: 브랜드 포트폴리오 전략
- 브랜드간 예산 재배분 권고 (ROAS 높은 브랜드에 예산 이동)
- 각 브랜드의 시장 포지션 고려 (Grosmimi=프리미엄 유아식기, CHA&MOM=스킨케어 진입, Naeiae=스낵)
- TACoS 관점: 광고비가 전체 매출의 몇 %인지 (15% 이하 건강, 25% 이상 과다)

=== 캠페인 조정 강도 기준 (campaign_adjustments 필수 적용) ===
- 7일 ROAS < 1.0: action=pause, priority=urgent
- 7일 ROAS 1.0~1.5: action=reduce_bid, bid_change_pct=-30, priority=urgent
- 7일 ROAS 1.5~2.0: action=reduce_bid, bid_change_pct=-15, priority=high
- 7일 ROAS 2.0~3.0: action=monitor, priority=medium
- 7일 ROAS 3.0~5.0: action=increase_budget, budget_change_pct=+20, priority=medium
- 7일 ROAS > 5.0: action=increase_budget, budget_change_pct=+30, bid_change_pct=+10, priority=high
- 클릭 있는데 7일 매출 $0: action=pause, priority=urgent
- 어제(yd) ROAS가 7일 평균 대비 30%+ 급락: reduce_bid -20% 추가
- 어제(yd) 광고비가 7일 일평균 대비 100%+ 급등: 예산 캡 설정 권고

=== 텍스트 포맷 규칙 (executive_summary, insight, action, reason 등 모든 텍스트 필드에 적용) ===
- 줄바꿈(\\n)을 적극 활용하여 가독성 확보
- 핵심 수치는 **볼드**로 강조 (예: **ROAS 4.2x**, **$1,500 절약**)
- 불렛포인트(- )로 항목 구분. 하위 항목은 들여쓰기 후 - 사용
- 번호 매기기(1. 2. 3.)로 순서/단계 표현
- 한 문단에 모든 내용 넣지 말고, 의미 단위로 줄바꿈
- 예시:
  "executive_summary": "**전체 ROAS 3.8x**로 양호하나, CHA&MOM 브랜드 **ROAS 1.2x** 위험 수준\\n- Grosmimi: 7일 ROAS **5.1x** (30일 대비 +15% 개선중)\\n- CHA&MOM: 7일 ROAS **1.2x** (30일 2.0x 대비 -40% 급락) → 즉시 조치 필요"

=== 출력 형식: JSON (아래 구조 엄격히 준수, 모든 필드 필수) ===
{
  "executive_summary": "3줄 핵심 요약: (1) 전체 건전성 한줄 (2) 가장 큰 리스크 (3) 가장 큰 기회",
  "overall_assessment": "good | warning | danger",
  "health_score": {
    "score": 72,
    "spend_efficiency": "30일 매출/지출 비율 해석",
    "cvr_diagnosis": "전체 CVR 수준 및 벤치마크 대비 진단",
    "trend_direction": "improving | stable | declining"
  },
  "period_comparison": {
    "trend_30d_vs_7d": "30일 대비 최근 7일 전반적 트렌드 해석",
    "yesterday_vs_7d": "어제 성과가 7일 평균 대비 어떤 상태인지 해석",
    "improving_brands": ["7일이 30일보다 좋아진 브랜드"],
    "declining_brands": ["7일이 30일보다 나빠진 브랜드"],
    "momentum": "가속 | 유지 | 감속 | 역전"
  },
  "brand_insights": [
    {
      "brand": "브랜드명",
      "status": "good|warning|danger",
      "insight": "어제/7일/30일 비교 인사이트 (ROAS, CVR, CPC 수치 포함)",
      "action": "브랜드 레벨 즉각 액션 (구체적 수치 포함)",
      "budget_recommendation": "현재 일예산 추정 -> 권장 일예산 (증감%)"
    }
  ],
  "brand_campaign_analysis": [
    {
      "brand": "브랜드명",
      "top_campaigns": [
        {"campaign": "캠페인명", "roas_7d": 5.2, "roas_yd": 4.8, "cvr_7d": 12.5, "why_good": "구체적 이유 (CVR/CTR/CPC 포함)", "action": "예산 30% 증액 + 유사 키워드 확장", "scale_potential": "high|medium|low"}
      ],
      "problem_campaigns": [
        {"campaign": "캠페인명", "roas_7d": 0.8, "roas_yd": 0.5, "cvr_7d": 2.1, "issue": "문제점 (CVR 낮음=리스팅 문제 / CTR 낮음=타겟팅 문제 / CPC 높음=입찰 과다)", "action": "즉시 일시중단", "root_cause": "targeting|listing|bidding|competition"}
      ],
      "brand_strategy": "이 브랜드 이번 주 예산/입찰/키워드 전략 한 줄 요약"
    }
  ],
  "campaign_adjustments": [
    {
      "campaign": "캠페인명",
      "brand": "브랜드명",
      "current_roas_7d": 1.2,
      "current_roas_yd": 0.9,
      "current_cvr": 3.5,
      "current_cpc": 1.20,
      "action": "pause | reduce_bid | reduce_budget | increase_bid | increase_budget | monitor",
      "bid_change_pct": -30,
      "budget_change_pct": null,
      "keyword_action": "없음 | 키워드 추가 권고 | 부정키워드 추가 | 키워드 일시중단",
      "reason": "구체적 진단 (ROAS/CVR/CPC 수치 + 벤치마크 대비 해석)",
      "priority": "urgent | high | medium",
      "root_cause": "targeting|listing|bidding|competition|seasonality"
    }
  ],
  "wasted_spend_analysis": {
    "total_wasted_7d": 0.00,
    "worst_offenders": [
      {"campaign": "캠페인명", "spend_7d": 50.0, "clicks_7d": 30, "sales_7d": 0, "diagnosis": "원인 진단"}
    ],
    "savings_potential": "절약 가능 금액 및 재배분 권고"
  },
  "anomaly_analysis": "이상 감지 항목에 대한 전문가 해석 및 즉각 조치",
  "weekly_actions": [
    {"priority": 1, "action": "구체적 액션 (금액/% 포함)", "expected_result": "기대 효과 (ROAS X.X->Y.Y 또는 절약 $XX)", "campaign": "대상 캠페인명", "urgency": "즉시|이번주내|모니터링"},
    {"priority": 2, "action": "구체적 액션", "expected_result": "기대 효과", "campaign": "대상", "urgency": "즉시|이번주내|모니터링"},
    {"priority": 3, "action": "구체적 액션", "expected_result": "기대 효과", "campaign": "대상", "urgency": "즉시|이번주내|모니터링"}
  ]
}"""


def analyze_with_claude(payload: Dict) -> Dict:
    """Call Claude API with PPC expert role and return structured analysis."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    user_message = f"""다음은 PST 기준 어제({payload['yesterday']}) Amazon PPC 광고 성과 데이터입니다.
전문 PPC 에이전시 전략가로서 깊이 있는 분석을 JSON으로 제공하세요.

=== 분석 데이터 ===
{json.dumps(payload, ensure_ascii=False, indent=2)}

=== 분석 체크리스트 (반드시 수행) ===
1. 3기간 비교: summary.yesterday vs summary.7d vs summary.30d (ROAS, CVR, CPC, CTR 모두)
2. CVR 진단: 캠페인별 cvr_7d 확인. CVR < 5%면 리스팅/가격 문제 의심, CVR > 15%면 스케일업 대상
3. CPC 효율: cpc_7d > $1.50이면 입찰 과다, cpc_7d < $0.50이면 노출 부족 가능성
4. Wasted Spend: campaigns_7d.zero_sales 캠페인의 총 지출 계산 + 재배분 권고
5. 브랜드 포트폴리오: 브랜드간 ROAS 격차 분석 -> 예산 재배분 방향
6. campaign_adjustments: 시스템 프롬프트의 ROAS 구간 기준 엄격 적용 + root_cause 진단
7. health_score: 0-100 점수 (ROAS 40점 + CVR 25점 + 트렌드 20점 + 효율성 15점)
8. anomalies_detected의 각 항목에 대해 일시적 vs 구조적 문제 판단
- JSON만 출력 (코드블록 없이 순수 JSON)"""

    for attempt in range(3):
        max_tok = 16384 if attempt == 0 else 32768
        try:
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
                timeout=300,
            )
        except requests.exceptions.ReadTimeout:
            print(f"  [WARN] Claude API timeout (300s), retry {attempt+1}/3")
            if attempt < 2:
                continue
            raise
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
            if attempt < 2:
                print(f"  [WARN] Claude JSON 파싱 실패 (stop={stop}, max_tokens={max_tok}), 재시도 {attempt+1}/3")
                continue
            raise RuntimeError(f"Claude JSON 파싱 3회 연속 실패 (stop={stop})")


# ===========================================================================
# HTML Email Builder
# ===========================================================================

def _md_to_html(text: str) -> str:
    """Convert markdown-like text from Claude analysis to styled HTML."""
    import re
    if not text:
        return ""
    lines = text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<div style='height:6px'></div>")
            continue

        # Bold: **text** or __text__
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        stripped = re.sub(r'__(.+?)__', r'<strong>\1</strong>', stripped)

        # Inline code/highlight: `text`
        stripped = re.sub(r'`(.+?)`', r'<code style="background:#f5f5f5;padding:1px 5px;border-radius:3px;font-size:12px">\1</code>', stripped)

        # Bullet points: - or * or  or
        bullet_match = re.match(r'^[-*]\s+(.+)', stripped)
        sub_bullet_match = re.match(r'^[-*]\s+(.+)', line) if line.startswith("  ") or line.startswith("\t") else None

        if sub_bullet_match:
            if not in_list:
                html_parts.append("<ul style='margin:4px 0 4px 16px;padding-left:12px;list-style:disc'>")
                in_list = True
            html_parts.append(f"<li style='margin:3px 0;color:#555;font-size:13px'>{sub_bullet_match.group(1)}</li>")
        elif bullet_match:
            if not in_list:
                html_parts.append("<ul style='margin:4px 0;padding-left:16px;list-style:none'>")
                in_list = True
            content = bullet_match.group(1)
            # Detect emoji-style bullets or numbered items
            html_parts.append(f"<li style='margin:5px 0;color:#333;font-size:13px;position:relative;padding-left:12px'>"
                              f"<span style='position:absolute;left:-4px;color:#1565c0'>&#8226;</span>{content}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Numbered lines: 1. or 1)
            num_match = re.match(r'^(\d+)[.)]\s+(.+)', stripped)
            if num_match:
                num, content = num_match.groups()
                html_parts.append(
                    f"<div style='display:flex;align-items:flex-start;margin:5px 0'>"
                    f"<span style='background:#232F3E;color:white;border-radius:50%;min-width:20px;height:20px;"
                    f"display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;"
                    f"margin-right:8px;flex-shrink:0'>{num}</span>"
                    f"<span style='color:#333;font-size:13px;line-height:1.5'>{content}</span></div>")
            else:
                html_parts.append(f"<p style='margin:4px 0;color:#333;font-size:13px;line-height:1.6'>{stripped}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def status_color(status: str) -> str:
    return {"good": "#1a5c3a", "warning": "#8d6e00", "danger": "#8b1a1a"}.get(status, "#555")


def fmt_usd(v) -> str:
    return f"${v:,.2f}" if v is not None else "-"


def fmt_roas(v) -> str:
    if v is None:
        return "-"
    color = "#1a5c3a" if v >= 3.0 else ("#8b1a1a" if v < 2.0 else "#8d6e00")
    return f'<span style="color:{color};font-weight:bold">{v:.2f}x</span>'


def fmt_acos(v) -> str:
    if v is None:
        return "-"
    color = "#1a5c3a" if v < 15 else ("#8b1a1a" if v > 25 else "#8d6e00")
    return f'<span style="color:{color};font-weight:bold">{v:.1f}%</span>'


def fmt_cvr(v) -> str:
    if v is None or v == 0:
        return "-"
    color = "#1a5c3a" if v >= 10 else ("#8b1a1a" if v < 5 else "#8d6e00")
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
        momentum = pc.get("momentum", "")
        momentum_colors = {"가속": "#1a5c3a", "유지": "#8d6e00", "감속": "#8b1a1a", "역전": "#8b1a1a"}
        momentum_badge = f'<span style="background:{momentum_colors.get(momentum, "#555")};color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px">{momentum}</span>' if momentum else ""
        trend_html = f"""
        <div style="background:#e3f2fd;border-left:4px solid #1565c0;padding:12px 16px;margin:16px 0;border-radius:0 6px 6px 0">
          <strong style="color:#1565c0">30일 vs 7일 트렌드</strong>{momentum_badge}
          <div style="margin:8px 0">{_md_to_html(pc.get('trend_30d_vs_7d', ''))}</div>
          <div style="margin:6px 0">{_md_to_html(pc.get('yesterday_vs_7d', ''))}</div>
          <div style="margin-top:8px;padding-top:8px;border-top:1px solid #bbdefb;font-size:13px">
            <span style="color:#1a5c3a">&#8593; 개선: <strong>{impr_brands}</strong></span> &nbsp;|&nbsp;
            <span style="color:#8b1a1a">&#8595; 악화: <strong>{decl_brands}</strong></span>
          </div>
        </div>"""

    # brand table — 30d + 7d side by side
    brand_rows = ""
    for b in payload.get("brand_breakdown", []):
        r7  = b.get("roas_7d", 0)
        r30 = b.get("roas_30d", 0)
        pct = b.get("roas_7d_vs_30d_pct")
        pct_str = (f'+{pct:.1f}%' if pct >= 0 else f'{pct:.1f}%') if pct is not None else "-"
        pct_color = "#1a5c3a" if (pct or 0) >= 0 else "#8b1a1a"
        brand_rows += f"""
        <tr>
          <td style="padding:8px 12px;font-weight:500">{b['brand']}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(b.get('spend_30d'))}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_roas(r30)}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_usd(b.get('spend_7d'))}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_roas(r7)}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_cvr(b.get('cvr_7d', b.get('cvr')))}</td>
          <td style="padding:8px 12px;text-align:right;font-weight:bold;color:{pct_color}">{pct_str}</td>
        </tr>"""

    # brand insights
    brand_insight_html = ""
    for bi in analysis.get("brand_insights", []):
        sc = status_color(bi.get("status", "warning"))
        budget_rec = bi.get("budget_recommendation", "")
        budget_html = f'<div style="margin-top:6px;padding:4px 10px;background:#e8f5e9;border-radius:4px;font-size:12px;color:#1a5c3a">{budget_rec}</div>' if budget_rec else ""
        brand_insight_html += f"""
        <div style="border-left:4px solid {sc};padding:10px 16px;margin:8px 0;background:#fafafa;border-radius:0 6px 6px 0">
          <strong style="color:{sc};font-size:15px">{bi['brand']}</strong>
          <div style="margin:6px 0">{_md_to_html(bi.get('insight', ''))}</div>
          <div style="margin:6px 0;padding:8px 12px;background:#f0f4f8;border-radius:6px">
            <span style="color:#1565c0;font-weight:bold;font-size:12px">ACTION:</span>
            <div style="margin-top:4px">{_md_to_html(bi.get('action', ''))}</div>
          </div>
          {budget_html}
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
          <td style="padding:7px 12px;color:#8b1a1a">{c.get('issue', '')}</td>
          <td style="padding:7px 12px">{c.get('action', '')}</td>
        </tr>"""

    # zero sales 7d
    zero7 = payload.get("campaigns_7d", {}).get("zero_sales", [])
    zero7_html = ""
    for z in zero7:
        zero7_html += f"""<tr style="background:#fff3f3">
          <td style="padding:7px 12px;font-size:12px">{z['campaign']}</td>
          <td style="padding:7px 12px;text-align:right">{fmt_usd(z.get('cost'))}</td>
          <td style="padding:7px 12px;text-align:right;color:#8b1a1a">$0</td>
        </tr>"""

    # anomalies
    anomaly_items = "".join(f'<li style="margin:6px 0">{a}</li>' for a in payload.get("anomalies_detected", []))
    anomaly_analysis_html = ""
    if analysis.get("anomaly_analysis"):
        anomaly_analysis_html = f"""
        <div style="background:#fff3e0;border-left:4px solid #8d6e00;padding:12px 16px;margin-top:10px">
          <strong style="color:#e65100">전문가 해석</strong>
          <div style="margin:8px 0">{_md_to_html(analysis['anomaly_analysis'])}</div>
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
              <td style="padding:6px 10px;text-align:right">{fmt_cvr(c.get('cvr_7d'))}</td>
              <td style="padding:6px 10px;text-align:right">{fmt_acos(c.get('acos_7d'))}</td>
            </tr>"""

        # top/problem rows from Claude
        def _scale_badge(s):
            colors = {"high": "#1a5c3a", "medium": "#8d6e00", "low": "#8b1a1a"}
            labels = {"high": "HIGH", "medium": "MED", "low": "LOW"}
            if not s: return ""
            return f'<span style="background:{colors.get(s,"#888")};color:white;padding:1px 6px;border-radius:8px;font-size:10px;margin-left:4px">{labels.get(s, s)}</span>'

        top_rows = "".join(f"""<tr>
          <td style="padding:8px 10px;font-size:12px;font-weight:500">{t['campaign']}</td>
          <td style="padding:6px 10px;text-align:right;background:#fff3cd">{fmt_roas(t.get('roas_yd'))}</td>
          <td style="padding:6px 10px;text-align:right;color:#1a5c3a">{fmt_roas(t.get('roas_7d'))}</td>
          <td style="padding:6px 10px;font-size:12px">{_md_to_html(t.get('why_good',''))}</td>
          <td style="padding:6px 10px">
            <div style="color:#1a5c3a;font-weight:bold;font-size:12px">{_md_to_html(t.get('action',''))}</div>
            {_scale_badge(t.get('scale_potential',''))}
          </td>
        </tr>""" for t in bca.get("top_campaigns", []))

        def _root_badge(rc):
            colors = {"targeting": "#7b1fa2", "listing": "#1565c0", "bidding": "#e65100", "competition": "#c62828", "seasonality": "#558b2f"}
            if not rc: return ""
            return f'<span style="background:{colors.get(rc,"#888")};color:white;padding:1px 6px;border-radius:8px;font-size:10px">{rc}</span>'

        prob_rows = "".join(f"""<tr>
          <td style="padding:8px 10px;font-size:12px;font-weight:500">{p['campaign']}</td>
          <td style="padding:6px 10px;text-align:right;background:#fff3cd">{fmt_roas(p.get('roas_yd'))}</td>
          <td style="padding:6px 10px;text-align:right;color:#8b1a1a">{fmt_roas(p.get('roas_7d'))}</td>
          <td style="padding:6px 10px;font-size:12px">
            {_root_badge(p.get('root_cause',''))}
            <div style="margin-top:3px">{_md_to_html(p.get('issue',''))}</div>
          </td>
          <td style="padding:6px 10px">
            <div style="color:#8d6e00;font-weight:bold;font-size:12px">{_md_to_html(p.get('action',''))}</div>
          </td>
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
            <div style="margin:0 0 10px">{_md_to_html(b_insight.get('insight',''))}</div>

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
                  <th style="padding:6px 10px;text-align:right">7일 CVR</th>
                  <th style="padding:6px 10px;text-align:right">7일 ACOS</th>
                </tr>
              </thead>
              <tbody>{data_rows}</tbody>
            </table>

            {"" if not top_rows else f'''
            <p style="margin:10px 0 6px;font-weight:bold;color:#1a5c3a;font-size:13px">잘된 캠페인</p>
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
            <p style="margin:10px 0 6px;font-weight:bold;color:#8b1a1a;font-size:13px">문제 캠페인</p>
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
        "pause": ("일시중단", "#8b1a1a"),
        "reduce_bid": ("입찰가 인하", "#8d6e00"),
        "reduce_budget": ("예산 감소", "#8d6e00"),
        "increase_bid": ("입찰가 증액", "#1a5c3a"),
        "increase_budget": ("예산 증액", "#1a5c3a"),
        "monitor": ("모니터링", "#555"),
    }
    PRIORITY_COLORS = {"urgent": "#8b1a1a", "high": "#8d6e00", "medium": "#1565c0", "low": "#555"}

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
          <td style="padding:7px 10px;font-size:12px">{_md_to_html(adj.get('reason',''))}</td>
        </tr>"""

    # weekly actions
    URGENCY_COLORS = {"즉시": "#8b1a1a", "이번주내": "#8d6e00", "모니터링": "#1565c0"}
    action_html = ""
    for wa in analysis.get("weekly_actions", []):
        urg = wa.get("urgency", "이번주내")
        urg_color = URGENCY_COLORS.get(urg, "#555")
        action_html += f"""
        <div style="display:flex;align-items:flex-start;margin:12px 0">
          <div style="background:#232F3E;color:white;border-radius:50%;min-width:28px;height:28px;
                      display:flex;align-items:center;justify-content:center;
                      font-weight:bold;margin-right:14px;font-size:14px">{wa['priority']}</div>
          <div>
            <span style="background:{urg_color};color:white;padding:1px 8px;border-radius:10px;font-size:11px;margin-right:6px">{urg}</span>
            <strong style="color:#232F3E">{wa['action']}</strong>
            <p style="margin:3px 0;color:#666;font-size:13px">대상: {wa.get('campaign', '-')}</p>
            <p style="margin:3px 0;color:#1a5c3a;font-size:13px">&#8594; {wa.get('expected_result', '')}</p>
          </div>
        </div>"""

    # ── Python 3.11 호환: 중첩 f-string 금지 → 미리 변수로 추출 ────────
    _ppc_hs = analysis.get("health_score") or {}
    if _ppc_hs:
        _ppc_trend_color = "#1a5c3a" if _ppc_hs.get("trend_direction") == "improving" else "#8b1a1a" if _ppc_hs.get("trend_direction") == "declining" else "#8d6e00"
        _ppc_trend_label = "↑ 개선중" if _ppc_hs.get("trend_direction") == "improving" else "↓ 악화중" if _ppc_hs.get("trend_direction") == "declining" else "→ 유지"
        _ppc_health_block = f'''
    <div style="background:linear-gradient(135deg,#232F3E,#37475A);border-radius:10px;padding:20px 24px;margin:16px 0;color:white">
      <div style="display:flex;align-items:center;gap:16px">
        <div style="font-size:42px;font-weight:bold;min-width:60px">{_ppc_hs.get("score", "-")}</div>
        <div style="font-size:11px;color:#aaa;border-left:1px solid #555;padding-left:16px">
          <div>HEALTH SCORE /100</div>
          <div style="color:#ccc;margin-top:4px">{_ppc_hs.get("spend_efficiency", "")}</div>
          <div style="color:#ccc;margin-top:2px">{_ppc_hs.get("cvr_diagnosis", "")}</div>
          <div style="margin-top:4px">
            <span style="background:{_ppc_trend_color};padding:2px 8px;border-radius:10px;font-size:11px">{_ppc_trend_label}</span>
          </div>
        </div>
      </div>
    </div>'''
    else:
        _ppc_health_block = ""

    _ppc_adj_block = ""
    if adj_rows:
        _ppc_adj_block = f'''
    <h2 style="color:#232F3E;border-bottom:2px solid #232F3E;padding-bottom:8px;margin-top:30px">캠페인별 세부 조정 권고</h2>
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
    </table>'''

    _ppc_zero7_block = ""
    if zero7_html:
        _ppc_zero7_block = f'''
    <h2 style="color:#8b1a1a;border-bottom:2px solid #8b1a1a;padding-bottom:8px;margin-top:24px">경고: 7일간 광고비 지출 + 매출 $0 캠페인</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="background:#ffebee">
        <th style="padding:8px 12px;text-align:left">캠페인</th>
        <th style="padding:8px 12px;text-align:right">7일 광고비</th>
        <th style="padding:8px 12px;text-align:right">매출</th>
      </tr></thead>
      <tbody>{zero7_html}</tbody>
    </table>'''

    _wsa = analysis.get("wasted_spend_analysis") or {}
    _ppc_wasted_block = ""
    if _wsa and _wsa.get("worst_offenders"):
        _wo_rows = "".join(
            f'<tr><td style="padding:5px 10px;font-size:11px">{wo.get("campaign","")}</td>'
            f'<td style="padding:5px 10px;text-align:right">{fmt_usd(wo.get("spend_7d",0))}</td>'
            f'<td style="padding:5px 10px;text-align:right">{wo.get("clicks_7d",0)}</td>'
            f'<td style="padding:5px 10px;color:#8b1a1a;font-size:11px">{wo.get("diagnosis","")}</td></tr>'
            for wo in _wsa.get("worst_offenders", []))
        _ppc_wasted_block = f'''
    <h2 style="color:#8b1a1a;border-bottom:2px solid #8b1a1a;padding-bottom:8px;margin-top:30px">낭비 광고비 분석 (7일)</h2>
    <div style="background:#fff3f3;border-radius:8px;padding:16px 20px;margin-bottom:12px">
      <div style="font-size:18px;font-weight:bold;color:#8b1a1a">총 낭비 추정: {fmt_usd(_wsa.get("total_wasted_7d", 0))}</div>
      <p style="margin:6px 0;color:#555;font-size:13px">{_wsa.get("savings_potential", "")}</p>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="background:#ffebee">
        <th style="padding:6px 10px;text-align:left">캠페인</th>
        <th style="padding:6px 10px;text-align:right">7일 지출</th>
        <th style="padding:6px 10px;text-align:right">클릭</th>
        <th style="padding:6px 10px;text-align:left">진단</th>
      </tr></thead>
      <tbody>{_wo_rows}</tbody>
    </table>'''

    _ppc_anomaly_block = ""
    if anomaly_items:
        _ppc_anomaly_block = f'''
    <h2 style="color:#8d6e00;border-bottom:2px solid #8d6e00;padding-bottom:8px;margin-top:30px">이상 감지 알림</h2>
    <div style="background:#fff8e1;border-radius:6px;padding:16px 20px">
      <ul style="margin:0;padding-left:18px;color:#555;line-height:1.8">{anomaly_items}</ul>
    </div>
    {anomaly_analysis_html}'''

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
      {_md_to_html(analysis.get('executive_summary', '')).replace('color:#333', 'color:#ddd').replace('color:#555', 'color:#bbb')}
    </div>
  </div>

  <div style="padding:24px 30px">

    {trend_html}

    {_ppc_health_block}

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
        <tr style="background:#f9f9f9">
          <td style="padding:8px 12px">CVR (전환율)</td>
          <td style="padding:8px 12px;text-align:right">{fmt_cvr(s_yd.get('cvr'))}</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{fmt_cvr(s_7d.get('cvr'))}</td>
          <td style="padding:8px 12px;text-align:right">{fmt_cvr(s_30d.get('cvr'))}</td>
        </tr>
        <tr>
          <td style="padding:8px 12px">주문수</td>
          <td style="padding:8px 12px;text-align:right">{s_yd.get('purchases', 0):,}</td>
          <td style="padding:8px 12px;text-align:right;background:#f0fff0">{s_7d.get('purchases', 0):,}</td>
          <td style="padding:8px 12px;text-align:right">{s_30d.get('purchases', 0):,}</td>
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
          <th style="padding:10px 12px;text-align:right">7일 CVR</th>
          <th style="padding:10px 12px;text-align:right">트렌드</th>
        </tr>
      </thead>
      <tbody>{brand_rows}</tbody>
    </table>

    <!-- Brand-by-Brand Detailed Analysis -->
    <h2 style="color:#232F3E;border-bottom:2px solid #232F3E;padding-bottom:8px;margin-top:30px">브랜드별 상세 분석</h2>
    {brand_section_html}

    <!-- Campaign Adjustment Table -->
    {_ppc_adj_block}

    {_ppc_zero7_block}

    {_ppc_wasted_block}

    {_ppc_anomaly_block}

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
        yd = payload.get("yesterday")
        if yd:
            data_end = date.fromisoformat(yd)
        print(f"  어제(payload): {data_end}")
        print(f"  어제 광고비: ${payload['summary']['yesterday']['spend']:,.2f}")
        print(f"  30일 총 ROAS: {payload['summary']['30d']['roas']:.2f}x")
    else:
        print(f"\n[PPC Agent] PST 기준 오늘: {pst_today}")
        print(f"[PPC Agent] 분석 기준일: {analysis_date} / 어제(PST): {data_end}")

        # Step 1: DataKeeper에서 데이터 로드
        print("\n[Step 1] DataKeeper에서 amazon_ads_daily 로드 중...")
        raw_rows = fetch_from_datakeeper(days=args.days)
        if not raw_rows:
            print("[ERROR] 수집된 데이터 없음")
            sys.exit(1)

        all_rows = compute_metrics(raw_rows)
        print(f"  -> {len(all_rows)}개 일별 행 (compute_metrics 완료)")

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
