"""
run_polar_weekly.py - Polar Financial Model 주간 자동 실행 + 이메일 발송

데이터 수집 (no_polar/) → polar_financial_model.py → Excel 이메일 발송

Usage:
    python tools/run_polar_weekly.py                     # 자동: --end=전월
    python tools/run_polar_weekly.py --end 2026-02       # Feb 28까지
    python tools/run_polar_weekly.py --dry-run           # 이메일 발송 없이
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT      = TOOLS_DIR.parent
NO_POLAR  = TOOLS_DIR / "no_polar"
DATA_STORAGE = ROOT / "Data Storage" / "polar"


def run(cmd, label=""):
    tag = label or Path(cmd[2]).stem if len(cmd) > 2 else ""
    print(f"\n[{tag}] {' '.join(str(c) for c in cmd)}")
    sys.stdout.flush()
    result = subprocess.run([str(c) for c in cmd], cwd=str(TOOLS_DIR))
    if result.returncode != 0:
        print(f"  [WARN] {tag} 실패 (exit {result.returncode}) - 계속 진행")
    return result.returncode == 0


def prev_month() -> str:
    today = date.today()
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)
    return last_month.strftime("%Y-%m")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01", help="시작 월 YYYY-MM")
    parser.add_argument("--end",   default=prev_month(), help="종료 월 YYYY-MM (기본: 전월)")
    parser.add_argument("--to",    default=os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr"))
    parser.add_argument("--dry-run", action="store_true", help="이메일 발송 없이 Excel만 생성")
    args = parser.parse_args()

    python = sys.executable
    print(f"\n[Polar Weekly] 데이터 범위: {args.start} ~ {args.end}")
    print(f"[Polar Weekly] 실행일: {date.today()}")

    # ── Step 1: 데이터 수집 ──────────────────────────────────────────────────
    fetchers = [
        (NO_POLAR / "fetch_meta_ads_monthly.py",     "Meta Ads Q6"),
        (NO_POLAR / "fetch_shopify_sales_monthly.py","Shopify Sales Q1"),
        (NO_POLAR / "fetch_shopify_cogs_monthly.py", "Shopify COGS Q2"),
        (NO_POLAR / "fetch_amazon_sales_monthly.py", "Amazon Sales Q3"),
        (NO_POLAR / "fetch_amazon_ads_monthly.py",   "Amazon Ads Q5"),
        (NO_POLAR / "fetch_google_ads_monthly.py",   "Google Ads Q7"),
    ]
    print("\n[Step 1] 데이터 수집 중...")
    for script, label in fetchers:
        run([python, "-u", script, "--start", args.start, "--end", args.end], label=label)

    # ── Step 1b: 누락 데이터 파일 플레이스홀더 ──────────────────────────────
    polar_data = ROOT / ".tmp" / "polar_data"
    polar_data.mkdir(parents=True, exist_ok=True)
    empty_table = {"tableData": [], "totalData": [{}]}
    placeholders = {
        "q8_tiktok_ads_campaign.json": empty_table,
        "q9_meta_campaign_ids.json": {"campaigns": []},
    }
    for fname, default in placeholders.items():
        fpath = polar_data / fname
        if not fpath.exists():
            fpath.write_text(json.dumps(default), encoding="utf-8")
            print(f"  [PLACEHOLDER] {fname} 생성 (데이터 없음)")

    # ── Step 2: Financial Model 생성 ─────────────────────────────────────────
    print("\n[Step 2] Financial Model Excel 생성 중...")
    ok = run([python, "-u", TOOLS_DIR / "polar_financial_model.py"], label="polar_financial_model")
    if not ok:
        print("[ERROR] Financial Model 생성 실패")
        sys.exit(1)

    # ── Step 3: Excel 파일 찾기 ──────────────────────────────────────────────
    DATA_STORAGE.mkdir(parents=True, exist_ok=True)
    excel_files = sorted(DATA_STORAGE.glob("financial_model_*.xlsx"))
    if not excel_files:
        print("[ERROR] Excel 파일을 찾을 수 없음")
        sys.exit(1)
    excel_path = excel_files[-1]
    print(f"\n[Step 3] Excel: {excel_path.name}")

    if args.dry_run:
        print(f"\n[Dry Run] 이메일 발송 건너뜀. 파일: {excel_path}")
        return

    # ── Step 4: 이메일 발송 ──────────────────────────────────────────────────
    subject = (
        f"[Financial Model] 주간 리포트 {date.today()} "
        f"| 데이터: {args.start} ~ {args.end}"
    )
    body = f"""<h2>Orbiters Financial Model</h2>
<p>첨부 파일: <b>{excel_path.name}</b></p>
<ul>
  <li>데이터 범위: {args.start} ~ {args.end}</li>
  <li>생성일: {date.today()}</li>
</ul>
<p style="color:#888;font-size:12px;">자동 발송 (GitHub Actions)</p>"""

    print(f"\n[Step 4] 이메일 발송 중 -> {args.to}")
    result = subprocess.run(
        [python, "-u", str(TOOLS_DIR / "send_gmail.py"),
         "--to", args.to,
         "--subject", subject,
         "--body", body,
         "--attachment", str(excel_path)],
        cwd=str(TOOLS_DIR),
    )
    if result.returncode != 0:
        print("[ERROR] 이메일 발송 실패")
        sys.exit(1)

    print(f"\n[완료] {args.to} 발송 완료!")


if __name__ == "__main__":
    main()
