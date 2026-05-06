"""
Meta JP (Grosmimi) 광고 자동 분석 + Gmail 리포트.

Modes:
  1d  : 어제 1일 스냅샷 (캠페인별 + 광고 TOP5 + 알림)
  7d  : 최근 7일 트렌드 (일별 차트 + WoW + 광고 ranking)
  14d : 14일 진단 (학습단계 + 크리에이티브 분류 + Freq 매트릭스)

Usage:
  python tools/meta_jp_daily.py --mode 1d
  python tools/meta_jp_daily.py --mode 7d --no-send
  python tools/meta_jp_daily.py --mode 14d --to se.heo@orbiters.co.kr
"""

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from env_loader import load_env  # noqa: E402

load_env()

TOKEN = os.getenv("META_JP_ACCESS_TOKEN")
ACCT = os.getenv("META_JP_AD_ACCOUNT_ID")
BASE = "https://graph.facebook.com/v18.0"

DEFAULT_TO = "se.heo@orbiters.co.kr"
TMP_DIR = ROOT / ".tmp" / "meta_jp_daily"
TMP_DIR.mkdir(parents=True, exist_ok=True)

CTR_BENCH = 1.71  # JP 6-24m mom benchmark
CTR_LOW = 1.0
FREQ_HIGH = 3.0
CPC_SPIKE_PCT = 30.0


def api_get(path, params=None):
    params = dict(params or {})
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


def fetch(level, time_range=None, date_preset=None, with_daily=False):
    fields = [
        "campaign_id", "campaign_name", "adset_id", "adset_name",
        "ad_id", "ad_name", "spend", "impressions", "clicks",
        "ctr", "cpc", "cpm", "frequency", "reach",
    ]
    params = {
        "fields": ",".join(fields),
        "level": level,
        "limit": 500,
    }
    if with_daily:
        params["time_increment"] = 1
    if time_range:
        params["time_range"] = json.dumps(time_range)
    elif date_preset:
        params["date_preset"] = date_preset
    return api_get(f"{ACCT}/insights", params)


def to_float(v, default=0.0):
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def fmt_won(v):
    return f"₩{int(round(to_float(v))):,}"


def fmt_pct(v):
    return f"{to_float(v):.2f}%"


def fmt_num(v, decimals=0):
    f = to_float(v)
    if decimals == 0:
        return f"{int(round(f)):,}"
    return f"{f:,.{decimals}f}"


def best_worst_from_rows(ad_rows, min_impr=200):
    """광고 단위 BEST/WORST TOP3 by CTR/CPC."""
    ads = []
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < min_impr:
            continue
        ads.append({
            "ad_name": row.get("ad_name", ""),
            "campaign_name": row.get("campaign_name", ""),
            "spend": to_float(row.get("spend")),
            "impressions": impr,
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
        })
    ctr_pool = [a for a in ads if a["ctr"] > 0]
    cpc_pool = [a for a in ads if a["cpc"] > 0]
    return {
        "ctr_best": sorted(ctr_pool, key=lambda x: x["ctr"], reverse=True)[:3],
        "ctr_worst": sorted(ctr_pool, key=lambda x: x["ctr"])[:3],
        "cpc_best": sorted(cpc_pool, key=lambda x: x["cpc"])[:3],
        "cpc_worst": sorted(cpc_pool, key=lambda x: x["cpc"], reverse=True)[:3],
    }


def build_advice_1d(d):
    """1d 운용 조언 (룰 기반)."""
    tips = []
    t = d["total"]
    ctr = t["ctr"]
    if ctr >= CTR_BENCH * 1.5:
        tips.append(f"전체 CTR {ctr:.2f}%로 벤치({CTR_BENCH}%) 대비 우수. <b>현재 운용 유지 + 예산 점진 증액(20% 이내)</b> 검토.")
    elif ctr < CTR_LOW:
        tips.append(f"전체 CTR {ctr:.2f}%로 임계값 미달. <b>WORST 광고 즉시 일시정지 + BEST 광고 변형 추가</b>.")
    if d["delta"]["cpc_pct"] > 30:
        tips.append(f"CPC 전일 +{d['delta']['cpc_pct']:.1f}% 급등. 학습 재진입 가능성 — <b>예산·타겟 변경 24h 동결</b>.")
    if d["delta"]["spend_pct"] > 50:
        tips.append(f"Spend 전일 +{d['delta']['spend_pct']:.1f}% 급증. 캠페인 cap 도달 또는 입찰 변동 — <b>일별 cap 재설정 검토</b>.")
    bw = d.get("best_worst", {})
    if bw.get("ctr_best") and bw.get("ctr_worst"):
        b = bw["ctr_best"][0]["ctr"]
        w = bw["ctr_worst"][0]["ctr"]
        if b > 0 and w > 0 and b > w * 3:
            tips.append(f"BEST/WORST CTR 격차 3배 이상 ({b:.2f}% vs {w:.2f}%). <b>WORST 3개 즉시 정지 + BEST 소재의 카피·앵글 변형 신규 3개 투입</b>.")
    if not tips:
        tips.append("전반 정상 범위. 7일 추세 누적 후 재평가 권장.")
    return tips


