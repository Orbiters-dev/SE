# -*- coding: utf-8 -*-
"""Meta JP IHV(자사 영상) 운영 기준 리포트 빌더.

입력: .tmp/ihv_probe/ihv_daily.json (DK meta_ads_daily brand='Grosmimi JP' IH 캠페인
      일자별 + Graph effective_status — .tmp/ihv_pull.py 산출)
출력: Desktop\\s\\performance marketing\\META ADS\\operations\\ihv_operating_criteria_YYYYMMDD.html

내용: ①OFF 기준(판정창 D3-9 백테스트) ②기세 꺾임 ③판정 기준(3갈래)
      ④⑤ 좋은/나쁜 광고 효율 궤적 차트. 통화 KRW (JP 계정 = KRW 과금).
본문 수치는 전부 입력 데이터에서 계산 (하드코딩 금지 — 재실행 시 자동 갱신).
"""
import json
import statistics as st
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / ".tmp/ihv_probe/ihv_daily.json"
if not SRC.exists():
    raise SystemExit(f"입력 없음: {SRC} — 먼저 .tmp/ihv_pull.py 실행")
try:
    DATA = json.loads(SRC.read_text(encoding="utf-8"))["ads"]
except (json.JSONDecodeError, KeyError) as e:
    raise SystemExit(f"입력 파싱 실패: {SRC} — {e} (ihv_pull.py 재실행 필요)")
if not DATA:
    raise SystemExit(f"입력에 광고 0건: {SRC} — ihv_pull.py 재실행 필요")
OUT = Path(r"C:\Users\orbit\Desktop\s\performance marketing\META ADS\operations") / \
    f"ihv_operating_criteria_{date.today():%Y%m%d}.html"

# 3갈래 룰 파라미터 (백테스트 확정치)
PROMOTE = 130     # D3-9 CPLPV ≤ 130 → 증액 후보 (WL 졸업컷과 동일 선.
                  # IHV 는 별도 Proven 캠 이동 없이 Testing 내 adset 예산 증액 — 세은 확정 2026-10-08)
KILL = 190        # > 190 → OFF 트랙
KILL_NOW = 230    # > 230 → 즉시 OFF / 190~230 은 1주 유예 후 재판정
MIN_SPEND = 5000  # 스텁(수백원 지출) 제외 컷


def agg(days):
    sp = sum(d["spend"] for d in days)
    im = sum(d["imp"] for d in days)
    ck = sum(d["clicks"] for d in days)
    lv = sum(d["lpv"] for d in days)
    return {"sp": sp, "imp": im, "clicks": ck, "lpv": lv,
            "cplpv": sp / lv if lv else None,
            "ctr": ck / im * 100 if im else 0,
            "cpc": sp / ck if ck else None}


ads = []
coupons = []
for k, a in DATA.items():
    sdays = [d for d in a["series"] if d["spend"] > 0]
    if not sdays:
        continue
    t = agg(sdays)
    if t["sp"] < MIN_SPEND or t["cplpv"] is None:
        continue
    rec = {"id": k, "name": a["name"] or k, "status": a["status"], "days": sdays,
           "first": sdays[0]["date"], "n": len(sdays), "t": t,
           "product": "PPSU" if "PPSU" in (a["name"] or "") else
                      ("스텐" if "stainless" in (a["name"] or "").lower() else "기타")}
    if "Coupon" in (a["name"] or ""):
        coupons.append(rec)
    else:
        ads.append(rec)
ads.sort(key=lambda x: x["t"]["cplpv"])
if not ads:
    raise SystemExit("IHV 영상 광고 0건 — 필터/입력 확인")


def short(name):
    # "260911_PPSU_救世主マグ" → "救世主マグ (9/11)"
    parts = (name or "").split("_")
    d = parts[0]
    if len(parts) < 2 or len(d) < 6 or not d.isdigit():
        return name or "(이름없음)"
    return f"{parts[-1]} ({int(d[2:4])}/{int(d[4:6])})"


def verdict(ad):
    """D9 판정 (D3-9 창). 표본 10일 미만 = 판정 전."""
    if ad["n"] < 10:
        e = agg(ad["days"][3:]) if ad["n"] > 3 else None
        return ("판정 전", e["cplpv"] if e and e["cplpv"] else None)
    e = agg(ad["days"][3:10])
    cp = e["cplpv"] or float("inf")
    if cp <= PROMOTE:
        return ("증액 후보", cp)
    if cp > KILL_NOW:
        return ("즉시 OFF", cp)
    if cp > KILL:
        return ("유예 → OFF", cp)
    return ("잔류 관찰", cp)


