"""
WAT Tool: Master status manager for cross-domain state persistence.

Manages .tmp/master_status.json — the central state file that provides
context continuity across Claude sessions.

Domains: twitter, compliance, content, dashboard

Usage:
    python tools/master_status.py --briefing              # Generate session briefing
    python tools/master_status.py --sync                   # Sync all domain states
    python tools/master_status.py --add-task "..." --domain twitter --priority high
    python tools/master_status.py --complete-task <id>
    python tools/master_status.py --log "..." --domain twitter
    python tools/master_status.py --weekly-report
    python tools/master_status.py --daily-summary [--teams]
    python tools/master_status.py --check-roas
"""

import os
import sys
import json
import argparse
import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from typing import Optional

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
TMP_DIR = PROJECT_ROOT / ".tmp"
STATUS_PATH = TMP_DIR / "master_status.json"
STATUS_BACKUP_PATH = TMP_DIR / "master_status.json.bak"

# Existing state files to sync from
TWITTER_LOG_PATH = TMP_DIR / "twitter_log.json"
TWITTER_AGENT_LOG_PATH = TMP_DIR / "twitter_agent_log.json"
TWITTER_ENGAGE_LOG_PATH = TMP_DIR / "twitter_engage_log.json"
TWITTER_ANALYTICS_PATH = TMP_DIR / "twitter_analytics.json"
TWITTER_TRENDS_PATH = TMP_DIR / "twitter_trends.json"
CONTENT_PLAN_PATH = TMP_DIR / "content_plan.json"
COMPLIANCE_DIR = TMP_DIR / "compliance"

# ── Constants ────────────────────────────────────────────────────────────
VALID_DOMAINS = ["twitter", "compliance", "content", "dashboard"]
VALID_PRIORITIES = ["low", "medium", "high", "critical"]
VALID_SEVERITIES = ["info", "warning", "critical"]
ACTION_LOG_MAX = 1000
JST = timezone(timedelta(hours=9))

DOMAIN_LABELS = {
    "twitter": "Twitter/X",
    "compliance": "Compliance",
    "content": "Content Ideas",
    "dashboard": "Marketing Dashboard",
}


# ── Helpers ──────────────────────────────────────────────────────────────
def get_jst_now() -> datetime:
    return datetime.now(JST)


def _safe_read_json(path: Path) -> Optional[dict]:
    """Read a JSON file, return None on any error."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read {path.name}: {e}")
    return None


def _default_status() -> dict:
    """Return a fresh default status structure."""
    now = get_jst_now().isoformat()
    return {
        "last_updated": now,
        "last_session": {
            "started_at": None,
            "ended_at": None,
            "summary": "",
            "decisions": [],
        },
        "domains": {
            "twitter": {
                "status": "unknown",
                "last_tweet_at": None,
                "last_tweet_slot": None,
                "tweets_today": 0,
                "tweets_this_month": 0,
                "followers_count": None,
                "followers_delta_7d": None,
                "engagement_rate_7d": None,
                "top_performing_type": None,
                "pending_issues": [],
                "next_action": "Sync required",
                "next_action_at": None,
            },
            "compliance": {
                "status": "unknown",
                "last_regulation_scan": None,
                "last_scan_findings": 0,
                "high_risk_alerts": [],
                "pending_label_reviews": 0,
                "pending_review_details": [],
                "next_scan_due": None,
                "next_action": "Sync required",
                "next_action_at": None,
            },
            "content": {
                "status": "unknown",
                "last_batch_date": None,
                "batch_total": 0,
                "batch_used": 0,
                "batch_remaining": 0,
                "image_gen_queue": 0,
                "next_action": "Sync required",
                "next_action_at": None,
            },
            "dashboard": {
                "status": "unknown",
                "last_data_pull": None,
                "last_v8_update": None,
                "roas": {
                    "meta_jp": {"current": None, "target": 3.0, "status": "unknown"},
                    "amazon_jp": {"current": None, "target": 4.0, "status": "unknown"},
                    "rakuten": {"current": None, "target": 3.5, "status": "unknown"},
                },
                "total_ad_spend_mtd": None,
                "total_sales_mtd": None,
                "blended_roas": None,
                "next_action": "Sync required",
                "next_action_at": None,
            },
        },
        "task_queue": [],
        "action_log": [],
        "alerts": [],
    }


# ═══════════════════════════════════════════════════════════════════════
# LOAD / SAVE
# ═══════════════════════════════════════════════════════════════════════

def load_status() -> dict:
    """Load master status. Returns default structure if file doesn't exist or is corrupt."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    if not STATUS_PATH.exists():
        logger.info("No master_status.json found. Creating default.")
        status = _default_status()
        save_status(status)
        return status

    data = _safe_read_json(STATUS_PATH)
    if data is None:
        logger.warning("master_status.json is corrupt. Backing up and resetting.")
        if STATUS_PATH.exists():
            shutil.copy2(STATUS_PATH, STATUS_BACKUP_PATH)
        status = _default_status()
        save_status(status)
        return status

    return data