def build_advice_7d(d):
    tips = []
    w = d["wow"]
    if w["spend_pct"] > 30 and w["ctr_pct"] < -10:
        tips.append(f"<b>주의:</b> Spend +{w['spend_pct']:.0f}% 늘었는데 CTR {w['ctr_pct']:.0f}% 하락. 예산 증액 효과 X — <b>예산 원복 + 소재 교체</b>.")
    elif w["spend_pct"] > 30 and w["ctr_pct"] >= 0:
        tips.append(f"증액({w['spend_pct']:.0f}%) 후 CTR 유지. <b>해당 캠페인 안정 신호 — 추가 +20% 증액 검토 가능</b>.")
    if w["cpc_pct"] > 20:
        tips.append(f"WoW CPC +{w['cpc_pct']:.0f}% 상승. 경매 경쟁 또는 소재 피로 — <b>오디언스 만료 후 신규 LAL/Interest 추가</b>.")

    spends = [x["spend"] for x in d["daily_trend"]]
    if spends and sum(spends) > 0:
        avg = sum(spends) / len(spends)
        std_pct = ((max(spends) - min(spends)) / avg * 100) if avg else 0
        if std_pct > 80:
            tips.append(f"일별 spend 변동폭 ±{std_pct:.0f}%. 안정적 학습 어려움 — <b>CBO 권장 + 일별 cap 균등화</b>.")

    bw = d.get("best_worst", {})
    if bw.get("ctr_worst"):
        worst = bw["ctr_worst"]
        spend_loss = sum(a["spend"] for a in worst)
        if spend_loss > 0 and worst:
            ctr_lo = min(a["ctr"] for a in worst)
            ctr_hi = max(a["ctr"] for a in worst)
            tips.append(f"WORST 3 (CTR {ctr_lo:.2f}~{ctr_hi:.2f}%) 7일간 {fmt_won(spend_loss)} 소진. <b>해당 광고 즉시 정지 + BEST 컨셉 변형 3종 신규 투입</b>.")

    camps = d.get("campaigns", [])
    if len(camps) >= 2:
        camps_sorted = sorted(camps, key=lambda x: x["ctr"], reverse=True)
        top, bot = camps_sorted[0], camps_sorted[-1]
        if top["ctr"] > 0 and bot["ctr"] > 0 and top["ctr"] > bot["ctr"] * 2:
            tips.append(f"캠페인 격차 큼: <b>{top['name']}</b> CTR {top['ctr']:.2f}% vs <b>{bot['name']}</b> {bot['ctr']:.2f}%. <b>저성과 캠페인 예산 30% 삭감 → 고성과 이전</b>.")

    if not tips:
        tips.append("주간 트렌드 안정. 다음 14일 진단까지 현재 운용 유지.")
    return tips


def build_advice_14d(d):
    tips = []
    learning = d.get("learning", [])
    stable = [x for x in learning if x["stability"] == "안정"]
    learning_only = [x for x in learning if x["stability"] == "학습중"]
    if learning_only and not stable:
        tips.append(f"전 캠페인 학습 단계. <b>예산·소재·타겟 변경 7일간 동결</b> 권장 (학습 종료 조건: 주 50건 전환 또는 CPC 변동 ±30% 이내).")
    elif stable and learning_only:
        tips.append(f"안정 {len(stable)}개 / 학습중 {len(learning_only)}개. <b>학습중 캠페인 건드리지 말고 안정 캠페인부터 점진 증액</b>.")

    cc = d.get("creative_class", {})
    img = cc.get("image")
    vid = cc.get("video")
    wl = cc.get("wl")
    if img and vid:
        if vid["ctr"] > img["ctr"] * 1.3:
            tips.append(f"영상 우세 (CTR {vid['ctr']:.2f}% vs 이미지 {img['ctr']:.2f}%). <b>영상 슬롯 비중 60%+ 확대 + 이미지는 hook 컷 위주로 재구성</b>.")
        elif img["ctr"] > vid["ctr"] * 1.3:
            tips.append(f"이미지 우세 (CTR {img['ctr']:.2f}% vs 영상 {vid['ctr']:.2f}%). <b>이미지 변형 5종 추가 + 영상은 컷 길이·썸네일 재테스트</b>.")
    if wl and (img or vid):
        ref_ctr = max((cc[k]["ctr"] for k in ("image", "video") if cc.get(k)), default=0)
        if ref_ctr > 0 and wl["ctr"] > ref_ctr * 1.2:
            tips.append(f"WL(인플루언서) CTR {wl['ctr']:.2f}%로 자체 소재 대비 우수. <b>WL 광고 비중 확대 + Use existing post 추가 협업 발굴</b>.")

    fatigue = d.get("fatigue", [])
    if len(fatigue) >= 3:
        spend = sum(f["spend"] for f in fatigue)
        tips.append(f"피로도 경고 {len(fatigue)}개 (14일 spend {fmt_won(spend)}). <b>즉시 정지 + 신규 소재 동수 투입</b>. 미정지 시 잔존 예산도 비효율 누적.")

    bw = d.get("best_worst", {})
    if bw.get("ctr_best") and bw.get("ctr_worst"):
        b = bw["ctr_best"][0]
        w = bw["ctr_worst"][0]
        if b["ctr"] > 0 and w["ctr"] > 0 and b["ctr"] > w["ctr"] * 4:
            tips.append(f"광고 격차 4배+: <b>BEST 「{b['ad_name'][:30]}」 컨셉 변형 5종 추가 + WORST 3개 영구 폐기</b>.")

    if not tips:
        tips.append("14일 진단상 즉시 액션 항목 없음. 신규 소재 정기 투입(주 3개)으로 피로 누적 예방.")
    return tips


def render_advice_section(tips, header="메타몽 운용 조언"):
    items = "".join(f"<li>{t}</li>" for t in tips)
    return f"""
<h2>{header}</h2>
<div style="background:#eff6ff;border-left:4px solid #2563eb;padding:12px 18px;border-radius:4px;">
  <ul style="margin:6px 0;">{items}</ul>
  <p class=meta style="margin:8px 0 0;">룰 기반 자동 생성. 최종 의사결정은 세은 직접.</p>
</div>
"""


