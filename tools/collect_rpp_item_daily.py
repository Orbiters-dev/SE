# -*- coding: utf-8 -*-
"""RPP 아이템별 일별 클릭·주문 수집 → 채널 CVR 실험의 PPC 차감분.

RPP 商品別 리포트(downloadPerfFile selectionType=3)는 全期間 집계만 되고 日ごと(periodType=2)는
400 이라, access API 와 동일하게 **하루씩(startDate=endDate) 全期間** 호출로 아이템×일을 만든다.
식별자 = 商品管理番号(access API 와 동일 → fliptop=onetouch / 기본컵=strawcup300·_ss).

인증·헤더 캡처는 collect_rpp_daily.py 패턴(로그인 후 시드 클릭으로 x-xsrf-token 캡처 → 페이지 fetch 리플레이).

산출: .tmp/channel_cvr_experiment/rpp_daily.json
  {date: {"fliptop":{"visit":클릭,"orders":주문}, "kihon":{"visit":클릭,"orders":주문}}}
  visit=クリック数(合計), orders=売上件数(合計12時間) — 상품페이지 same-day 주문과 정렬(720h는 click일 귀속이라 mismatch).
이 파일을 tools/channel_cvr_daily.py --rpp-json 으로 먹이면 상품페이지 전체에서 RPP분 차감 = 순수 소셜 CVR.

CLI:
  python tools/collect_rpp_item_daily.py --date-from 2026-09-07 --date-to 2026-09-23
"""
import argparse
import base64
import csv
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
OUT = ROOT / ".tmp" / "channel_cvr_experiment" / "rpp_daily.json"
REPORTS_URL = "https://ad.rms.rakuten.co.jp/rpp/reports"

FETCH_JS = """async ([payload, headers]) => {
    const r = await fetch('/rpp/api/reports/downloadPerfFile', {
        method: 'POST', headers: headers, body: JSON.stringify(payload), credentials: 'include' });
    const buf = await r.arrayBuffer(); let s=''; const u=new Uint8Array(buf);
    for (let i=0;i<u.length;i++) s+=String.fromCharCode(u[i]);
    return {status: r.status, b64: btoa(s)};
}"""


def _group(mng: str):
    m = (mng or "").lower()
    if "onetouch" in m:
        return "fliptop"
    if ("strawcup300" in m or "strawcup_ss" in m) and "stainless" not in m:
        return "kihon"
    return None


def _daterange(d0: str, d1: str):
    a = datetime.strptime(d0, "%Y-%m-%d")
    b = datetime.strptime(d1, "%Y-%m-%d")
    while a <= b:
        yield a.strftime("%Y-%m-%d")
        a += timedelta(days=1)


def _parse_day(txt: str) -> dict:
    """商品別 CSV(1일) → {group: {visit, orders}}."""
    lines = txt.splitlines()
    hi = next((i for i, l in enumerate(lines) if '"商品管理番号"' in l), None)
    agg = {"fliptop": {"visit": 0, "orders": 0}, "kihon": {"visit": 0, "orders": 0}}
    if hi is None:
        return agg
    for row in csv.DictReader(io.StringIO("\n".join(lines[hi:]))):
        g = _group(row.get("商品管理番号", ""))
        if not g:
            continue
        clicks = (row.get("クリック数(合計)") or "0").replace(",", "").strip()
        orders = (row.get("売上件数(合計12時間)") or "0").replace(",", "").strip()
        try:
            agg[g]["visit"] += int(clicks or 0)
            agg[g]["orders"] += int(orders or 0)
        except ValueError:
            pass
    return agg


def collect(date_from: str, date_to: str, headless: bool = True) -> dict:
    from playwright.sync_api import sync_playwright
    import rms_review_playwright as rms

    cap: dict = {}
    out: dict = {}
    with sync_playwright() as p:
        br = p.chromium.launch(headless=headless)
        pg = br.new_context(locale="ja-JP", accept_downloads=True).new_page()
        pg.on("request", lambda q: cap.update(headers=q.headers, post=q.post_data)
              if "downloadPerfFile" in q.url else None)
        rms.do_login(pg)
        pg.goto(REPORTS_URL, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(3500)
        try:
            with pg.expect_download(timeout=45000):
                pg.evaluate("""() => {[...document.querySelectorAll('a,button,input')]
                    .find(x => ((x.innerText||x.value||'')).includes('この条件でダウンロード')).click();}""")
        except Exception as e:
            print(f"[WARN] seed click: {e}")
        if not cap.get("post"):
            raise RuntimeError("downloadPerfFile 캡처 실패 — 리포트 페이지 구조 변경 의심")
        base = json.loads(cap["post"])
        headers = {k: v for k, v in cap["headers"].items()
                   if k.lower() not in ("cookie", "content-length", "host", "user-agent", "accept-encoding")
                   and not k.startswith(":")}
        for day in _daterange(date_from, date_to):
            payload = dict(base, selectionType=3, periodType=0, startDate=day, endDate=day)
            res = pg.evaluate(FETCH_JS, [payload, headers])
            if res["status"] != 201:
                out[day] = {"_error": res["status"]}
                continue
            txt = base64.b64decode(res["b64"]).decode("cp932", "replace")
            out[day] = _parse_day(txt)
        br.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    data = collect(args.date_from, args.date_to, headless=not args.no_headless)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = {d: v for d, v in data.items() if "_error" not in v}
    tot_f = sum(v["fliptop"]["visit"] for v in ok.values())
    tot_k = sum(v["kihon"]["visit"] for v in ok.values())
    print(f"[OK] {OUT} ({len(ok)}/{len(data)}일) · RPP 클릭 합계 fliptop={tot_f} kihon={tot_k}")


if __name__ == "__main__":
    main()
