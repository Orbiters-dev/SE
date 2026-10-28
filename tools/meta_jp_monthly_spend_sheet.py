"""Meta JP Monthly Spend Sheet — Meta JP spend + Rakuten 매출 + 간접 ROAS 월별 집계.

Path 3 (캐시 fallback) 적용 — PG 401 시 .tmp/datakeeper/meta_ads_daily.json 사용.

Usage:
    python tools/meta_jp_monthly_spend_sheet.py --dry-run
    python tools/meta_jp_monthly_spend_sheet.py --create-sheet
    python tools/meta_jp_monthly_spend_sheet.py --sheet-id <ID>
"""
import os
import sys
import json
import argparse
import re
from collections import defaultdict
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from env_loader import load_env
load_env()

import requests

CACHE_META = os.path.join(DIR, "..", ".tmp", "datakeeper", "meta_ads_daily.json")
JP_BRAND = "Grosmimi JP"
SEEUN_EMAIL = "se.heo@orbiters.co.kr"


def _load_meta_jp():
    """캐시 우선 (fresh + complete) → 없으면 PG. PG는 4·5월 누락 상태라 신뢰 X."""
    if os.path.exists(CACHE_META):
        mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_META))
        with open(CACHE_META, encoding="utf-8") as f:
            all_rows = json.load(f)
        rows = [r for r in all_rows if r.get("brand") == JP_BRAND]
        print(f"[Meta JP] Cache: {len(rows)} rows (mtime: {mtime:%Y-%m-%d %H:%M})")
        if rows:
            return rows
    from data_keeper_client import DataKeeper
    dk = DataKeeper()
    rows = dk.get("meta_ads_daily", brand=JP_BRAND, days=180)
    print(f"[Meta JP] PG fallback: {len(rows)} rows (캐시 미생성)")
    return rows


def _load_rakuten():
    """Rakuten 매출 (JPY) — PG 만 사용 (캐시 없음)."""
    from data_keeper_client import DataKeeper
    dk = DataKeeper()
    rows = dk.get("rakuten_orders_daily", days=180)
    print(f"[Rakuten] PG: {len(rows)} rows")
    return rows


def _classify_ad(ad_name: str, adset_name: str):
    """ad_name·adset_name → (channel, stage, product)."""
    a = (ad_name or "").lower()
    s = (adset_name or "").lower()
    channel = "WL" if "wl" in a or "wl" in s else "일반"
    if "proven" in s or "proven" in a:
        stage = "Proven"
    elif "testing" in s or "testing" in a:
        stage = "Testing"
    else:
        stage = "기타"
    if "ppsu" in a or "ppsu" in s:
        product = "PPSU"
    elif "stainless" in a or "stainless" in s:
        product = "Stainless"
    elif "flip" in a or "fliptop" in a:
        product = "FlipTop"
    elif "straw" in a:
        product = "StrawCup"
    elif "tumbler" in a:
        product = "Tumbler"
    else:
        product = "기타"
    return channel, stage, product


def _monthly_fx_jpy_to_krw():
    """월별 평균 환율 (JPY → KRW). Frankfurter (ECB) — 무료 무인증."""
    fx = {}
    for ym in ["2026-03", "2026-04", "2026-05", "2026-06"]:
        try:
            r = requests.get(
                f"https://api.frankfurter.app/{ym}-01..{ym}-28",
                params={"from": "JPY", "to": "KRW"},
                timeout=15,
            )
            d = r.json()
            rates = d.get("rates", {})
            vals = [v["KRW"] for v in rates.values() if "KRW" in v]
            if vals:
                fx[ym] = sum(vals) / len(vals)
                print(f"[FX] {ym}: {fx[ym]:.3f} KRW/JPY (Frankfurter, {len(vals)}일 평균)")
                continue
        except Exception as e:
            print(f"[FX] {ym}: Frankfurter 실패 ({str(e)[:50]})")
        fx[ym] = 9.0
        print(f"[FX] {ym}: fallback 9.0")
    return fx


def aggregate(meta_rows, rakuten_rows, fx):
    """월별 wide 집계."""
    agg = defaultdict(lambda: {
        "total_spend_krw": 0.0,
        "Proven_PPSU": 0.0, "Proven_Stainless": 0.0,
        "Testing_PPSU": 0.0, "Testing_Stainless": 0.0,
        "WL_spend": 0.0, "일반_spend": 0.0,
        "rakuten_revenue_jpy": 0.0, "rakuten_orders": 0,
    })
    for r in meta_rows:
        d = r.get("date", "")
        if len(d) < 7: continue
        ym = d[:7]
        spend = float(r.get("spend") or 0)
        agg[ym]["total_spend_krw"] += spend
        ch, st, pr = _classify_ad(r.get("ad_name", ""), r.get("adset_name", ""))
        key = f"{st}_{pr}"
        if key in agg[ym]:
            agg[ym][key] += spend
        if ch == "WL":
            agg[ym]["WL_spend"] += spend
        else:
            agg[ym]["일반_spend"] += spend
    for r in rakuten_rows:
        d = r.get("date", "")
        if len(d) < 7: continue
        ym = d[:7]
        agg[ym]["rakuten_revenue_jpy"] += float(r.get("revenue") or 0)
        agg[ym]["rakuten_orders"] += int(r.get("orders") or 0)
    # 환율 환산 + ROAS
    for ym, v in agg.items():
        rate = fx.get(ym, 9.0)
        v["fx_jpy_krw"] = rate
        v["rakuten_revenue_krw"] = v["rakuten_revenue_jpy"] * rate
        v["roas"] = (v["rakuten_revenue_krw"] / v["total_spend_krw"]) if v["total_spend_krw"] > 0 else 0
    return agg