def render_best_worst_table(bw):
    def rows(items):
        if not items:
            return f"<tr><td colspan=6 class=meta>데이터 부족</td></tr>"
        return "".join(
            f"<tr><td class=l>{a['ad_name'][:55]}</td><td>{fmt_pct(a['ctr'])}</td>"
            f"<td>{fmt_won(a['cpc'])}</td><td>{a.get('freq', 0):.2f}</td>"
            f"<td>{fmt_won(a['spend'])}</td><td>{fmt_num(a['impressions'])}</td></tr>"
            for a in items
        )
    head = "<tr><th>광고</th><th>CTR</th><th>CPC</th><th>Freq</th><th>Spend</th><th>Impr</th></tr>"
    return f"""
<h2>광고 BEST / WORST</h2>
<table>
  <tr><th colspan=6 style="background:#dcfce7;color:#065f46">▲ CTR BEST 3 (높은 순)</th></tr>
  {head}
  {rows(bw['ctr_best'])}
  <tr><th colspan=6 style="background:#fee2e2;color:#991b1b">▼ CTR WORST 3 (낮은 순)</th></tr>
  {head}
  {rows(bw['ctr_worst'])}
  <tr><th colspan=6 style="background:#dcfce7;color:#065f46">▲ CPC BEST 3 (낮은 순 = 효율)</th></tr>
  {head}
  {rows(bw['cpc_best'])}
  <tr><th colspan=6 style="background:#fee2e2;color:#991b1b">▼ CPC WORST 3 (높은 순)</th></tr>
  {head}
  {rows(bw['cpc_worst'])}
</table>
<p class=meta>최소 노출수 필터: 1d≥100 / 7d≥200 / 14d≥500</p>
"""


# ============================================================
# 1d Analysis
# ============================================================
def analyze_1d(target_date):
    yday = target_date
    dby = target_date - timedelta(days=1)
    cur = fetch("ad", time_range={"since": yday.isoformat(), "until": yday.isoformat()})
    prev = fetch("ad", time_range={"since": dby.isoformat(), "until": dby.isoformat()})

    by_camp = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "reach": 0, "freq_sum": 0, "n": 0})
    for row in cur:
        c = by_camp[row.get("campaign_name", "(unknown)")]
        c["spend"] += to_float(row.get("spend"))
        c["impressions"] += to_float(row.get("impressions"))
        c["clicks"] += to_float(row.get("clicks"))
        c["reach"] += to_float(row.get("reach"))
        c["freq_sum"] += to_float(row.get("frequency"))
        c["n"] += 1

    camp_rows = []
    for name, v in by_camp.items():
        ctr = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
        freq = (v["freq_sum"] / v["n"]) if v["n"] else 0
        camp_rows.append({
            "name": name, "spend": v["spend"], "impressions": v["impressions"],
            "clicks": v["clicks"], "ctr": ctr, "cpc": cpc, "freq": freq, "reach": v["reach"],
        })
    camp_rows.sort(key=lambda x: x["spend"], reverse=True)

    ad_rows = []
    for row in cur:
        impr = to_float(row.get("impressions"))
        clicks = to_float(row.get("clicks"))
        if impr < 100:
            continue
        ad_rows.append({
            "ad_name": row.get("ad_name", ""),
            "campaign_name": row.get("campaign_name", ""),
            "spend": to_float(row.get("spend")),
            "impressions": impr,
            "clicks": clicks,
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
        })
    top5 = sorted(ad_rows, key=lambda x: x["ctr"], reverse=True)[:5]

    prev_by_camp = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0})
    for row in prev:
        p = prev_by_camp[row.get("campaign_name", "(unknown)")]
        p["spend"] += to_float(row.get("spend"))
        p["impressions"] += to_float(row.get("impressions"))
        p["clicks"] += to_float(row.get("clicks"))
    cur_total = {
        "spend": sum(c["spend"] for c in camp_rows),
        "impressions": sum(c["impressions"] for c in camp_rows),
        "clicks": sum(c["clicks"] for c in camp_rows),
    }
    prev_total = {
        "spend": sum(p["spend"] for p in prev_by_camp.values()),
        "impressions": sum(p["impressions"] for p in prev_by_camp.values()),
        "clicks": sum(p["clicks"] for p in prev_by_camp.values()),
    }
    cur_ctr = (cur_total["clicks"] / cur_total["impressions"] * 100) if cur_total["impressions"] else 0
    cur_cpc = (cur_total["spend"] / cur_total["clicks"]) if cur_total["clicks"] else 0
    prev_ctr = (prev_total["clicks"] / prev_total["impressions"] * 100) if prev_total["impressions"] else 0
    prev_cpc = (prev_total["spend"] / prev_total["clicks"]) if prev_total["clicks"] else 0

    delta = {
        "spend_pct": ((cur_total["spend"] - prev_total["spend"]) / prev_total["spend"] * 100) if prev_total["spend"] else 0,
        "ctr_pct": ((cur_ctr - prev_ctr) / prev_ctr * 100) if prev_ctr else 0,
        "cpc_pct": ((cur_cpc - prev_cpc) / prev_cpc * 100) if prev_cpc else 0,
    }

    alerts = []
    for c in camp_rows:
        if c["impressions"] >= 1000 and 0 < c["ctr"] < CTR_LOW:
            alerts.append(f"CTR 낮음: {c['name']} ({fmt_pct(c['ctr'])})")
        if c["freq"] > FREQ_HIGH:
            alerts.append(f"Freq 피로: {c['name']} ({c['freq']:.2f})")
    if delta["cpc_pct"] > CPC_SPIKE_PCT and prev_cpc > 0:
        alerts.append(f"CPC 급등: 전일 대비 +{delta['cpc_pct']:.1f}%")

    return {
        "date": yday, "prev_date": dby,
        "total": {**cur_total, "ctr": cur_ctr, "cpc": cur_cpc},
        "campaigns": camp_rows, "top5": top5, "alerts": alerts, "delta": delta,
        "best_worst": best_worst_from_rows(cur, min_impr=100),
    }


