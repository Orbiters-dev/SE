# -*- coding: utf-8 -*-
"""Rakuten RPP 일별 광고비 수집기 → data/rpp_daily.json

RMS 공식 API 는 RPP 미노출. 대신 RPP 콘솔 내부 API 를 쓴다 (2026-07-21 실측 검증):
  POST ad.rms.rakuten.co.jp/rpp/api/reports/downloadPerfFile
  payload periodType=2 (日ごとに集計) → 지정 기간의 일별 row CSV(cp932) 1방.

인증은 Playwright 로그인(rms_review_playwright.do_login) 후 리포트 페이지에서
「この条件でダウンロード」 1클릭으로 x-xsrf-token 헤더를 캡처, 페이지 컨텍스트
fetch 로 리플레이한다 (ctx.request 는 403 — 페이지 fetch 만 통과).

주의:
- 720時間(D+30) 매출 귀속은 소급 갱신 → 매일 최근 35일 창을 재수집(upsert).
- 실적 0 인 날은 CSV 에서 row 자체가 생략될 수 있음 → 창 내 결측일은 0 으로 채움.

사용:
  python tools/collect_rpp_daily.py                  # 일일 모드: 최근 35일 upsert
  python tools/collect_rpp_daily.py --backfill 2025-11-01   # 과거 백필(31일 단위)
  python tools/collect_rpp_daily.py --update-app     # + meta-app 시드 복사 & vercel 재배포
"""
import argparse
import base64
import csv
import io
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
STORE = ROOT / "data" / "rpp_daily.json"

REPORTS_URL = "https://ad.rms.rakuten.co.jp/rpp/reports"

FETCH_JS = """async ([payload, headers]) => {
    const r = await fetch('/rpp/api/reports/downloadPerfFile', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        credentials: 'include',
    });
    const buf = await r.arrayBuffer();
    let binary = '';
    const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return {status: r.status, b64: btoa(binary)};
}"""

# CSV 컬럼명 → 저장 키 (すべての広告 / 日ごとに集計 리포트 기준)
COLUMNS = {
    "クリック数(合計)": ("clicks", int),
    "実績額(合計)": ("spend_jpy", int),
    "CPC実績(合計)": ("cpc_jpy", int),
    "CTR(%)": ("ctr_pct", float),
    "売上金額(合計12時間)": ("sales_12h_jpy", int),
    "売上件数(合計12時間)": ("orders_12h", int),
    "ROAS(合計12時間)(%)": ("roas_12h_pct", float),
    "売上金額(合計720時間)": ("sales_720h_jpy", int),
    "売上件数(合計720時間)": ("orders_720h", int),
    "ROAS(合計720時間)(%)": ("roas_720h_pct", float),
}

DATE_RE = re.compile(r"(\d{4})年(\d{2})月(\d{2})日")


def load_store() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {"updated_at": None, "source": "rpp downloadPerfFile periodType=2", "days": {}}


