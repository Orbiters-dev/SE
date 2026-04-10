"""
CI Watchdog — GitHub Actions scheduled workflow monitor.
Checks all scheduled workflows for failures/missed runs and sends Teams alert.

Usage:
    python tools/ci_watchdog.py                    # check last 24h, alert on failure
    python tools/ci_watchdog.py --hours 12         # check last 12h
    python tools/ci_watchdog.py --dry-run          # print report only, no Teams alert
    python tools/ci_watchdog.py --list             # list all monitored workflows
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import ssl

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

REPO = os.getenv("GITHUB_REPOSITORY", "Orbiters-dev/WJ-Test1")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
TEAMS_WEBHOOK = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")
SSL_CTX = ssl.create_default_context()

# Workflows to monitor: (filename, display_name, expected_schedule_description)
MONITORED_WORKFLOWS = [
    # === Weekly IG ===
    ("weekly_ig_content.yml", "인획이 기획안", "매주 금 14:00 KST"),
    ("wednesday_ig_competitor.yml", "IG 경쟁사 분석", "매주 수 10:00 KST"),
    # === Twitter Squad ===
    ("kikaku.yml", "기획맨 (주간 트윗 플랜)", "매주 금 09:00 KST"),
    ("tweet.yml", "트윗 자동투고", "매일 10:00/19:00 KST"),
    ("hashtag.yml", "해시태그 조사맨", "매주 목 08:00 KST"),
    ("chousa.yml", "조사맨", "매주 화/목 08:00 KST"),
    ("kantoku.yml", "감독", "매일 09:00 KST"),
    ("soukantoku.yml", "총감독", "매일 09:00 KST"),
    ("commenter.yml", "코멘터", "매일"),
    # === Data & PPC ===
    ("data_keeper.yml", "Data Keeper", "매일 17:00/05:00 KST"),
    ("amazon_ppc_daily.yml", "Amazon PPC Daily", "매일"),
    ("meta_ads_daily.yml", "Meta Ads Daily", "매일 17:00/05:00 KST"),
    ("syncly_daily.yml", "Syncly Daily Crawl", "매일 08:00 KST"),
    # === Weekly ===
    ("einstein_weekly.yml", "아인슈타인 주간", "매주 월 09:00 KST"),
    ("einstein_daily.yml", "아인슈타인 데일리", "매일 18:00 KST"),
    ("kpi_weekly.yml", "KPI Weekly", "매주 일 08:00 KST"),
    # === Other ===
    ("communicator.yml", "커뮤니케이터", "매일 12h 간격"),
    ("ppc_dashboard_action.yml", "PPC Dashboard", "매일 07:00 KST"),
]


# ── GitHub API ────────────────────────────────────────────────────────────────

def _gh_api(path: str) -> dict:
    """Call GitHub API with token auth."""
    url = f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    req = Request(url, headers=headers)
    try:
        resp = urlopen(req, context=SSL_CTX, timeout=15)
        return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        logger.warning(f"GitHub API error: {e.code} for {path}")
        return {}


def get_workflow_runs(workflow_file: str, hours: int) -> list[dict]:
    """Get runs for a specific workflow file within the last N hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = f"/repos/{REPO}/actions/workflows/{workflow_file}/runs?per_page=10&created=%3E{since}"
    data = _gh_api(path)
    return data.get("workflow_runs", [])


# ── Check Logic ──────────────────────────────────────────────────────────────

def check_all_workflows(hours: int) -> list[dict]:
    """Check all monitored workflows. Returns list of status dicts."""
    results = []

    for wf_file, display_name, schedule_desc in MONITORED_WORKFLOWS:
        runs = get_workflow_runs(wf_file, hours)

        if not runs:
            results.append({
                "name": display_name,
                "file": wf_file,
                "schedule": schedule_desc,
                "status": "no_runs",
                "detail": f"지난 {hours}시간 내 실행 기록 없음",
            })
            continue

        # Check most recent run
        latest = runs[0]
        conclusion = latest.get("conclusion")
        status = latest.get("status")
        created = latest.get("created_at", "")

        if status != "completed":
            results.append({
                "name": display_name,
                "file": wf_file,
                "schedule": schedule_desc,
                "status": "running",
                "detail": f"실행 중 (#{latest.get('run_number')})",
                "created": created,
            })
        elif conclusion == "success":
            results.append({
                "name": display_name,
                "file": wf_file,
                "schedule": schedule_desc,
                "status": "success",
                "detail": f"성공 (#{latest.get('run_number')})",
                "created": created,
            })
        else:
            # failure, cancelled, etc.
            results.append({
                "name": display_name,
                "file": wf_file,
                "schedule": schedule_desc,
                "status": "failure",
                "detail": f"{conclusion} (#{latest.get('run_number')})",
                "created": created,
                "url": latest.get("html_url", ""),
            })

    return results