# ============================================================
# 7d Analysis
# ============================================================
def analyze_7d(end_date):
    start = end_date - timedelta(days=6)
    prev_start = end_date - timedelta(days=13)
    prev_end = end_date - timedelta(days=7)

    cur_daily = fetch("campaign",
                      time_range={"since": start.isoformat(), "until": end_date.isoformat()},
                      with_daily=True)
    prev_daily = fetch("campaign",
                       time_range={"since": prev_start.isoformat(), "until": prev_end.isoformat()},
                       with_daily=True)
    ad_rows = fetch("ad", time_range={"since": start.isoformat(), "until": end_date.isoformat()})

    daily_agg = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0})
    for row in cur_daily:
        d = row.get("date_start", "")
        daily_agg[d]["spend"] += to_float(row.get("spend"))
        daily_agg[d]["impressions"] += to_float(row.get("impressions"))
        daily_agg[d]["clicks"] += to_float(row.get("clicks"))
    daily_trend = []
    cur_d = start
    while cur_d <= end_date:
        ds = cur_d.isoformat()
        v = daily_agg.get(ds, {"spend": 0, "impressions": 0, "clicks": 0})
        ctr = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
        daily_trend.append({"date": ds, "spend": v["spend"], "ctr": ctr, "cpc": cpc, "impressions": v["impressions"]})
        cur_d += timedelta(days=1)

    by_camp = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "freq_sum": 0, "n": 0})
    for row in cur_daily:
        c = by_camp[row.get("campaign_name", "(unknown)")]
        c["spend"] += to_float(row.get("spend"))
        c["impressions"] += to_float(row.get("impressions"))
        c["clicks"] += to_float(row.get("clicks"))
        c["freq_sum"] += to_float(row.get("frequency"))
        c["n"] += 1
    camp_rows = []
    for name, v in by_camp.items():
        ctr = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
        freq = (v["freq_sum"] / v["n"]) if v["n"] else 0
        camp_rows.append({"name": name, "spend": v["spend"], "impressions": v["impressions"],
                          "clicks": v["clicks"], "ctr": ctr, "cpc": cpc, "freq": freq})
    camp_rows.sort(key=lambda x: x["spend"], reverse=True)

    ads = []
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < 200:
            continue
        ads.append({
            "ad_name": row.get("ad_name", ""),
            "spend": to_float(row.get("spend")),
            "impressions": impr,
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
        })
    top10 = sorted(ads, key=lambda x: x["spend"], reverse=True)[:10]

    cur_sum = {"spend": 0, "impressions": 0, "clicks": 0}
    prev_sum = {"spend": 0, "impressions": 0, "clicks": 0}
    for row in cur_daily:
        for k in cur_sum:
            cur_sum[k] += to_float(row.get(k))
    for row in prev_daily:
        for k in prev_sum:
            prev_sum[k] += to_float(row.get(k))
    cur_ctr = (cur_sum["clicks"] / cur_sum["impressions"] * 100) if cur_sum["impressions"] else 0
    cur_cpc = (cur_sum["spend"] / cur_sum["clicks"]) if cur_sum["clicks"] else 0
    prev_ctr = (prev_sum["clicks"] / prev_sum["impressions"] * 100) if prev_sum["impressions"] else 0
    prev_cpc = (prev_sum["spend"] / prev_sum["clicks"]) if prev_sum["clicks"] else 0
    wow = {
        "spend": cur_sum["spend"], "spend_prev": prev_sum["spend"],
        "spend_pct": ((cur_sum["spend"] - prev_sum["spend"]) / prev_sum["spend"] * 100) if prev_sum["spend"] else 0,
        "ctr": cur_ctr, "ctr_prev": prev_ctr,
        "ctr_pct": ((cur_ctr - prev_ctr) / prev_ctr * 100) if prev_ctr else 0,
        "cpc": cur_cpc, "cpc_prev": prev_cpc,
        "cpc_pct": ((cur_cpc - prev_cpc) / prev_cpc * 100) if prev_cpc else 0,
    }

    return {
        "start": start, "end": end_date,
        "total": {**cur_sum, "ctr": cur_ctr, "cpc": cur_cpc},
        "daily_trend": daily_trend, "campaigns": camp_rows, "top10": top10, "wow": wow,
        "best_worst": best_worst_from_rows(ad_rows, min_impr=200),
    }


