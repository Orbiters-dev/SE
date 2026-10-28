"""
tools/build_vtr_baseline.py — Phase 1 VTR baseline 분포 + 임계 시뮬레이션

Grosmimi JP 인플루언서 영상의 D+3 VTR(View-to-Follower Ratio)을 PAID/GIFT × micro/nano
4-way 풀로 분류해서 히스토그램 + P50/P70 임계 시뮬레이션 산출.

Data sources:
  1. Data Keeper: content_posts (followers, post_date) + content_metrics_daily (views D+3)
  2. Master Sheet (1wkue4G7FP.../Grosmimi 탭): username → Deal Type (PAID/GIFT) 매칭

Pool classification:
  - micro: followers >= 10,000
  - nano: followers < 10,000

Usage:
  python tools/build_vtr_baseline.py --days 60
  python tools/build_vtr_baseline.py --days 60 --output .tmp/vtr_distribution.png
"""

import argparse
import io
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import gspread
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from data_keeper_client import DataKeeper

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SHEET_ID = "1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU"
TAB_GID = 386147805  # Grosmimi 탭

NANO_THRESHOLD = 10_000  # follower < 10K = nano, >= 10K = micro

POOL_KEYS = ["PAID_micro", "PAID_nano", "GIFT_micro", "GIFT_nano"]
POOL_TITLES = {
    "PAID_micro": "PAID × Micro (>=10K)",
    "PAID_nano": "PAID × Nano (<10K)",
    "GIFT_micro": "GIFT × Micro (>=10K)",
    "GIFT_nano": "GIFT × Nano (<10K)",
}


SHEET_HEADER_ROW = 2  # 0-indexed (row 3 in sheet UI)
COL_CREATOR_ID = 3    # IG handle (예: mon_yuru.ikuji)
COL_DEAL_TYPE = 23    # X열 (Paid / Unpaid)
COL_URL = 16          # post URL
COL_VIEWS = 33        # 시트 누적 view (참고용 — D+3 아님)


def fetch_master_sheet() -> dict[str, dict]:
    """Master Sheet에서 IG handle -> {deal, url, views_cum} 매핑 반환."""
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
    if not os.path.exists(sa_path):
        alt = os.path.join(DIR, "..", sa_path)
        if os.path.exists(alt):
            sa_path = alt
    creds = Credentials.from_service_account_file(
        sa_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)
    ws = next((w for w in sheet.worksheets() if w.id == TAB_GID), None)
    if ws is None:
        raise RuntimeError(f"Tab gid={TAB_GID} not found in sheet {SHEET_ID}")
    rows = ws.get_all_values()
    if len(rows) <= SHEET_HEADER_ROW + 1:
        return {}

    mapping: dict[str, dict] = {}
    for row in rows[SHEET_HEADER_ROW + 1:]:
        if COL_CREATOR_ID >= len(row):
            continue
        handle = row[COL_CREATOR_ID].strip().lstrip("@").lower()
        if not handle:
            continue
        deal_raw = row[COL_DEAL_TYPE].strip().lower() if COL_DEAL_TYPE < len(row) else ""
        if "paid" in deal_raw and "unpaid" not in deal_raw:
            deal = "PAID"
        elif "unpaid" in deal_raw or "gift" in deal_raw or "seeding" in deal_raw:
            deal = "GIFT"
        else:
            continue
        url = row[COL_URL].strip() if COL_URL < len(row) else ""
        views_cum_raw = row[COL_VIEWS].strip() if COL_VIEWS < len(row) else ""
        try:
            views_cum = int(views_cum_raw.replace(",", "")) if views_cum_raw else 0
        except ValueError:
            views_cum = 0
        # 한 handle에 영상 여러 개일 수 있음 → URL로 키 분리는 다음 단계. 일단 첫 매칭 유지
        if handle not in mapping:
            mapping[handle] = {"deal": deal, "url": url, "views_cum": views_cum}
    return mapping


