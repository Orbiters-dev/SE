#!/usr/bin/env python3
"""RMS データダウンロード「店舗データ」CSV を取得し、アクセス人数・転換率を抽出。

メタ流入比重 = Meta LPV ÷ アクセス人数 / 転換率 = 売上件数 ÷ アクセス人数 算出用の分母を供給。
楽天 RMS には access 系の REST API が無いため、データダウンロード画面の CSV を
Playwright で自動取得する（ログインは rms_review_playwright.do_login を再利用）。

CLI:
  python tools/rms_access_downloader.py --period monthly
  python tools/rms_access_downloader.py --period daily --json
出力: 月(or 日) → {access(アクセス人数), uu(ユニークユーザー), cvr(転換率%), orders(売上件数), sales}
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rms_review_playwright import do_login  # noqa: E402  (ログイン共通フロー)
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / ".tmp" / "rms_access"
DATADL_URL = "https://datatool.rms.rakuten.co.jp/datadownload"


def download_shop_csv(period: str = "monthly", headless: bool = True) -> Path:
    """店舗データ CSV を period(daily|monthly) で取得し保存パスを返す。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    radio_val = "monthly" if period == "monthly" else "daily"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()
        do_login(page)
        page.goto(DATADL_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        page.select_option('select[name="name"]', "shop")     # 데이터 종류 = 店舗データ
        # 커스텀 라디오(span.rms-check-box 가 클릭 가로챔) → label 텍스트 클릭
        label_txt = "月次" if radio_val == "monthly" else "日次"
        page.click(f'label:has-text("{label_txt}")')          # 期間 = 日次 / 月次
        page.wait_for_timeout(1500)                           # 날짜 범위 자동 갱신 대기
        with page.expect_download(timeout=60000) as dl_info:
            page.click('button:has-text("CSVダウンロード")')
        path = OUT_DIR / f"shop_{radio_val}.csv"
        dl_info.value.save_as(str(path))
        browser.close()
    return path


def _to_int(v):
    try:
        return int(float(str(v).replace(",", ""))) if str(v).strip() not in ("", "-") else 0
    except (TypeError, ValueError):
        return 0


def _to_float(v):
    try:
        return float(str(v).replace(",", "")) if str(v).strip() not in ("", "-") else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_shop_csv(path: Path) -> list:
    """店舗データ CSV → デバイス=すべて 行のみ抽出。헤더 행은 '日付' 으로 시작."""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        header = None
        for r in csv.reader(f):
            if not r:
                continue
            if r[0] == "日付":
                header = r
                continue
            if not header:
                continue
            rec = dict(zip(header, r))
            # 日次엔 曜日 컬럼이 있고 月次엔 없어 デバイス 위치가 다름 → 컬럼명으로 판정
            if rec.get("デバイス") != "すべて":
                continue
            if not rec.get("日付", "")[:4].isdigit():
                continue
            rows.append({
                "date": rec.get("日付", ""),
                "access": _to_int(rec.get("アクセス人数")),
                "uu": _to_int(rec.get("ユニークユーザー数")),
                "cvr": _to_float(rec.get("転換率")),
                "orders": _to_int(rec.get("売上件数")),
                "sales": _to_int(rec.get("売上金額")),
            })
    return rows


def aggregate_monthly(rows: list) -> dict:
    """日次/月次 행을 월(YYYY-MM) 단위로 합산. 전환율은 주문÷접속 재계산."""
    agg = defaultdict(lambda: {"access": 0, "uu": 0, "orders": 0, "sales": 0})
    for r in rows:
        ym = r["date"][:7].replace("/", "-")
        if not ym:
            continue
        agg[ym]["access"] += r["access"]
        agg[ym]["uu"] += r["uu"]
        agg[ym]["orders"] += r["orders"]
        agg[ym]["sales"] += r["sales"]
    out = {}
    for ym, d in agg.items():
        cvr = (d["orders"] / d["access"] * 100) if d["access"] > 0 else 0.0
        out[ym] = {**d, "cvr": round(cvr, 3)}
    return out


def fetch_access_monthly(period: str = "monthly", headless: bool = True) -> dict:
    """店舗 전체 접속자수(アクセス人数) 월별 dict. 메타 유입 비중 분모 공급."""
    path = download_shop_csv(period=period, headless=headless)
    return aggregate_monthly(parse_shop_csv(path))


_NUM_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def classify_product(manage_number: str):
    m = (manage_number or "").lower()
    if "ppsu" in m:
        return "PPSU"
    if "stainless" in m:
        return "Stainless"
    return None   # 니플 등 제외


def fetch_product_access(headless: bool = True, ym: str = None) -> dict:
    """商品ページ get-item-list API → 제품별 {access(visitAll), orders(unitsAll)}.

    ym=YYYYMM (기본 당월). 商品管理番号 로 PPSU/Stainless 분류 (니플 제외).
    화면 파싱 대신 내부 API 직접 호출 — 안정적이고 과거월(startDate/endDate)도 지원.
    """
    from playwright.sync_api import sync_playwright
    if not ym:
        ym = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m")
    url = ("https://datatool.rms.rakuten.co.jp/access/item/get-item-list/"
           f"?period=monthly&device=all&startDate={ym}&endDate={ym}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()
        do_login(page)
        data = page.request.get(url, timeout=30000).json()
        browser.close()
    agg = {}
    for d in data.get("data", []):
        prod = classify_product((d.get("item") or {}).get("mngNumber"))
        if not prod:
            continue
        sf = d.get("salesFormula") or {}
        a = agg.setdefault(prod, {"access": 0, "orders": 0})
        a["access"] += sf.get("visitAll", 0)    # アクセス人数
        a["orders"] += sf.get("unitsAll", 0)    # 판매개수(오더수)
    return agg


def update_app_seed(headless: bool = True) -> dict:
    """月次(완료월) + 日次(당월) 합산 → meta-app/lib/store-seed.json 갱신 후 vercel 재배포.

    매일 Task Scheduler 로 실행하면 전환 탭의 스토어 접속자수·비중·전환율이 자동 갱신된다.
    """
    # "전체"는 앱에서 PPSU+Stainless 합산이라 店舗 CSV 불필요. 商品ページ 제품별 접속만 갱신.
    this_month = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m")
    prod_access = fetch_product_access(headless)              # 商品ページ 月次 당월 (商品管理番号 분류)
    pa_path = ROOT / "meta-app" / "lib" / "product-access-seed.json"
    seed = json.loads(pa_path.read_text(encoding="utf-8")) if pa_path.exists() else {}
    for prod, acc in prod_access.items():                     # 당월만 갱신, 과거월 유지
        seed.setdefault(prod, {})[this_month] = acc
    pa_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[product-access] {this_month}: {prod_access}")

    try:
        r = subprocess.run("vercel --prod --yes", cwd=str(ROOT / "meta-app"),
                           shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        print("[deploy]", "OK" if r.returncode == 0 else f"FAIL rc={r.returncode}")
        if r.returncode != 0:
            print((r.stderr or "")[-300:])
    except Exception as exc:
        print("[deploy] exception:", exc)
    return seed


def main():
    ap = argparse.ArgumentParser(description="RMS 店舗データ CSV → 접속자수/전환율")
    ap.add_argument("--period", choices=["monthly", "daily"], default="monthly")
    ap.add_argument("--no-headless", action="store_true", help="브라우저 표시")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--update-app", action="store_true", help="store-seed.json 갱신 + meta-app 재배포")
    args = ap.parse_args()

    if args.update_app:
        update_app_seed(headless=not args.no_headless)
        return

    monthly = fetch_access_monthly(period=args.period, headless=not args.no_headless)
    if args.json:
        print(json.dumps(monthly, ensure_ascii=False, indent=2))
    else:
        print(f"{'월':9} {'접속자수':>10} {'UU':>9} {'주문':>7} {'전환율%':>8}")
        for ym, d in sorted(monthly.items()):
            print(f"{ym:9} {d['access']:>10,} {d['uu']:>9,} {d['orders']:>7,} {d['cvr']:>8.3f}")


if __name__ == "__main__":
    main()