# ============================================================
# 14d Analysis
# ============================================================
def analyze_14d(end_date):
    start = end_date - timedelta(days=13)
    cur_daily = fetch("campaign",
                      time_range={"since": start.isoformat(), "until": end_date.isoformat()},
                      with_daily=True)
    ad_rows = fetch("ad", time_range={"since": start.isoformat(), "until": end_date.isoformat()})

    by_camp_day = defaultdict(lambda: defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0}))
    for row in cur_daily:
        c = row.get("campaign_name", "(unknown)")
        d = row.get("date_start", "")
        by_camp_day[c][d]["spend"] += to_float(row.get("spend"))
        by_camp_day[c][d]["impressions"] += to_float(row.get("impressions"))
        by_camp_day[c][d]["clicks"] += to_float(row.get("clicks"))
    learning = []
    for camp, days in by_camp_day.items():
        ds = sorted(days.keys())
        if len(ds) < 5:
            continue
        recent5 = ds[-5:]
        cpc_recent = []
        for d in recent5:
            v = days[d]
            cpc = (v["spend"] / v["clicks"]) if v["clicks"] else 0
            cpc_recent.append(cpc)
        cpc_avg = sum(cpc_recent) / len(cpc_recent) if cpc_recent else 0
        cpc_var = max(cpc_recent) - min(cpc_recent) if cpc_recent else 0
        stability = "안정" if cpc_avg > 0 and cpc_var / cpc_avg < 0.3 else "학습중"
        learning.append({"campaign": camp, "cpc_avg": cpc_avg, "stability": stability,
                         "days_active": len(ds)})
    learning.sort(key=lambda x: x["days_active"], reverse=True)

    creative_groups = {"image": [], "video": [], "wl": []}
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < 100:
            continue
        ad_name = row.get("ad_name", "").lower()
        if "wl" in ad_name or "partner" in ad_name or "@" in row.get("ad_name", ""):
            grp = "wl"
        elif "video" in ad_name or "reel" in ad_name or "动画" in ad_name or "動画" in ad_name:
            grp = "video"
        else:
            grp = "image"
        creative_groups[grp].append({
            "spend": to_float(row.get("spend")),
            "impressions": impr,
            "clicks": to_float(row.get("clicks")),
            "ctr": to_float(row.get("ctr")),
            "cpc": to_float(row.get("cpc")),
            "freq": to_float(row.get("frequency")),
        })
    creative_class = {}
    for grp, rows in creative_groups.items():
        if not rows:
            creative_class[grp] = None
            continue
        spend = sum(r["spend"] for r in rows)
        impr = sum(r["impressions"] for r in rows)
        clicks = sum(r["clicks"] for r in rows)
        freq_avg = sum(r["freq"] for r in rows) / len(rows)
        creative_class[grp] = {
            "n": len(rows), "spend": spend, "impressions": impr,
            "ctr": (clicks / impr * 100) if impr else 0,
            "cpc": (spend / clicks) if clicks else 0,
            "freq": freq_avg,
        }

    fatigue = []
    for row in ad_rows:
        impr = to_float(row.get("impressions"))
        if impr < 500:
            continue
        freq = to_float(row.get("frequency"))
        ctr = to_float(row.get("ctr"))
        if freq > FREQ_HIGH or (freq > 2.0 and ctr < CTR_LOW):
            fatigue.append({
                "ad_name": row.get("ad_name", ""),
                "campaign_name": row.get("campaign_name", ""),
                "freq": freq, "ctr": ctr, "spend": to_float(row.get("spend")),
            })
    fatigue.sort(key=lambda x: x["freq"], reverse=True)

    actions = []
    if fatigue:
        actions.append(f"폐기 검토: Freq>3.0 광고 {len(fatigue)}개 (총 spend {fmt_won(sum(f['spend'] for f in fatigue))})")
    if creative_class.get("image") and creative_class.get("video"):
        ic = creative_class["image"]["ctr"]
        vc = creative_class["video"]["ctr"]
        if vc > ic * 1.3:
            actions.append(f"영상 우세: video CTR {vc:.2f}% vs image {ic:.2f}% — 영상 비중 증액 검토")
        elif ic > vc * 1.3:
            actions.append(f"이미지 우세: image CTR {ic:.2f}% vs video {vc:.2f}% — 이미지 슬롯 확대")

    return {
        "start": start, "end": end_date,
        "learning": learning, "creative_class": creative_class,
        "fatigue": fatigue[:10], "actions": actions,
        "best_worst": best_worst_from_rows(ad_rows, min_impr=500),
    }


# ============================================================
# Charts (matplotlib, base64-inline PNG)
# ============================================================
def chart_daily_trend(daily_trend):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    dates = [d["date"][5:] for d in daily_trend]
    spend = [d["spend"] for d in daily_trend]
    ctr = [d["ctr"] for d in daily_trend]
    cpc = [d["cpc"] for d in daily_trend]
    fig, ax1 = plt.subplots(figsize=(10, 4))
    color1 = "#2563eb"
    ax1.bar(dates, spend, color=color1, alpha=0.4, label="Spend (₩)")
    ax1.set_ylabel("Spend (₩)", color=color1)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax2 = ax1.twinx()
    ax2.plot(dates, ctr, color="#dc2626", marker="o", label="CTR (%)")
    ax2.plot(dates, cpc, color="#059669", marker="s", label="CPC (₩)", linestyle="--")
    ax2.set_ylabel("CTR (%) / CPC (₩)")
    fig.legend(loc="upper right", bbox_to_anchor=(0.95, 0.95))
    plt.title("Daily Trend (Spend / CTR / CPC)")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


# ============================================================
# HTML Render
# ============================================================
CSS = """
<style>
  body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1f2937; max-width: 900px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 22px; border-bottom: 2px solid #2563eb; padding-bottom: 8px; }
  h2 { font-size: 17px; margin-top: 24px; color: #1f2937; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 13px; }
  th, td { border: 1px solid #e5e7eb; padding: 6px 10px; text-align: right; }
  th { background: #f3f4f6; text-align: center; }
  td.l { text-align: left; }
  .alert { background: #fef2f2; border-left: 4px solid #dc2626; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }
  .ok { background: #f0fdf4; border-left: 4px solid #059669; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }
  .delta-up { color: #dc2626; font-weight: 600; }
  .delta-down { color: #059669; font-weight: 600; }
  .meta { color: #6b7280; font-size: 12px; }
</style>
"""


def delta_span(pct, lower_is_better=False):
    if pct == 0:
        return "<span>±0.0%</span>"
    arrow = "▲" if pct > 0 else "▼"
    is_bad = (pct > 0) if lower_is_better else (pct < 0)
    cls = "delta-up" if is_bad else "delta-down"
    return f'<span class="{cls}">{arrow} {abs(pct):.1f}%</span>'


