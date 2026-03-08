"""
run_daily_all.py - 매일 오전 8시 전체 자동화 + 결과 이메일 발송

모든 일일 태스크를 순차 실행하고, 결과 서머리를 이메일로 발송한다.

Usage:
    python tools/run_daily_all.py
    python tools/run_daily_all.py --dry-run     # 이메일 발송 없이
    python tools/run_daily_all.py --skip syncly  # 특정 태스크 스킵
"""

import argparse
import os
import subprocess
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
PYTHON = sys.executable
RECIPIENT = os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr")


# ── Task Definitions ─────────────────────────────────────────────────────────

TASKS = [
    {
        "id": "syncly",
        "name": "Syncly Export",
        "desc": "Syncly 인플루언서 포스트 CSV 수집",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "fetch_syncly_export.py")],
    },
    {
        "id": "sns_grosmimi",
        "name": "SNS Tracker (Grosmimi)",
        "desc": "Shopify PR + Syncly D+60 → Google Sheet SNS 탭",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "sync_sns_tab.py")],
    },
    {
        "id": "sns_chaenmom",
        "name": "SNS Tracker (CHA&MOM)",
        "desc": "CHA&MOM 브랜드 SNS 탭 동기화",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "sync_sns_tab_chaenmom.py")],
    },
    {
        "id": "amazon_ppc",
        "name": "Amazon PPC Daily",
        "desc": "아마존 광고 일일 리포트 (HTML + 이메일)",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "run_amazon_ppc_daily.py")],
    },
    {
        "id": "meta_ads",
        "name": "Meta Ads Daily",
        "desc": "메타 광고 일일 리포트 (HTML + 이메일)",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "run_meta_ads_daily.py")],
    },
]


def run_task(task):
    """태스크 실행. (success, output_lines, duration_sec) 반환."""
    start = datetime.now()
    try:
        result = subprocess.run(
            task["cmd"],
            cwd=str(TOOLS_DIR),
            capture_output=True,
            text=True,
            timeout=600,  # 10분 타임아웃
        )
        elapsed = (datetime.now() - start).total_seconds()
        output = (result.stdout or "") + (result.stderr or "")
        lines = output.strip().splitlines()
        # 마지막 10줄만 보관
        summary_lines = lines[-10:] if len(lines) > 10 else lines
        return result.returncode == 0, summary_lines, elapsed
    except subprocess.TimeoutExpired:
        elapsed = (datetime.now() - start).total_seconds()
        return False, ["[TIMEOUT] 10분 초과"], elapsed
    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        return False, [f"[ERROR] {str(e)}"], elapsed


def build_email_body(results):
    """결과를 HTML 이메일 본문으로 변환."""
    today = date.today().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")

    ok_count = sum(1 for r in results if r["ok"])
    fail_count = len(results) - ok_count

    # Status badge
    if fail_count == 0:
        status = '<span style="color:#006100;font-weight:bold;">ALL PASS</span>'
    else:
        status = f'<span style="color:#9C0006;font-weight:bold;">{fail_count} FAILED</span>'

    rows = ""
    for r in results:
        icon = "&#9989;" if r["ok"] else "&#10060;"
        dur = f'{r["duration"]:.0f}s'
        detail_lines = "<br>".join(r["summary"][-5:]) if r["summary"] else "-"
        rows += f"""<tr>
            <td style="padding:6px;border:1px solid #ddd;">{icon}</td>
            <td style="padding:6px;border:1px solid #ddd;"><b>{r['name']}</b><br><span style="color:#666;font-size:11px;">{r['desc']}</span></td>
            <td style="padding:6px;border:1px solid #ddd;">{dur}</td>
            <td style="padding:6px;border:1px solid #ddd;font-size:11px;font-family:monospace;white-space:pre-wrap;">{detail_lines}</td>
        </tr>"""

    body = f"""<h2>WAT Daily Report — {today} {now}</h2>
<p>Status: {status} ({ok_count}/{len(results)} 성공)</p>

<table style="border-collapse:collapse;width:100%;font-size:13px;">
<tr style="background:#002060;color:white;">
    <th style="padding:8px;border:1px solid #ddd;width:30px;"></th>
    <th style="padding:8px;border:1px solid #ddd;">Task</th>
    <th style="padding:8px;border:1px solid #ddd;width:50px;">Time</th>
    <th style="padding:8px;border:1px solid #ddd;">Output Summary</th>
</tr>
{rows}
</table>

<p style="color:#888;font-size:11px;margin-top:20px;">자동 발송 — WAT Scheduler (Windows Task Scheduler)</p>"""

    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="이메일 발송 없이 실행")
    parser.add_argument("--skip", nargs="*", default=[], help="스킵할 태스크 ID")
    parser.add_argument("--to", default=RECIPIENT)
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  WAT Daily All — {date.today()} {datetime.now().strftime('%H:%M')}")
    print(f"{'='*60}")

    results = []

    for task in TASKS:
        if task["id"] in args.skip:
            print(f"\n[SKIP] {task['name']}")
            continue

        print(f"\n[RUN] {task['name']} — {task['desc']}")
        ok, summary, duration = run_task(task)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {task['name']} ({duration:.0f}s)")
        for line in summary[-3:]:
            print(f"  {line}")

        results.append({
            "name": task["name"],
            "desc": task["desc"],
            "ok": ok,
            "summary": summary,
            "duration": duration,
        })

    # ── 이메일 발송 ──────────────────────────────────────────────────────────
    ok_count = sum(1 for r in results if r["ok"])
    fail_count = len(results) - ok_count
    subject_status = "ALL PASS" if fail_count == 0 else f"{fail_count} FAILED"
    subject = f"[WAT Daily] {date.today()} — {subject_status} ({ok_count}/{len(results)})"

    body = build_email_body(results)

    if args.dry_run:
        print(f"\n[Dry Run] 이메일 발송 건너뜀")
        print(f"  To: {args.to}")
        print(f"  Subject: {subject}")
        return

    print(f"\n[EMAIL] {args.to} → {subject}")
    result = subprocess.run(
        [PYTHON, "-u", str(TOOLS_DIR / "send_gmail.py"),
         "--to", args.to,
         "--subject", subject,
         "--body", body],
        cwd=str(TOOLS_DIR),
    )
    if result.returncode != 0:
        print("[ERROR] 이메일 발송 실패")
        sys.exit(1)

    print(f"\n[완료] 전체 {len(results)}개 태스크 실행, 이메일 발송 완료!")


if __name__ == "__main__":
    main()
