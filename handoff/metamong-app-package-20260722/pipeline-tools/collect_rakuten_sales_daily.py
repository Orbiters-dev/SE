# -*- coding: utf-8 -*-
"""Rakuten 일별 매출 수집기 → data/rakuten_sales_daily.json

RMS Order API (ESA 헤더, credentials/rakuten_rms_config.json) searchOrder→getOrder,
priceTaxIncl×units 합산 = 일별 총매출 (주문일 기준, 캔슬확정 orderProgress=900 제외).
.tmp/fetch_rakuten_period_sales.py 검증 로직의 프로덕션화 (2026-07-01 세은 확정 경로).

meta-app Total ROAS = 라쿠텐 총매출 ÷ (Meta spend + RPP spend) 의 분자.

주의: 취소 확정이 사후 반영되므로 매일 최근 40일 창을 재수집(upsert)한다.

사용:
  python tools/collect_rakuten_sales_daily.py                    # 최근 40일 upsert
  python tools/collect_rakuten_sales_daily.py --backfill 2025-11-01
  python tools/collect_rakuten_sales_daily.py --update-app       # + meta-app 시드 복사
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
STORE = ROOT / "data" / "rakuten_sales_daily.json"
SEED = ROOT / "meta-app" / "lib" / "rakuten-sales-seed.json"
CONFIG = ROOT / "credentials" / "rakuten_rms_config.json"

CANCELLED_PROGRESS = {900}  # 캔슬확정


def _num(v, default=0.0) -> float:
    """API 필드 안전 변환 — 비수치 문자열/None 은 default (크래시·오집계 방지)."""
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else default
    except (TypeError, ValueError):
        return default


def load_store() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {"updated_at": None, "source": "RMS searchOrder/getOrder priceTaxIncl*units", "days": {}}


def save_store(store: dict) -> None:
    store["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STORE.parent.mkdir(parents=True, exist_ok=True)
    # 원자적 쓰기 — 쓰다 죽어도 기존 store 가 깨지지 않게 tmp 후 replace
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STORE)


def _post_with_retry(client, path: str, body: dict, tries: int = 4):
    """RMS POST + 403(rate limit) 지수 백오프 재시도. 청크 연사 시 403 실측(7/21)."""
    import time
    import requests as rq
    for attempt in range(tries):
        resp = client.session.post(client._url(path), json=body)
        if resp.status_code == 403 and attempt < tries - 1:
            wait = 2 ** attempt * 2  # 2s → 4s → 8s
            print(f"  [RATE] 403 — {wait}s 대기 후 재시도")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise rq.HTTPError("403 retries exhausted")


def collect(days: int) -> dict[str, dict]:
    """최근 N일 주문 → {'YYYY-MM-DD': {sales_jpy, orders, units}} (취소 제외)."""
    import time
    from rakuten_rms_client import RakutenRMSClient

    client = RakutenRMSClient(str(CONFIG))
    now = datetime.now()
    numbers: list[str] = []
    seen: set[str] = set()
    for offset in range(0, days, 7):
        chunk_end = now - timedelta(days=offset)
        chunk_start = now - timedelta(days=min(offset + 7, days))
        page = 1
        while True:
            data = _post_with_retry(client, "/es/2.0/order/searchOrder", {
                "dateType": 1,
                "startDatetime": chunk_start.strftime("%Y-%m-%dT%H:%M:%S+0900"),
                "endDatetime": chunk_end.strftime("%Y-%m-%dT%H:%M:%S+0900"),
                "PaginationRequestModel": {"requestRecordsAmount": 1000, "requestPage": page},
            })
            for n in (data.get("orderNumberList") or []):
                if n not in seen:
                    seen.add(n)
                    numbers.append(n)
            pag = data.get("PaginationResponseModel") or {}
            if page >= (pag.get("totalPages") or 1):
                break
            page += 1
        time.sleep(0.6)  # 연사 rate limit 회피
    print(f"  주문번호 {len(numbers)}건 (최근 {days}일)")

    orders: list[dict] = []
    for i in range(0, len(numbers), 100):
        data = _post_with_retry(client, "/es/2.0/order/getOrder",
                                {"orderNumberList": numbers[i:i + 100], "version": 3})
        orders.extend(data.get("OrderModelList") or [])
        time.sleep(0.6)

    out: dict[str, dict] = {}
    cancelled = 0
    for o in orders:
        day = (o.get("orderDatetime") or "")[:10]
        if not day:
            continue
        # int 코어션 — API 가 "900"(str) 로 줘도 캔슬 필터가 뚫리지 않게
        if int(_num(o.get("orderProgress"), -1)) in CANCELLED_PROGRESS:
            cancelled += 1
            continue
        rec = out.setdefault(day, {"sales_jpy": 0, "orders": 0, "units": 0})
        rec["orders"] += 1
        for pkg in (o.get("PackageModelList") or []):
            for item in (pkg.get("ItemModelList") or []):
                units = int(_num(item.get("units"), 0))  # 결측 = 0 (과대집계 방지)
                price = _num(item.get("priceTaxIncl")) or _num(item.get("price"))
                rec["sales_jpy"] += int(round(price * units))
                rec["units"] += units
    print(f"  주문 상세 {len(orders)}건 (취소 제외 {cancelled}건) → {len(out)}일")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", metavar="YYYY-MM-DD", help="지정일부터 오늘까지 수집")
    ap.add_argument("--days", type=int, default=40, help="일일 모드 재수집 창 (기본 40일)")
    ap.add_argument("--update-app", action="store_true", help="meta-app 시드 복사")
    args = ap.parse_args()

    today = date.today()
    if args.backfill:
        start = date.fromisoformat(args.backfill)
        days = (today - start).days + 1
    else:
        start = today - timedelta(days=args.days - 1)
        days = args.days

    got = collect(days)

    store = load_store()
    # 안전가드: 수집 결과가 통째로 비면 (API 부분 실패 의심) 기존 데이터를 0 으로
    # 덮어쓰지 않고 중단한다. 실제 무주문 40일 연속은 이 스토어 이력상 비현실적.
    if not got and store["days"]:
        print("[ABORT] 수집 0일 — API 실패 의심, 기존 store 보존 (0 덮어쓰기 방지)")
        return 1
    added = updated = 0
    # 수집 창 내 결측일 = 주문 0 (어제까지만 확정으로 채움, 오늘은 부분치라 있는 것만)
    cur = start
    yesterday = today - timedelta(days=1)
    while cur <= yesterday:
        key = cur.isoformat()
        rec = got.get(key, {"sales_jpy": 0, "orders": 0, "units": 0})
        if key not in store["days"]:
            added += 1
        elif store["days"][key] != rec:
            updated += 1
        store["days"][key] = rec
        cur += timedelta(days=1)
    store["days"] = dict(sorted(store["days"].items()))
    save_store(store)

    total = sum(r["sales_jpy"] for r in store["days"].values())
    recent = [(d, r["sales_jpy"]) for d, r in sorted(store["days"].items())[-7:]]
    print(f"[RKT Sales] +{added}일 신규 / ~{updated}일 갱신 → {STORE.name} (총 {len(store['days'])}일, 누적 ¥{total:,})")
    print("  최근 7일:", " ".join(f"{d[5:]}=¥{s:,}" for d, s in recent))

    if args.update_app:
        SEED.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[RKT Sales] seed → {SEED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