def save_status(status: dict) -> None:
    """Save master status. Atomic write via temp file + rename."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    status["last_updated"] = get_jst_now().isoformat()
    tmp_path = STATUS_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    tmp_path.replace(STATUS_PATH)


# ═══════════════════════════════════════════════════════════════════════
# DOMAIN STATE
# ═══════════════════════════════════════════════════════════════════════

def update_domain(domain: str, updates: dict) -> None:
    """Merge updates into a domain's state."""
    if domain not in VALID_DOMAINS:
        logger.error(f"Invalid domain: {domain}")
        return
    status = load_status()
    status["domains"][domain].update(updates)
    save_status(status)


def get_domain(domain: str) -> dict:
    """Return current state of a single domain."""
    status = load_status()
    return status["domains"].get(domain, {})


# ═══════════════════════════════════════════════════════════════════════
# TASK QUEUE
# ═══════════════════════════════════════════════════════════════════════

def add_task(domain: str, description: str, priority: str = "medium",
             due_date: str = None, source: str = "manual") -> str:
    """Add a task to the queue. Returns task ID."""
    if priority not in VALID_PRIORITIES:
        priority = "medium"

    status = load_status()
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(status['task_queue']):03d}"

    task = {
        "id": task_id,
        "created_at": get_jst_now().isoformat(),
        "domain": domain,
        "priority": priority,
        "description": description,
        "status": "pending",
        "due_date": due_date,
        "source": source,
    }

    status["task_queue"].append(task)
    save_status(status)
    logger.info(f"Task added: [{priority}] {description} ({task_id})")
    return task_id


def complete_task(task_id: str) -> bool:
    """Mark a task as completed."""
    status = load_status()
    for task in status["task_queue"]:
        if task["id"] == task_id:
            task["status"] = "completed"
            task["completed_at"] = get_jst_now().isoformat()
            save_status(status)
            logger.info(f"Task completed: {task_id}")
            return True
    logger.warning(f"Task not found: {task_id}")
    return False


def get_pending_tasks(domain: str = None, priority: str = None) -> list[dict]:
    """Get pending tasks, optionally filtered."""
    status = load_status()
    tasks = [t for t in status["task_queue"] if t["status"] == "pending"]
    if domain:
        tasks = [t for t in tasks if t["domain"] == domain]
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    tasks.sort(key=lambda t: priority_order.get(t["priority"], 9))
    return tasks


# ═══════════════════════════════════════════════════════════════════════
# ACTION LOG
# ═══════════════════════════════════════════════════════════════════════

def log_action(domain: str, action: str, details: dict = None,
               source: str = "agent") -> None:
    """Append an action to the history log. FIFO at ACTION_LOG_MAX."""
    status = load_status()
    entry = {
        "timestamp": get_jst_now().isoformat(),
        "domain": domain,
        "action": action,
        "details": details or {},
        "source": source,
    }
    status["action_log"].append(entry)

    # FIFO trim
    if len(status["action_log"]) > ACTION_LOG_MAX:
        status["action_log"] = status["action_log"][-ACTION_LOG_MAX:]

    save_status(status)