def save_store(store: dict) -> None:
    store["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_daily_csv(data: bytes) -> dict[str, dict]:
    """일별 CSV → {'YYYY-MM-DD': {지표}}. 프리앰블(검색조건 블록)은 헤더행까지 스킵."""
    text = data.decode("cp932")
    lines = text.splitlines()
    header_idx = next((i for i, l in enumerate(lines) if l.startswith('"日付"')), None)
    if header_idx is None:
        raise ValueError(f"헤더행 없음 — 응답이 CSV 가 아님: {text[:200]}")
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
    out: dict[str, dict] = {}
    for row in reader:
        m = DATE_RE.search(row.get("日付", ""))
        if not m:
            continue
        day = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        rec = {}
        for col, (key, cast) in COLUMNS.items():
            raw = (row.get(col) or "0").replace(",", "").strip()
            try:
                rec[key] = cast(raw)
            except ValueError:
                rec[key] = 0
        out[day] = rec
    return out


def zero_record() -> dict:
    return {key: cast(0) for key, cast in COLUMNS.values()}


def pull_windows(windows: list[tuple[str, str]]) -> dict[str, dict]:
    """Playwright 세션 1회로 여러 기간 창을 일별 수집."""
    from playwright.sync_api import sync_playwright
    import rms_review_playwright as rms

    captured: dict = {}
    days: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ja-JP", accept_downloads=True)
        page = ctx.new_page()
        page.on("request", lambda req: captured.update(headers=req.headers, post=req.post_data)
                if "downloadPerfFile" in req.url else None)

        rms.do_login(page)
        page.goto(REPORTS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)
        # 시드 클릭 1회 — x-xsrf-token 포함 헤더 + 기본 payload 캡처
        try:
            with page.expect_download(timeout=45000):
                page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('a, button, input[type=button], input[type=submit]'));
                    els.find(e => (e.innerText || e.value || '').includes('この条件でダウンロード')).click();
                }""")
        except Exception as e:
            print(f"[WARN] 시드 클릭: {e}")
        if not captured.get("post"):
            raise RuntimeError("downloadPerfFile 요청 캡처 실패 — 리포트 페이지 구조 변경 의심")

        base_payload = json.loads(captured["post"])
        headers = {k: v for k, v in captured["headers"].items()
                   if k.lower() not in ("cookie", "content-length", "host", "user-agent", "accept-encoding")
                   and not k.startswith(":")}

        for start, end in windows:
            payload = dict(base_payload, selectionType=1, periodType=2, startDate=start, endDate=end)
            res = page.evaluate(FETCH_JS, [payload, headers])
            data = base64.b64decode(res["b64"])
            if res["status"] != 201:
                print(f"[WARN] {start}~{end} HTTP {res['status']}: {data[:200]!r} — 스킵")
                continue
            got = parse_daily_csv(data)
            days.update(got)
            print(f"  {start}~{end}: {len(got)}일 수집")
        browser.close()
    return days


def month_windows(start: date, end: date) -> list[tuple[str, str]]:
    """31일 이하 창으로 분할 (キーワード別 1ヶ月 제한 전례 → 안전폭)."""
    wins = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=30), end)
        wins.append((cur.isoformat(), stop.isoformat()))
        cur = stop + timedelta(days=1)
    return wins


def update_app(store: dict) -> None:
    """meta-app 시드 갱신 + vercel 재배포 (예산 탭 월별 뷰가 이 시드를 읽음)."""
    import subprocess
    seed = ROOT / "meta-app" / "lib" / "rpp-daily-seed.json"
    seed.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[RPP Daily] seed → {seed.relative_to(ROOT)}")
    r = subprocess.run("vercel --prod --yes", cwd=str(ROOT / "meta-app"),
                       shell=True, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"[WARN] vercel 배포 실패:\n{r.stderr[-500:]}")
    else:
        print("[RPP Daily] meta-app 재배포 완료")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", metavar="YYYY-MM-DD", help="지정일부터 어제까지 백필")
    ap.add_argument("--days", type=int, default=35, help="일일 모드 재수집 창 (기본 35일)")
    ap.add_argument("--update-app", action="store_true", help="meta-app 시드 복사 + vercel 재배포")
    args = ap.parse_args()

    yesterday = date.today() - timedelta(days=1)
    if args.backfill:
        start = date.fromisoformat(args.backfill)
        windows = month_windows(start, yesterday)
        fill_start = start
    else:
        start = yesterday - timedelta(days=args.days - 1)
        windows = [(start.isoformat(), yesterday.isoformat())]
        fill_start = start

    got = pull_windows(windows)

    store = load_store()
    added = updated = 0
    # 창 내 결측일 = 실적 0 (row 생략 케이스, 7/19 실측)
    cur = fill_start
    while cur <= yesterday:
        key = cur.isoformat()
        rec = got.get(key, zero_record())
        if key not in store["days"]:
            added += 1
        elif store["days"][key] != rec:
            updated += 1
        store["days"][key] = rec
        cur += timedelta(days=1)
    store["days"] = dict(sorted(store["days"].items()))
    save_store(store)

    total = sum(r["spend_jpy"] for r in store["days"].values())
    recent = [(d, r["spend_jpy"]) for d, r in sorted(store["days"].items())[-7:]]
    print(f"[RPP Daily] +{added}일 신규 / ~{updated}일 갱신 → {STORE.name} (총 {len(store['days'])}일, 누적 ¥{total:,})")
    print("  최근 7일:", " ".join(f"{d[5:]}=¥{s:,}" for d, s in recent))
    if args.update_app:
        update_app(store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