def _print_table(agg):
    cols = ["월", "총 spend (KRW)", "Proven PPSU", "Proven Stainless",
            "Testing PPSU", "Testing Stainless", "WL spend", "일반 spend",
            "Rakuten 매출 (JPY)", "주문수", "환율", "Rakuten 매출 (KRW)", "간접 ROAS"]
    print("\n=== Meta JP Monthly Spend + ROAS ===")
    print(" | ".join(f"{c:>16}" for c in cols))
    print("-" * 220)
    for ym in sorted(agg.keys()):
        v = agg[ym]
        row = [ym,
               f"{v['total_spend_krw']:,.0f}",
               f"{v['Proven_PPSU']:,.0f}",
               f"{v['Proven_Stainless']:,.0f}",
               f"{v['Testing_PPSU']:,.0f}",
               f"{v['Testing_Stainless']:,.0f}",
               f"{v['WL_spend']:,.0f}",
               f"{v['일반_spend']:,.0f}",
               f"{v['rakuten_revenue_jpy']:,.0f}",
               f"{v['rakuten_orders']}",
               f"{v['fx_jpy_krw']:.3f}",
               f"{v['rakuten_revenue_krw']:,.0f}",
               f"{v['roas']:.2f}x"]
        print(" | ".join(f"{x:>16}" for x in row))


def _push_to_sheet(agg, sheet_id=None, create=False):
    """Google Sheets push. sheet_id 없으면 신규 생성."""
    from sheets_utils import get_sheets_client
    gc = get_sheets_client()
    if create or not sheet_id:
        sh = gc.create("Meta JP Monthly Spend")
        sh.share(SEEUN_EMAIL, perm_type="user", role="writer")
        sheet_id = sh.id
        print(f"[Sheet] Created new sheet — id={sheet_id}")
        print(f"        URL: https://docs.google.com/spreadsheets/d/{sheet_id}/")
        print(f"        Shared with: {SEEUN_EMAIL}")
    else:
        sh = gc.open_by_key(sheet_id)
        print(f"[Sheet] Using existing sheet id={sheet_id}")
    ws = sh.sheet1
    ws.update_title("Monthly")
    headers = ["월", "총 spend (KRW)", "Proven PPSU", "Proven Stainless",
               "Testing PPSU", "Testing Stainless", "WL spend", "일반 spend",
               "Rakuten 매출 (JPY)", "주문수", "환율 JPY→KRW",
               "Rakuten 매출 (KRW)", "간접 ROAS"]
    data = [headers]
    for ym in sorted(agg.keys()):
        v = agg[ym]
        data.append([ym,
                     round(v["total_spend_krw"]),
                     round(v["Proven_PPSU"]),
                     round(v["Proven_Stainless"]),
                     round(v["Testing_PPSU"]),
                     round(v["Testing_Stainless"]),
                     round(v["WL_spend"]),
                     round(v["일반_spend"]),
                     round(v["rakuten_revenue_jpy"]),
                     v["rakuten_orders"],
                     round(v["fx_jpy_krw"], 3),
                     round(v["rakuten_revenue_krw"]),
                     round(v["roas"], 2)])
    ws.clear()
    ws.update("A1", data)
    print(f"[Sheet] {len(data)-1} rows uploaded")
    return sheet_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="시트 push 없이 표만 출력")
    ap.add_argument("--create-sheet", action="store_true", help="신규 시트 생성 + 세은 공유")
    ap.add_argument("--sheet-id", type=str, default=None, help="기존 시트 ID")
    args = ap.parse_args()

    meta = _load_meta_jp()
    rakuten = _load_rakuten()
    fx = _monthly_fx_jpy_to_krw()
    agg = aggregate(meta, rakuten, fx)
    _print_table(agg)

    if args.dry_run:
        print("\n[DRY-RUN] 시트 push 없음.")
        return
    if args.create_sheet or args.sheet_id:
        _push_to_sheet(agg, sheet_id=args.sheet_id, create=args.create_sheet)
    else:
        print("\n시트 push 안 함. --create-sheet 또는 --sheet-id 사용.")


if __name__ == "__main__":
    main()