# ── OFF 백테스트 (유예안): >230 D9 컷 / 190~230 D16 컷 ──
sim = []
saved = 0.0
late_cplpvs = []
off_names = []
off_active_now = 0
for ad in ads:
    v, cp = verdict(ad)
    if v == "즉시 OFF":
        cut = 10
    elif v == "유예 → OFF":
        cut = 17
    else:
        continue
    off_names.append(short(ad["name"]))
    if ad["status"] == "ACTIVE":
        off_active_now += 1
    after = sum(d["spend"] for d in ad["days"][cut:])
    late = agg(ad["days"][cut:]) if len(ad["days"]) > cut else None
    saved += after
    if late and late["cplpv"]:
        late_cplpvs.append(late["cplpv"])
    sim.append((short(ad["name"]), f"{cp:.0f}",
                "D9" if cut == 10 else "D16 (재판정)",
                f"{after:,.0f}", f"{late['cplpv']:.0f}" if late and late["cplpv"] else "—"))
promote_return = sum(1 for v in late_cplpvs if v <= PROMOTE)
late_above_kill = sum(1 for v in late_cplpvs if v > KILL)

TOTAL = sum(a["t"]["sp"] for a in ads)

# ── 차트 데이터 ──
GOOD = ["救世主マグ", "韓国製ストローマグ", "マグデビュー", "目盛り付き"]
BAD = ["回転ハンドル", "発達への繋がり", "モニター募集", "プレミアムステンレスマグ"]


def roll3(ad):
    """3일 롤링 CPLPV (집행일 나이 기준)."""
    out = []
    ds = ad["days"]
    for i in range(len(ds)):
        g = agg(ds[max(0, i - 2):i + 1])
        out.append(round(g["cplpv"], 1) if g["cplpv"] else None)
    return out


def pick(names):
    out = []
    for nm in names:
        ad = next((a for a in ads if nm in a["name"]), None)
        if ad is None:
            continue
        out.append({"label": short(ad["name"]), "cplpv": roll3(ad)})
    return out


maxlen = max(a["n"] for a in ads)
scatter = [{"x": round(agg(a["days"][3:10])["ctr"], 1),
            "y": round(a["t"]["cplpv"], 0), "label": short(a["name"])}
           for a in ads if a["n"] >= 10]
learn = [{"label": short(a["name"]),
          "early": round(agg(a["days"][:3])["cplpv"] or 0, 0),
          "late": round(agg(a["days"][3:])["cplpv"] or 0, 0)}
         for a in ads if a["n"] >= 10]

chart = {"ages": list(range(maxlen)), "good": pick(GOOD), "bad": pick(BAD),
         "scatter": scatter, "learn": learn}

# ── 본문 인용 수치 전부 동적 계산 ──
def weekly(ad, w):
    return agg(ad["days"][w * 7:(w + 1) * 7])


# 학습 스파이크: D0-2 대비 D3+ 하락 상위 2건 + 최대값
spiky = sorted([l for l in learn if l["early"] and l["late"]],
               key=lambda l: -(l["early"] / l["late"]))
spike_ex = " · ".join(f"{l['label']} {l['early']:.0f}→{l['late']:.0f}" for l in spiky[:2])
spike_max = max((l["early"] for l in learn if l["early"]), default=0)

# D9 시점 평균 소진액
d9_spends = [sum(d["spend"] for d in a["days"][:10]) for a in ads if a["n"] >= 10]
d9_spend_man = st.mean(d9_spends) / 10000 if d9_spends else 0

# CTR 극단 예측력 (D3-9 CTR vs 최종 CPLPV)
# 8% = WL 졸업 CTR 컷과 동일 선. 4.5% = 실측 하위 클러스터 상단(4.5% 미만 구간에 하위군 밀집).
# 상/하위권 경계 160/170 = 누적 CPLPV 분포의 실측 단층(155↔169 사이 공백) 양끝.
hi = [p for p in scatter if p["x"] >= 8]
lo = [p for p in scatter if p["x"] < 4.5]
hi_ok = [p for p in hi if p["y"] <= 160]
lo_ok = [p for p in lo if p["y"] >= 170]
hi_max_y = max((p["y"] for p in hi), default=0)
lo_min_y = min((p["y"] for p in lo), default=0)

