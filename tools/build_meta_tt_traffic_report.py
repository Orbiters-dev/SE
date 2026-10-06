# -*- coding: utf-8 -*-
"""Meta vs TikTok 트래픽 비교 리포트 (독립 HTML).

설계: C:/Users/orbit/.claude/plans/ads-curious-clarke.md
실험: memory/project_meta_tiktok_channel_cvr_experiment.md

2레이어 비교:
  A) 광고 플랫폼 측(볼륨/효율) — Meta DK(PPSU_Proven 트래픽, stainless 제외) vs TT 대시보드 수동 누적.
  B) 랜딩 도달 측(질) — 라쿠텐 fliptop vs 기본컵 非RPP 방문·주문·CVR (스왑 후 fliptop=Meta·기본컵=TikTok 유료 유입, 오가닉 상시 혼입 = 순수 채널 아님).

데이터원:
  - Meta: DataKeeper meta_ads_daily (objective=OUTCOME_TRAFFIC, brand=Grosmimi JP/Grosmimi, JP, stainless 제외)
  - 라쿠텐: .tmp/channel_cvr_experiment/daily_cvr.json (gross) − rpp_daily.json (RPP 차감) = gross 소셜근사
  - TikTok: .tmp/channel_cvr_experiment/tt_ads_summary.json (수동 스크랩 누적)

통화: Meta=KRW, TikTok=JPY. 환산 1 JPY = 8.6 KRW (2026-10-02, xe/wise 8.56~8.62 중앙값).

CLI: python tools/build_meta_tt_traffic_report.py [--open]
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_keeper_client import DataKeeper  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / ".tmp" / "channel_cvr_experiment"
REPORTS = ROOT / "reports"

JPY_KRW = 8.6                       # 2026-10-02 환율 (xe/wise 8.56~8.62)
SWAP_DATE = "2026-09-21"
# fliptop 착지 ad 식별 = 9/21 스왑 롤백맵의 ad_id (PPSU Proven + Testing의 PPSU, stainless 0 교차검증)
SWAP_ROLLBACK = ROOT / ".tmp" / "swap_fliptop_rollback_20260921.json"
# Meta fliptop 착지 유효 구간 = 스왑(9/21) 다음날부터. TT 재스크랩과 동일기간 9/22~10/5 맞춤 (오늘자).
META_CMP_FROM, META_CMP_TO = "2026-09-22", "2026-10-05"
# TikTok 캠페인 누적 구간은 tt_ads_summary.json 에서 읽는다 (period_from~to).
# ⚠️ API 반려로 수동 스크랩. 2026-10-06 재스크랩으로 9/22~10/5 커버 → A레이어 동일기간 오늘자 복원.
# 라쿠텐 일별 추세 구간 (B 랜딩질) = 오늘자까지 확장 (D+14 누적)
RKT_FROM, RKT_TO = "2026-09-07", "2026-10-05"


def _days(d0, d1):
    return (datetime.strptime(d1, "%Y-%m-%d") - datetime.strptime(d0, "%Y-%m-%d")).days + 1


# ───────────────────────── Meta (DK) ─────────────────────────
def fetch_meta():
    """9/21 스왑된 42 ad_id(=fliptop URL 착지) 트래픽 광고의 일별 집계.
    롤백맵으로 정확 식별 → Proven+Testing의 PPSU 전량 포함, stainless 혼입 0(교차검증)."""
    swap_ids = set(json.loads(SWAP_ROLLBACK.read_text(encoding="utf-8")).keys())
    dk = DataKeeper()
    rows = dk.get("meta_ads_daily", date_from=RKT_FROM, date_to=RKT_TO)
    sw = [r for r in rows if str(r.get("ad_id")) in swap_ids]
    byd = defaultdict(lambda: {"spend": 0.0, "impr": 0, "clicks": 0, "lpv": 0})
    for r in sw:
        d = r.get("date")
        byd[d]["spend"] += float(r.get("spend") or 0)
        byd[d]["impr"] += int(r.get("impressions") or 0)
        byd[d]["clicks"] += int(r.get("clicks") or 0)
        byd[d]["lpv"] += int(r.get("landing_page_view") or 0)
    return dict(byd), len(swap_ids)


def meta_agg(meta_daily, d0, d1):
    spend = impr = clicks = lpv = 0
    for d, v in meta_daily.items():
        if d0 <= d <= d1:
            spend += v["spend"]; impr += v["impr"]; clicks += v["clicks"]; lpv += v["lpv"]
    n = _days(d0, d1)
    return {"spend": round(spend), "impr": impr, "clicks": clicks, "lpv": lpv,
            "ctr": round(clicks / impr * 100, 2) if impr else 0,
            "cpc": round(spend / clicks, 1) if clicks else 0,
            "cplpv": round(spend / lpv, 1) if lpv else 0,
            "days": n,
            "spend_d": round(spend / n), "clicks_d": round(clicks / n), "impr_d": round(impr / n)}


# ───────────────────────── 라쿠텐 (non-RPP) ─────────────────────────
def load_rakuten():
    daily = json.loads((EXP / "daily_cvr.json").read_text(encoding="utf-8"))
    rpp = json.loads((EXP / "rpp_daily.json").read_text(encoding="utf-8"))
    out = {}
    for day, groups in daily.items():
        if "_error" in groups:
            continue
        row = {}
        for g in ("fliptop", "kihon"):
            gross = groups.get(g, {})
            sub = (rpp.get(day, {}) or {}).get(g, {})
            v = max(0, (gross.get("visit", 0) or 0) - (sub.get("visit", 0) or 0))
            o = max(0, (gross.get("orders", 0) or 0) - (sub.get("orders", 0) or 0))
            row[g] = {"visit": v, "orders": o}
        out[day] = row
    return out


def rkt_window(rkt, d0, d1):
    acc = {g: {"visit": 0, "orders": 0, "days": 0} for g in ("fliptop", "kihon")}
    for day, row in rkt.items():
        if not (d0 <= day <= d1):
            continue
        for g in ("fliptop", "kihon"):
            acc[g]["visit"] += row[g]["visit"]
            acc[g]["orders"] += row[g]["orders"]
            acc[g]["days"] += 1
    for g in acc:
        n = acc[g]["days"] or 1
        acc[g]["visit_avg"] = round(acc[g]["visit"] / n, 1)
        acc[g]["cvr"] = round(acc[g]["orders"] / acc[g]["visit"] * 100, 2) if acc[g]["visit"] else 0.0
    return acc


# ───────────────────────── HTML ─────────────────────────
def kw(n):
    return f"{n:,.0f}"


def build_html(meta_daily, rkt, tt):
    m = meta_agg(meta_daily, META_CMP_FROM, META_CMP_TO)
    tt_spend_krw = round(tt["spend"] * JPY_KRW)
    # TT CPC = 대시보드 반올림값(정수 JPY)은 1~2엔 구간에서 손실 큼 → spend/clicks 정밀 계산
    tt_cpc = round(tt["spend"] / tt["clicks"], 2) if tt.get("clicks") else tt["cpc"]
    tt_cpc_krw = round(tt_cpc * JPY_KRW, 1)
    # 효율 배수 (동일기간 META_CMP)
    clicks_ratio = round(tt["clicks"] / m["clicks"], 1) if m["clicks"] else 0
    cpc_ratio = round(m["cpc"] / tt_cpc_krw, 1) if tt_cpc_krw else 0
    spend_ratio = round(m["spend"] / tt_spend_krw, 1) if tt_spend_krw else 0
    # 라쿠텐 스왑 전/후
    pre = rkt_window(rkt, "2026-09-07", "2026-09-21")
    post = rkt_window(rkt, "2026-09-22", RKT_TO)
    # 스왑 직후 fliptop 방문 리프트 (非RPP 실측 — legend 동적 생성)
    f21 = rkt.get("2026-09-21", {}).get("fliptop", {}).get("visit", 0)
    f22 = rkt.get("2026-09-22", {}).get("fliptop", {}).get("visit", 0)
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")

    # Part A 비교표
    def row_cmp(label, meta_v, tt_v, note=""):
        return (f'<tr><td class="lbl">{label}</td><td class="meta">{meta_v}</td>'
                f'<td class="tt">{tt_v}</td><td class="note">{note}</td></tr>')

    partA = "".join([
        row_cmp("지출(spend)", f"{kw(m['spend'])} KRW", f"{kw(tt['spend'])} JPY<br><span class=sub>≈{kw(tt_spend_krw)} KRW</span>", f"<b>Meta가 {spend_ratio}배 더 씀</b>"),
        row_cmp("노출(impressions)", kw(m["impr"]), kw(tt["impressions"]), f"TT {round(tt['impressions']/m['impr'],1)}배"),
        row_cmp("클릭(clicks)", kw(m["clicks"]), kw(tt["clicks"]), f"<b>TT {clicks_ratio}배</b>"),
        row_cmp("CTR", f"{m['ctr']}%", f"{tt['ctr']}%", "유사 (정의 다름)"),
        row_cmp("CPC(클릭당)", f"{m['cpc']} KRW", f"{tt_cpc} JPY<br><span class=sub>≈{tt_cpc_krw} KRW</span>", f"<b>Meta가 {cpc_ratio}배 비쌈</b>"),
    ])

    # Part B 라쿠텐 일별 표
    rows_rkt = []
    for day in sorted(rkt):
        if not (RKT_FROM <= day <= RKT_TO):
            continue
        f, k = rkt[day]["fliptop"], rkt[day]["kihon"]
        cls = ' class="swap"' if day == SWAP_DATE else (' class="after"' if day >= "2026-09-22" else "")
        mark = " ⟵스왑" if day == SWAP_DATE else ""
        def cvr(o, v): return round(o / v * 100, 2) if v else 0
        rows_rkt.append(
            f'<tr{cls}><td class="day">{day[5:]}{mark}</td>'
            f'<td>{kw(f["visit"])}</td><td>{f["orders"]}</td><td>{cvr(f["orders"],f["visit"])}</td>'
            f'<td>{kw(k["visit"])}</td><td>{k["orders"]}</td><td>{cvr(k["orders"],k["visit"])}</td></tr>')

    def scard(s):
        return (f'fliptop <b>{kw(s["fliptop"]["visit_avg"])}</b>방문/일 · 주문 {s["fliptop"]["orders"]} · CVR {s["fliptop"]["cvr"]}%'
                f'<br>기본컵(PPSU) <b>{kw(s["kihon"]["visit_avg"])}</b>방문/일 · 주문 {s["kihon"]["orders"]} · CVR {s["kihon"]["cvr"]}%')

    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meta vs TikTok 트래픽 비교 — 2026-09</title><style>
*{{box-sizing:border-box}}
body{{font-family:'Segoe UI','Malgun Gothic',sans-serif;background:#f4f6f9;color:#1b2430;margin:0;padding:34px}}
.wrap{{max-width:1040px;margin:0 auto}}
h1{{font-size:24px;margin:0 0 4px}} .sub{{color:#8a94a2;font-size:12px}}
.topmeta{{color:#6b7684;font-size:12.5px;margin:6px 0 24px}}
.card{{background:#fff;border:1px solid #e4e9f0;border-radius:14px;padding:22px 26px;margin-bottom:22px;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
.card h2{{font-size:17px;margin:0 0 4px}} .card .desc{{color:#5a6675;font-size:13px;margin:0 0 16px;line-height:1.6}}
.tldr{{background:linear-gradient(135deg,#eef4ff,#fdeef5);border:1px solid #dde6f2}}
.tldr ul{{margin:8px 0 0;padding-left:20px}} .tldr li{{margin:7px 0;font-size:14px;line-height:1.6}}
.kpis{{display:flex;gap:14px;flex-wrap:wrap;margin:4px 0 8px}}
.kpi{{flex:1;min-width:150px;background:#f7f9fc;border-radius:10px;padding:14px 16px;border:1px solid #eceff4}}
.kpi .v{{font-size:23px;font-weight:700}} .kpi .l{{font-size:11.5px;color:#7a8696;margin-top:3px}}
.kpi.tt .v{{color:#e23b7a}} .kpi.meta .v{{color:#2563c9}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #e4e9f0;padding:7px 10px;text-align:center}}
th{{background:#eef2f7;font-weight:600}}
td.lbl{{text-align:left;font-weight:600;background:#fafbfd}} td.meta{{color:#2563c9;font-weight:600}} td.tt{{color:#e23b7a;font-weight:600}}
td.note{{color:#5a6675;font-size:12px;text-align:left}} .sub{{font-size:11px;color:#9aa4b2}}
td.day{{text-align:left;font-variant-numeric:tabular-nums}}
tr.swap td{{background:#fff7e6;font-weight:600}} tr.after td{{background:#f3f8ff}}
.gf{{background:#eaf2ff}} .gk{{background:#fdeef5}}
.smy{{display:flex;gap:20px;flex-wrap:wrap}} .smy>div{{flex:1;min-width:300px;background:#f7f9fc;border-radius:10px;padding:14px 16px;font-size:13px;line-height:1.8;border:1px solid #eceff4}}
.smy h4{{margin:0 0 6px;font-size:13px;color:#41505f}}
.warn{{background:#fff8ee;border:1px solid #f3dca8}} .warn h2{{color:#9a6a00}}
.warn ol{{margin:6px 0 0;padding-left:20px}} .warn li{{margin:8px 0;font-size:13px;line-height:1.6}}
.flag{{background:#fdecea;border:1px solid #f1b0a8;border-radius:8px;padding:10px 14px;font-size:12.5px;color:#a3382c;margin-top:12px}}
.legend{{font-size:11.5px;color:#8a94a2;margin-top:8px}}
.src{{color:#9aa4b2;font-size:11.5px;margin-top:6px}}
</style></head><body><div class="wrap">

<h1>Meta vs TikTok — 트래픽 비교 리포트</h1>
<div class="topmeta">Meta→fliptop(ワンタッチ) · TikTok→PPSU 기본컵 &nbsp;|&nbsp; 채널 분담 스왑 {SWAP_DATE} 17:07 &nbsp;|&nbsp; A 광고볼륨 {META_CMP_FROM}~{META_CMP_TO}(동일기간) · B 라쿠텐질 {RKT_FROM}~{RKT_TO} &nbsp;|&nbsp; 산출 {now} JST (틱톡이) &nbsp;|&nbsp; 환율 1 JPY=8.6 KRW</div>

<div class="card tldr"><h2>TL;DR</h2><ul>
<li><b>Meta는 TikTok의 {spend_ratio}배 예산({kw(m['spend'])} vs ≈{kw(tt_spend_krw)} KRW)을 쓰고도 클릭은 더 적었다</b> — Meta {kw(m['clicks'])} vs TT {kw(tt['clicks'])} 클릭(TT {clicks_ratio}배). CPC는 Meta가 {cpc_ratio}배({m['cpc']}원 vs ≈{tt_cpc_krw}원). 동일기간 {META_CMP_FROM}~{META_CMP_TO}.</li>
<li><b>CTR은 Meta {m['ctr']}% · TT {tt['ctr']}%로 유사</b>하나, 지표 정의가 다르다(Meta=link click / TT=destination click). 절대값 직접 등치 금지 — "클릭 볼륨/단가" 레이어로만 비교.</li>
<li><b>랜딩 질(라쿠텐 CVR)</b> — 스왑 후({META_CMP_FROM}~{int(RKT_TO[5:7])}/{int(RKT_TO[8:10])}, D+14 누적) fliptop/기본컵 방문·주문·CVR을 실측 반영. 대표님 가설(Meta=저의도 광폭) 검증은 아래 B표의 전/후 리프트로 읽는다.</li>
</ul></div>

<div class="card"><h2>A. 광고 플랫폼 측 — 볼륨 · 효율 ({META_CMP_FROM}~{META_CMP_TO} 동일기간)</h2>
<p class="desc">각 플랫폼 대시보드/DK 자체 지표. 착지 전제와 무관하게 "광고가 트래픽을 얼마나·얼마나 싸게 만들었나"를 본다. Meta=9/21 fliptop URL로 스왑된 42개 광고(PPSU Proven + Testing의 PPSU, stainless 0 교차검증). TikTok=<code>260918_traffic_IHV_PPSU&amp;Stainless</code> 동일기간 누적.</p>
<div class="kpis">
<div class="kpi tt"><div class="v">{clicks_ratio}×</div><div class="l">TT 클릭 볼륨 (vs Meta)</div></div>
<div class="kpi meta"><div class="v">{cpc_ratio}×</div><div class="l">Meta CPC 배수 (더 비쌈)</div></div>
<div class="kpi tt"><div class="v">{tt['ctr']}%</div><div class="l">TT CTR(destination)</div></div>
<div class="kpi meta"><div class="v">{m['ctr']}%</div><div class="l">Meta CTR(link)</div></div>
</div>
<table><tr><th>지표</th><th class="meta">fliptop</th><th class="tt">TikTok (PPSU)</th><th>해석</th></tr>
{partA}</table>
<div class="legend">Meta 통화=KRW, TikTok 통화=JPY. ≈KRW는 1 JPY=8.6 환산(참고). LPV: Meta {kw(m['lpv'])}건(CPLPV {m['cplpv']} KRW) / TT 대시보드 미제공.</div>
</div>

<div class="card"><h2>B. 랜딩 도달 측 — 라쿠텐 질 (RPP 차감 = gross 소셜근사)</h2>
<p class="desc">라쿠텐 상품페이지 방문·주문에서 RPP(유료검색)만 차감. 스왑 후 fliptop 페이지엔 Meta·기본컵 페이지엔 TikTok 유료가 유입되지만, <b>오가닉·직접유입·RPP 외 라쿠텐 유료는 차감 못 함 → 순수 채널 아님</b>. "스왑 전후 변화(리프트)"로만 읽어야 한다.</p>
<div class="smy">
<div><h4>스왑 전 (9/7~9/21)</h4>{scard(pre)}</div>
<div><h4>스왑 후 (9/22~{int(RKT_TO[5:7])}/{int(RKT_TO[8:10])})</h4>{scard(post)}</div>
</div>
<div class="legend" style="margin-top:10px">※ 방문엔 <b>항상 오가닉·직접유입(+RPP 외 라쿠텐 유료)이 섞여 있음 — 순수 채널 아님</b>. 유료 유입 변화: 스왑 <b>전</b> = fliptop·기본컵 <b>둘 다 Meta</b>. 스왑 <b>후</b> = fliptop에 <b>Meta</b>·기본컵에 <b>TikTok</b>(오가닉은 양쪽 계속 혼입). 그래서 페이지 라벨에 단일 채널 안 붙임 — <b>스왑 전/후 리프트(변화)로만</b> 해석.</div>
<table style="margin-top:8px"><tr><th rowspan="2">날짜</th><th class="gf" colspan="3">fliptop</th><th class="gk" colspan="3">기본컵 PPSU</th></tr>
<tr><th class="gf">방문</th><th class="gf">주문</th><th class="gf">CVR%</th><th class="gk">방문</th><th class="gk">주문</th><th class="gk">CVR%</th></tr>
{''.join(rows_rkt)}</table>
<div class="legend">방문=アクセス人数(visitAll)−RPP클릭, 주문=orderCountAll−RPP주문. 스왑 직후 fliptop 방문 급증({kw(f21)}→{kw(f22)}, 非RPP)=Meta 트래픽의 fliptop 착지 전환 신호. 주문 0 다수=D+1 지연·저표본.</div>
</div>

<div class="card warn"><h2>⚠️ 한계 · 읽는 법</h2><ol>
<li><b>gross 소셜근사</b> — 라쿠텐 방문에서 RPP만 뺐다. 오가닉 검색·직접유입·내부 브라우즈가 남아 "순수 채널 트래픽"이 아니다. 실제 RPP는 방문의 극히 일부(fliptop 日 5~42·기본컵 20~95)라 잔차가 크다 → 절대값 아닌 <b>리프트(스왑 전후 변화)</b>로 해석.</li>
<li><b>상품 confound</b> — fliptop(¥4,200·12m~) ≠ 기본컵(¥3,190·6m~). 가격·연령대가 달라 CVR 직접 등치 금지. 각 페이지를 자기 베이스라인과 비교.</li>
</ol></div>

<div class="src">소스: Meta=DataKeeper meta_ads_daily(OUTCOME_TRAFFIC·JP·stainless제외) · TikTok=Ads Manager 수동 스크랩(.tmp/tiktok_probe→tt_ads_summary.json, {tt['period_from']}~{tt['period_to']}) · 라쿠텐=RMS get-item-list − RPP商品別 리포트 · 빌더 tools/build_meta_tt_traffic_report.py · 실험설계 project_meta_tiktok_channel_cvr_experiment</div>
</div></body></html>"""
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    meta_daily, _n_swap = fetch_meta()
    rkt = load_rakuten()
    tt = json.loads((EXP / "tt_ads_summary.json").read_text(encoding="utf-8"))

    html = build_html(meta_daily, rkt, tt)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "meta_tt_traffic_compare_202609.html"
    out.write_text(html, encoding="utf-8")
    print(f"[OK] report: {out}")
    if args.open:
        import webbrowser
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