def get_recent_actions(domain: str = None, hours: int = 24) -> list[dict]:
    """Get actions from the last N hours."""
    status = load_status()
    cutoff = (get_jst_now() - timedelta(hours=hours)).isoformat()
    actions = [a for a in status["action_log"] if a["timestamp"] >= cutoff]
    if domain:
        actions = [a for a in actions if a["domain"] == domain]
    return actions


# ═══════════════════════════════════════════════════════════════════════
# ALERTS
# ═══════════════════════════════════════════════════════════════════════

def create_alert(domain: str, severity: str, message: str) -> str:
    """Create an alert. Returns alert ID."""
    if severity not in VALID_SEVERITIES:
        severity = "info"

    status = load_status()
    alert_id = f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(status['alerts']):03d}"

    alert = {
        "id": alert_id,
        "created_at": get_jst_now().isoformat(),
        "domain": domain,
        "severity": severity,
        "message": message,
        "acknowledged": False,
    }

    status["alerts"].append(alert)
    save_status(status)
    logger.info(f"Alert [{severity}] {domain}: {message}")
    return alert_id


def acknowledge_alert(alert_id: str) -> bool:
    """Mark alert as acknowledged."""
    status = load_status()
    for alert in status["alerts"]:
        if alert["id"] == alert_id:
            alert["acknowledged"] = True
            save_status(status)
            return True
    return False


def get_active_alerts() -> list[dict]:
    """Get unacknowledged alerts."""
    status = load_status()
    return [a for a in status["alerts"] if not a.get("acknowledged")]


# ═══════════════════════════════════════════════════════════════════════
# DOMAIN SYNC — Read existing .tmp/ files into master status
# ═══════════════════════════════════════════════════════════════════════

def sync_twitter_state() -> dict:
    """Sync Twitter state from existing .tmp/twitter_*.json files."""
    updates = {"status": "active"}

    # Tweet log
    log = _safe_read_json(TWITTER_LOG_PATH)
    if log:
        tweets = log.get("tweets", [])
        today_str = date.today().isoformat()
        month_str = today_str[:7]

        published = [t for t in tweets if t.get("status") == "published"]
        today_count = sum(1 for t in published if t.get("posted_at", "").startswith(today_str))
        month_count = sum(1 for t in published if t.get("posted_at", "").startswith(month_str))

        updates["tweets_today"] = today_count
        updates["tweets_this_month"] = month_count

        if published:
            last = published[-1]
            updates["last_tweet_at"] = last.get("posted_at")
            updates["last_tweet_text_preview"] = last.get("text_preview", "")[:60]
    else:
        updates["tweets_today"] = 0
        updates["tweets_this_month"] = 0

    # Agent log
    agent_log = _safe_read_json(TWITTER_AGENT_LOG_PATH)
    if agent_log:
        activities = agent_log.get("activities", [])
        if activities:
            last_activity = activities[-1]
            updates["last_agent_activity"] = last_activity.get("activity")
            updates["last_agent_slot"] = last_activity.get("slot")

    # Engage log
    engage_log = _safe_read_json(TWITTER_ENGAGE_LOG_PATH)
    if engage_log:
        replies = engage_log.get("replies", [])
        today_replies = sum(1 for r in replies if r.get("replied_at", "").startswith(date.today().isoformat()))
        updates["engagements_today"] = today_replies

    # Trends freshness
    trends = _safe_read_json(TWITTER_TRENDS_PATH)
    if trends:
        scraped_at = trends.get("scraped_at", "")
        updates["trends_last_scraped"] = scraped_at
        updates["trends_item_count"] = trends.get("total_items", len(trends.get("items", [])))

    # Analytics
    analytics = _safe_read_json(TWITTER_ANALYTICS_PATH)
    if analytics:
        updates["analytics_data"] = True

    update_domain("twitter", updates)
    return updates


