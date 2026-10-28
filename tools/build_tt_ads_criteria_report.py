# -*- coding: utf-8 -*-
"""TikTok Ads 운영 기준 리포트 빌더.

입력: .tmp/tiktok_probe/tt_daily_ads.json (Ads Manager 일자별×광고별 스크랩, 9/18~10/8)
출력: reports/tt_ads_criteria_20261008.html

내용: ①OFF 기준(룰 시뮬 포함) ②기세 꺾임 시점 ③판정 기준 ④⑤ 좋은/나쁜 광고 효율 궤적 차트.
지표 전부 TikTok 'destination' 정의 (LPV=landing page view). CPC/CPLPV는 원시값 재계산.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / ".tmp/tiktok_probe/tt_daily_ads.json"
if not SRC.exists():
    raise SystemExit(f"입력 없음: {SRC} — 먼저 .tmp/tiktok_probe/scrape_daily_ads.py + parse_daily.py 실행")
try:
    DATA = json.loads(SRC.read_text(encoding="utf-8"))
except json.JSONDecodeError as e:
    raise SystemExit(f"입력 JSON 파싱 실패: {SRC} — {e}")
OUT = BASE / "reports" / "tt_ads_criteria_20261008.html"

# OFF 룰 파라미터 (시뮬 대상)
GATE = 200        # 판정일 = 일 지출 >= 200 JPY
FROM_DAY = 3      # D0~D2 판정 제외 (D0~D1 탐색 트래픽 왜곡 + D2는 정상 광고도 위반 찍는 노이즈 날. 세은 확정 2026-10-08)
CPLPV_BAD = 4.0   # 위반: CPLPV > 4 JPY
CTR_BAD = 8.0     # 또는 CTR < 8%
STREAK = 3        # 판정일 연속 3회 위반 → OFF

# ---------------- 시계열 구성 ----------------
ads = {}
for date in sorted(DATA.keys()):
    for r in DATA[date]:
        a = ads.setdefault(r["ad_id"], {"name": r["name"], "series": []})
        a["series"].append({"date": date, "spend": r["spend"], "imp": r["impressions"],
                            "clicks": r["clicks"], "conv": r["conversions"]})
        if not r["name"].startswith("2026-"):
            a["name"] = r["name"]

def label(ad_id, name):
    return f"0918_#{ad_id[-4:]}" if name.startswith("2026-") else name

cum = []
for ad_id, a in ads.items():
    sdays = [x for x in a["series"] if x["spend"] > 0]
    spend = sum(x["spend"] for x in a["series"])
    imp = sum(x["imp"] for x in a["series"])
    clicks = sum(x["clicks"] for x in a["series"])
    conv = sum(x["conv"] for x in a["series"])
    if imp == 0:
        continue
    cum.append({
        "ad_id": ad_id, "label": label(ad_id, a["name"]), "spend": spend, "imp": imp,
        "clicks": clicks, "conv": conv,
        "ctr": clicks / imp * 100,
        "cplpv": spend / conv if conv else None,
        "days": sdays, "first": sdays[0]["date"] if sdays else "-",
    })
cum.sort(key=lambda x: (x["cplpv"] is None, x["cplpv"]))

GOOD = ["0918_#5490", "0918_#3858", "0918_#5522", "0918_#6642"]
BAD = ["0918_#2770", "0929_韓国ママの秘密", "0918_#3842", "0918_#6658", "0929_ママたちの間で話題のマグ"]
MID = ["0918_#3826", "0918_#3810"]

# ---------------- 캠페인 일별 ----------------
daily = []
for date in sorted(DATA.keys()):
    rows = DATA[date]
    spend = sum(r["spend"] for r in rows)
    imp = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv = sum(r["conversions"] for r in rows)
    daily.append({"date": date[5:], "spend": spend,
                  "ctr": clicks / imp * 100 if imp else 0,
                  "cplpv": spend / conv if conv else None})

# ---------------- OFF 룰 시뮬 ----------------
def simulate(ad):
    """판정일(D2+, 지출>=GATE)에서 CPLPV>4 or CTR<8% 연속 STREAK회 → OFF.
    반환: (off_date, off_dayindex, spent_until_off) 또는 None."""
    streak = 0
    spent = 0.0
    for i, d in enumerate(ad["days"]):
        spent += d["spend"]
        if i < FROM_DAY or d["spend"] < GATE:
            continue
        ctr = d["clicks"] / d["imp"] * 100 if d["imp"] else 0
        cplpv = d["spend"] / d["conv"] if d["conv"] else float("inf")
        if cplpv > CPLPV_BAD or ctr < CTR_BAD:
            streak += 1
        else:
            streak = 0
        if streak >= STREAK:
            return d["date"], i, spent
    return None

sim_rows = []
total_saved = 0.0
for c in cum:
    r = simulate(c)
    if c["label"] in BAD:
        if r:
            off_date, di, spent = r
            saved = c["spend"] - spent
            total_saved += saved
            sim_rows.append((c["label"], f"D{di} ({off_date[5:]})", f"{spent:,.0f}", f"{saved:,.0f}"))
        else:
            sim_rows.append((c["label"], "미발동", f"{c['spend']:,.0f}", "0"))
    elif r:  # 좋은/중간 광고 오탐 체크
        sim_rows.append((c["label"] + " ⚠오탐", f"D{r[1]} ({r[0][5:]})", f"{r[2]:,.0f}", "-"))

# ---------------- D1 미끼 통계 ----------------
def trap(c):
    early = [d for i, d in enumerate(c["days"]) if i <= 1]
    late = [d for i, d in enumerate(c["days"]) if i >= 2]
    e_imp = sum(d["imp"] for d in early); e_clk = sum(d["clicks"] for d in early)
    l_imp = sum(d["imp"] for d in late); l_clk = sum(d["clicks"] for d in late)
    return (e_clk / e_imp * 100 if e_imp else 0, l_clk / l_imp * 100 if l_imp else 0)

trap_rows = [(c["label"], *trap(c), c["label"] in BAD) for c in cum if c["label"] in GOOD + BAD]

# ---------------- 차트 데이터 ----------------
def series_by_day(lbl):
    c = next(x for x in cum if x["label"] == lbl)
    cplpv, ctr = [], []
    for d in c["days"]:
        cplpv.append(round(d["spend"] / d["conv"], 2) if d["conv"] and d["spend"] > 0 else None)
        ctr.append(round(d["clicks"] / d["imp"] * 100, 2) if d["imp"] else None)
    return {"label": lbl, "cplpv": cplpv, "ctr": ctr}

chart = {
    "daily": {"labels": [d["date"] for d in daily],
              "spend": [d["spend"] for d in daily],
              "cplpv": [round(d["cplpv"], 2) if d["cplpv"] else None for d in daily],
              "ctr": [round(d["ctr"], 2) for d in daily]},
    "good": [series_by_day(l) for l in GOOD],
    "bad": [series_by_day(l) for l in BAD],
    "trap": {"labels": [t[0] for t in trap_rows],
             "early": [round(t[1], 1) for t in trap_rows],
             "late": [round(t[2], 1) for t in trap_rows],
             "isbad": [t[3] for t in trap_rows]},
}

TOTAL = sum(r["spend"] for rows in DATA.values() for r in rows)

# ---------------- 누적 표 ----------------
def tier(c):
    if c["label"] in BAD:
        return "OFF 대상"
    if c["label"] in GOOD:
        return "정상"
    if c["label"] in MID:
        return "중간"
    return "판정 유보 (지출 미달)"

cum_rows = "".join(
    f"<tr class='{ 'bad' if c['label'] in BAD else ('good' if c['label'] in GOOD else '') }'>"
    f"<td>{c['label']}</td><td class='r'>{c['spend']:,.0f}</td><td class='r'>{c['conv']:,}</td>"
    f"<td class='r'>{c['cplpv']:.2f}</td><td class='r'>{c['ctr']:.1f}%</td>"
    f"<td class='r'>{c['spend']/TOTAL*100:.0f}%</td><td>{tier(c)}</td></tr>"
    for c in cum)

sim_html = "".join(f"<tr><td>{a}</td><td>{b}</td><td class='r'>{c}</td><td class='r'>{d}</td></tr>"
                   for a, b, c, d in sim_rows)

bad_spend = sum(c["spend"] for c in cum if c["label"] in BAD)
bad_lpv = sum(c["conv"] for c in cum if c["label"] in BAD)

HTML = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>TikTok Ads 운영 기준 — 캠페인 전체 히스토리 실측 (2026-10-08)</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
body{{font-family:'Pretendard','Malgun Gothic',sans-serif;max-width:1060px;margin:24px auto;padding:0 20px;color:#1a1a1a;line-height:1.55}}
h1{{font-size:21px;border-bottom:3px solid #111;padding-bottom:8px}}
h2{{font-size:16px;margin-top:34px;border-left:4px solid #111;padding-left:9px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0}}
th{{background:#111;color:#fff;padding:6px 8px;text-align:left;font-weight:600}}
td{{border-bottom:1px solid #e3e3e3;padding:5px 8px}}
.r{{text-align:right}} tr.good td{{background:#f0f7f0}} tr.bad td{{background:#fbf0f0}}
.note{{font-size:12px;color:#555;background:#f5f5f5;border-left:3px solid #999;padding:8px 12px;margin:10px 0}}
.chartbox{{margin:14px 0;padding:10px;border:1px solid #ddd;border-radius:6px}}
canvas{{max-height:330px}}
.kpi{{font-size:13px}} .kpi b{{font-size:14px}}
</style></head><body>

<h1>TikTok Ads 운영 기준 — 캠페인 전체 히스토리 실측</h1>
<p class="kpi">모수: 캠페인 1개(260918_traffic_IHV_PPSU&amp;Stainless, 유일한 집행 이력) · 광고 17개 · 2026-09-18 ~ 10-08 (21일, 10/8은 당일 진행분) · 총 지출 <b>99,355엔</b> · Ads Manager 일자별 실측(일합 vs 누적 오차 0.01%).<br>
지표는 전부 TikTok <b>destination 기준</b>(LPV=landing page view, 구매 아님). CPC·CPLPV는 원시값 재계산.</p>

<h2>TL;DR — 질문 5개 답</h2>
<table>
<tr><th style="width:34%">질문</th><th>답</th></tr>
<tr><td>1. 언제 OFF?</td><td><b>D3부터, 일 지출 ≥200엔인 날 기준 「CPLPV &gt; 4엔 or CTR &lt; 8%」 3판정일 연속 → OFF</b> (최초 OFF = 집행 6일차, 120시간+ 관찰 보장). 과거 21일에 적용 시 실패 5개 전부 D5~D10에 차단, 정상 광고 오탐 0, 지출 39% 절약 (아래 시뮬).</td></tr>
<tr><td>2. 기세 꺾이는 시점</td><td>실패 소재는 <b>2~5일차에 결판</b>(5/5건이 D2~D5 붕괴). 생존 소재 4개는 21일 내 꺾임 없음. 중간 2개만 8~11일차 완만 피로. "오래 돌려서 꺾였다"보다 <b>초반 생존 여부가 거의 전부</b>.</td></tr>
<tr><td>3. 잘/못 판정 기준</td><td>지출 게이트(누적 ≥1,500엔) 통과 후: <b>정상 = CPLPV ≤ 3엔 &amp; CTR ≥ 10%</b> / 실패 = CPLPV ≥ 4엔 or CTR &lt; 8%. 실측 분포가 1.7엔↔4.6엔, 14%↔8%로 갈라져 중간지대 거의 없음.</td></tr>
<tr><td>4. 잘 돌아가는 광고 궤적</td><td>CPLPV가 <b>0.7~1.5엔 좁은 밴드에서 횡보</b>, 지출이 몇 배로 출렁여도 밴드 유지 (차트 ②).</td></tr>
<tr><td>5. 안 돌아가는 광고 궤적</td><td><b>D0~D1 CTR 19~56% 미끼 스파이크 → D2~D5 붕괴(CTR 2~6%, CPLPV 7~27엔) → 복구 없이 고착.</b> 5건 전부 동일 패턴 (차트 ③·④).</td></tr>
</table>

<h2>광고 17개 전기간 성적 (CPLPV 오름차순)</h2>
<table>
<tr><th>광고</th><th class="r">지출(엔)</th><th class="r">LPV</th><th class="r">CPLPV(엔)</th><th class="r">CTR</th><th class="r">지출비중</th><th>판정</th></tr>
{cum_rows}
</table>
<p class="note">실패 5개가 지출 <b>{bad_spend:,.0f}엔(64%)</b>를 소진하고 LPV는 {bad_lpv:,}개(25%)만 생산. 같은 돈을 정상 광고 단가(≈0.9엔)로 돌렸으면 LPV 약 5배. <b>자동배분이 효율을 따라가지 않음</b>(지출 1·2위가 효율 최하위권) — 수동 OFF 룰이 필요한 직접 근거.</p>

<h2>① OFF 룰 + 과거 21일 백테스트</h2>
<p class="kpi">룰: <b>D0~D2 판정 금지</b> → D3부터 일 지출 ≥200엔인 날만 판정일로 집계 → <b>CPLPV &gt; 4엔 or CTR &lt; 8% 가 판정일 3회 연속 → OFF</b> (최초 OFF = 집행 6일차 = 120시간+ 관찰 후).<br>
D0~D1 제외 근거: 탐색 트래픽이 CTR 왜곡 — 실패 5건도 초반 1~2일 CTR 19~56%로 정상권. D2 제외 근거: 정상 광고도 D2에 위반을 찍는 노이즈 날 — #5490(D2 6.72엔→D4부터 0.8~1.0엔 복귀)·#3826(D2 5.34엔→D3 1.05엔 복귀). 판정 시작을 D4로 더 미루면 #2770이 간헐 회복일 덕에 D13까지 생존(절약 18%로 반토막)·#6658 미차단 — D3가 최적점.</p>
<table>
<tr><th>광고</th><th>OFF 발동 시점</th><th class="r">그때까지 지출(엔)</th><th class="r">절약(엔)</th></tr>
{sim_html}
<tr><td><b>합계</b></td><td></td><td></td><td class="r"><b>{total_saved:,.0f} (전체 지출의 {total_saved/99355*100:.0f}%)</b></td></tr>
</table>
<p class="note">오탐 검증: 정상·중간 광고 전부 미발동. "3회 연속" 조건은 실패 광고의 간헐 회복일(#2770의 D6·D10·D17) 미끼와 정상 광고의 일시 흔들림을 모두 흡수 — 0918_#3826(D1~D2 8.3→5.3엔으로 나빴다가 D3 1.0엔 복구, 최종 1.59엔) 같은 회복형을 살림.</p>

<h2>② 캠페인 일별 흐름 + 신규 소재 투입 리스크</h2>
<div class="chartbox"><canvas id="c1"></canvas></div>
<p class="kpi">9/30에 0929 신규 5본 투입 → 투입 당일은 좋았으나(전체 CPLPV 0.85엔) <b>10/1·10/3·10/4에 韓国ママの秘密가 지출을 흡수하며 캠페인 전체가 6.3~17.5엔으로 붕괴</b>. 한 캠페인 안에 신규를 넣으면 기존 성과가 같이 흔들림 — 신규 투입 후 D2~D4는 광고별 감시 필수 구간.</p>

<h2>③ 잘 돌아가는 광고의 움직임 — CPLPV 밴드 횡보</h2>
<div class="chartbox"><canvas id="c2"></canvas></div>
<p class="kpi">생존 4개는 21일 내내 0.7~1.5엔 밴드 (y축 로그). 일 지출이 21엔→2,142엔으로 100배 출렁여도(#5490) 단가가 밴드를 벗어나지 않음 = <b>"잘 돌아간다" = 단가의 안정성</b>이지 특정 날 성과가 아님.</p>

<h2>④ 안 돌아가는 광고의 움직임 — D2 붕괴 후 고착</h2>
<div class="chartbox"><canvas id="c3"></canvas></div>
<p class="kpi">5개 전부 D2~D5 구간에 CPLPV 7~27엔으로 점프 후 끝까지 4엔 아래로 복귀 못 함 (y축 로그). 간헐적 회복일(#2770의 D6·D10·D17)이 있어도 누적은 4.7엔 — <b>하루 반등을 회복으로 믿지 말 것</b>(그래서 룰이 "3판정일 연속").</p>

<h2>⑤ D0~D1은 전부 잘 나온다 — 미끼 구간 증명</h2>
<div class="chartbox"><canvas id="c4"></canvas></div>
<p class="kpi">실패 광고도 첫 1~2일 합산 CTR 19~48%로 정상 광고와 구분 불가 → D2 이후 2~6%로 추락. <b>론칭 직후 성과로 증액·판정 금지.</b></p>

<h2>구매(라쿠텐 착지) 레이어 — 판정 보류 유지</h2>
<p class="kpi">TT 착지인 기본컵의 라쿠텐 주문은 19일간 25건(일 0~3건)으로 TT 일 지출(1천~6.3천엔)과 연동 신호 없음. LPV 효율 기준과 별개로 <b>구매 CVR 판정은 D+14 누적 후</b>(기존 결론 유지). 위 기준은 "트래픽 캠페인으로서 소재·배분 관리" 기준이고, 채널 자체의 매출 기여 판정이 아님.</p>

<p class="note">한계: ①지표 전부 TikTok destination 정의 — Meta link click과 직접 비교 금지 ②상태(Active)는 현재값이라 과거 수동 on/off 이력은 식별 불가 ③표본 = 캠페인 1개·트래픽 목적·21일. GMV Max 등 다른 목적엔 이 임계값 이식 금지, 구조(D0~D1 제외·연속 판정·지출 게이트)만 이식.</p>

<script>
const C = {json.dumps(chart, ensure_ascii=False)};
const gcol = ["#1a7a3a","#2f9e55","#57b878","#8fd3a8"];
const bcol = ["#b02020","#d04545","#e07070","#8a1515","#f0a0a0"];
new Chart(document.getElementById('c1'), {{
 data: {{labels: C.daily.labels, datasets: [
  {{type:'bar', label:'지출(엔)', data:C.daily.spend, backgroundColor:'#c9d4e4', yAxisID:'y'}},
  {{type:'line', label:'CPLPV(엔)', data:C.daily.cplpv, borderColor:'#b02020', yAxisID:'y2', tension:.2}},
  {{type:'line', label:'CTR(%)', data:C.daily.ctr, borderColor:'#1a7a3a', yAxisID:'y2', tension:.2, borderDash:[5,3]}}]}},
 options: {{scales: {{y:{{position:'left', title:{{display:true,text:'지출(엔)'}}}},
  y2:{{position:'right', title:{{display:true,text:'CPLPV(엔) / CTR(%)'}}, grid:{{drawOnChartArea:false}}}}}},
  plugins:{{title:{{display:true,text:'캠페인 일별: 지출 · CPLPV · CTR (9/18~10/8)'}}}}}}
}});
function adChart(id, series, cols, title) {{
 const maxLen = Math.max(...series.map(s=>s.cplpv.length));
 new Chart(document.getElementById(id), {{type:'line',
  data: {{labels: Array.from({{length:maxLen}},(_,i)=>'D'+i),
   datasets: series.map((s,i)=>({{label:s.label, data:s.cplpv, borderColor:cols[i],
     backgroundColor:cols[i], tension:.15, spanGaps:true, pointRadius:2.5}}))}},
  options: {{scales:{{y:{{type:'logarithmic', title:{{display:true,text:'CPLPV(엔, 로그)'}}}}}},
   plugins:{{title:{{display:true,text:title}}}}}}}});
}}
adChart('c2', C.good, gcol, '정상 광고 4개 — 일별 CPLPV (런칭 후 경과일)');
adChart('c3', C.bad, bcol, '실패 광고 5개 — 일별 CPLPV (런칭 후 경과일)');
new Chart(document.getElementById('c4'), {{type:'bar',
 data: {{labels: C.trap.labels, datasets: [
  {{label:'D0~D1 CTR(%)', data:C.trap.early, backgroundColor:'#7a9cc9'}},
  {{label:'D2 이후 CTR(%)', data:C.trap.late,
    backgroundColor:C.trap.isbad.map(b=>b?'#d04545':'#2f9e55')}}]}},
 options: {{plugins:{{title:{{display:true,text:'론칭 직후 CTR vs 이후 CTR — 초록=정상, 빨강=실패'}}}}}}
}});
</script>
</body></html>
"""

OUT.write_text(HTML, encoding="utf-8")
print(f"saved {OUT}")
print(f"OFF 시뮬 절약 합계: {total_saved:,.0f} JPY ({total_saved/99355*100:.1f}%)")
for r in sim_rows:
    print("  ", r)