def render_1d(d):
    t = d["total"]
    rows = "".join(
        f"<tr><td class=l>{c['name']}</td><td>{fmt_won(c['spend'])}</td>"
        f"<td>{fmt_num(c['impressions'])}</td><td>{fmt_pct(c['ctr'])}</td>"
        f"<td>{fmt_won(c['cpc'])}</td><td>{c['freq']:.2f}</td>"
        f"<td>{fmt_num(c['reach'])}</td></tr>"
        for c in d["campaigns"]
    )
    top5 = "".join(
        f"<tr><td class=l>{a['ad_name'][:50]}</td><td>{fmt_pct(a['ctr'])}</td>"
        f"<td>{fmt_won(a['cpc'])}</td><td>{fmt_won(a['spend'])}</td>"
        f"<td>{fmt_num(a['impressions'])}</td></tr>"
        for a in d["top5"]
    )
    alerts_html = (
        '<div class="alert"><b>⚠ 알림</b><ul>' +
        "".join(f"<li>{a}</li>" for a in d["alerts"]) + "</ul></div>"
    ) if d["alerts"] else '<div class="ok">알림 없음 (모든 지표 정상 범위)</div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{CSS}</head><body>
<h1>Meta JP Daily — {d['date']}</h1>
<p class=meta>비교: 전일 ({d['prev_date']}) · 계정: act_{ACCT.replace('act_', '')}</p>

<h2>전체 요약</h2>
<table>
  <tr><th>Spend</th><th>Impressions</th><th>Clicks</th><th>CTR</th><th>CPC</th></tr>
  <tr><td>{fmt_won(t['spend'])} {delta_span(d['delta']['spend_pct'])}</td>
      <td>{fmt_num(t['impressions'])}</td>
      <td>{fmt_num(t['clicks'])}</td>
      <td>{fmt_pct(t['ctr'])} {delta_span(d['delta']['ctr_pct'])}</td>
      <td>{fmt_won(t['cpc'])} {delta_span(d['delta']['cpc_pct'], lower_is_better=True)}</td></tr>
</table>

{alerts_html}

<h2>캠페인별</h2>
<table>
  <tr><th>캠페인</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th><th>Reach</th></tr>
  {rows}
</table>

<h2>광고 TOP 5 (CTR 순)</h2>
<table>
  <tr><th>광고</th><th>CTR</th><th>CPC</th><th>Spend</th><th>Impr</th></tr>
  {top5}
</table>

<p class=meta>벤치 CTR 1.71% · 임계값: CTR&lt;{CTR_LOW}% / Freq&gt;{FREQ_HIGH} / CPC 전일 +{CPC_SPIKE_PCT}%</p>

{render_best_worst_table(d['best_worst'])}

{render_advice_section(build_advice_1d(d))}
</body></html>"""


def render_7d(d):
    t = d["total"]
    w = d["wow"]
    img_b64 = chart_daily_trend(d["daily_trend"])
    chart_html = f'<img src="data:image/png;base64,{img_b64}" style="max-width:100%;"/>' if img_b64 else "<p class=meta>(matplotlib 미설치)</p>"

    daily_rows = "".join(
        f"<tr><td class=l>{x['date']}</td><td>{fmt_won(x['spend'])}</td>"
        f"<td>{fmt_num(x['impressions'])}</td><td>{fmt_pct(x['ctr'])}</td>"
        f"<td>{fmt_won(x['cpc'])}</td></tr>"
        for x in d["daily_trend"]
    )
    camp_rows = "".join(
        f"<tr><td class=l>{c['name']}</td><td>{fmt_won(c['spend'])}</td>"
        f"<td>{fmt_num(c['impressions'])}</td><td>{fmt_pct(c['ctr'])}</td>"
        f"<td>{fmt_won(c['cpc'])}</td><td>{c['freq']:.2f}</td></tr>"
        for c in d["campaigns"]
    )
    top10 = "".join(
        f"<tr><td class=l>{a['ad_name'][:50]}</td><td>{fmt_won(a['spend'])}</td>"
        f"<td>{fmt_num(a['impressions'])}</td><td>{fmt_pct(a['ctr'])}</td>"
        f"<td>{fmt_won(a['cpc'])}</td><td>{a['freq']:.2f}</td></tr>"
        for a in d["top10"]
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{CSS}</head><body>
<h1>Meta JP Weekly — {d['start']} ~ {d['end']}</h1>
<p class=meta>WoW 비교: 전주 ({d['end'] - timedelta(days=13)} ~ {d['end'] - timedelta(days=7)})</p>

<h2>주간 요약 (WoW)</h2>
<table>
  <tr><th>지표</th><th>이번주</th><th>전주</th><th>변화</th></tr>
  <tr><td class=l>Spend</td><td>{fmt_won(w['spend'])}</td><td>{fmt_won(w['spend_prev'])}</td><td>{delta_span(w['spend_pct'])}</td></tr>
  <tr><td class=l>CTR</td><td>{fmt_pct(w['ctr'])}</td><td>{fmt_pct(w['ctr_prev'])}</td><td>{delta_span(w['ctr_pct'])}</td></tr>
  <tr><td class=l>CPC</td><td>{fmt_won(w['cpc'])}</td><td>{fmt_won(w['cpc_prev'])}</td><td>{delta_span(w['cpc_pct'], lower_is_better=True)}</td></tr>
</table>

<h2>일별 추이</h2>
{chart_html}
<table>
  <tr><th>날짜</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th></tr>
  {daily_rows}
</table>

<h2>캠페인 7일 합계</h2>
<table>
  <tr><th>캠페인</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th></tr>
  {camp_rows}
</table>

<h2>광고 TOP 10 (Spend 순)</h2>
<table>
  <tr><th>광고</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th></tr>
  {top10}
</table>

{render_best_worst_table(d['best_worst'])}

{render_advice_section(build_advice_7d(d))}
</body></html>"""


