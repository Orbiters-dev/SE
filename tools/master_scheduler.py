"""
WAT Tool: Unified master scheduler daemon for all 4 domains.

Extends the twitter_scheduler.py daemon pattern to coordinate:
- Twitter (trends, analytics, content planning — NOT tweet posting)
- Compliance (monthly scans, health refresh)
- Content (weekly batch generation)
- Dashboard (weekly data pulls, V8 Excel update)

Twitter tweet posting remains handled by twitter_scheduler.py.
The two daemons communicate through shared state files in .tmp/.

Usage:
    python tools/master_scheduler.py --daemon            # run background daemon
    python tools/master_scheduler.py --check             # show schedule status
    python tools/master_scheduler.py --run dashboard     # run a domain's tasks now
    python tools/master_scheduler.py --run-task <key>    # run a specific task
    python tools/master_scheduler.py --dry-run           # preview next 24h schedule
"""

import os
import sys
import json
import time
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# ── Environment ──────────────────────────────────────────────────────────
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

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
TMP_DIR = PROJECT_ROOT / ".tmp"
PYTHON = sys.executable

# ── Time ─────────────────────────────────────────────────────────────────
JST = timezone(timedelta(hours=9))


def get_jst_now() -> datetime:
    """Get current time in JST (UTC+9)."""
    return datetime.now(JST)


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULE DEFINITION
# ═══════════════════════════════════════════════════════════════════════

SCHEDULE = {
    # ── Twitter (meta-tasks, NOT tweet posting) ──────────────────────
    "twitter_trends": {
        "domain": "twitter",
        "type": "weekly",
        "days": [0, 3],           # Monday, Thursday
        "hour": 8, "minute": 0,
        "script": "tools/twitter_trends.py",
        "args": [],
        "timeout": 300,
        "description": "Scrape JP parenting trends",
    },
    "twitter_analytics": {
        "domain": "twitter",
        "type": "daily",
        "hour": 23, "minute": 30,
        "script": "tools/twitter_analytics.py",
        "args": ["--collect"],
        "timeout": 120,
        "description": "Daily Twitter analytics snapshot",
    },
    "twitter_weekly_plan": {
        "domain": "twitter",
        "type": "weekly",
        "days": [6],              # Sunday
        "hour": 20, "minute": 0,
        "script": "tools/plan_twitter_content.py",
        "args": ["--count", "7"],
        "timeout": 600,
        "description": "Generate next week's Twitter content plan",
    },

    # ── Content Ideas ────────────────────────────────────────────────
    "content_weekly_trends": {
        "domain": "content",
        "type": "weekly",
        "days": [0],              # Monday
        "hour": 8, "minute": 0,
        "script": "tools/scrape_jp_trends.py",
        "args": ["--max-pages", "3"],
        "timeout": 600,
        "description": "Monday trend scraping for content ideas",
    },
    "content_weekly_batch": {
        "domain": "content",
        "type": "weekly",
        "days": [0],              # Monday
        "hour": 9, "minute": 0,
        "script": "tools/plan_weekly_content.py",
        "args": [],
        "timeout": 900,
        "description": "Generate 10 weekly content ideas",
    },

    # ── Dashboard ────────────────────────────────────────────────────
    "dashboard_meta_pull": {
        "domain": "dashboard",
        "type": "weekly",
        "days": [4],              # Friday
        "hour": 9, "minute": 0,
        "script": "tools/meta_api.py",
        "args": [],
        "timeout": 120,
        "description": "Pull Meta Ads weekly data",
    },
    "dashboard_amazon_pull": {
        "domain": "dashboard",
        "type": "weekly",
        "days": [4],              # Friday
        "hour": 9, "minute": 15,
        "script": "tools/amazon_sp_api.py",
        "args": [],
        "timeout": 120,
        "description": "Pull Amazon SP weekly data",
    },
    "dashboard_rakuten_pull": {
        "domain": "dashboard",
        "type": "weekly",
        "days": [4],              # Friday
        "hour": 9, "minute": 30,
        "script": "tools/rakuten_api.py",
        "args": [],
        "timeout": 120,
        "description": "Pull Rakuten weekly data",
    },
    "dashboard_v8_update": {
        "domain": "dashboard",
        "type": "weekly",
        "days": [4],              # Friday
        "hour": 10, "minute": 0,
        "script": "tools/update_v8.py",
        "args": [],
        "timeout": 300,
        "description": "Update V8 Excel with fresh data",
    },
    "dashboard_roas_check": {
        "domain": "dashboard",
        "type": "weekly",
        "days": [4],              # Friday
        "hour": 10, "minute": 30,
        "script": "tools/master_status.py",
        "args": ["--check-roas"],
        "timeout": 60,
        "description": "Check ROAS thresholds and alert if below target",
    },

    # ── Compliance ───────────────────────────────────────────────────
    "compliance_monthly_scan": {
        "domain": "compliance",
        "type": "monthly",
        "day_of_month": 1,
        "hour": 10, "minute": 0,
        "script": "tools/compliance/scan_regulations.py",
        "args": [],
        "timeout": 1800,
        "description": "Monthly regulation scan (eCFR/CPSC/Amazon)",
    },
    "compliance_health_refresh": {
        "domain": "compliance",
        "type": "monthly",
        "day_of_month": 1,
        "hour": 11, "minute": 0,
        "script": "tools/compliance/generate_compliance_health.py",
        "args": [],
        "timeout": 600,
        "description": "Refresh compliance health dashboard data",
    },

    # ── Master (cross-domain) ────────────────────────────────────────
    "daily_state_sync": {
        "domain": "master",
        "type": "daily",
        "hour": 8, "minute": 30,
        "script": "tools/master_status.py",
        "args": ["--sync"],
        "timeout": 60,
        "description": "Morning state sync across all domains",
    },
    "daily_summary": {
        "domain": "master",
        "type": "daily",
        "hour": 22, "minute": 0,
        "script": "tools/master_status.py",
        "args": ["--daily-summary", "--teams"],
        "timeout": 120,
        "description": "Daily cross-domain summary to Teams",
    },
    "weekly_report": {
        "domain": "master",
        "type": "weekly",
        "days": [4],              # Friday
        "hour": 17, "minute": 0,
        "script": "tools/master_status.py",
        "args": ["--weekly-report", "--teams"],
        "timeout": 120,
        "description": "Weekly performance report to Teams",
    },
}

