# -*- coding: utf-8 -*-
"""채널별(Meta=fliptop / TikTok=기본컵) 일별 방문·주문·CVR 수집 + 링크 변동 전후 리포트.

실험 설계: memory/project_meta_tiktok_channel_cvr_experiment.md
- Meta 광고 전량 → fliptop URL (grosmimi_ppsu_onetouch_*)
- TikTok 광고 전량 → 기본컵 URL (grosmimi_ppsu_strawcup300 / _ss)
스왑 완료 = 2026-09-21 17:07.

데이터원: RMS get-item-list API (period=daily 는 기간 합산이라 하루씩 startDate=endDate 반복 호출).
  salesFormula.visitAll(アクセス人数) / orderCountAll(주문수) / unitsAll(판매개수) / cvrAll(전환율%)
  로그인 1회(do_login) 후 page.request 재사용.

PPC(RPP) 차감: RPP 아이템 fliptop=10000002 / 기본컵=10000001 의 일별 방문·주문을 --rpp-json 으로
  주면 분자/분모에서 차감(=순수 소셜 근사). 미지정 시 gross(PPC 미차감) 로 산출하고 리포트에 명시. (삐삐 영역)

CLI:
  python tools/channel_cvr_daily.py --date-from 2026-09-07 --date-to 2026-09-23
  python tools/channel_cvr_daily.py --date-from 2026-09-07 --date-to 2026-09-23 --open
"""
import argparse
import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from rms_review_playwright import do_login  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / ".tmp" / "channel_cvr_experiment"
API = "https://datatool.rms.rakuten.co.jp/access/item/get-item-list/"
SWAP_DATE = "2026-09-21"          # 스왑 당일(17:07) — post 는 다음날부터
POST_START = (datetime.strptime(SWAP_DATE, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
GROUPS = {                        # 표시명 → mngNumber 매칭 규칙
    "fliptop": lambda m: "onetouch" in m,                                   # Meta 타겟
    "kihon":   lambda m: ("strawcup300" in m or "strawcup_ss" in m) and "stainless" not in m,  # TikTok 타겟
}
LABEL = {"fliptop": "fliptop (Meta 타겟)", "kihon": "기본컵 PPSU (TikTok 타겟)"}


def _daterange(d0: str, d1: str):
    a = datetime.strptime(d0, "%Y-%m-%d")
    b = datetime.strptime(d1, "%Y-%m-%d")
    while a <= b:
        yield a.strftime("%Y-%m-%d")
        a += timedelta(days=1)


def _group_of(mng: str):
    m = (mng or "").lower()
    for g, fn in GROUPS.items():
        if fn(m):
            return g
    return None


def fetch_daily(date_from: str, date_to: str, headless: bool = True) -> dict:
    """{date: {group: {visit, orders, units}}}  (로그인 1회 후 하루씩 호출)."""
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=headless)
        p = b.new_page()
        do_login(p)
        for day in _daterange(date_from, date_to):
            ymd = day.replace("-", "")
            url = f"{API}?period=daily&device=all&startDate={ymd}&endDate={ymd}"
            r = p.request.get(url, timeout=40000)
            if r.status != 200:
                out[day] = {"_error": r.status}
                continue
            rows = (r.json() or {}).get("data", [])
            agg = {g: {"visit": 0, "orders": 0, "units": 0} for g in GROUPS}
            for x in rows:
                g = _group_of((x.get("item") or {}).get("mngNumber"))
                if not g:
                    continue
                sf = x.get("salesFormula") or {}
                agg[g]["visit"] += sf.get("visitAll", 0) or 0
                agg[g]["orders"] += sf.get("orderCountAll", 0) or 0
                agg[g]["units"] += sf.get("unitsAll", 0) or 0
            out[day] = agg
        b.close()
    return out


def apply_rpp(daily: dict, rpp_json: str):
    """RPP 일별 차감. rpp_json = {date: {fliptop:{visit,orders}, kihon:{...}}}."""
    rpp = json.loads(Path(rpp_json).read_text(encoding="utf-8"))
    for day, groups in daily.items():
        for g in GROUPS:
            sub = (rpp.get(day, {}) or {}).get(g, {})
            if not sub or "_error" in groups:
                continue
            groups[g]["visit"] = max(0, groups[g]["visit"] - sub.get("visit", 0))
            groups[g]["orders"] = max(0, groups[g]["orders"] - sub.get("orders", 0))
    return daily


def _cvr(o, v):
    return round(o / v * 100, 3) if v else 0.0


def summarize(daily: dict):
    """스왑 전/후 평균 방문·CVR."""
    pre = {g: {"visit": 0, "orders": 0, "days": 0} for g in GROUPS}
    post = {g: {"visit": 0, "orders": 0, "days": 0} for g in GROUPS}
    for day, groups in sorted(daily.items()):
        if "_error" in groups:
            continue
        bucket = post if day >= "2026-09-22" else pre
        for g in GROUPS:
            bucket[g]["visit"] += groups[g]["visit"]
            bucket[g]["orders"] += groups[g]["orders"]
            bucket[g]["days"] += 1
    def pack(b):
        return {g: {"visit_avg": round(b[g]["visit"] / b[g]["days"], 1) if b[g]["days"] else 0,
                    "orders": b[g]["orders"],
                    "cvr": _cvr(b[g]["orders"], b[g]["visit"]),
                    "days": b[g]["days"]} for g in GROUPS}
    return {"pre": pack(pre), "post": pack(post)}


def build_html(daily: dict, ppc_excluded: bool, out_path: Path):
    smy = summarize(daily)
    tag = "PPC(RPP) 차감 = 순수 소셜 근사" if ppc_excluded else "PPC 미차감(gross) — RPP 차감분 대기(삐삐)"
    badge = "b-ok" if ppc_excluded else "b-wait"
    rows_html = []
    for day in sorted(daily):
        g = daily[day]
        if "_error" in g:
            rows_html.append(f'<tr><td class="day">{day[5:]}</td><td colspan="6" class="zero">err {g["_error"]}</td></tr>')
            continue
        f, k = g["fliptop"], g["kihon"]
        cls = ' class="swap-row"' if day == SWAP_DATE else (' class="after"' if day >= "2026-09-22" else "")
        mark = " ⟵ 스왑(17:07)" if day == SWAP_DATE else ""
        def z(n):
            return f'<span class="zero">{n}</span>' if n == 0 else str(n)
        rows_html.append(
            f'<tr{cls}><td class="day">{day[5:]}{mark}</td>'
            f'<td>{f["visit"]:,}</td><td>{z(f["orders"])}</td><td>{_cvr(f["orders"],f["visit"])}</td>'
            f'<td>{k["visit"]:,}</td><td>{z(k["orders"])}</td><td>{_cvr(k["orders"],k["visit"])}</td></tr>')
    def scard(period, s):
        return "".join(
            f'<div><span>{LABEL[g]}</span><b>{s[g]["visit_avg"]:,}</b>방문/일 · 주문 {s[g]["orders"]} · CVR {s[g]["cvr"]}%</div>'
            for g in GROUPS)
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meta/TikTok 채널 CVR — 링크 변동 전후 (일별)</title><style>
body{{font-family:'Segoe UI','Malgun Gothic',sans-serif;background:#f6f7f9;color:#1c2530;margin:0;padding:32px}}
.wrap{{max-width:1000px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#6b7684;font-size:13px;margin-bottom:22px}}
.card{{background:#fff;border:1px solid #e5e9ef;border-radius:12px;padding:20px 24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.card h2{{font-size:16px;margin:0 0 12px;display:flex;gap:8px;align-items:center}}
.badge{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px}}
.b-ok{{background:#e8f5e9;color:#2e7d32}} .b-wait{{background:#fff4e0;color:#b26a00}} .b-warn{{background:#fdecea;color:#c0392b}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #e5e9ef;padding:6px 9px;text-align:center}}
th{{background:#f0f3f7;font-weight:600}} td.day{{text-align:left;font-variant-numeric:tabular-nums}}
.zero{{color:#c4ccd6}} .swap-row td{{background:#fff7e6;font-weight:600}} .after td{{background:#eaf3fb}}
.grp-f{{background:#eef6ff}} .grp-k{{background:#fdf0f5}}
.smy{{display:flex;gap:24px;flex-wrap:wrap}} .smy>div{{flex:1;min-width:260px}}
.smy h3{{font-size:13px;margin:0 0 8px;color:#41505f}}
.smy .box div{{background:#f5f7fa;border-radius:8px;padding:9px 13px;font-size:12.5px;margin-bottom:6px}}
.smy .box span{{color:#6b7684;display:block;font-size:11px}} .smy .box b{{font-size:17px;margin-right:6px}}
.note{{font-size:12.5px;color:#5a6675;line-height:1.7}} .note b{{color:#c0392b}}
</style></head><body><div class="wrap">
<h1>Meta / TikTok 채널 CVR — 링크 변동 전후 (일별)</h1>
<div class="sub">Meta→fliptop(ワンタッチ) · TikTok→기본컵(PPSU) &nbsp;|&nbsp; 스왑 2026-09-21 17:07 &nbsp;|&nbsp; 산출 {datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')} JST (메타몽) &nbsp;|&nbsp; <span class="badge {badge}">{tag}</span></div>

<div class="card"><h2>스왑 전 vs 후 요약</h2><div class="smy">
<div><h3>스왑 전 (~9/21, {smy['pre']['fliptop']['days']}일)</h3><div class="box">{scard('pre',smy['pre'])}</div></div>
<div><h3>스왑 후 (9/22~, {smy['post']['fliptop']['days']}일)</h3><div class="box">{scard('post',smy['post'])}</div></div>
</div>
<p class="note" style="margin-top:14px">읽는 법: <b>방문(분모)</b>은 스왑 직후 반응이 즉시 나타남(Meta 트래픽이 fliptop로 착지). <b>CVR/주문</b>은 주문 지연·저표본으로 D+2엔 판정 불가 — 주간 누적 필요. 스왑 후 fliptop 방문↑인데 CVR이 낮게 유지되면 대표님 가설(Meta=넓은 저의도 유입)의 신호.</p></div>

<div class="card"><h2>일별 상세 <span class="badge b-ok">RMS get-item-list 실측</span></h2>
<table><tr><th rowspan="2">날짜</th><th class="grp-f" colspan="3">fliptop (Meta 타겟)</th><th class="grp-k" colspan="3">기본컵 PPSU (TikTok 타겟)</th></tr>
<tr><th class="grp-f">방문</th><th class="grp-f">주문</th><th class="grp-f">CVR%</th><th class="grp-k">방문</th><th class="grp-k">주문</th><th class="grp-k">CVR%</th></tr>
{''.join(rows_html)}</table>
<p class="note">방문=アクセス人数(visitAll), 주문=orderCountAll, CVR=주문/방문. {'RPP 차감 반영.' if ppc_excluded else '<b>PPC(RPP) 미차감</b> — 삐삐 RPP 일별(fliptop 10000002/기본컵 10000001) 확보 시 --rpp-json 으로 재생성하면 순수 소셜 CVR 로 갱신.'}</p></div>

<div class="sub">소스: RMS get-item-list(period=daily 하루씩) · 실험설계 project_meta_tiktok_channel_cvr_experiment · 생성 tools/channel_cvr_daily.py</div>
</div></body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path


def update_app_seed(daily: dict, ppc_excluded: bool) -> Path:
    """meta-app/lib/channel-cvr-seed.json 갱신 후 vercel --prod 재배포 (rms_access_downloader 패턴)."""
    seed = {
        "updated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "swap_date": SWAP_DATE,
        "post_start": POST_START,
        "ppc_excluded": ppc_excluded,
        "days": {d: g for d, g in daily.items() if "_error" not in g},
    }
    path = ROOT / "meta-app" / "lib" / "channel-cvr-seed.json"
    path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[seed] {path} ({len(seed['days'])} days)")
    try:
        r = subprocess.run("vercel --prod --yes", cwd=str(ROOT / "meta-app"),
                           shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        print("[deploy]", "OK" if r.returncode == 0 else f"FAIL rc={r.returncode}")
        if r.returncode != 0:
            print((r.stderr or "")[-400:])
    except Exception as exc:
        print("[deploy] exception:", exc)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--rpp-json", help="RPP 일별 차감 데이터 (삐삐)")
    ap.add_argument("--no-headless", action="store_true")
    ap.add_argument("--open", action="store_true", help="생성 후 브라우저로 열기")
    ap.add_argument("--update-app", action="store_true", help="meta-app 전환 탭 seed 갱신 + Vercel 재배포")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    daily = fetch_daily(args.date_from, args.date_to, headless=not args.no_headless)
    (OUT_DIR / "daily_cvr.json").write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")

    ppc_excluded = False
    if args.rpp_json:
        daily = apply_rpp(daily, args.rpp_json)
        ppc_excluded = True

    out = build_html(daily, ppc_excluded, OUT_DIR / "channel_cvr_daily_report.html")
    print(f"[OK] daily JSON: {OUT_DIR/'daily_cvr.json'}")
    print(f"[OK] report: {out}")
    if args.update_app:
        update_app_seed(daily, ppc_excluded)
    if args.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
