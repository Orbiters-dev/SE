"""
Anthropic API Billing Tracker
==============================
월별/누적 API 비용을 조회합니다.
Admin API Key 필요: .env 에 ANTHROPIC_ADMIN_KEY=sk-ant-admin... 설정

Usage:
    python tools/fetch_anthropic_billing.py              # 최근 12개월
    python tools/fetch_anthropic_billing.py --months 6
    python tools/fetch_anthropic_billing.py --from 2025-06 --to 2026-03
    python tools/fetch_anthropic_billing.py --csv        # CSV 저장
"""

import os
import sys
import argparse
import base64
import csv
import time
import requests
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import env_loader  # auto-loads .env

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ADMIN_KEY = os.environ.get("ANTHROPIC_ADMIN_KEY", "")
BASE_URL = "https://api.anthropic.com"
HEADERS = {
    "anthropic-version": "2023-06-01",
    "x-api-key": ADMIN_KEY,
}
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".tmp")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def _get(url: str, params: list, retries: int = 6) -> dict:
    for attempt in range(retries):
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if resp.status_code == 429:
            wait = 2 ** attempt * 10  # 10, 20, 40, 80, 160, 320s
            print(f"\n[rate limit] {wait}s wait...", end="", flush=True)
            time.sleep(wait)
            continue
        if resp.status_code == 401:
            print("\n[ERROR] Admin API Key 인증 실패. .env 의 ANTHROPIC_ADMIN_KEY 확인")
            sys.exit(1)
        if resp.status_code == 403:
            print("\n[ERROR] 권한 없음. Admin Key(sk-ant-admin...) 인지 확인")
            sys.exit(1)
        if not resp.ok:
            print(f"\n[ERROR] {resp.status_code}: {resp.text[:300]}")
            sys.exit(1)
        return resp.json()
    print("\n[ERROR] Rate limit 재시도 초과")
    sys.exit(1)


def fetch_cost_for_period(start: str, end: str) -> list[dict]:
    """
    start/end: 'YYYY-MM-DDT00:00:00Z' 형태
    cursor pagination: next_page 는 base64(다음 starting_at) 이므로
    해당 cursor 를 다음 starting_at 으로 사용해 이어서 호출.
    반환: [{starting_at, ending_at, results:[{amount, description, model,...}]}]
    """
    url = f"{BASE_URL}/v1/organizations/cost_report"
    all_rows = []
    cur_start = start

    while True:
        params = [
            ("starting_at", cur_start),
            ("ending_at", end),
            ("bucket_width", "1d"),
            ("group_by[]", "description"),
        ]
        data = _get(url, params)
        all_rows.extend(data.get("data", []))

        if data.get("has_more") and data.get("next_page"):
            token = data["next_page"]
            # next_page = "page_<base64(timestamp)>" → decode to get next starting_at
            encoded = token[5:]  # strip "page_"
            encoded += "=" * (-len(encoded) % 4)  # fix padding
            next_start = base64.b64decode(encoded).decode("utf-8")
            # stop if cursor has passed the end boundary
            if next_start >= end:
                break
            cur_start = next_start
        else:
            break

    return all_rows


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
def collect_monthly_costs(start_ym: str, end_ym: str) -> dict[str, dict]:
    """
    start_ym, end_ym: 'YYYY-MM'
    30일 청크로 분할 → 월별 집계
    Returns: {
        'YYYY-MM': {
            'cost_usd': float,
            'by_model': {'claude-sonnet-4-6': float, ...},
            'by_type': {'tokens': float, 'web_search': float, ...}
        }
    }
    """
    start_dt = datetime.strptime(start_ym, "%Y-%m").replace(tzinfo=timezone.utc)
    end_base = datetime.strptime(end_ym, "%Y-%m").replace(tzinfo=timezone.utc)
    end_dt = end_base + relativedelta(months=1) - relativedelta(days=1)

    monthly: dict[str, dict] = {}
    chunk_start = start_dt

    while chunk_start <= end_dt:
        chunk_end = min(chunk_start + relativedelta(days=29), end_dt)
        s = chunk_start.strftime("%Y-%m-%dT00:00:00Z")
        e = chunk_end.strftime("%Y-%m-%dT23:59:59Z")

        rows = fetch_cost_for_period(s, e)
        print(".", end="", flush=True)
        time.sleep(1)  # rate limit 방지

        for row in rows:
            month = row.get("starting_at", "")[:7]  # 'YYYY-MM'
            if not month:
                continue
            if month not in monthly:
                monthly[month] = {"cost_usd": 0.0, "by_model": {}, "by_type": {}}

            for result in row.get("results", []):
                amt = float(result.get("amount", 0) or 0)
                model = result.get("model") or "other"
                cost_type = result.get("cost_type") or "other"

                monthly[month]["cost_usd"] += amt
                monthly[month]["by_model"][model] = monthly[month]["by_model"].get(model, 0.0) + amt
                monthly[month]["by_type"][cost_type] = monthly[month]["by_type"].get(cost_type, 0.0) + amt

        chunk_start = chunk_end + relativedelta(days=1)

    return monthly


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def print_summary(monthly: dict[str, dict]):
    months = sorted(monthly.keys())
    cumulative = 0.0
    total_tokens = 0.0
    total_search = 0.0

    print("\n" + "=" * 78)
    print(f"{'Month':<10}  {'Monthly $':>10}  {'Cumulative $':>13}  Top Model")
    print("-" * 78)

    for m in months:
        d = monthly[m]
        cost = d["cost_usd"]
        cumulative += cost

        by_model = d["by_model"]
        top_model = max(by_model, key=by_model.get) if by_model else "-"
        # 짧게 표시
        model_short = top_model.replace("claude-", "").replace("-20251001", "")
        model_label = f"{model_short} (${by_model.get(top_model, 0):,.0f})"

        total_tokens += d["by_type"].get("tokens", 0)
        total_search += d["by_type"].get("web_search", 0)

        print(f"{m:<10}  ${cost:>9,.0f}  ${cumulative:>12,.0f}  {model_label}")

    print("=" * 78)
    print(f"{'TOTAL':<10}  ${cumulative:>9,.0f}  (tokens: ${total_tokens:,.0f} / web search: ${total_search:,.0f})")
    print("=" * 78)

    # 모델별 전체 합산
    all_models: dict[str, float] = {}
    for d in monthly.values():
        for model, amt in d["by_model"].items():
            all_models[model] = all_models.get(model, 0.0) + amt

    if all_models:
        print("\n[ Model Breakdown - All Time ]")
        for model, amt in sorted(all_models.items(), key=lambda x: -x[1]):
            pct = amt / cumulative * 100 if cumulative else 0
            model_short = model.replace("claude-", "").replace("-20251001", "")
            print(f"  {model_short:<35} ${amt:>10,.0f}  ({pct:.1f}%)")