def fetch_jp_posts(days: int, handle_filter: set[str] | None = None) -> list[dict]:
    """JP region 또는 Master Sheet handle 매칭 영상 fetch.

    brand 라벨이 비어있는 영상도 username이 우리 인플루언서면 포함.
    """
    dk = DataKeeper()
    date_from = (date.today() - timedelta(days=days)).isoformat()
    rows = dk.get("content_posts", date_from=date_from, limit=10000)
    result: list[dict] = []
    for r in rows:
        uname = str(r.get("username", "")).strip().lstrip("@").lower()
        region = str(r.get("region", "")).lower()
        brand = str(r.get("brand", "")).lower()
        # 매칭 조건: handle이 Master Sheet에 있거나 / brand=grosmimi 명시 / region=jp+brand 비어 있어도 handle 매칭
        if handle_filter is not None:
            if uname in handle_filter:
                result.append(r)
                continue
        if region in ("jp", "both") and (brand == "grosmimi" or brand == ""):
            result.append(r)
    return result


def fetch_metrics_window(days_buffer: int) -> dict[tuple, int]:
    """content_metrics_daily 윈도우 fetch. {(post_id, date_str): views} 반환."""
    dk = DataKeeper()
    date_from = (date.today() - timedelta(days=days_buffer)).isoformat()
    rows = dk.get("content_metrics_daily", date_from=date_from, limit=50000)
    result: dict[tuple, int] = {}
    for r in rows:
        pid = r.get("post_id")
        d = r.get("date")
        if pid and d:
            d_str = str(d)[:10]
            result[(pid, d_str)] = int(r.get("views") or 0)
    return result


