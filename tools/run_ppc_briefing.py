"""
run_ppc_briefing.py — Amazon JP PPC 일일 시사점 브리핑 (Teams)

Data Keeper → 어제/7일/30일 비교 → Claude 분석 (시사점 5개+) → Teams webhook 발송

Usage:
    python tools/run_ppc_briefing.py
    python tools/run_ppc_briefing.py --dry-run          # 발송 없이 확인만
    python tools/run_ppc_briefing.py --days 30           # 수집 기간 변경
"""

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

from data_keeper_client import DataKeeper

# --- config ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")

JST = timezone(timedelta(hours=9))
TMP_DIR = TOOLS_DIR.parent / ".tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# Step 1: Data Keeper에서 데이터 수집 + 페이로드 구성
# ===========================================================================

def fetch_and_build_payload(days: int = 30) -> dict:
    """Data Keeper에서 amazon_ads_daily 조회 → 분석용 페이로드 구성."""
    dk = DataKeeper()

    jst_today = datetime.now(JST).date()
    yesterday = jst_today - timedelta(days=1)

    # 30일 데이터 수집
    rows = dk.get("amazon_ads_daily", days=days)
    if not rows:
        raise ValueError("Data Keeper에서 amazon_ads_daily 데이터를 가져올 수 없습니다.")

    print(f"  총 {len(rows)}개 행 수집 (최근 {days}일)")

    # 날짜별 + 브랜드별 + 캠페인별 집계
    # rows 구조: date, brand, campaign_name, campaign_id, impressions, clicks, cost, sales, orders, ...
    def safe_float(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (ValueError, TypeError):
            return default

    def safe_int(v, default=0):
        try:
            return int(v) if v is not None else default
        except (ValueError, TypeError):
            return default

    # 날짜 파싱
    for r in rows:
        d = r.get("date", r.get("report_date", ""))
        if isinstance(d, str):
            r["_date"] = d[:10]
        else:
            r["_date"] = str(d)[:10]

    yesterday_str = yesterday.isoformat()
    d7_start = (yesterday - timedelta(days=6)).isoformat()
    d30_start = (yesterday - timedelta(days=29)).isoformat()

    def aggregate(rows_subset):
        spend = sum(safe_float(r.get("cost", r.get("spend", 0))) for r in rows_subset)
        sales = sum(safe_float(r.get("sales", r.get("sales14d", r.get("attributed_sales", 0)))) for r in rows_subset)
        clicks = sum(safe_int(r.get("clicks", 0)) for r in rows_subset)
        impressions = sum(safe_int(r.get("impressions", 0)) for r in rows_subset)
        orders = sum(safe_int(r.get("orders", r.get("purchases", r.get("purchases14d", 0)))) for r in rows_subset)
        roas = round(sales / spend, 2) if spend > 0 else 0
        acos = round(spend / sales * 100, 1) if sales > 0 else None
        cpc = round(spend / clicks, 2) if clicks > 0 else 0
        ctr = round(clicks / impressions * 100, 2) if impressions > 0 else 0
        return {
            "spend": round(spend, 2), "sales": round(sales, 2),
            "roas": roas, "acos": acos, "cpc": cpc, "ctr": ctr,
            "clicks": clicks, "impressions": impressions, "orders": orders,
        }

    # 기간별 필터
    yd_rows = [r for r in rows if r["_date"] == yesterday_str]
    d7_rows = [r for r in rows if d7_start <= r["_date"] <= yesterday_str]
    d30_rows = [r for r in rows if d30_start <= r["_date"] <= yesterday_str]

    summary = {
        "yesterday": {**aggregate(yd_rows), "date": yesterday_str},
        "7d": {**aggregate(d7_rows), "period": f"{d7_start} ~ {yesterday_str}"},
        "30d": {**aggregate(d30_rows), "period": f"{d30_start} ~ {yesterday_str}"},
    }

    # 브랜드별 집계
    brands = set(r.get("brand", "Unknown") for r in rows)
    brand_breakdown = []
    for brand in sorted(brands):
        b_d7 = [r for r in d7_rows if r.get("brand") == brand]
        b_d30 = [r for r in d30_rows if r.get("brand") == brand]
        agg_7 = aggregate(b_d7)
        agg_30 = aggregate(b_d30)
        trend = round((agg_7["roas"] - agg_30["roas"]) / agg_30["roas"] * 100, 1) if agg_30["roas"] > 0 else 0
        brand_breakdown.append({
            "brand": brand,
            "spend_7d": agg_7["spend"], "sales_7d": agg_7["sales"], "roas_7d": agg_7["roas"],
            "spend_30d": agg_30["spend"], "sales_30d": agg_30["sales"], "roas_30d": agg_30["roas"],
            "roas_trend_pct": trend,
        })

    # 캠페인별 집계 (7일 기준 Top/Bottom)
    campaign_data = defaultdict(list)
    for r in d7_rows:
        cname = r.get("campaign_name", r.get("campaign", "Unknown"))
        campaign_data[cname].append(r)

    campaign_7d = []
    for cname, c_rows in campaign_data.items():
        agg = aggregate(c_rows)
        brand = c_rows[0].get("brand", "Unknown") if c_rows else "Unknown"
        # 어제 데이터
        yd_c = [r for r in yd_rows if r.get("campaign_name", r.get("campaign")) == cname]
        agg_yd = aggregate(yd_c) if yd_c else {"spend": 0, "sales": 0, "roas": 0}
        campaign_7d.append({
            "campaign": cname, "brand": brand,
            "spend_7d": agg["spend"], "sales_7d": agg["sales"], "roas_7d": agg["roas"],
            "acos_7d": agg["acos"], "clicks_7d": agg["clicks"],
            "spend_yd": agg_yd["spend"], "sales_yd": agg_yd["sales"], "roas_yd": agg_yd["roas"],
        })

    campaign_7d.sort(key=lambda x: x["roas_7d"], reverse=True)
    top5 = campaign_7d[:5]
    bottom5 = [c for c in campaign_7d if c["spend_7d"] > 0][-5:]
    zero_sales = [c for c in campaign_7d if c["sales_7d"] == 0 and c["spend_7d"] > 0]

    # 이상 감지
    anomalies = []
    for c in campaign_7d:
        if c["spend_7d"] > 0 and c["sales_7d"] == 0 and c["clicks_7d"] > 5:
            anomalies.append(f"클릭있는데 매출0: {c['campaign']} (클릭 {c['clicks_7d']}회, 지출 ¥{c['spend_7d']:,.0f})")
        if c["roas_7d"] > 0 and c["roas_yd"] > 0:
            drop = (c["roas_7d"] - c["roas_yd"]) / c["roas_7d"] * 100
            if drop >= 30:
                anomalies.append(f"ROAS 급락: {c['campaign']} (7일평균 {c['roas_7d']}x → 어제 {c['roas_yd']}x, -{drop:.0f}%)")

    # 주간 트렌드 (4주)
    weekly_trend = []
    for w in range(4):
        w_end = yesterday - timedelta(days=w * 7)
        w_start = w_end - timedelta(days=6)
        w_rows = [r for r in rows if w_start.isoformat() <= r["_date"] <= w_end.isoformat()]
        if w_rows:
            agg = aggregate(w_rows)
            weekly_trend.append({
                "week": f"W{w+1}",
                "label": f"{w_start.strftime('%m/%d')}~{w_end.strftime('%m/%d')}",
                **agg,
            })

    payload = {
        "analysis_date": jst_today.isoformat(),
        "yesterday": yesterday_str,
        "summary": summary,
        "brand_breakdown": brand_breakdown,
        "campaigns_7d": {
            "top5": top5,
            "bottom5": bottom5,
            "zero_sales": zero_sales,
        },
        "anomalies_detected": anomalies,
        "weekly_trend": weekly_trend,
        "total_campaigns": len(campaign_7d),
    }

    return payload


# ===========================================================================
# Step 2: Claude 분석 → 시사점 추출
# ===========================================================================

SYSTEM_PROMPT = """당신은 10년 경력의 아마존 JP PPC 전문 마케터입니다.

분석 기준:
- ROAS: 3.0↑ 우수 / 2.0~3.0 보통 / 2.0↓ 위험
- ACOS: 15%↓ 효율 / 15~25% 보통 / 25%↑ 비효율
- 통화: JPY(¥), 정수 표기

★★★ 출력 구조 (매우 중요) ★★★
브랜드별로 분류하여 시사점을 정리하세요.
각 브랜드 안에 해당 브랜드의 시사점을 넣으세요.
전체에 해당하는 시사점은 "전체" 브랜드에 넣으세요.

★★★ 출력 스타일 ★★★
- title: 15자 이내 키워드
- detail: 핵심 숫자 1줄
- action: 구체적 액션 1줄
- one_line_summary: 15자 이내
- top_priority_action: 1줄, 30자 이내
절대 장문 금지. 짧고 강하게.

출력 형식 (코드블록 없이 순수 JSON):

{
  "brand_insights": {
    "전체": [
      {"title": "키워드", "detail": "숫자 1줄", "severity": "good|warning|danger", "action": "액션 1줄"}
    ],
    "Grosmimi": [...],
    "CHA&MOM": [...],
    "Naeiae": [...]
  },
  "overall_grade": "A|B|C|D|F",
  "one_line_summary": "15자 이내",
  "top_priority_action": "30자 이내"
}

각 브랜드 시사점 1~3개. 해당 없으면 빈 배열. 전체는 1~2개.
"""


def analyze_with_claude(payload: dict) -> dict:
    """Claude API로 PPC 데이터 분석 → 시사점 JSON 반환."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    user_message = f"""다음은 JST 기준 어제({payload['yesterday']}) Amazon JP PPC 광고 성과 데이터입니다.
전체를 아우르는 시사점을 5개 이상 뽑아주세요. 브랜드별, 캠페인별, 트렌드, 이상 징후 등을 종합적으로 분석해주세요.

=== 분석 데이터 ===
{json.dumps(payload, ensure_ascii=False, indent=2)}

중요:
- summary.yesterday(어제) vs summary.7d vs summary.30d 세 기간 모두 비교하세요
- brand_breakdown의 roas_trend_pct(7일 vs 30일 ROAS 변화율)을 트렌드 판단에 활용하세요
- campaigns_7d.zero_sales는 최근 7일 매출 없는 캠페인 → 즉시 조치 필요
- anomalies_detected는 이상 감지 항목입니다
- weekly_trend(W1=최근, W4=오래됨)로 ROAS 추이를 파악하세요
- JSON만 출력하세요 (코드블록 없이 순수 JSON)"""

    for attempt in range(3):
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        body = resp.json()
        text = body["content"][0]["text"].strip()

        # strip code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip().rstrip("```").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"  [WARN] Claude JSON 파싱 실패, 재시도 {attempt+1}/3")
            continue
    raise ValueError("Claude 응답을 JSON으로 파싱할 수 없습니다.")


# ===========================================================================
# Step 3: HTML 이메일 생성
# ===========================================================================

def build_html_email(payload: dict, analysis: dict) -> str:
    """분석 결과를 HTML 이메일로 변환."""
    yesterday = payload["yesterday"]
    summary = payload["summary"]
    grade = analysis.get("overall_grade", "?")
    one_line = analysis.get("one_line_summary", "")
    top_action = analysis.get("top_priority_action", "")
    insights = analysis.get("insights", [])

    # 등급별 색상
    grade_colors = {
        "A": ("#27ae60", "#e8f8f0"), "B": ("#2ecc71", "#eafaf1"),
        "C": ("#f39c12", "#fef9e7"), "D": ("#e67e22", "#fdf2e9"),
        "F": ("#e74c3c", "#fdedec"),
    }
    gc, gbg = grade_colors.get(grade, ("#95a5a6", "#f2f3f4"))

    severity_icons = {"good": "🟢", "warning": "🟡", "danger": "🔴"}
    severity_colors = {
        "good": "#e8f8f0", "warning": "#fef9e7", "danger": "#fdedec"
    }

    # 시사점 HTML
    insights_html = ""
    for i, ins in enumerate(insights, 1):
        sev = ins.get("severity", "warning")
        icon = severity_icons.get(sev, "⚪")
        bg = severity_colors.get(sev, "#f2f3f4")
        insights_html += f"""
        <div style="background:{bg}; border-left:4px solid {gc}; padding:12px 16px; margin:8px 0; border-radius:4px;">
            <div style="font-weight:bold; font-size:14px; margin-bottom:4px;">
                {icon} {i}. {ins.get('title', '')}
            </div>
            <div style="font-size:13px; color:#333; margin-bottom:6px;">
                {ins.get('detail', '')}
            </div>
            <div style="font-size:12px; color:#666; font-style:italic;">
                → {ins.get('action', '')}
            </div>
        </div>"""

    # 요약 테이블
    yd = summary["yesterday"]
    d7 = summary["7d"]
    d30 = summary["30d"]

    def fmt_money(v):
        return f"¥{int(v):,}" if v else "¥0"

    def fmt_pct(v):
        return f"{v:.1f}%" if v is not None else "—"

    # 브랜드 테이블
    brand_rows = ""
    for b in payload.get("brand_breakdown", []):
        trend_arrow = "▲" if b["roas_trend_pct"] > 0 else "▼" if b["roas_trend_pct"] < 0 else "→"
        trend_color = "#27ae60" if b["roas_trend_pct"] > 0 else "#e74c3c" if b["roas_trend_pct"] < 0 else "#333"
        brand_rows += f"""
        <tr>
            <td style="padding:8px; border:1px solid #ddd; font-weight:bold;">{b['brand']}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(b['spend_7d'])}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(b['sales_7d'])}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{b['roas_7d']}x</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(b['spend_30d'])}</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:right;">{b['roas_30d']}x</td>
            <td style="padding:8px; border:1px solid #ddd; text-align:center; color:{trend_color}; font-weight:bold;">
                {trend_arrow} {b['roas_trend_pct']:+.1f}%
            </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif; max-width:680px; margin:0 auto; background:#f5f5f5; padding:20px;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg, #2c3e50, #3498db); color:white; padding:24px; border-radius:8px 8px 0 0;">
        <h1 style="margin:0; font-size:20px;">📊 Amazon JP PPC 일일 브리핑</h1>
        <p style="margin:8px 0 0; opacity:0.9; font-size:14px;">{yesterday} (JST)</p>
    </div>

    <!-- Grade + One-liner -->
    <div style="background:white; padding:20px; border-bottom:1px solid #eee;">
        <div style="display:flex; align-items:center;">
            <div style="background:{gc}; color:white; font-size:28px; font-weight:bold; width:50px; height:50px;
                        border-radius:50%; display:inline-flex; align-items:center; justify-content:center; margin-right:16px;">
                {grade}
            </div>
            <div>
                <div style="font-size:16px; font-weight:bold; color:#333;">{one_line}</div>
                <div style="font-size:13px; color:#666; margin-top:4px;">🎯 최우선 액션: {top_action}</div>
            </div>
        </div>
    </div>

    <!-- Quick Numbers -->
    <div style="background:white; padding:16px 20px; border-bottom:1px solid #eee;">
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
            <tr style="background:#f8f9fa;">
                <th style="padding:8px; text-align:left; border:1px solid #ddd;"></th>
                <th style="padding:8px; border:1px solid #ddd;">어제</th>
                <th style="padding:8px; border:1px solid #ddd;">7일</th>
                <th style="padding:8px; border:1px solid #ddd;">30일</th>
            </tr>
            <tr>
                <td style="padding:8px; border:1px solid #ddd; font-weight:bold;">광고비</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(yd['spend'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(d7['spend'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(d30['spend'])}</td>
            </tr>
            <tr>
                <td style="padding:8px; border:1px solid #ddd; font-weight:bold;">매출</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(yd['sales'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(d7['sales'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(d30['sales'])}</td>
            </tr>
            <tr>
                <td style="padding:8px; border:1px solid #ddd; font-weight:bold;">ROAS</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{yd['roas']}x</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right; background:#e8f8f0; font-weight:bold;">{d7['roas']}x</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{d30['roas']}x</td>
            </tr>
            <tr>
                <td style="padding:8px; border:1px solid #ddd; font-weight:bold;">ACOS</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_pct(yd['acos'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_pct(d7['acos'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_pct(d30['acos'])}</td>
            </tr>
            <tr>
                <td style="padding:8px; border:1px solid #ddd; font-weight:bold;">CPC</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(yd['cpc'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(d7['cpc'])}</td>
                <td style="padding:8px; border:1px solid #ddd; text-align:right;">{fmt_money(d30['cpc'])}</td>
            </tr>
        </table>
    </div>

    <!-- Brand Breakdown -->
    <div style="background:white; padding:16px 20px; border-bottom:1px solid #eee;">
        <h2 style="font-size:16px; margin:0 0 12px;">🏷️ 브랜드별 성과</h2>
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
            <tr style="background:#2c3e50; color:white;">
                <th style="padding:8px;">브랜드</th>
                <th style="padding:8px;">7일 광고비</th>
                <th style="padding:8px;">7일 매출</th>
                <th style="padding:8px;">7일 ROAS</th>
                <th style="padding:8px;">30일 광고비</th>
                <th style="padding:8px;">30일 ROAS</th>
                <th style="padding:8px;">트렌드</th>
            </tr>
            {brand_rows}
        </table>
    </div>

    <!-- Insights -->
    <div style="background:white; padding:16px 20px; border-bottom:1px solid #eee;">
        <h2 style="font-size:16px; margin:0 0 12px;">💡 시사점</h2>
        {insights_html}
    </div>

    <!-- Anomalies -->
    {"" if not payload.get("anomalies_detected") else f'''
    <div style="background:#fdedec; padding:16px 20px; border-bottom:1px solid #eee;">
        <h2 style="font-size:16px; margin:0 0 8px; color:#e74c3c;">⚠️ 이상 감지</h2>
        <ul style="margin:0; padding-left:20px; font-size:13px;">
            {"".join(f"<li>{a}</li>" for a in payload["anomalies_detected"])}
        </ul>
    </div>
    '''}

    <!-- Footer -->
    <div style="background:#f8f9fa; padding:16px 20px; border-radius:0 0 8px 8px; font-size:11px; color:#999; text-align:center;">
        분석일: {payload['analysis_date']} | 데이터: Data Keeper (amazon_ads_daily) | 분석: Claude Sonnet 4.6<br>
        캠페인 수: {payload.get('total_campaigns', '?')}개 | 이 이메일은 자동 생성됩니다.
    </div>

</body>
</html>"""

    return html


# ===========================================================================
# Step 4: Teams webhook 발송
# ===========================================================================

def build_teams_message(payload: dict, analysis: dict) -> str:
    """분석 결과를 Teams 심플 텍스트로 변환. 모바일에서도 보기 좋게."""
    yesterday = payload["yesterday"]
    summary = payload["summary"]
    grade = analysis.get("overall_grade", "?")
    one_line = analysis.get("one_line_summary", "")
    top_action = analysis.get("top_priority_action", "")
    insights = analysis.get("insights", [])

    yd = summary["yesterday"]
    d7 = summary["7d"]
    d30 = summary["30d"]

    grade_emoji = {"A": "🏆", "B": "👍", "C": "⚠️", "D": "👎", "F": "🚨"}.get(grade, "❓")

    def fmt(v):
        return f"¥{int(v):,}" if v else "¥0"

    def pct(v):
        return f"{v:.1f}%" if v is not None else "—"

    sev_icon = {"good": "✅", "warning": "⚠️", "danger": "🚨"}
    brand_insights = analysis.get("brand_insights", {})

    # 구버전 호환 (insights 배열 → 전체로)
    if not brand_insights and insights:
        brand_insights = {"전체": insights}

    L = []

    # ── 헤더 ──
    L.append(f"{grade_emoji} [{grade}] {one_line}")
    L.append(f"📅 {yesterday}")
    L.append("")

    # ── 전체 지표 ──
    L.append(f"📊 전체 성과")
    L.append(f"  어제  {fmt(yd['spend'])} → {fmt(yd['sales'])}  ROAS {yd['roas']}x  ACOS {pct(yd['acos'])}")
    L.append(f"  7일   {fmt(d7['spend'])} → {fmt(d7['sales'])}  ROAS {d7['roas']}x  ACOS {pct(d7['acos'])}")
    L.append(f"  30일  {fmt(d30['spend'])} → {fmt(d30['sales'])}  ROAS {d30['roas']}x  ACOS {pct(d30['acos'])}")
    L.append("")

    # ── 전체 시사점 ──
    overall_ins = brand_insights.get("전체", [])
    if overall_ins:
        for ins in overall_ins:
            icon = sev_icon.get(ins.get("severity", "warning"), "⚪")
            L.append(f"  {icon} {ins.get('title', '')}")
            if ins.get("detail"):
                L.append(f"     {ins['detail']}")
            L.append(f"     👉 {ins.get('action', '')}")
        L.append("")

    # ── 브랜드별 블록 ──
    brand_data = {b["brand"]: b for b in payload.get("brand_breakdown", [])}
    brand_order = ["Grosmimi", "CHA&MOM", "Naeiae"]

    for brand_name in brand_order:
        b = brand_data.get(brand_name)
        b_ins = brand_insights.get(brand_name, [])
        if not b and not b_ins:
            continue

        # 트렌드 아이콘
        if b:
            if b["roas_trend_pct"] > 5:
                arrow = "📈"
            elif b["roas_trend_pct"] < -5:
                arrow = "📉"
            else:
                arrow = "➡️"
            L.append(f"{'— ' * 10}")
            L.append(f"{arrow} {brand_name}")
            L.append(f"  ROAS  7d {b['roas_7d']}x / 30d {b['roas_30d']}x ({b['roas_trend_pct']:+.0f}%)")
            L.append(f"  광고비 7d {fmt(b['spend_7d'])} / 매출 7d {fmt(b['sales_7d'])}")
        else:
            L.append(f"{'— ' * 10}")
            L.append(f"🏷️ {brand_name}")

        # 해당 브랜드 시사점
        for ins in b_ins:
            icon = sev_icon.get(ins.get("severity", "warning"), "⚪")
            L.append(f"  {icon} {ins.get('title', '')}")
            if ins.get("detail"):
                L.append(f"     {ins['detail']}")
            L.append(f"     👉 {ins.get('action', '')}")
        L.append("")

    # ── 이상 감지 ──
    anomalies = payload.get("anomalies_detected", [])
    if anomalies:
        L.append("🚨 이상 감지")
        for a in anomalies:
            L.append(f"  • {a}")
        L.append("")

    # ── 최우선 액션 ──
    L.append(f"🎯 {top_action}")

    return "\n".join(L)


def send_to_teams(text: str) -> bool:
    """Teams webhook으로 심플 텍스트 발송. {"text": "..."} 포맷만 사용."""
    if not TEAMS_WEBHOOK_URL:
        raise ValueError("TEAMS_WEBHOOK_URL_SEEUN not set in .env")

    resp = requests.post(
        TEAMS_WEBHOOK_URL,
        json={"text": text},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return True


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Amazon JP PPC 일일 시사점 브리핑")
    parser.add_argument("--days", type=int, default=30, help="수집 기간 (기본 30일)")
    parser.add_argument("--dry-run", action="store_true", help="Teams 발송 없이 확인만")
    args = parser.parse_args()

    jst_today = datetime.now(JST).date()
    yesterday = jst_today - timedelta(days=1)

    print(f"\n[PPC Briefing] JST 기준 오늘: {jst_today}")
    print(f"[PPC Briefing] 분석 대상: 어제 ({yesterday})")

    # Step 1: 데이터 수집
    print("\n[Step 1] Data Keeper에서 데이터 수집 중...")
    payload = fetch_and_build_payload(args.days)
    print(f"  어제 광고비: ¥{int(payload['summary']['yesterday']['spend']):,}")
    print(f"  7일 ROAS: {payload['summary']['7d']['roas']}x")
    print(f"  30일 ROAS: {payload['summary']['30d']['roas']}x")
    print(f"  이상 감지: {len(payload.get('anomalies_detected', []))}건")

    # 페이로드 저장
    payload_path = TMP_DIR / f"ppc_briefing_payload_{yesterday}.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  페이로드 저장: {payload_path}")

    # Step 2: Claude 분석
    print("\n[Step 2] Claude 분석 중...")
    analysis = analyze_with_claude(payload)
    brand_insights = analysis.get("brand_insights", {})
    total_insights = sum(len(v) for v in brand_insights.values()) if brand_insights else len(analysis.get("insights", []))
    print(f"  시사점 {total_insights}개 추출 ({len(brand_insights)}개 브랜드)")
    print(f"  등급: {analysis.get('overall_grade', '?')}")
    print(f"  요약: {analysis.get('one_line_summary', '')}")

    # 분석 결과 저장
    analysis_path = TMP_DIR / f"ppc_briefing_analysis_{yesterday}.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 3: HTML 백업 저장
    print("\n[Step 3] HTML 백업 저장 중...")
    html = build_html_email(payload, analysis)
    html_path = TMP_DIR / f"ppc_briefing_{yesterday}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"  저장됨: {html_path}")

    # Step 4: Teams 발송
    teams_text = build_teams_message(payload, analysis)
    if args.dry_run:
        print(f"\n[Dry Run] Teams 발송 건너뜀.")
        print(f"--- Teams 메시지 미리보기 ---\n{teams_text}\n---")
    else:
        print(f"\n[Step 4] Teams webhook 발송 중...")
        try:
            send_to_teams(teams_text)
            print("  Teams 발송 완료!")
        except Exception as e:
            print(f"  [ERROR] Teams 발송 실패: {e}")
            print(f"  HTML 파일은 저장됨: {html_path}")
            return 1

    print(f"\n[완료] PPC 브리핑 생성 완료 ({yesterday})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