# ── Failure tracking ─────────────────────────────────────────────────
MAX_CONSECUTIVE_FAILURES = 3
RETRY_DELAY_SECONDS = 300  # 5 min retry

# ═══════════════════════════════════════════════════════════════════════
# SCHEDULING LOGIC
# ═══════════════════════════════════════════════════════════════════════

def should_run(task_key: str, config: dict, now: datetime, executed: set) -> bool:
    """Determine if a task should run at this moment."""
    if task_key in executed:
        return False

    if now.hour != config["hour"] or now.minute != config["minute"]:
        return False

    task_type = config.get("type", "daily")

    if task_type == "daily":
        return True

    elif task_type == "weekly":
        return now.weekday() in config.get("days", [])

    elif task_type == "monthly":
        return now.day == config.get("day_of_month", 1)

    return False


def get_next_run(task_key: str, config: dict, now: datetime) -> datetime:
    """Calculate the next run time for a task (for --check display)."""
    task_type = config.get("type", "daily")
    target_hour = config["hour"]
    target_minute = config["minute"]

    if task_type == "daily":
        candidate = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    elif task_type == "weekly":
        days = config.get("days", [0])
        for offset in range(8):
            candidate = now + timedelta(days=offset)
            candidate = candidate.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if candidate > now and candidate.weekday() in days:
                return candidate

    elif task_type == "monthly":
        dom = config.get("day_of_month", 1)
        try:
            candidate = now.replace(day=dom, hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if candidate <= now:
                if now.month == 12:
                    candidate = candidate.replace(year=now.year + 1, month=1)
                else:
                    candidate = candidate.replace(month=now.month + 1)
        except ValueError:
            candidate = now + timedelta(days=30)
        return candidate

    return now + timedelta(days=1)


# ═══════════════════════════════════════════════════════════════════════
# TASK EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def execute_task(task_key: str, config: dict, dry_run: bool = False) -> dict:
    """Execute a scheduled task by spawning a subprocess."""
    script = config["script"]
    script_path = PROJECT_ROOT / script
    args = config.get("args", [])
    timeout = config.get("timeout", 120)

    logger.info(f"[{task_key}] Executing: {script} {' '.join(args)}")

    if dry_run:
        logger.info(f"[{task_key}] DRY RUN — would execute {script}")
        return {"status": "dry_run", "task": task_key}

    if not script_path.exists():
        msg = f"Script not found: {script_path}"
        logger.error(f"[{task_key}] {msg}")
        return {"status": "failed", "task": task_key, "error": msg}

    cmd = [PYTHON, str(script_path)] + args
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        duration = time.time() - start_time

        if result.returncode == 0:
            logger.info(f"[{task_key}] Completed in {duration:.1f}s")
            _log_to_master(task_key, config, "success", duration)
            return {
                "status": "success",
                "task": task_key,
                "duration": duration,
                "output": result.stdout[-500:] if result.stdout else "",
            }
        else:
            error = result.stderr[-500:] if result.stderr else f"exit code {result.returncode}"
            logger.error(f"[{task_key}] Failed: {error[:200]}")
            _log_to_master(task_key, config, "failed", duration, error)
            return {
                "status": "failed",
                "task": task_key,
                "duration": duration,
                "error": error,
            }

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        msg = f"Timeout after {timeout}s"
        logger.error(f"[{task_key}] {msg}")
        _log_to_master(task_key, config, "timeout", duration, msg)
        return {"status": "timeout", "task": task_key, "error": msg}

    except Exception as e:
        duration = time.time() - start_time
        msg = str(e)
        logger.error(f"[{task_key}] Exception: {msg}")
        _log_to_master(task_key, config, "error", duration, msg)
        return {"status": "failed", "task": task_key, "error": msg}


def _log_to_master(task_key: str, config: dict, status: str,
                   duration: float, error: str = "") -> None:
    """Log task execution to master_status.json."""
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from master_status import log_action
        details = {"task": task_key, "duration": round(duration, 1)}
        if error:
            details["error"] = error[:300]
        log_action(config["domain"], f"scheduled_{status}", details, source="scheduler")
    except Exception as e:
        logger.warning(f"Could not log to master_status: {e}")


def _notify_failure(task_key: str, config: dict, error: str) -> None:
    """Send Teams notification for task failure."""
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from teams_notify import send_task_failure
        send_task_failure(config["domain"], task_key, error)
    except Exception as e:
        logger.warning(f"Could not send Teams failure notification: {e}")


# ═══════════════════════════════════════════════════════════════════════
# EVENT TRIGGERS (threshold-based rules)
# ═══════════════════════════════════════════════════════════════════════

def check_event_triggers() -> list[dict]:
    """Check event-triggered rules. Called once per daemon loop."""
    triggered = []

    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from master_status import load_status, get_jst_now as ms_jst, create_alert

        status = load_status()
        now = ms_jst()

        # Rule: Content batch exhausted
        content = status["domains"].get("content", {})
        if content.get("batch_remaining", -1) == 0 and content.get("batch_total", 0) > 0:
            # Only alert once per day
            today = now.date().isoformat()
            existing = [a for a in status.get("alerts", [])
                        if a.get("domain") == "content"
                        and "batch exhausted" in a.get("message", "")
                        and a.get("created_at", "").startswith(today)]
            if not existing:
                alert_id = create_alert("content", "warning", "Content batch exhausted - generate new ideas")
                triggered.append({"rule": "content_exhausted", "alert_id": alert_id})

        # Rule: Trends stale (> 4 days)
        twitter = status["domains"].get("twitter", {})
        trends_at = twitter.get("trends_last_scraped")
        if trends_at:
            try:
                trends_dt = datetime.fromisoformat(trends_at)
                if trends_dt.tzinfo is None:
                    trends_dt = trends_dt.replace(tzinfo=JST)
                if (now - trends_dt).days >= 4:
                    today = now.date().isoformat()
                    existing = [a for a in status.get("alerts", [])
                                if a.get("domain") == "twitter"
                                and "trends stale" in a.get("message", "").lower()
                                and a.get("created_at", "").startswith(today)]
                    if not existing:
                        alert_id = create_alert("twitter", "info",
                                                f"Trends stale ({(now - trends_dt).days} days) - refresh recommended")
                        triggered.append({"rule": "trends_stale", "alert_id": alert_id})
            except (ValueError, TypeError):
                pass

    except Exception as e:
        logger.warning(f"Event trigger check failed: {e}")

    return triggered


# ═══════════════════════════════════════════════════════════════════════
# MASTER COMMAND EXECUTION (Teams → Notion → here)
# ═══════════════════════════════════════════════════════════════════════

def execute_master_command(command: str, params: dict, sender: str = "") -> dict:
    """Execute a master command from Teams and return result.

    Returns:
        dict with keys: success (bool), result_text (str), domain (str)
    """
    import io
    sys.path.insert(0, str(TOOLS_DIR))

    try:
        if command == "briefing":
            from master_status import generate_briefing
            text = generate_briefing()
            return {"success": True, "result_text": text, "domain": "master"}

        elif command == "schedule":
            buf = io.StringIO()
            _show_check_to_buffer(buf)
            return {"success": True, "result_text": buf.getvalue(), "domain": "master"}

        elif command == "status":
            domain = params.get("domain", "")
            if domain:
                from master_status import sync_all, get_domain
                sync_all()
                state = get_domain(domain)
                text = json.dumps(state, ensure_ascii=False, indent=2)
                return {"success": True, "result_text": f"[{domain.upper()}]\n{text}", "domain": domain}
            else:
                from master_status import generate_daily_summary
                summary = generate_daily_summary()
                text = json.dumps(summary, ensure_ascii=False, indent=2)
                return {"success": True, "result_text": text, "domain": "master"}

        elif command == "run":
            domain = params.get("domain", "")
            if not domain:
                return {"success": False, "result_text": "Domain not specified. Usage: 실행 dashboard", "domain": ""}
            results = run_domain(domain)
            if not results:
                return {"success": False, "result_text": f"No tasks found for domain: {domain}", "domain": domain}
            text_parts = []
            for r in results:
                icon = "OK" if r["status"] == "success" else "FAIL"
                text_parts.append(f"[{icon}] {r.get('task', '?')}: {r['status']}")
            return {"success": True, "result_text": "\n".join(text_parts), "domain": domain}

        elif command == "add_task":
            from master_status import add_task
            domain = params.get("domain", "master")
            priority = params.get("priority", "medium")
            description = params.get("description", "")
            if not description:
                return {"success": False, "result_text": "Task description is empty.", "domain": ""}
            task_id = add_task(domain, description, priority, source=f"teams:{sender}")
            return {"success": True, "result_text": f"Task added: {task_id}\n[{priority.upper()}] {description}", "domain": domain}

        elif command == "ack_alert":
            from master_status import acknowledge_alert, get_active_alerts
            alert_id = params.get("alert_id", "")
            if alert_id:
                ok = acknowledge_alert(alert_id)
                if ok:
                    return {"success": True, "result_text": f"Alert acknowledged: {alert_id}", "domain": "master"}
                else:
                    return {"success": False, "result_text": f"Alert not found: {alert_id}", "domain": "master"}
            else:
                alerts = get_active_alerts()
                if not alerts:
                    return {"success": True, "result_text": "No active alerts.", "domain": "master"}
                for a in alerts:
                    acknowledge_alert(a["id"])
                return {"success": True, "result_text": f"Acknowledged {len(alerts)} alert(s).", "domain": "master"}

        elif command == "help":
            return {"success": True, "result_text": "__HELP__", "domain": "master"}

        else:
            return {"success": False, "result_text": f"Unknown command: {command}", "domain": ""}

    except Exception as e:
        logger.error(f"Command execution error [{command}]: {e}")
        return {"success": False, "result_text": f"Error: {str(e)[:300]}", "domain": "master"}


def _show_check_to_buffer(buf):
    """Write schedule check output to a StringIO buffer."""
    now = get_jst_now()
    DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    buf.write(f"Schedule -- {now.strftime('%Y-%m-%d %H:%M')} JST\n")
    buf.write("=" * 45 + "\n")

    domains = {}
    for key, config in SCHEDULE.items():
        d = config["domain"]
        if d not in domains:
            domains[d] = []
        domains[d].append((key, config))

    for domain, tasks in domains.items():
        buf.write(f"\n[{domain.upper()}]\n")
        for key, config in tasks:
            next_run = get_next_run(key, config, now)
            delta = next_run - now
            hours = delta.total_seconds() / 3600
            if hours < 1:
                time_str = f"in {int(delta.total_seconds() / 60)}min"
            elif hours < 24:
                time_str = f"in {hours:.1f}h"
            else:
                time_str = next_run.strftime("%a %H:%M")
            buf.write(f"  {key:<28} Next: {time_str}\n")

    buf.write(f"\nTotal: {len(SCHEDULE)} tasks\n")


def _poll_master_commands():
    """Poll Notion for pending master commands and execute them."""
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from teams_actions import (
            check_pending_master_commands, mark_action_handled,
            reclassify_untagged_actions,
        )
        from teams_notify import send_command_result, send_command_help
        from master_status import log_action

        # Step 1: Reclassify untagged actions from Power Automate
        reclassify_untagged_actions(max_age_minutes=30)

        # Step 2: Poll for master commands
        commands = check_pending_master_commands(max_age_minutes=30)

        # Step 3: Execute each command
        for cmd_entry in commands:
            page_id = cmd_entry["id"]
            command = cmd_entry["command"]
            params = cmd_entry["params"]
            sender = cmd_entry["sender"]

            logger.info(f"[MASTER CMD] {command} from {sender} (params: {params})")

            result = execute_master_command(command, params, sender)

            # Mark as handled in Notion
            mark_action_handled(page_id)

            # Send result back to Teams
            if result["result_text"] == "__HELP__":
                send_command_help()
            else:
                send_command_result(
                    command=command,
                    result_text=result["result_text"],
                    sender=sender,
                    domain=result.get("domain", ""),
                    success=result["success"],
                )

            # Log to master status
            log_action("master", f"command_{command}", {
                "sender": sender,
                "params": params,
                "success": result["success"],
            }, source="teams_command")

    except ImportError as e:
        logger.debug(f"Master command deps not available: {e}")
    except Exception as e:
        logger.error(f"Master command polling error: {e}")


# ═══════════════════════════════════════════════════════════════════════
# DAEMON
# ═══════════════════════════════════════════════════════════════════════

def run_daemon():
    """Main daemon loop. Polls every 30 seconds. Processes Teams commands."""
    logger.info("=" * 60)
    logger.info("  MASTER SCHEDULER DAEMON STARTED")
    logger.info(f"  Domains: Twitter | Compliance | Content | Dashboard")
    logger.info(f"  Tasks: {len(SCHEDULE)}")
    logger.info(f"  Teams commands: enabled")
    logger.info(f"  Polling: every 30 seconds")
    logger.info("=" * 60)

    executed_today = set()
    failure_counts = {}  # task_key -> consecutive failure count
    last_event_check = datetime.min.replace(tzinfo=JST)

    while True:
        try:
            now = get_jst_now()

            # ── Execute scheduled tasks ──────────────────────────────
            for task_key, config in SCHEDULE.items():
                if should_run(task_key, config, now, executed_today):
                    if failure_counts.get(task_key, 0) >= MAX_CONSECUTIVE_FAILURES:
                        logger.warning(f"[{task_key}] Paused after {MAX_CONSECUTIVE_FAILURES} consecutive failures")
                        executed_today.add(task_key)
                        continue

                    result = execute_task(task_key, config)
                    executed_today.add(task_key)

                    if result["status"] in ("failed", "timeout"):
                        failure_counts[task_key] = failure_counts.get(task_key, 0) + 1
                        _notify_failure(task_key, config, result.get("error", "unknown"))
                        if failure_counts[task_key] == 1:
                            logger.info(f"[{task_key}] Will retry in {RETRY_DELAY_SECONDS}s")
                            executed_today.discard(task_key)
                    else:
                        failure_counts[task_key] = 0

            # ── Check event triggers (every 10 minutes) ─────────────
            if (now - last_event_check).total_seconds() >= 600:
                check_event_triggers()
                last_event_check = now

            # ── Poll and execute Teams master commands ───────────────
            _poll_master_commands()

            # ── Reset at midnight JST ────────────────────────────────
            if now.hour == 0 and now.minute == 0:
                executed_today.clear()
                failure_counts.clear()
                logger.info("Midnight reset: cleared executed_today and failure counts")

            time.sleep(30)

        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
            break
        except Exception as e:
            logger.error(f"Daemon loop error: {e}")
            time.sleep(60)


# ═══════════════════════════════════════════════════════════════════════
# MANUAL EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def run_domain(domain: str, dry_run: bool = False) -> list[dict]:
    """Run all tasks for a specific domain immediately."""
    tasks = {k: v for k, v in SCHEDULE.items() if v["domain"] == domain}
    if not tasks:
        logger.error(f"No tasks found for domain: {domain}")
        return []

    results = []
    for task_key, config in tasks.items():
        result = execute_task(task_key, config, dry_run=dry_run)
        results.append(result)
    return results


def run_single_task(task_key: str, dry_run: bool = False) -> dict:
    """Run a single task by key."""
    if task_key not in SCHEDULE:
        logger.error(f"Unknown task: {task_key}")
        return {"status": "error", "error": f"Unknown task: {task_key}"}
    return execute_task(task_key, SCHEDULE[task_key], dry_run=dry_run)


# ═══════════════════════════════════════════════════════════════════════
# STATUS DISPLAY
# ═══════════════════════════════════════════════════════════════════════

def show_check():
    """Display current schedule status with next run times."""
    now = get_jst_now()
    print(f"\n{'='*70}")
    print(f"  MASTER SCHEDULER STATUS — {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"{'='*70}\n")

    DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Group by domain
    domains = {}
    for key, config in SCHEDULE.items():
        d = config["domain"]
        if d not in domains:
            domains[d] = []
        domains[d].append((key, config))

    domain_icons = {"twitter": "🐦", "content": "🎨", "dashboard": "📊",
                    "compliance": "🛡️", "master": "🤖"}

    for domain, tasks in domains.items():
        icon = domain_icons.get(domain, "")
        print(f"  {icon} {domain.upper()}")
        print(f"  {'─'*60}")

        for key, config in tasks:
            next_run = get_next_run(key, config, now)
            delta = next_run - now
            hours = delta.total_seconds() / 3600

            if hours < 1:
                time_str = f"in {int(delta.total_seconds() / 60)}min"
            elif hours < 24:
                time_str = f"in {hours:.1f}h"
            else:
                time_str = f"{next_run.strftime('%a %H:%M')}"

            # Schedule description
            task_type = config.get("type", "daily")
            if task_type == "daily":
                sched = f"Daily {config['hour']:02d}:{config['minute']:02d}"
            elif task_type == "weekly":
                days = [DAY_NAMES[d] for d in config.get("days", [])]
                sched = f"{'/'.join(days)} {config['hour']:02d}:{config['minute']:02d}"
            elif task_type == "monthly":
                sched = f"1st {config['hour']:02d}:{config['minute']:02d}"
            else:
                sched = "?"

            print(f"    {key:<30} {sched:<20} Next: {time_str}")

        print()

    print(f"{'='*70}")
    print(f"  Total tasks: {len(SCHEDULE)}")
    print(f"  Twitter posting: Managed by twitter_scheduler.py (separate daemon)")
    print(f"{'='*70}\n")


def show_dry_run():
    """Preview what would run in the next 24 hours."""
    now = get_jst_now()
    print(f"\n{'='*60}")
    print(f"  DRY RUN: Next 24 hours from {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"{'='*60}\n")

    timeline = []
    for key, config in SCHEDULE.items():
        next_run = get_next_run(key, config, now)
        if (next_run - now).total_seconds() <= 86400:
            timeline.append((next_run, key, config))

    timeline.sort(key=lambda x: x[0])

    if not timeline:
        print("  No tasks scheduled in the next 24 hours.")
    else:
        for run_time, key, config in timeline:
            domain_icons = {"twitter": "🐦", "content": "🎨", "dashboard": "📊",
                            "compliance": "🛡️", "master": "🤖"}
            icon = domain_icons.get(config["domain"], "")
            print(f"  {run_time.strftime('%H:%M')}  {icon} {key}")
            print(f"          {config['description']}")
            print(f"          -> {config['script']} {' '.join(config.get('args', []))}")
            print()

    print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Master Scheduler Daemon")
    parser.add_argument("--daemon", action="store_true", help="Run background daemon")
    parser.add_argument("--check", action="store_true", help="Show schedule status")
    parser.add_argument("--dry-run", action="store_true", help="Preview next 24h schedule")
    parser.add_argument("--run", type=str, metavar="DOMAIN", help="Run all tasks for a domain now")
    parser.add_argument("--run-task", type=str, metavar="KEY", help="Run a specific task by key")
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
    elif args.check:
        show_check()
    elif args.dry_run:
        show_dry_run()
    elif args.run:
        results = run_domain(args.run, dry_run=False)
        for r in results:
            status_icon = "✅" if r["status"] == "success" else "❌"
            print(f"  {status_icon} {r.get('task', '?')}: {r['status']}")
    elif args.run_task:
        result = run_single_task(args.run_task)
        status_icon = "✅" if result["status"] == "success" else "❌"
        print(f"  {status_icon} {result.get('task', '?')}: {result['status']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