def compute_d3_vtr(posts: list[dict], metrics: dict[tuple, int], master: dict[str, dict]) -> list[dict]:
    """각 post의 D+3 VTR 계산 + 풀 분류. master entry는 {deal, url, views_cum}."""
    out: list[dict] = []
    for p in posts:
        followers = int(p.get("followers") or 0)
        if followers <= 0:
            continue
        post_date_raw = p.get("post_date")
        if not post_date_raw:
            continue
        if isinstance(post_date_raw, str):
            try:
                pd = datetime.strptime(post_date_raw[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
        else:
            pd = post_date_raw
        d3 = (pd + timedelta(days=3)).isoformat()
        views = metrics.get((p["post_id"], d3))
        if views is None or views <= 0:
            continue
        uname = str(p.get("username", "")).strip().lstrip("@").lower()
        entry = master.get(uname)
        if not entry:
            continue
        deal = entry["deal"]
        size = "nano" if followers < NANO_THRESHOLD else "micro"
        vtr = views / followers
        out.append({
            "post_id": p["post_id"],
            "username": uname,
            "followers": followers,
            "views_d3": views,
            "vtr": round(vtr, 4),
            "post_date": pd.isoformat(),
            "deal": deal,
            "size": size,
            "url": p.get("url", ""),
        })
    return out


def group_4way(records: list[dict]) -> dict[str, list[float]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in records:
        key = f"{r['deal']}_{r['size']}"
        groups[key].append(r["vtr"])
    return dict(groups)


def plot_histograms(groups: dict[str, list[float]], output_path: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, key in zip(axes.flat, POOL_KEYS):
        vals = sorted(groups.get(key, []))
        title = POOL_TITLES[key]
        if len(vals) < 3:
            ax.text(0.5, 0.5, f"N={len(vals)}\n(표본 부족)", ha="center", va="center", fontsize=14)
            ax.set_title(title)
            ax.set_xticks([])
            ax.set_yticks([])
            continue
        ax.hist(vals, bins=min(20, max(5, len(vals) // 2)), edgecolor="black", color="#4F81BD")
        p50 = float(np.percentile(vals, 50))
        p70 = float(np.percentile(vals, 70))
        ax.axvline(p50, color="orange", linestyle="--", linewidth=2, label=f"P50 = {p50:.3f}")
        ax.axvline(p70, color="red", linestyle="--", linewidth=2, label=f"P70 = {p70:.3f}")
        ax.set_title(f"{title}  (N={len(vals)})")
        ax.set_xlabel("VTR = views D+3 / followers")
        ax.set_ylabel("Count")
        ax.legend()
    fig.suptitle("Grosmimi JP — D+3 VTR 분포 (4-way 풀)", fontsize=16, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output_path, dpi=110)
    plt.close()


def simulate_thresholds(groups: dict[str, list[float]]) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("D+3 VTR 임계 시뮬레이션 — 풀별 P50 / P70 + 통과율")
    lines.append("=" * 70)
    lines.append(f"{'Pool':<14} {'N':>4} {'P50':>9} {'P70':>9} {'>P50%':>8} {'>P70%':>8}")
    lines.append("-" * 70)
    for key in POOL_KEYS:
        vals = groups.get(key, [])
        if not vals:
            lines.append(f"{key:<14} {0:>4} {'-':>9} {'-':>9} {'-':>8} {'-':>8}")
            continue
        p50 = float(np.percentile(vals, 50))
        p70 = float(np.percentile(vals, 70))
        pass50 = sum(1 for v in vals if v > p50) / len(vals) * 100
        pass70 = sum(1 for v in vals if v > p70) / len(vals) * 100
        lines.append(
            f"{key:<14} {len(vals):>4} {p50:>9.4f} {p70:>9.4f} {pass50:>7.1f}% {pass70:>7.1f}%"
        )
    lines.append("-" * 70)
    lines.append("적정 통과율 30~50% — 그 구간 들어오는 임계를 후보로 잡는다.")
    lines.append("N < 20 풀은 percentile 노이즈 큼 → 통합 풀 fallback 검토.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60, help="Historical window (일)")
    parser.add_argument("--output", type=str, default=".tmp/vtr_distribution.png")
    parser.add_argument("--report", type=str, default=".tmp/vtr_simulation.txt")
    parser.add_argument("--records", type=str, default=".tmp/vtr_records.json")
    args = parser.parse_args()

    load_dotenv()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.records).parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Fetching Master Sheet (Grosmimi 탭) Deal Type 매핑 ...")
    master = fetch_master_sheet()
    paid_n = sum(1 for v in master.values() if v["deal"] == "PAID")
    gift_n = sum(1 for v in master.values() if v["deal"] == "GIFT")
    print(f"  -> {len(master)} 매핑 (PAID={paid_n}, GIFT={gift_n})")
    if not master:
        print("  [WARN] Master Sheet 매핑 0건. Sheet 구조 변경 확인 필요.")

    handle_set = set(master.keys())
    print(f"[2/5] Fetching content_posts (last {args.days} days) + handle 매칭 ...")
    posts = fetch_jp_posts(args.days, handle_filter=handle_set)
    matched = sum(1 for p in posts if str(p.get("username", "")).lstrip("@").lower() in handle_set)
    print(f"  -> {len(posts)} posts ({matched} Master Sheet 매칭)")

    print(f"[3/5] Fetching content_metrics_daily ({args.days + 5} days buffer) ...")
    metrics = fetch_metrics_window(args.days + 5)
    print(f"  -> {len(metrics)} metric rows")

    print("[4/5] Computing D+3 VTR + classifying 4-way pools ...")
    records = compute_d3_vtr(posts, metrics, master)
    print(f"  -> {len(records)} 영상 (Master Sheet 매칭 + D+3 metric 모두 존재)")

    groups = group_4way(records)
    for k in POOL_KEYS:
        print(f"     {k}: N={len(groups.get(k, []))}")

    with open(args.records, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

    print("[5/5] Plotting histograms + threshold simulation ...")
    plot_histograms(groups, args.output)
    report = simulate_thresholds(groups)
    print()
    print(report)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)

    print()
    print("[OK] 산출물:")
    print(f"  {args.output}")
    print(f"  {args.report}")
    print(f"  {args.records}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