def save_csv(monthly: dict[str, dict], filepath: str):
    months = sorted(monthly.keys())
    cumulative = 0.0
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Month", "Cost_USD", "Cumulative_USD", "Tokens_USD", "WebSearch_USD"])
        for m in months:
            d = monthly[m]
            cost = d["cost_usd"]
            cumulative += cost
            writer.writerow([
                m,
                f"{cost:.2f}",
                f"{cumulative:.2f}",
                f"{d['by_type'].get('tokens', 0):.2f}",
                f"{d['by_type'].get('web_search', 0):.2f}",
            ])

    print(f"\n[CSV] {filepath}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Anthropic API 누적 빌링 트래커")
    parser.add_argument("--months", type=int, default=12, help="최근 N개월 (기본 12)")
    parser.add_argument("--from", dest="from_ym", default=None, help="시작월 YYYY-MM")
    parser.add_argument("--to", dest="to_ym", default=None, help="종료월 YYYY-MM")
    parser.add_argument("--csv", action="store_true", help="CSV 저장")
    args = parser.parse_args()

    if not ADMIN_KEY:
        print("\n[ERROR] ANTHROPIC_ADMIN_KEY 없음. .env 에 추가:")
        print("  ANTHROPIC_ADMIN_KEY=sk-ant-admin...")
        sys.exit(1)

    now = datetime.now(tz=timezone.utc)
    start_ym = args.from_ym or (now - relativedelta(months=args.months - 1)).strftime("%Y-%m")
    end_ym = args.to_ym or now.strftime("%Y-%m")

    print(f"\nAnthropist Billing Tracker  |  {start_ym} ~ {end_ym}")
    print("Fetching", end="", flush=True)

    monthly = collect_monthly_costs(start_ym, end_ym)
    print(" done")

    if not monthly:
        print("[INFO] 데이터 없음")
        return

    print_summary(monthly)

    if args.csv:
        ts = now.strftime("%Y%m%d")
        path = os.path.join(OUTPUT_DIR, f"anthropic_billing_{start_ym}_{end_ym}_{ts}.csv")
        save_csv(monthly, path)


if __name__ == "__main__":
    main()