def render_14d(d):
    learning_rows = "".join(
        f"<tr><td class=l>{x['campaign']}</td><td>{x['days_active']}일</td>"
        f"<td>{fmt_won(x['cpc_avg'])}</td><td>{x['stability']}</td></tr>"
        for x in d["learning"]
    ) or "<tr><td colspan=4>데이터 부족</td></tr>"

    cc_rows = ""
    for grp, label in [("image", "이미지"), ("video", "영상"), ("wl", "WL(인플루언서)")]:
        v = d["creative_class"].get(grp)
        if v:
            cc_rows += (f"<tr><td class=l>{label} ({v['n']}개)</td><td>{fmt_won(v['spend'])}</td>"
                        f"<td>{fmt_num(v['impressions'])}</td><td>{fmt_pct(v['ctr'])}</td>"
                        f"<td>{fmt_won(v['cpc'])}</td><td>{v['freq']:.2f}</td></tr>")
        else:
            cc_rows += f"<tr><td class=l>{label}</td><td colspan=5>없음</td></tr>"

    fatigue_rows = "".join(
        f"<tr><td class=l>{x['ad_name'][:50]}</td><td>{x['freq']:.2f}</td>"
        f"<td>{fmt_pct(x['ctr'])}</td><td>{fmt_won(x['spend'])}</td></tr>"
        for x in d["fatigue"]
    ) or "<tr><td colspan=4>피로도 경고 광고 없음</td></tr>"

    actions_html = (
        '<div class="alert"><b>Action Items</b><ul>' +
        "".join(f"<li>{a}</li>" for a in d["actions"]) + "</ul></div>"
    ) if d["actions"] else '<div class="ok">즉시 액션 항목 없음</div>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{CSS}</head><body>
<h1>Meta JP Bi-weekly Audit — {d['start']} ~ {d['end']}</h1>

<h2>학습 단계 진단</h2>
<table>
  <tr><th>캠페인</th><th>활성 일수</th><th>최근 5일 CPC 평균</th><th>안정성</th></tr>
  {learning_rows}
</table>
<p class=meta>최근 5일 CPC 변동폭이 평균의 30% 미만이면 "안정" 판정</p>

<h2>크리에이티브 분류</h2>
<table>
  <tr><th>유형</th><th>Spend</th><th>Impr</th><th>CTR</th><th>CPC</th><th>Freq</th></tr>
  {cc_rows}
</table>

<h2>피로도 경고 (Freq&gt;3.0 또는 Freq&gt;2.0+CTR&lt;1%)</h2>
<table>
  <tr><th>광고</th><th>Freq</th><th>CTR</th><th>Spend</th></tr>
  {fatigue_rows}
</table>

{actions_html}

{render_best_worst_table(d['best_worst'])}

{render_advice_section(build_advice_14d(d))}
</body></html>"""


# ============================================================
# Auditor (rule-based + Gemini)
# ============================================================
REQUIRED_SECTIONS = {
    "1d": ["전체 요약", "캠페인별", "광고 TOP 5", "광고 BEST / WORST", "메타몽 운용 조언"],
    "7d": ["주간 요약", "일별 추이", "캠페인 7일 합계", "광고 BEST / WORST", "메타몽 운용 조언"],
    "14d": ["학습 단계", "크리에이티브 분류", "광고 BEST / WORST", "메타몽 운용 조언"],
}


def audit_rule_based(analysis, html, mode):
    """Code-level integrity checks. Returns list of violations."""
    v = []
    total = analysis.get("total", {})

    if mode == "1d":
        camp_sum = sum(c["spend"] for c in analysis.get("campaigns", []))
        if total.get("spend") and camp_sum > 0:
            diff = abs(camp_sum - total["spend"]) / total["spend"]
            if diff > 0.02:
                v.append(f"SPEND_INCONSISTENT: camp_sum={camp_sum:.0f} vs total={total['spend']:.0f} ({diff*100:.1f}% off)")

    if total.get("impressions", 0) == 0 and mode != "14d":
        v.append("EMPTY_DATA: 0 impressions — Meta API fetch failure suspected")

    bw = analysis.get("best_worst", {})
    if bw.get("ctr_best") and len(bw["ctr_best"]) >= 2:
        ctrs = [a["ctr"] for a in bw["ctr_best"]]
        if ctrs != sorted(ctrs, reverse=True):
            v.append("CTR_BEST_NOT_DESC: BEST 정렬 오류")
    if bw.get("ctr_worst") and len(bw["ctr_worst"]) >= 2:
        ctrs = [a["ctr"] for a in bw["ctr_worst"]]
        if ctrs != sorted(ctrs):
            v.append("CTR_WORST_NOT_ASC: WORST 정렬 오류")
    if bw.get("cpc_best") and len(bw["cpc_best"]) >= 2:
        cpcs = [a["cpc"] for a in bw["cpc_best"]]
        if cpcs != sorted(cpcs):
            v.append("CPC_BEST_NOT_ASC: CPC BEST 정렬 오류")
    if bw.get("cpc_worst") and len(bw["cpc_worst"]) >= 2:
        cpcs = [a["cpc"] for a in bw["cpc_worst"]]
        if cpcs != sorted(cpcs, reverse=True):
            v.append("CPC_WORST_NOT_DESC: CPC WORST 정렬 오류")

    if bw.get("ctr_best") and bw.get("ctr_worst"):
        if bw["ctr_best"][0]["ctr"] < bw["ctr_worst"][0]["ctr"]:
            v.append("BEST_LT_WORST: CTR BEST가 WORST보다 낮음 (논리 오류)")

    for sec in REQUIRED_SECTIONS.get(mode, []):
        if sec not in html:
            v.append(f"MISSING_SECTION: '{sec}' 누락")

    forbidden = ["가능성", "추정", "추측", "아마도"]
    for word in forbidden:
        if word in html:
            v.append(f"SPECULATION_WORD: '{word}' 추측 표현 포함")
            break

    return v


def audit_gemini(html, mode):
    """Semantic audit via Gemini. Returns dict {pass, score, violations}."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"pass": True, "skip": True, "reason": "genai not installed"}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"pass": True, "skip": True, "reason": "GEMINI_API_KEY missing"}

    client = genai.Client(api_key=api_key)
    rules = """
[감사 규칙 — Meta JP 광고 리포트]
1. 본문 숫자(spend/CTR/CPC/Freq)와 조언 텍스트의 진단이 일치할 것
2. BEST/WORST 격차에 비례하는 액션 제안일 것 (격차 작은데 "즉시 폐기" 등 과잉 금지)
3. 표/테이블 형식 깨짐 없음 (빈 td, 잘못된 colspan 등)
4. 한국어 비즈니스 톤. "가능성/추정/추측" 등 추측 표현 금지
5. 단위 일관성: 금액은 ₩, 비율은 %, Freq는 소수점
6. 조언 섹션이 데이터 부족 시 "데이터 부족" 명시 (가짜 인사이트 금지)

JSON 응답 (mime=application/json):
{"pass": bool, "score": 0-100, "violations": [{"rule": "string", "fix": "string"}]}
score >= 80 일 때만 pass=true.
"""
    import re
    # base64 차트 데이터 제거 (감사 텍스트 분량 확보)
    audit_html = re.sub(r'data:image/png;base64,[^"]+', '[CHART_PNG]', html)
    prompt = f"다음 Meta JP {mode} 리포트 HTML을 감사하세요.\n\n{rules}\n\n[HTML]\n{audit_html[:50000]}"

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        text = (resp.text or "").strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json.loads(text)
        return result
    except Exception as e:
        return {"pass": False, "score": 0,
                "violations": [{"rule": "AUDITOR_ERROR", "fix": str(e)}],
                "error": str(e)}