def sync_compliance_state() -> dict:
    """Sync compliance state from .tmp/compliance/ files."""
    updates = {"status": "idle"}

    if not COMPLIANCE_DIR.exists():
        updates["status"] = "no_data"
        update_domain("compliance", updates)
        return updates

    # Find latest regulation scan
    scan_files = sorted(COMPLIANCE_DIR.glob("regulation_scan_*.json"))
    if scan_files:
        latest_scan = _safe_read_json(scan_files[-1])
        if latest_scan:
            updates["last_regulation_scan"] = latest_scan.get("scanned_at", scan_files[-1].stem)
            changes = latest_scan.get("changes", [])
            updates["last_scan_findings"] = len(changes)
            high_risk = [c for c in changes if c.get("severity") == "HIGH"]
            updates["high_risk_alerts"] = [c.get("summary", "") for c in high_risk]

    # Compliance health
    health = _safe_read_json(COMPLIANCE_DIR / "compliance_health.json")
    if health:
        updates["health_report_date"] = health.get("generated_at")
        brands = health.get("brands", [])
        red_count = sum(1 for b in brands if b.get("status") == "RED")
        yellow_count = sum(1 for b in brands if b.get("status") == "YELLOW")
        updates["brands_red"] = red_count
        updates["brands_yellow"] = yellow_count

    # Label reviews
    label_files = list(COMPLIANCE_DIR.glob("label_review_*.json"))
    updates["pending_label_reviews"] = len(label_files)

    # Next scan due: 1st of next month
    now = get_jst_now()
    if now.month == 12:
        next_scan = datetime(now.year + 1, 1, 1, 10, 0, tzinfo=JST)
    else:
        next_scan = datetime(now.year, now.month + 1, 1, 10, 0, tzinfo=JST)
    updates["next_scan_due"] = next_scan.isoformat()
    updates["next_action"] = "Monthly regulation scan"
    updates["next_action_at"] = next_scan.isoformat()

    update_domain("compliance", updates)
    return updates


def sync_content_state() -> dict:
    """Sync content state from content plan files."""
    updates = {"status": "idle"}

    plan = _safe_read_json(CONTENT_PLAN_PATH)
    if plan:
        updates["last_batch_date"] = plan.get("planned_at")
        posts = plan.get("posts", [])
        updates["batch_total"] = len(posts)
        used = sum(1 for p in posts if p.get("status") in ["published", "posted"])
        updates["batch_used"] = used
        updates["batch_remaining"] = len(posts) - used

        # Count image gen needs
        images_needed = 0
        for p in posts:
            if p.get("status") not in ["published", "posted"]:
                images_needed += len(p.get("image_prompts", []))
        updates["image_gen_queue"] = images_needed
    else:
        updates["status"] = "no_plan"

    # Weekly content plan Excel
    weekly_plans = sorted(TMP_DIR.glob("weekly_content_plan_*.xlsx"))
    if weekly_plans:
        latest = weekly_plans[-1]
        updates["latest_weekly_plan"] = latest.name
        updates["latest_weekly_plan_date"] = latest.name.replace("weekly_content_plan_", "").replace(".xlsx", "")

    # Next Monday for batch
    now = get_jst_now()
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = datetime(now.year, now.month, now.day, 9, 0, tzinfo=JST) + timedelta(days=days_until_monday)
    updates["next_action"] = "Weekly content batch (Monday)"
    updates["next_action_at"] = next_monday.isoformat()

    update_domain("content", updates)
    return updates


