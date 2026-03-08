"""
run_and_notify.py - 태스크 실행 + 결과 이메일 개별 발송

Usage:
    python tools/run_and_notify.py --task syncly
    python tools/run_and_notify.py --task amazon_ppc
    python tools/run_and_notify.py --task meta_ads
    python tools/run_and_notify.py --task sns_tracker
    python tools/run_and_notify.py --task orbi_kpis
    python tools/run_and_notify.py --task syncly --dry-run
"""

import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
PYTHON = sys.executable
RECIPIENT = os.getenv("PPC_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr")


TASK_DEFS = {
    "syncly": {
        "name": "Syncly Export",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "fetch_syncly_export.py")],
        "emoji": "&#128247;",  # camera
    },
    "sns_tracker": {
        "name": "SNS Content Tracker",
        "cmd": [
            # 두 스크립트 순차 실행
            [PYTHON, "-u", str(TOOLS_DIR / "sync_sns_tab.py")],
            [PYTHON, "-u", str(TOOLS_DIR / "sync_sns_tab_chaenmom.py")],
        ],
        "emoji": "&#128200;",  # chart
        "multi": True,
    },
    "amazon_ppc": {
        "name": "Amazon PPC Daily",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "run_amazon_ppc_daily.py")],
        "emoji": "&#128230;",  # package
    },
    "meta_ads": {
        "name": "Meta Ads Daily",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "run_meta_ads_daily.py")],
        "emoji": "&#128225;",  # megaphone
    },
    "orbi_kpis": {
        "name": "ORBI KPIs Weekly",
        "cmd": [PYTHON, "-u", str(TOOLS_DIR / "run_polar_weekly.py")],
        "emoji": "&#128202;",  # bar chart
    },
}


def run_single(cmd):
    """단일 명령 실행. (ok, lines, seconds)"""
    start = datetime.now()
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT),
            capture_output=True, timeout=1800,
        )
        elapsed = (datetime.now() - start).total_seconds()
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        output = stdout + stderr
        lines = output.strip().splitlines()
        lines.append(f"[run_and_notify] exit_code={result.returncode}")
        return result.returncode == 0, lines, elapsed
    except subprocess.TimeoutExpired:
        return False, ["[TIMEOUT] 30min exceeded"], (datetime.now() - start).total_seconds()
    except Exception as e:
        return False, [f"[ERROR] {e}"], (datetime.now() - start).total_seconds()


def run_task(task_def):
    """태스크 실행 (multi 지원)."""
    if task_def.get("multi"):
        all_lines = []
        total_time = 0
        all_ok = True
        for cmd in task_def["cmd"]:
            ok, lines, sec = run_single(cmd)
            all_lines += lines
            total_time += sec
            if not ok:
                all_ok = False
        return all_ok, all_lines, total_time
    else:
        return run_single(task_def["cmd"])


def diagnose_failure(task_id, lines):
    """실패 원인 분석. 에러 패턴 매칭으로 원인 + 해결 방법 제시."""
    all_text = "\n".join(lines).lower()

    diagnoses = []

    # 인증/토큰 문제
    if any(k in all_text for k in ("401", "unauthorized", "token expired", "invalid_grant", "refresh token")):
        diagnoses.append(("인증 토큰 만료", "해당 API의 refresh token을 갱신하세요. .env 또는 ~/.wat_secrets 확인."))
    if any(k in all_text for k in ("403", "forbidden", "access denied", "permission")):
        diagnoses.append(("권한 부족", "API 권한(scope)을 확인하거나, 계정 접근 권한을 확인하세요."))

    # 네트워크
    if any(k in all_text for k in ("timeout", "timed out", "connectionerror", "connection refused", "네트워크")):
        diagnoses.append(("네트워크/타임아웃", "인터넷 연결 또는 대상 서버 상태를 확인하세요."))

    # Rate limit
    if any(k in all_text for k in ("429", "rate limit", "too many requests", "throttl")):
        diagnoses.append(("API Rate Limit", "요청이 너무 많습니다. 잠시 후 재시도하거나 호출 간격을 늘리세요."))

    # 파일/경로
    if any(k in all_text for k in ("filenotfounderror", "no such file", "not found", "경로")):
        diagnoses.append(("파일/경로 없음", "필요한 데이터 파일이나 credential 파일이 누락되었을 수 있습니다."))

    # 모듈/패키지
    if any(k in all_text for k in ("modulenotfounderror", "no module named", "importerror")):
        diagnoses.append(("Python 패키지 누락", "pip install로 필요한 패키지를 설치하세요."))

    # Syncly 세션
    if task_id == "syncly" and any(k in all_text for k in ("session expired", "login", "continue with google")):
        diagnoses.append(("Syncly 세션 만료", "python tools/fetch_syncly_export.py --login 으로 재로그인하세요."))

    # Playwright
    if any(k in all_text for k in ("playwright", "browser", "chromium")):
        diagnoses.append(("브라우저 자동화 오류", "Playwright 브라우저가 정상 설치되었는지 확인. playwright install chromium"))

    # Google Sheets
    if any(k in all_text for k in ("spreadsheetnotfound", "google sheets", "gspread")):
        diagnoses.append(("Google Sheet 접근 오류", "시트 ID가 맞는지, 서비스 계정에 시트 공유가 되었는지 확인하세요."))

    # ENV 누락
    if any(k in all_text for k in ("env", "api_key", "not set", "none", "missing key")):
        diagnoses.append(("환경변수 누락", ".env 또는 ~/.wat_secrets에 필요한 API 키가 없습니다."))

    # 일반 에러
    if not diagnoses:
        # stderr에서 마지막 에러 라인 찾기
        error_lines = [l for l in lines if any(k in l.lower() for k in ("error", "exception", "traceback", "fail"))]
        if error_lines:
            last_err = error_lines[-1].strip()
            diagnoses.append(("실행 에러", last_err))
        else:
            diagnoses.append(("알 수 없는 오류", "scheduler/logs/ 로그 파일에서 전체 출력을 확인하세요."))

    return diagnoses