def run_auditor(analysis, html, mode):
    """Combined: rule + Gemini. Returns (passed, report_str)."""
    rule_v = audit_rule_based(analysis, html, mode)
    gemini = audit_gemini(html, mode)

    lines = []
    lines.append(f"[AUDIT] mode={mode}")
    lines.append(f"  Rule violations: {len(rule_v)}")
    for x in rule_v:
        lines.append(f"    - {x}")
    if gemini.get("skip"):
        lines.append(f"  Gemini: SKIPPED ({gemini.get('reason')})")
    else:
        score = gemini.get("score", 0)
        lines.append(f"  Gemini score: {score}")
        for vv in gemini.get("violations", []):
            lines.append(f"    - {vv.get('rule')}: {vv.get('fix', '')[:120]}")

    rule_pass = len(rule_v) == 0
    gemini_pass = gemini.get("pass", False) or gemini.get("skip", False)
    passed = rule_pass and gemini_pass
    lines.append(f"  → {'PASS' if passed else 'FAIL'}")
    return passed, "\n".join(lines)


# ============================================================
# Send
# ============================================================
def send(to, subject, html_path):
    cmd = [sys.executable, str(TOOLS / "send_gmail.py"),
           "--to", to, "--subject", subject, "--body-file", str(html_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"[FAIL] send_gmail: {r.stderr}")
        return False
    print(f"[OK] sent to {to}")
    return True


# ============================================================
# Main
# ============================================================
def main():
    if not TOKEN or not ACCT:
        print("[ERROR] META_JP_ACCESS_TOKEN / META_JP_AD_ACCOUNT_ID missing in .env")
        sys.exit(1)

    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["1d", "7d", "14d"], default="1d")
    p.add_argument("--to", default=DEFAULT_TO)
    p.add_argument("--no-send", action="store_true")
    p.add_argument("--skip-audit", action="store_true",
                   help="EMERGENCY ONLY — bypass auditor (logs warning)")
    p.add_argument("--date", help="reference date YYYY-MM-DD (default: yesterday)")
    args = p.parse_args()

    ref = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    print(f"[INFO] mode={args.mode} ref_date={ref}")

    if args.mode == "1d":
        analysis = analyze_1d(ref)
        html = render_1d(analysis)
        subject = f"[Meta JP] Daily {ref}"
    elif args.mode == "7d":
        analysis = analyze_7d(ref)
        html = render_7d(analysis)
        subject = f"[Meta JP] Weekly {analysis['start']} ~ {analysis['end']}"
    else:
        analysis = analyze_14d(ref)
        html = render_14d(analysis)
        subject = f"[Meta JP] Bi-weekly Audit {analysis['start']} ~ {analysis['end']}"

    out_path = TMP_DIR / f"meta_jp_{args.mode}_{ref.isoformat()}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"[OK] saved {out_path} ({len(html):,} bytes)")

    # Auditor gate
    if args.skip_audit:
        print("[WARN] --skip-audit: 감사 우회 (긴급 모드)")
    else:
        passed, audit_report = run_auditor(analysis, html, args.mode)
        print(audit_report)
        audit_log = TMP_DIR / f"meta_jp_{args.mode}_{ref.isoformat()}.audit.log"
        audit_log.write_text(audit_report, encoding="utf-8")
        if not passed:
            print(f"[BLOCKED] auditor FAIL — 발송 차단. 로그: {audit_log}")
            if not args.no_send:
                sys.exit(2)

    if args.no_send:
        print("[SKIP] --no-send")
        return

    send(args.to, subject, out_path)


if __name__ == "__main__":
    main()
