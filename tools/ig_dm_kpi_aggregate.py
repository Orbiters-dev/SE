"""IG DM 원장 → 리치아웃/답장/계약 코호트 집계 → 트래커 시트 "Outreach Auto" 탭.

Python 3.10+ (repo 표준 3.14).

코호트 정의 (2026-08-25 세은 확정 — 담당자 분해 없음, 계정 단위):
- 리치아웃: 원장에서 첫 메시지(가장 오래된 관측 메시지)가 우리 발신인 스레드.
  귀속일 = 그 첫 발신 시각 (JST). peer 당 1회 (최초 리치아웃 채택).
- 답장: 리치아웃 스레드에서 첫 발신 이후 상대의 첫 수신 발생.
  귀속 = 리치아웃 주차 (코호트 — 늦은 답장도 발송 주차로 귀속).
- 계약: WL Code & Payment 탭(계약서 받은 사람만 기재)의 Creator ID 를
  리치아웃 스레드 peer 와 매칭. 핸들 단위 dedup — 행이 여러 개(복수 딜리버러블)여도
  계약 1건. 귀속 = 해당 스레드의 리치아웃 주차.
  DM 스레드가 없는 계약(타 경로)은 별도 카운트로 표기만.
- capped 스레드(20개 창 가득)는 첫 발신 시각이 실제보다 늦을 수 있어
  Low Confidence 컬럼으로 따로 표기.

Usage:
    python tools/ig_dm_kpi_aggregate.py            # 집계 + 시트 반영
    python tools/ig_dm_kpi_aggregate.py --dry-run  # 시트 반영 없이 표만 출력
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

LEDGER = ROOT / "data" / "ig_dm_ledger.json"
TRACKER_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
WL_TAB_GID = 751080099          # "WL Code & Payment"
OUT_TAB = "Outreach Auto"
OUT_TAB_MONTHLY = "Outreach Auto Monthly"
JST = timezone(timedelta(hours=9))


def parse_ts(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
    except (ValueError, TypeError):
        return None


def week_start(d: datetime) -> str:
    """월요일 시작 주차 라벨 (JST)."""
    monday = d.date() - timedelta(days=d.weekday())
    return monday.isoformat()


def norm_handle(s: str) -> str:
    return (s or "").strip().lstrip("@").lower()


def load_ledger() -> dict:
    if not LEDGER.exists():
        raise SystemExit(f"ERROR: 원장 없음 — 먼저 ig_dm_collector.py 실행 ({LEDGER})")
    try:
        d = json.loads(LEDGER.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"ERROR: 원장 JSON 손상 ({LEDGER}): {e}") from e
    if not isinstance(d.get("threads"), dict):
        raise SystemExit(f"ERROR: 원장 스키마 손상 — threads 키 없음 ({LEDGER})")
    return d


def analyze_threads(ledger: dict) -> dict[str, dict]:
    """peer 핸들별 {reachout_ts, reply_ts, capped} — 우리가 먼저 연 스레드만."""
    out: dict[str, dict] = {}
    for t in ledger["threads"].values():
        msgs = t.get("messages") or []
        if not msgs:
            continue
        first = msgs[0]
        if first.get("dir") != "out":
            continue  # 상대가 먼저 연 스레드 (인바운드 문의) = 리치아웃 아님
        reachout_ts = parse_ts(first.get("ts", ""))
        if not reachout_ts:
            continue
        reply_ts = None
        for m in msgs:
            ts = parse_ts(m.get("ts", ""))
            if m.get("dir") == "in" and ts and ts > reachout_ts:
                reply_ts = ts
                break
        peer = norm_handle(t.get("peer", ""))
        if not peer:
            continue
        # 같은 peer 와 스레드 복수 → 가장 이른 리치아웃 1건만 (동시각이면 먼저 본 것 유지)
        if peer in out and out[peer]["reachout_ts"] <= reachout_ts:
            continue
        out[peer] = {
            "reachout_ts": reachout_ts,
            "reply_ts": reply_ts,
            "capped": bool(t.get("capped")),
        }
    return out


def fetch_contract_handles(gc) -> set[str]:
    """WL 탭 Creator ID 열 전체 → 핸들 set (행 중복 = 계약 1건으로 dedup)."""
    sh = gc.open_by_key(TRACKER_ID)
    ws = next(w for w in sh.worksheets() if w.id == WL_TAB_GID)
    rows = ws.get_values("D4:D")  # D = Creator ID (헤더 3행). 상한 없음 — 전 행.
    return {h for r in rows if r for h in [norm_handle(r[0])] if h}


def build_weekly(threads: dict, contract_set: set[str], all_peers: set[str]) -> tuple[list[list], dict]:
    weekly = defaultdict(lambda: {"reachout": 0, "reply": 0, "contract": 0, "low_conf": 0})
    # 표기 편차 흡수: 앞뒤 언더스코어 제거 키로도 매칭 (WL "_musukono_kiroku_" vs DM "musukono_kiroku" 류)
    us = lambda s: s.strip("_")
    contract_us = {us(h): h for h in contract_set}
    matched_contracts = set()
    for peer, info in threads.items():
        wk = week_start(info["reachout_ts"])
        weekly[wk]["reachout"] += 1
        if info["capped"]:
            weekly[wk]["low_conf"] += 1
        if info["reply_ts"]:
            weekly[wk]["reply"] += 1
        hit = peer if peer in contract_set else contract_us.get(us(peer), "")
        if hit and hit not in matched_contracts:
            weekly[wk]["contract"] += 1  # peer 는 threads 키라 주 1회만 진입 — 중복 불가
            matched_contracts.add(hit)
    unmatched = sorted(contract_set - matched_contracts)
    # 미매칭 분해: DM 스레드는 있으나 시작 소급 판정 불가(과거 20개 캡) vs DM 자체 없음
    all_us = {us(p) for p in all_peers}
    origin_unknown = [h for h in unmatched if h in all_peers or us(h) in all_us]
    no_dm = [h for h in unmatched if not (h in all_peers or us(h) in all_us)]

    rows = []
    for wk in sorted(weekly):
        w = weekly[wk]
        reply_rate = f"{w['reply'] / w['reachout']:.0%}" if w["reachout"] else "-"
        contract_rate = f"{w['contract'] / w['reachout']:.0%}" if w["reachout"] else "-"
        rows.append([wk, w["reachout"], w["reply"], reply_rate,
                     w["contract"], contract_rate, w["low_conf"]])
    meta = {
        "total_reachout": sum(w["reachout"] for w in weekly.values()),
        "total_reply": sum(w["reply"] for w in weekly.values()),
        "total_contract": sum(w["contract"] for w in weekly.values()),
        "contracts_origin_unknown": origin_unknown,
        "contracts_no_dm": no_dm,
    }
    return rows, meta


def build_monthly(threads: dict, contract_set: set[str]) -> list[list]:
    """월별 코호트 (리치아웃 날짜 기준 — 주간 합산 아님, 월 경계 정확) + TOTAL 행."""
    us = lambda s: s.strip("_")
    contract_us = {us(h): h for h in contract_set}
    monthly = defaultdict(lambda: {"reachout": 0, "reply": 0, "contract": 0})
    matched = set()
    for peer, info in threads.items():
        mo = info["reachout_ts"].strftime("%Y-%m")
        monthly[mo]["reachout"] += 1
        if info["reply_ts"]:
            monthly[mo]["reply"] += 1
        hit = peer if peer in contract_set else contract_us.get(us(peer), "")
        if hit and hit not in matched:
            monthly[mo]["contract"] += 1
            matched.add(hit)
    rate = lambda n, d: f"{n / d:.0%}" if d else "-"
    rows = []
    for mo in sorted(monthly):
        m = monthly[mo]
        rows.append([mo, m["reachout"], m["reply"], rate(m["reply"], m["reachout"]),
                     m["contract"], rate(m["contract"], m["reachout"])])
    tr = sum(m["reachout"] for m in monthly.values())
    tp = sum(m["reply"] for m in monthly.values())
    tc = sum(m["contract"] for m in monthly.values())
    rows.append(["TOTAL", tr, tp, rate(tp, tr), tc, rate(tc, tr)])
    return rows


def write_monthly_sheet(gc, rows: list[list]) -> None:
    sh = gc.open_by_key(TRACKER_ID)
    try:
        ws = sh.worksheet(OUT_TAB_MONTHLY)
    except Exception:
        ws = sh.add_worksheet(title=OUT_TAB_MONTHLY, rows=200, cols=8)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    header = [["Month", "Reachout", "Reply", "Reply %", "Contract", "Contract %", "", f"updated {now}"]]
    try:
        ws.clear()
        ws.update(values=header + rows, range_name="A1")
    except Exception as e:
        raise SystemExit(f"ERROR: 시트 쓰기 실패 ('{OUT_TAB_MONTHLY}' 탭) — {e}") from e


def write_sheet(gc, rows: list[list], meta: dict) -> None:
    sh = gc.open_by_key(TRACKER_ID)
    try:
        ws = sh.worksheet(OUT_TAB)
    except Exception:
        ws = sh.add_worksheet(title=OUT_TAB, rows=max(1000, len(rows) + 20), cols=10)
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    header = [["Week Start (Mon, JST)", "Reachout", "Reply", "Reply %",
               "Contract", "Contract %", "Low Confidence", "", f"updated {now}"]]
    ou, nd = meta["contracts_origin_unknown"], meta["contracts_no_dm"]
    trunc = lambda lst: ", ".join(lst[:30]) + (f" 외 {len(lst) - 30}건" if len(lst) > 30 else "")
    try:
        if ws.row_count < len(rows) + 6:
            ws.resize(rows=len(rows) + 20)
        ws.clear()
        ws.update(values=header + rows, range_name="A1")
        note_row = len(rows) + 3
        ws.update(values=[
            [f"코호트 미귀속 계약 {len(ou)}건 — DM 있으나 최초 발송일 소급불가(과거 20개 캡): {trunc(ou)}"],
            [f"DM 스레드 없는 계약 {len(nd)}건 (타 경로/표기 상이): {trunc(nd)}"],
        ], range_name=f"A{note_row}")
    except Exception as e:
        raise SystemExit(f"ERROR: 시트 쓰기 실패 ('{OUT_TAB}' 탭) — {e}") from e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ledger = load_ledger()
    threads = analyze_threads(ledger)
    print(f"리치아웃 스레드(우리가 먼저 발신): {len(threads)}개 "
          f"/ 전체 {len(ledger['threads'])}개")

    try:
        from sheets_utils import get_sheets_client
    except ImportError as e:
        raise SystemExit(f"ERROR: sheets_utils import 실패 — {e}") from e
    gc = get_sheets_client()
    contract_set = fetch_contract_handles(gc)
    print(f"WL 계약 핸들(고유): {len(contract_set)}건")

    all_peers = {norm_handle(t.get("peer", "")) for t in ledger["threads"].values()}
    all_peers.discard("")
    rows, meta = build_weekly(threads, contract_set, all_peers)
    print(f"\n{'주차(월)':<12}{'리치아웃':>8}{'답장':>6}{'답장률':>8}{'계약':>6}{'계약률':>8}{'저신뢰':>8}")
    for r in rows:
        print(f"{r[0]:<12}{r[1]:>8}{r[2]:>6}{r[3]:>8}{r[4]:>6}{r[5]:>8}{r[6]:>8}")
    print(f"\n합계 — 리치아웃 {meta['total_reachout']} / 답장 {meta['total_reply']}"
          f" / 계약(DM매칭) {meta['total_contract']}"
          f" / 소급불가 계약 {len(meta['contracts_origin_unknown'])}건"
          f" / DM 없는 계약 {len(meta['contracts_no_dm'])}건")

    monthly_rows = build_monthly(threads, contract_set)
    print("\n월별:")
    for r in monthly_rows:
        print(f"  {r[0]:<9}{r[1]:>6}{r[2]:>6}{r[3]:>7}{r[4]:>6}{r[5]:>7}")

    if args.dry_run:
        print("\nDRY RUN — 시트 미반영")
        return 0
    write_sheet(gc, rows, meta)
    write_monthly_sheet(gc, monthly_rows)
    print(f"\n시트 반영 완료 → '{OUT_TAB}' + '{OUT_TAB_MONTHLY}' 탭")
    return 0


if __name__ == "__main__":
    sys.exit(main())