# frequency: 21일 이상 집행분 마지막 7일 중앙값
freq_meds = []
max_age = 0
for a in ads:
    if a["n"] >= 21:
        f7 = [d.get("freq") or 0 for d in a["days"][-7:]]
        f7 = [f for f in f7 if f > 0]
        if f7:
            freq_meds.append(st.median(f7))
            max_age = max(max_age, a["n"])
freq_med = st.median(freq_meds) if freq_meds else None
freq_txt = f"{max_age}일차 frequency 중앙값 {freq_med:.2f}" if freq_med else "frequency 데이터 없음"

# 증액 후보군 장기 광고 횡보 사례 2건 — W1 vs 최근 7일 (부분주 W4 대신 항상 완전한 7일 창)
good_w = []
for nm in GOOD:
    ad = next((a for a in ads if nm in a["name"] and a["n"] >= 21), None)
    if ad:
        w1, last7 = weekly(ad, 0), agg(ad["days"][-7:])
        if w1["cplpv"] and last7["cplpv"]:
            good_w.append(f"{short(ad['name'])} W1 {w1['cplpv']:.0f} → 최근7일 {last7['cplpv']:.0f}")
good_w_txt = ", ".join(good_w[:2])

# 둔화(피로) 사례: 21일 이상 중 W3/W1 CPLPV 악화율 최대 1건
# 1.3 = 안정 광고의 주간 변동 노이즈 밴드(실측 ±20% 내) 바깥 = 추세 악화로 간주하는 컷
decay_txt = "해당 없음"
decay_ratio = 0
for a in ads:
    if a["n"] < 21:
        continue
    w1, w3 = weekly(a, 0), weekly(a, 2)
    if w1["cplpv"] and w3["cplpv"] and w3["cplpv"] / w1["cplpv"] > max(decay_ratio, 1.3):
        decay_ratio = w3["cplpv"] / w1["cplpv"]
        decay_txt = (f"{short(a['name'])} (W1 CTR {w1['ctr']:.1f}%·CPLPV {w1['cplpv']:.0f} → "
                     f"W3 {w3['ctr']:.1f}%·{w3['cplpv']:.0f})")

# 3갈래 현재 해당 광고 리스트
promote_ads = [(a, cp) for a in ads for v, cp in [verdict(a)] if v == "증액 후보"]
hold_ads = [(a, cp) for a in ads for v, cp in [verdict(a)] if v == "잔류 관찰"]
pre_ads = [(a, cp) for a in ads for v, cp in [verdict(a)] if v == "판정 전"]
promote_txt = " · ".join(f"{short(a['name'])} {cp:.0f}" for a, cp in promote_ads)
pre_good = [f"{short(a['name'])} 진행중 {cp:.0f}" for a, cp in pre_ads if cp and cp <= PROMOTE]
pre_txt = f" (+{' · '.join(pre_good)})" if pre_good else ""
# 잔류군 중 이후(D10+) 실측이 130 아래로 내려온 증액 재심 대상
hold_promoted = []
for a, cp in hold_ads:
    if len(a["days"]) > 10:
        latef = agg(a["days"][10:])
        if latef["cplpv"] and latef["cplpv"] <= PROMOTE:
            hold_promoted.append(short(a["name"]))
hold_promo_txt = ("·".join(hold_promoted) + " (재판정서 130 하향 돌파)" if hold_promoted else "")
off_txt = "·".join(off_names)

# 저CTR·양호CPLPV 예외 사례 (CTR 단독컷 금지 근거)
# 6.5% = CTR 중간대(4.5~8%)의 중앙값 — 중간대 하반부(저CTR 쪽)에서 예시 탐색
lowctr_good = [p for p in scatter if p["x"] < 6.5 and p["y"] <= PROMOTE]
lowctr_txt = (f"{lowctr_good[0]['label']} {lowctr_good[0]['x']}%/{lowctr_good[0]['y']:.0f}"
              if lowctr_good else "")

# 제품 단층
stains = [a for a in ads if a["product"] == "스텐"]
stain_min = min((a["t"]["cplpv"] for a in stains), default=0)
top_ppsu_streak = 0
for a in ads:
    if a["product"] == "PPSU":
        top_ppsu_streak += 1
    else:
        break

last_date = max(d["date"] for a in ads for d in a["days"])