def sync_dashboard_state() -> dict:
    """Sync dashboard state from Excel file modification dates and API cache."""
    updates = {"status": "idle"}

    # Check V8 Excel
    v8_path = PROJECT_ROOT / "Japan_Marketing Plan_Monthly_V8.xlsx"
    if v8_path.exists():
        mtime = datetime.fromtimestamp(v8_path.stat().st_mtime, tz=JST)
        updates["last_v8_update"] = mtime.isoformat()

    # Check cached API data
    for name, key in [("meta_ads_weekly.json", "meta"), ("amazon_ads_weekly.json", "amazon"), ("rakuten_sales_weekly.json", "rakuten")]:
        cache = _safe_read_json(TMP_DIR / name)
        if cache:
            updates[f"last_{key}_pull"] = cache.get("fetched_at", cache.get("date"))

    # Next Friday for data pull
    now = get_jst_now()
    days_until_friday = (4 - now.weekday()) % 7
    if days_until_friday == 0 and now.hour >= 11:
        days_until_friday = 7
    next_friday = datetime(now.year, now.month, now.day, 9, 0, tzinfo=JST) + timedelta(days=days_until_friday)
    updates["next_action"] = "Weekly data pull (Friday)"
    updates["next_action_at"] = next_friday.isoformat()

    update_domain("dashboard", updates)
    return updates


def sync_all() -> dict:
    """Run all sync functions. Returns full status dict."""
    logger.info("Syncing all domains...")
    sync_twitter_state()
    sync_compliance_state()
    sync_content_state()
    sync_dashboard_state()
    status = load_status()
    logger.info("All domains synced.")
    return status


# ═══════════════════════════════════════════════════════════════════════
# BRIEFING GENERATION
# ═══════════════════════════════════════════════════════════════════════