# ── Report ───────────────────────────────────────────────────────────────────

def print_report(results: list[dict], hours: int) -> tuple[int, int, int]:
    """Print results table. Returns (success, fail, no_runs) counts."""
    success = sum(1 for r in results if r["status"] == "success")
    fail = sum(1 for r in results if r["status"] == "failure")
    no_runs = sum(1 for r in results if r["status"] == "no_runs")
    running = sum(1 for r in results if r["status"] == "running")

    print(f"\n{'='*65}")
    print(f"  CI Watchdog Report | Last {hours}h | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*65}")
    print(f"  OK: {success} | FAIL: {fail} | NO RUNS: {no_runs} | RUNNING: {running}")
    print(f"{'-'*65}")

    for r in results:
        icon = {"success": "OK", "failure": "FAIL", "no_runs": "SKIP", "running": "RUN"}.get(r["status"], "??")
        print(f"  [{icon:4s}] {r['name']:20s} | {r['schedule']:22s} | {r['detail']}")

    print(f"{'='*65}\n")
    return success, fail, no_runs


# ── Teams Alert ──────────────────────────────────────────────────────────────

def send_teams_alert(results: list[dict], hours: int) -> bool:
    """Send Teams alert if there are failures."""
    import requests

    failures = [r for r in results if r["status"] == "failure"]
    if not failures:
        logger.info("No failures — skipping Teams alert")
        return True

    if not TEAMS_WEBHOOK:
        logger.warning("TEAMS_WEBHOOK_URL_SEEUN not set — cannot send alert")
        return False

    facts = []
    for f in failures:
        facts.append({"title": f["name"], "value": f"{f['detail']} | {f['schedule']}"})

    body = [
        {
            "type": "TextBlock",
            "text": f"CI Watchdog: {len(failures)}건 실패 감지",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Attention",
        },
        {
            "type": "FactSet",
            "facts": facts,
        },
        {
            "type": "TextBlock",
            "text": f"지난 {hours}시간 기준 | {datetime.now().strftime('%Y-%m-%d %H:%M KST')}",
            "size": "Small",
            "color": "Default",
            "isSubtle": True,
        },
    ]

    # Add action button to GitHub Actions
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": body,
                "actions": [{
                    "type": "Action.OpenUrl",
                    "title": "GitHub Actions 확인",
                    "url": f"https://github.com/{REPO}/actions",
                }],
            },
        }],
    }

    try:
        resp = requests.post(TEAMS_WEBHOOK, json=payload, timeout=15)
        if resp.status_code in (200, 202):
            logger.info(f"Teams alert sent: {len(failures)} failures reported")
            return True
        else:
            logger.error(f"Teams webhook failed: {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CI Watchdog — monitor scheduled workflows")
    parser.add_argument("--hours", type=int, default=24, help="Check runs within last N hours (default 24)")
    parser.add_argument("--dry-run", action="store_true", help="Print report only, no Teams alert")
    parser.add_argument("--list", action="store_true", help="List all monitored workflows")
    args = parser.parse_args()

    if args.list:
        print(f"\nMonitored workflows ({len(MONITORED_WORKFLOWS)}):")
        for wf_file, name, schedule in MONITORED_WORKFLOWS:
            print(f"  {name:25s} | {schedule:22s} | {wf_file}")
        return

    # Try to get token from git credential manager if not in env
    global GITHUB_TOKEN
    if not GITHUB_TOKEN:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "credential", "fill"],
                input="protocol=https\nhost=github.com\n",
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if line.startswith("password="):
                    GITHUB_TOKEN = line.split("=", 1)[1]
                    break
        except Exception:
            pass

    if not GITHUB_TOKEN:
        logger.error("No GitHub token available. Set GITHUB_TOKEN env var or configure git credentials.")
        sys.exit(1)

    logger.info(f"Checking {len(MONITORED_WORKFLOWS)} workflows (last {args.hours}h)...")
    results = check_all_workflows(args.hours)
    success, fail, no_runs = print_report(results, args.hours)

    if not args.dry_run and fail > 0:
        send_teams_alert(results, args.hours)

    # Exit code: 0 if no failures, 1 if failures detected
    sys.exit(1 if fail > 0 else 0)


if __name__ == "__main__":
    main()