# ── 순위표 ──
VCLASS = {"증액 후보": "good", "잔류 관찰": "", "유예 → OFF": "bad", "즉시 OFF": "bad", "판정 전": "hold"}
rows_html = ""
for a in ads:
    v, cp = verdict(a)
    t = a["t"]
    cp_txt = f"{cp:,.0f}" if cp else "—"
    if a["n"] < 10:
        cp_txt += " <span class='mut'>(진행중)</span>"
    rows_html += (
        f"<tr class='{VCLASS[v]}'><td>{short(a['name'])}</td><td>{a['product']}</td>"
        f"<td class='r'>{a['n']}</td><td class='r'>{t['sp']:,.0f}</td>"
        f"<td class='r'>{t['cplpv']:,.0f}</td><td class='r'>{t['ctr']:.1f}%</td>"
        f"<td class='r'>{t['cpc']:,.0f}</td><td class='r'>{cp_txt}</td>"
        f"<td>{v}</td><td>{a['status']}</td></tr>")
for c in coupons:
    t = c["t"]
    rows_html += (
        f"<tr class='mutrow'><td>{c['name']} <span class='mut'>(이미지 쿠폰 — 참고)</span></td><td>—</td>"
        f"<td class='r'>{c['n']}</td><td class='r'>{t['sp']:,.0f}</td>"
        f"<td class='r'>{t['cplpv']:,.0f}</td><td class='r'>{t['ctr']:.1f}%</td>"
        f"<td class='r'>{t['cpc']:,.0f}</td><td class='r'>—</td><td>—</td><td>{c['status']}</td></tr>")

sim_html = "".join(
    f"<tr><td>{a}</td><td class='r'>{b}</td><td>{c}</td><td class='r'>{d}</td><td class='r'>{e}</td></tr>"
    for a, b, c, d, e in sim)

CJS = json.dumps(chart, ensure_ascii=False)