def generate_briefing() -> str:
    """Generate a human-readable briefing for session start."""
    status = sync_all()
    now = get_jst_now()
    today = now.strftime("%Y-%m-%d")
    day_names_ko = ["월", "화", "수", "목", "금", "토", "일"]
    day_name = day_names_ko[now.weekday()]

    lines = []
    lines.append(f"{'='*50}")
    lines.append(f"  GROSMIMI JAPAN: Daily Briefing")
    lines.append(f"  {today} ({day_name}) {now.strftime('%H:%M')} JST")
    lines.append(f"{'='*50}")
    lines.append("")

    # ── Twitter ──────────────────────────────────────────────────────
    tw = status["domains"]["twitter"]
    lines.append("[TWITTER/X]")
    lines.append(f"  Status: {tw.get('status', 'unknown')}")
    lines.append(f"  Today: {tw.get('tweets_today', '?')} tweets posted")
    lines.append(f"  Month: {tw.get('tweets_this_month', '?')}/1,500")

    if tw.get("last_tweet_at"):
        lines.append(f"  Last tweet: {tw['last_tweet_at'][:16]}")
    if tw.get("last_tweet_text_preview"):
        lines.append(f"    \"{tw['last_tweet_text_preview']}...\"")
    if tw.get("engagements_today"):
        lines.append(f"  Engagements today: {tw['engagements_today']}")

    trends_at = tw.get("trends_last_scraped", "")
    if trends_at:
        try:
            trends_dt = datetime.fromisoformat(trends_at)
            days_ago = (now - trends_dt.replace(tzinfo=JST if trends_dt.tzinfo is None else trends_dt.tzinfo)).days
            lines.append(f"  Trends: {tw.get('trends_item_count', '?')} items ({days_ago}d ago)")
        except (ValueError, TypeError):
            lines.append(f"  Trends: {tw.get('trends_item_count', '?')} items")

    if tw.get("pending_issues"):
        for issue in tw["pending_issues"]:
            lines.append(f"  !! {issue}")
    lines.append("")

    # ── Compliance ───────────────────────────────────────────────────
    comp = status["domains"]["compliance"]
    lines.append("[COMPLIANCE]")
    lines.append(f"  Status: {comp.get('status', 'unknown')}")

    if comp.get("last_regulation_scan"):
        scan_str = str(comp["last_regulation_scan"])[:10]
        lines.append(f"  Last scan: {scan_str} ({comp.get('last_scan_findings', 0)} findings)")
    else:
        lines.append("  Last scan: None")

    if comp.get("high_risk_alerts"):
        for alert in comp["high_risk_alerts"]:
            lines.append(f"  !! HIGH RISK: {alert}")

    if comp.get("brands_red"):
        lines.append(f"  Brands RED: {comp['brands_red']}")
    if comp.get("brands_yellow"):
        lines.append(f"  Brands YELLOW: {comp['brands_yellow']}")

    lines.append(f"  Label reviews: {comp.get('pending_label_reviews', 0)} on file")

    if comp.get("next_scan_due"):
        lines.append(f"  Next scan: {str(comp['next_scan_due'])[:10]}")
    lines.append("")

    # ── Content ──────────────────────────────────────────────────────
    cont = status["domains"]["content"]
    lines.append("[CONTENT IDEAS]")
    lines.append(f"  Status: {cont.get('status', 'unknown')}")

    if cont.get("last_batch_date"):
        lines.append(f"  Last batch: {str(cont['last_batch_date'])[:10]}")
        lines.append(f"  Used/Total: {cont.get('batch_used', 0)}/{cont.get('batch_total', 0)} (remaining: {cont.get('batch_remaining', 0)})")
    else:
        lines.append("  No content plan found")

    if cont.get("image_gen_queue"):
        lines.append(f"  Images pending: {cont['image_gen_queue']}")

    if cont.get("latest_weekly_plan"):
        lines.append(f"  Weekly plan: {cont['latest_weekly_plan']}")
    lines.append("")

    # ── Dashboard ────────────────────────────────────────────────────
    dash = status["domains"]["dashboard"]
    lines.append("[MARKETING DASHBOARD]")
    lines.append(f"  Status: {dash.get('status', 'unknown')}")

    if dash.get("last_v8_update"):
        lines.append(f"  V8 last updated: {str(dash['last_v8_update'])[:10]}")

    roas = dash.get("roas", {})
    for channel, data in roas.items():
        if isinstance(data, dict) and data.get("current") is not None:
            target = data.get("target", "?")
            status_str = data.get("status", "")
            marker = " !!" if status_str == "below_target" else ""
            lines.append(f"  {channel}: ROAS {data['current']}x (target: {target}x){marker}")
    lines.append("")

    # ── Active Alerts ────────────────────────────────────────────────
    active_alerts = [a for a in status.get("alerts", []) if not a.get("acknowledged")]
    if active_alerts:
        lines.append("[ALERTS]")
        for alert in active_alerts:
            severity_icon = {"critical": "!!!", "warning": "!!", "info": "i"}.get(alert["severity"], "?")
            lines.append(f"  [{severity_icon}] {alert['domain']}: {alert['message']}")
        lines.append("")

    # ── Pending Tasks ────────────────────────────────────────────────
    pending = get_pending_tasks()
    if pending:
        lines.append("[TASK QUEUE]")
        for i, task in enumerate(pending[:10], 1):
            priority_icon = {"critical": "!!!!", "high": "!!!", "medium": "", "low": ""}.get(task["priority"], "")
            due = f" (due: {task['due_date']})" if task.get("due_date") else ""
            lines.append(f"  {i}. [{task['priority'].upper()}] {task['description']}{due}")
        if len(pending) > 10:
            lines.append(f"  ... and {len(pending) - 10} more")
        lines.append("")

    # ── Today's Priorities (auto-generated) ──────────────────────────
    lines.append("[TODAY'S RECOMMENDED ACTIONS]")
    priority_num = 1

    # Check day-of-week specific tasks
    if now.weekday() == 0:  # Monday
        lines.append(f"  {priority_num}. Weekly content batch generation")
        priority_num += 1
    if now.weekday() == 4:  # Friday
        lines.append(f"  {priority_num}. Dashboard weekly data pull + V8 update")
        priority_num += 1
    if now.day == 1:  # 1st of month
        lines.append(f"  {priority_num}. Monthly compliance regulation scan")
        priority_num += 1

    # Content batch exhausted
    if cont.get("batch_remaining", 0) == 0 and cont.get("batch_total", 0) > 0:
        lines.append(f"  {priority_num}. [URGENT] Content batch exhausted - generate new ideas")
        priority_num += 1

    # Trends stale
    if trends_at:
        try:
            trends_dt = datetime.fromisoformat(trends_at)
            if trends_dt.tzinfo is None:
                trends_dt = trends_dt.replace(tzinfo=JST)
            if (now - trends_dt).days >= 3:
                lines.append(f"  {priority_num}. Refresh Twitter trends (last: {(now - trends_dt).days}d ago)")
                priority_num += 1
        except (ValueError, TypeError):
            pass

    # Critical tasks
    for task in pending:
        if task["priority"] == "critical":
            lines.append(f"  {priority_num}. [CRITICAL] {task['description']}")
            priority_num += 1

    if priority_num == 1:
        lines.append("  No special actions for today. Routine operations.")

    lines.append("")

    # ── Last Session ─────────────────────────────────────────────────
    last = status.get("last_session", {})
    if last.get("ended_at"):
        lines.append(f"[LAST SESSION]")
        lines.append(f"  Ended: {str(last['ended_at'])[:16]}")
        if last.get("summary"):
            lines.append(f"  Summary: {last['summary']}")
        if last.get("decisions"):
            for d in last["decisions"]:
                lines.append(f"  Decision: {d}")
        lines.append("")

    lines.append(f"{'='*50}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def start_session() -> str:
    """Called at session start. Syncs all state, generates briefing, returns it."""
    status = load_status()
    status["last_session"]["started_at"] = get_jst_now().isoformat()
    save_status(status)
    return generate_briefing()


def end_session(summary: str, decisions: list[str] = None) -> None:
    """Called at session end. Saves session metadata."""
    status = load_status()
    status["last_session"]["ended_at"] = get_jst_now().isoformat()
    status["last_session"]["summary"] = summary
    status["last_session"]["decisions"] = decisions or []
    save_status(status)
    logger.info("Session ended. State saved.")


# ═══════════════════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════════════════

def generate_daily_summary() -> dict:
    """Generate daily cross-domain summary dict (for Teams notification)."""
    status = sync_all()
    tw = status["domains"]["twitter"]
    comp = status["domains"]["compliance"]
    cont = status["domains"]["content"]
    dash = status["domains"]["dashboard"]

    return {
        "date": date.today().isoformat(),
        "twitter": {
            "tweets_today": tw.get("tweets_today", 0),
            "tweets_month": tw.get("tweets_this_month", 0),
            "engagements": tw.get("engagements_today", 0),
        },
        "compliance": {
            "status": comp.get("status", "unknown"),
            "high_risk": len(comp.get("high_risk_alerts", [])),
            "next_scan": str(comp.get("next_scan_due", ""))[:10],
        },
        "content": {
            "remaining": cont.get("batch_remaining", 0),
            "total": cont.get("batch_total", 0),
            "images_pending": cont.get("image_gen_queue", 0),
        },
        "dashboard": {
            "roas": dash.get("roas", {}),
            "last_pull": str(dash.get("last_data_pull", ""))[:10] if dash.get("last_data_pull") else "N/A",
        },
        "alerts": get_active_alerts(),
        "pending_tasks": len(get_pending_tasks()),
    }


def generate_weekly_report() -> dict:
    """Generate weekly summary for all domains."""
    status = sync_all()
    actions = status.get("action_log", [])

    # Count actions per domain in last 7 days
    cutoff = (get_jst_now() - timedelta(days=7)).isoformat()
    recent = [a for a in actions if a["timestamp"] >= cutoff]
    domain_counts = {}
    for a in recent:
        d = a.get("domain", "unknown")
        domain_counts[d] = domain_counts.get(d, 0) + 1

    return {
        "period": f"{(date.today() - timedelta(days=7)).isoformat()} ~ {date.today().isoformat()}",
        "actions_by_domain": domain_counts,
        "total_actions": len(recent),
        "domains": status["domains"],
        "active_alerts": get_active_alerts(),
        "pending_tasks": get_pending_tasks(),
    }


# ═══════════════════════════════════════════════════════════════════════
# ROAS CHECK (event trigger for scheduler)
# ═══════════════════════════════════════════════════════════════════════

def check_roas_thresholds() -> list[dict]:
    """Check ROAS thresholds and create alerts if below target."""
    status = load_status()
    roas = status["domains"]["dashboard"].get("roas", {})
    triggered = []

    for channel, data in roas.items():
        if not isinstance(data, dict) or data.get("current") is None:
            continue

        current = data["current"]
        target = data.get("target", 0)
        if target <= 0:
            continue

        ratio = current / target
        if ratio < 0.7:
            msg = f"{channel} ROAS {current}x is {(1-ratio)*100:.0f}% below target {target}x"
            alert_id = create_alert("dashboard", "critical", msg)
            triggered.append({"channel": channel, "alert_id": alert_id, "message": msg})
        elif ratio < 0.8:
            msg = f"{channel} ROAS {current}x is {(1-ratio)*100:.0f}% below target {target}x"
            alert_id = create_alert("dashboard", "warning", msg)
            triggered.append({"channel": channel, "alert_id": alert_id, "message": msg})

    if triggered:
        logger.warning(f"ROAS alerts triggered: {len(triggered)}")
    else:
        logger.info("All ROAS channels within target.")

    return triggered


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Master Agent status manager")
    parser.add_argument("--briefing", action="store_true", help="Generate session briefing")
    parser.add_argument("--sync", action="store_true", help="Sync all domain states")
    parser.add_argument("--add-task", type=str, help="Add a task")
    parser.add_argument("--domain", type=str, help="Domain for task/log")
    parser.add_argument("--priority", type=str, default="medium", help="Task priority")
    parser.add_argument("--complete-task", type=str, help="Complete a task by ID")
    parser.add_argument("--log", type=str, help="Log an action")
    parser.add_argument("--daily-summary", action="store_true", help="Generate daily summary")
    parser.add_argument("--weekly-report", action="store_true", help="Generate weekly report")
    parser.add_argument("--check-roas", action="store_true", help="Check ROAS thresholds")
    parser.add_argument("--teams", action="store_true", help="Send output to Teams")
    args = parser.parse_args()

    if args.briefing:
        print(start_session())

    elif args.sync:
        sync_all()
        print("All domains synced.")

    elif args.add_task:
        domain = args.domain or "master"
        task_id = add_task(domain, args.add_task, args.priority)
        print(f"Task added: {task_id}")

    elif args.complete_task:
        if complete_task(args.complete_task):
            print(f"Task completed: {args.complete_task}")
        else:
            print(f"Task not found: {args.complete_task}")

    elif args.log:
        domain = args.domain or "master"
        log_action(domain, args.log)
        print(f"Action logged for {domain}")

    elif args.daily_summary:
        summary = generate_daily_summary()
        print(json.dumps(summary, ensure_ascii=False, indent=2))

        if args.teams:
            sys.path.insert(0, str(Path(__file__).parent))
            try:
                from teams_notify import send_daily_summary as _send
                _send(summary)
                print("Daily summary sent to Teams.")
            except ImportError:
                logger.warning("teams_notify.send_daily_summary not available yet")

    elif args.weekly_report:
        report = generate_weekly_report()
        print(json.dumps(report, ensure_ascii=False, indent=2))

        if args.teams:
            sys.path.insert(0, str(Path(__file__).parent))
            try:
                from teams_notify import send_weekly_report as _send
                _send(report)
                print("Weekly report sent to Teams.")
            except ImportError:
                logger.warning("teams_notify.send_weekly_report not available yet")

    elif args.check_roas:
        alerts = check_roas_thresholds()
        if alerts:
            for a in alerts:
                print(f"[ALERT] {a['message']}")
        else:
            print("All ROAS channels within target.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