def build_body(task_def, task_id, ok, lines, duration):
    """이메일 HTML 본문 생성."""
    today = date.today().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")
    status_color = "#006100" if ok else "#9C0006"
    status_text = "SUCCESS" if ok else "FAILED"

    # 주요 아웃풋 라인 (마지막 15줄)
    summary = lines[-15:] if len(lines) > 15 else lines
    output_html = "<br>".join(
        line.replace("<", "&lt;").replace(">", "&gt;")
        for line in summary
    ) if summary else "<i>출력 없음</i>"

    # FAIL 원인 분석 섹션
    diagnosis_html = ""
    if not ok:
        diagnoses = diagnose_failure(task_id, lines)
        diag_rows = ""
        for cause, fix in diagnoses:
            diag_rows += f"""<tr>
                <td style="padding:6px 10px;border:1px solid #f0c0c0;font-weight:bold;">{cause}</td>
                <td style="padding:6px 10px;border:1px solid #f0c0c0;">{fix}</td>
            </tr>"""
        diagnosis_html = f"""
<h3 style="color:#9C0006;margin-bottom:8px;">Failure Diagnosis</h3>
<table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:16px;">
<tr style="background:#FCE4D6;">
    <th style="padding:8px 10px;border:1px solid #f0c0c0;text-align:left;">원인</th>
    <th style="padding:8px 10px;border:1px solid #f0c0c0;text-align:left;">해결 방법</th>
</tr>
{diag_rows}
</table>"""

    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;">
<h2>{task_def['emoji']} {task_def['name']}</h2>
<table style="font-size:14px;margin-bottom:16px;">
    <tr><td style="padding:4px 12px 4px 0;color:#666;">날짜</td><td><b>{today} {now}</b></td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#666;">상태</td><td style="color:{status_color};font-weight:bold;">{status_text}</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#666;">소요 시간</td><td>{duration:.0f}초</td></tr>
</table>

{diagnosis_html}

<h3 style="margin-bottom:8px;">Output Summary</h3>
<div style="background:#f5f5f5;padding:12px;border-radius:6px;font-family:monospace;font-size:12px;line-height:1.6;white-space:pre-wrap;">{output_html}</div>

<p style="color:#888;font-size:11px;margin-top:24px;">WAT Scheduler — Windows Task Scheduler 자동 발송</p>
</div>"""


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, choices=TASK_DEFS.keys())
    parser.add_argument("--to", default=RECIPIENT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    task_def = TASK_DEFS[args.task]
    print(f"\n[WAT] {task_def['name']} start - {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    ok, lines, duration = run_task(task_def)
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {task_def['name']} ({duration:.0f}s)")

    # 이메일
    status_tag = "OK" if ok else "FAIL"
    subject = f"[WAT] {task_def['name']} - {status_tag} ({date.today()})"
    body = build_body(task_def, args.task, ok, lines, duration)

    if args.dry_run:
        print(f"[Dry Run] Subject: {subject}")
        return

    print(f"[EMAIL] → {args.to}")
    subprocess.run(
        [PYTHON, "-u", str(TOOLS_DIR / "send_gmail.py"),
         "--to", args.to,
         "--subject", subject,
         "--body", body],
        cwd=str(TOOLS_DIR),
    )
    print(f"[완료] {task_def['name']} 이메일 발송 완료")


if __name__ == "__main__":
    main()