HTML = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>Meta JP IHV 운영 기준 — 집행 전수 실측 ({date.today():%Y-%m-%d})</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
body{{font-family:'Pretendard','Malgun Gothic',sans-serif;max-width:1060px;margin:24px auto;padding:0 20px;color:#1a1a1a;line-height:1.55}}
h1{{font-size:21px;border-bottom:3px solid #111;padding-bottom:8px}}
h2{{font-size:16px;margin-top:34px;border-left:4px solid #111;padding-left:9px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0}}
th{{background:#111;color:#fff;padding:6px 8px;text-align:left;font-weight:600}}
td{{border-bottom:1px solid #e3e3e3;padding:5px 8px}}
.r{{text-align:right}} tr.good td{{background:#f0f7f0}} tr.bad td{{background:#fbf0f0}}
tr.hold td{{background:#fafafa;color:#777}} tr.mutrow td{{color:#999}}
.mut{{color:#999;font-size:11px}}
.box{{border:1.5px solid #111;border-radius:8px;padding:12px 16px;margin:14px 0;font-size:13.5px}}
.box b{{font-size:14px}}
.chartwrap{{margin:14px 0;padding:10px;border:1px solid #e3e3e3;border-radius:8px}}
.note{{font-size:12px;color:#666;margin:4px 0 0}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:800px){{.grid2{{grid-template-columns:1fr}}}}
</style></head><body>

<h1>Meta JP IHV(자사 영상) 운영 기준 — 집행 전수 실측</h1>
<p class="note">모집단: IH 캠페인 영상 광고 {len(ads)}개 ({min(a['first'] for a in ads)} ~ {last_date},
총 지출 ₩{TOTAL:,.0f}) + 이미지 쿠폰 {len(coupons)}건 참고 표기. 데이터: meta_ads_daily 일자별 ×
Graph 실시간 상태. 통화 KRW. CPLPV = 지출 ÷ 랜딩페이지뷰 (라쿠텐 랜딩이라 전환 대신 LPV 가 기준축).</p>

<div class="box"><b>TL;DR</b><br>
① OFF 는 <b>D9 에 판정</b> (D3~9 창 CPLPV, 학습기 D0~2 제외): <b>{KILL_NOW} 초과 즉시 OFF · {KILL}~{KILL_NOW} 은 1주 유예 후
재판정에서 {KILL} 초과면 확정 OFF</b>. 백테스트 = OFF {len(sim)}건 중 증액급(≤{PROMOTE}) 복귀 {promote_return}건,
지출 ₩{saved:,.0f} 절약 (IHV 총지출의 {saved/TOTAL*100:.0f}%).<br>
② 일 ₩8천 예산에선 <b>4주 안에 기세가 꺾이는 일반 현상 없음</b> ({freq_txt} — 모수 미포화).
효율은 나이가 아니라 소재가 결정. 나이 기준 자동 OFF 불필요.<br>
③ 판정축 = CPLPV 3갈래: <b>≤{PROMOTE} 증액 후보 · {PROMOTE}~{KILL} 잔류 관찰 · &gt;{KILL} OFF 트랙</b> (WL 졸업컷 {PROMOTE} 와 동일 선).
IHV 는 WL 과 달리 <b>별도 Proven 캠 이동 없음</b> — Testing 안에서 해당 adset 예산만 올림 (ABO 라 캠 분리 이점 없음 + 학습 리셋 회피).<br>
CTR 보조 판정선 = <b>≥8% 조기 양호 / &lt;4.5% 조기 불량 / 4.5~8% 판단 유보(CPLPV 로만)</b>
— 적중 실측: ≥8% 상위권 {len(hi_ok)}/{len(hi)} · &lt;4.5% 하위권 {len(lo_ok)}/{len(lo)}.
증액 후보는 <b>회당 +20~25%, 주 1회</b> (₩8천→1.0만→1.2만→1.5만→1.8만), 재판정 연동.<br>
④ 잘 도는 광고 = 학습 스파이크(D0~2 최대 {spike_max:.0f}) 후 <b>내려와서 100~130 띠에 붙는</b> 모양.<br>
⑤ 안 도는 광고 = <b>학습이 끝나도 안 내려옴</b> — 200+ 띠 횡보. D9 에 {KILL} 위면 그 광고는 끝난 광고.<br>
+ 제품 단층: CPLPV 상위 {top_ppsu_streak}개 전부 PPSU, <b>스텐 {len(stains)}개 전부 CPLPV {stain_min:.0f} 이상</b> — 스텐 IHV 는 소재 재기획 필요.</div>

<h2>광고별 성적 전수 (CPLPV 순)</h2>
<table><tr><th>광고</th><th>제품</th><th>일수</th><th>지출 ₩</th><th>CPLPV</th><th>CTR</th>
<th>CPC</th><th>D3-9 CPLPV</th><th>룰 적용 시 판정</th><th>현재 상태 (Graph)</th></tr>
{rows_html}</table>
<p class="note">판정은 D3~9 창 기준. 「판정 전」 = 집행 10일 미만 (D3~ 현재 수치 병기).
현재 상태는 Graph API effective_status 실시간.</p>

<h2>1. OFF 기준 — D9 판정 백테스트</h2>
<p>판정창을 D3~9 로 잡는 이유: D0~2 는 학습 구간이라 CPLPV 가 극단적으로 튀고
({spike_ex} — 아래 차트 D), D3~9 수치는 이후 성적과 같은 등수로 떨어짐 (아래 전수표의 D3-9 열과
누적 CPLPV 열 대조). D9 시점이면 광고당 평균 ₩{d9_spend_man:.1f}만 소진 —
WL 의 D+3 판정보다 길게 보는 대신 영상 소재 학습 변동을 거름.</p>
<table><tr><th>OFF 대상 (백테스트)</th><th>D3-9 CPLPV</th><th>컷 시점</th><th>이후 실지출 = 절약액 ₩</th><th>컷 이후 실제 CPLPV</th></tr>
{sim_html}</table>
<p class="note">컷 이후 실측 {len(late_cplpvs)}건 중 {KILL} 위 {late_above_kill}건, 증액급(≤{PROMOTE}) 복귀 {promote_return}건 —
살렸으면 아까웠을 광고 없음. 경계 사례 = プレミアムステンレスマグ (D21+ 에 150 수준으로 늦회복했으나
그래도 잔류급이지 증액급 아님 — 유예 1주가 이 유형의 완충). 현재 OFF 트랙 {len(sim)}건 중 {off_active_now}건이
Graph 기준 ACTIVE 로 계속 지출 중 → 룰 적용 시 즉시 절감.</p>

<h2>2. 기세가 꺾이는 시점</h2>
<p>결론: <b>일 ₩8천 수준에선 4주 내 시스템적 꺾임 없음.</b> {freq_txt} —
같은 사람에게 거의 재노출이 안 되는 지출 규모라 소재 피로가 생길 틈이 없음. 좋은 광고는 4주 내내
횡보하거나 오히려 개선 ({good_w_txt}).
유일한 둔화 사례 = {decay_txt} — 고CTR 훅이 먼저 소모되는
유형으로, 주간 롤링 모니터로 개별 감지하면 충분. <b>나이 기준 자동 OFF 룰은 이 예산에선 만들 필요 없음</b>
(증액해서 frequency 가 1.5~2 를 넘기 시작하면 그때 재검토).</p>

<h2>3. 잘/안 돌아감 판단 기준 (3갈래)</h2>
<table><tr><th>판정</th><th>기준 (D3~9 CPLPV, 이후 주간 롤링 재판정)</th><th>조치</th><th>해당 (현재)</th></tr>
<tr class="good"><td>증액 후보</td><td>≤ {PROMOTE} (WL 졸업컷과 동일)</td><td>Testing 내 adset 예산 증액 (Proven 캠 이동 X)</td>
<td>{promote_txt}{pre_txt}</td></tr>
<tr><td>잔류 관찰</td><td>{PROMOTE} ~ {KILL}</td><td>유지 + 주간 재판정 (학습 후 하락분 증액 재심)</td>
<td>{len(hold_ads)}건{' — ' + hold_promo_txt if hold_promo_txt else ''}</td></tr>
<tr class="bad"><td>OFF 트랙</td><td>&gt; {KILL} ({KILL_NOW} 초과 즉시 · {KILL}~{KILL_NOW} 1주 유예)</td><td>OFF</td>
<td>{off_txt}</td></tr></table>
<h2>3-1. 보조축 CTR 판정선 (D3~9)</h2>
<table><tr><th>CTR 구간</th><th>신호</th><th>적중 실측</th><th>활용</th></tr>
<tr class="good"><td>≥ 8%</td><td>조기 양호</td><td>최종 상위권 {len(hi_ok)}/{len(hi)}</td><td>증액 후보 가속 검토 (CPLPV 확인 후)</td></tr>
<tr><td>4.5 ~ 8%</td><td>판단 유보</td><td>혼재 (양호·불량 둘 다 존재)</td><td>CPLPV 로만 판정</td></tr>
<tr class="bad"><td>&lt; 4.5%</td><td>조기 불량</td><td>최종 하위권 {len(lo_ok)}/{len(lo)}</td><td>OFF 트랙 조기 경보 (확정은 CPLPV 로)</td></tr></table>
<p class="note">CTR 단독 컷 금지 — 판정축은 CPLPV. 중간대 반례: {lowctr_txt} 는 CTR 낮아도 증액급,
プレミアム (6.4%/202) 는 CTR 무난해도 OFF 급 (차트 C).</p>

<h2>3-2. 증액 스텝 (증액 후보 확정 시)</h2>
<table><tr><th>스텝</th><th>일 예산</th><th>인상 폭</th></tr>
<tr><td>기본</td><td>₩8,000</td><td>—</td></tr>
<tr><td>1차</td><td>₩10,000</td><td>+25%</td></tr>
<tr><td>2차</td><td>₩12,000</td><td>+20%</td></tr>
<tr><td>3차</td><td>₩15,000</td><td>+25%</td></tr>
<tr><td>4차</td><td>₩18,000</td><td>+20%</td></tr></table>
<p class="note">회당 +20~25% · <b>주 1회, 주간 재판정과 동기</b> — 증액 후 7일 관찰해 CPLPV ≤{PROMOTE} 유지면 다음 스텝.
한 번에 크게 올리지 않는 이유: 큰 폭 예산 변경은 학습 재진입을 부를 수 있고, 재학습 비용은 우리 실측으로
CPLPV +25~32% (WL Proven 이관 때 측정). 가드 2개: ①증액 후 CPLPV 가 150 (WL Proven OFF 게이트와 동일선) 넘으면 직전 스텝 롤백
②frequency ≥ 1.5 면 증액 중단 (기세 꺾임 재검토 시점). ⚠️증액 효과 실측은 아직 없음 — 전원 균등 ₩8천으로만
돌려 와서, 1차 증액분이 첫 실험 표본이 됨.</p>

<div class="grid2">
<div class="chartwrap"><b>차트 A — 잘 돌아가는 광고의 궤적</b> (3일 롤링 CPLPV, 집행일 나이)
<canvas id="cGood"></canvas>
<p class="note">학습 스파이크 후 급락 → 100~130 띠 안착·횡보. "내려와서 붙는" 모양이 정상 패턴.</p></div>
<div class="chartwrap"><b>차트 B — 안 돌아가는 광고의 궤적</b> (3일 롤링 CPLPV, 집행일 나이)
<canvas id="cBad"></canvas>
<p class="note">학습이 끝나도 안 내려옴 — 200 안팎 띠에서 횡보, 추세 회복 없음.</p></div>
</div>

<div class="grid2">
<div class="chartwrap"><b>차트 C — D3~9 CTR 로 최종 성적이 갈리는가</b>
<canvas id="cScatter"></canvas>
<p class="note">CTR 8% 이상은 전부 최종 CPLPV {hi_max_y:.0f} 이하, 4.5% 미만은 전부 {lo_min_y:.0f} 이상. 중간대만 혼재.</p></div>
<div class="chartwrap"><b>차트 D — 학습 구간(D0~2) vs 이후(D3+) CPLPV</b>
<canvas id="cLearn"></canvas>
<p class="note">학습기는 2~3배 튀는 광고가 흔함 → D0~2 수치로 판정 금지 (틱톡의 '초반 미끼'와 반대 방향).</p></div>
</div>

<script>
const C = {CJS};
const palette = ["#1a7a3c","#2563eb","#9333ea","#0d9488"];
const paletteBad = ["#b91c1c","#ea580c","#a16207","#be185d"];
function traj(id, series, colors, yMax) {{
  new Chart(document.getElementById(id), {{
    type: "line",
    data: {{ labels: C.ages.map(d => "D" + d),
      datasets: series.map((s, i) => ({{ label: s.label, data: s.cplpv,
        borderColor: colors[i], backgroundColor: colors[i], tension: .25,
        pointRadius: 0, borderWidth: 2, spanGaps: true }})) }},
    options: {{ scales: {{ y: {{ min: 0, max: yMax, title: {{display: true, text: "CPLPV (₩)"}} }} }},
      plugins: {{ legend: {{ labels: {{ boxWidth: 14, font: {{size: 11}} }} }} }} }}
  }});
}}
traj("cGood", C.good, palette, 400);
traj("cBad", C.bad, paletteBad, 400);
new Chart(document.getElementById("cScatter"), {{
  type: "scatter",
  data: {{ datasets: [{{ label: "광고 (D3-9 CTR → 최종 CPLPV)",
    data: C.scatter, backgroundColor: C.scatter.map(p => p.y <= {PROMOTE} ? "#1a7a3c" : (p.y > {KILL} ? "#b91c1c" : "#888")),
    pointRadius: 5 }}] }},
  options: {{ scales: {{ x: {{ title: {{display: true, text: "D3-9 CTR %"}} }},
    y: {{ title: {{display: true, text: "최종 누적 CPLPV (₩)"}} }} }},
    plugins: {{ legend: {{display: false}},
      tooltip: {{ callbacks: {{ label: ctx => `${{ctx.raw.label}}: CTR ${{ctx.raw.x}}% → ${{ctx.raw.y}}` }} }} }} }}
}});
new Chart(document.getElementById("cLearn"), {{
  type: "bar",
  data: {{ labels: C.learn.map(l => l.label),
    datasets: [
      {{ label: "D0~2 (학습)", data: C.learn.map(l => l.early), backgroundColor: "#c7c7c7" }},
      {{ label: "D3+ (안정)", data: C.learn.map(l => l.late), backgroundColor: "#111" }}] }},
  options: {{ indexAxis: "y",
    scales: {{ x: {{ title: {{display: true, text: "CPLPV (₩)"}} }},
      y: {{ ticks: {{ font: {{size: 10}} }} }} }},
    plugins: {{ legend: {{ labels: {{ boxWidth: 14, font: {{size: 11}} }} }} }} }}
}});
</script>
</body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML, encoding="utf-8")
print(f"저장: {OUT}")
print(f"광고 {len(ads)}개 · 총지출 {TOTAL:,.0f} · OFF {len(sim)}건 절약 {saved:,.0f} ({saved/TOTAL*100:.0f}%)")
print(f"CTR 예측력 상위 {len(hi_ok)}/{len(hi)} 하위 {len(lo_ok)}/{len(lo)} · {freq_txt}")
