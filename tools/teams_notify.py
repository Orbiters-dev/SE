"""
WAT Tool: Send Twitter action plans to Microsoft Teams for approval.
Posts Adaptive Cards to Teams webhook before executing any Twitter actions.

Usage:
    python tools/teams_notify.py --slot 11 --tweet "ツイート内容" --tweet-ko "한국어 번역"
    python tools/teams_notify.py --slot 11 --tweet "..." --replies "リプ1|||リプ2|||リプ3"
    python tools/teams_notify.py --test  # send test message
"""

import os
import sys
import json
import argparse
import logging
import requests
from pathlib import Path
from datetime import datetime

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

WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")
MASTER_WEBHOOK_URL = os.getenv("TEAMS_MASTER_WEBHOOK_URL")

SLOT_NAMES = {
    9: "🌅 아침 (Morning)",
    11: "☀️ 오전 (K-육아)",
    13: "🍱 점심 (Tips/질문)",
    15: "🌤️ 오후 (K-이유식)",
    17: "🌆 저녁 (일상)",
    19: "🌙 프라임타임 (공감/제품)",
    21: "🌛 밤 (마무리)",
    23: "🔬 심야 (밤공부)",
}


def send_action_plan(
    slot: int,
    tweet_text: str = "",
    tweet_ko: str = "",
    replies: list[str] = None,
    reply_targets: list[str] = None,
    extra_note: str = "",
) -> bool:
    """Send an action plan to Teams for approval before executing."""
    if not WEBHOOK_URL:
        logger.error("TEAMS_WEBHOOK_URL not set in .env")
        return False

    slot_name = SLOT_NAMES.get(slot, f"Slot {slot}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    body = [
        {
            "type": "TextBlock",
            "text": f"📋 [{slot}:00 JST] {slot_name}",
            "weight": "Bolder",
            "size": "Medium",
        },
        {
            "type": "TextBlock",
            "text": f"작성시간: {now}",
            "isSubtle": True,
            "spacing": "None",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
    ]

    # Tweet section
    if tweet_text:
        body.append(
            {
                "type": "TextBlock",
                "text": "🐦 트윗",
                "weight": "Bolder",
                "spacing": "Medium",
            }
        )
        body.append(
            {
                "type": "TextBlock",
                "text": tweet_text,
                "wrap": True,
                "spacing": "Small",
            }
        )
        if tweet_ko:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"({tweet_ko})",
                    "wrap": True,
                    "spacing": "Small",
                    "isSubtle": True,
                }
            )

    # Replies section
    if replies:
        body.append(
            {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"}
        )
        body.append(
            {
                "type": "TextBlock",
                "text": f"💬 리플 계획 ({len(replies)}개)",
                "weight": "Bolder",
            }
        )
        reply_text = ""
        for i, reply in enumerate(replies):
            target = reply_targets[i] if reply_targets and i < len(reply_targets) else ""
            target_str = f" → @{target}" if target else ""
            reply_text += f"• {reply}{target_str}\n"
        body.append(
            {
                "type": "TextBlock",
                "text": reply_text.strip(),
                "wrap": True,
                "spacing": "Small",
            }
        )

    # Extra note
    if extra_note:
        body.append(
            {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"}
        )
        body.append(
            {"type": "TextBlock", "text": extra_note, "wrap": True, "isSubtle": True}
        )

    # Footer
    body.append(
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"}
    )
    body.append(
        {
            "type": "TextBlock",
            "text": "⚠️ 수정/취소는 Claude에게 직접 전달. 10분 내 거부 없으면 자동 실행.",
            "wrap": True,
            "color": "Attention",
        }
    )

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        if resp.status_code == 202:
            logger.info(f"Teams notification sent for slot {slot}")
            return True
        else:
            logger.error(f"Teams webhook failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        return False


def send_result(slot: int, tweet_url: str = "", replies_done: int = 0,
                tweet_text: str = "", tweet_ko: str = "") -> bool:
    """Send execution result to Teams after actions are completed."""
    if not WEBHOOK_URL:
        return False

    slot_name = SLOT_NAMES.get(slot, f"Slot {slot}")

    body = [
        {
            "type": "TextBlock",
            "text": f"✅ [{slot}:00 JST] {slot_name} 실행 완료",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Good",
        },
    ]

    if tweet_text:
        body.append(
            {
                "type": "TextBlock",
                "text": f"🇯🇵 {tweet_text}",
                "wrap": True,
                "spacing": "Medium",
            }
        )
    if tweet_ko:
        body.append(
            {
                "type": "TextBlock",
                "text": f"🇰🇷 {tweet_ko}",
                "wrap": True,
                "spacing": "Small",
                "isSubtle": True,
            }
        )

    if tweet_url:
        body.append(
            {
                "type": "TextBlock",
                "text": f"🔗 {tweet_url}",
                "wrap": True,
                "spacing": "Small",
            }
        )

    if replies_done > 0:
        body.append(
            {
                "type": "TextBlock",
                "text": f"💬 리플 {replies_done}개 완료",
            }
        )

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        return resp.status_code == 202
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
# Multi-Domain Notifications (Master Agent)
# ═══════════════════════════════════════════════════════════════════════

DOMAIN_ICONS = {
    "twitter": "🐦",
    "compliance": "🛡️",
    "content": "🎨",
    "dashboard": "📊",
    "master": "🤖",
}

DOMAIN_NAMES_KO = {
    "twitter": "Twitter/X",
    "compliance": "컴플라이언스",
    "content": "콘텐츠 아이디어",
    "dashboard": "마케팅 대시보드",
    "master": "마스터 에이전트",
}

SEVERITY_COLORS = {
    "info": "Default",
    "warning": "Warning",
    "critical": "Attention",
}


def _post_card(body: list[dict], use_master: bool = False) -> bool:
    """Post an Adaptive Card to Teams.

    Args:
        body: Adaptive Card body blocks.
        use_master: If True, post to TEAMS_MASTER_WEBHOOK_URL (Master Sheet channel).
                    Falls back to TEAMS_WEBHOOK_URL if master webhook not configured.
    """
    url = WEBHOOK_URL
    if use_master and MASTER_WEBHOOK_URL:
        url = MASTER_WEBHOOK_URL

    if not url:
        logger.error("TEAMS_WEBHOOK_URL not set in .env")
        return False

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 202:
            return True
        else:
            logger.error(f"Teams webhook failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        return False


def send_daily_summary(summary: dict) -> bool:
    """Send daily cross-domain summary to Teams."""
    date_str = summary.get("date", datetime.now().strftime("%Y-%m-%d"))

    body = [
        {
            "type": "TextBlock",
            "text": f"🤖 Daily Summary — {date_str}",
            "weight": "Bolder",
            "size": "Medium",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
    ]

    # Twitter
    tw = summary.get("twitter", {})
    body.append({
        "type": "TextBlock",
        "text": f"🐦 Twitter: {tw.get('tweets_today', 0)} tweets | {tw.get('engagements', 0)} engagements | Month: {tw.get('tweets_month', 0)}/1,500",
        "wrap": True, "spacing": "Medium",
    })

    # Compliance
    comp = summary.get("compliance", {})
    comp_status = comp.get("status", "unknown")
    high_risk = comp.get("high_risk", 0)
    risk_str = f" | ⚠️ HIGH RISK: {high_risk}" if high_risk else ""
    body.append({
        "type": "TextBlock",
        "text": f"🛡️ Compliance: {comp_status}{risk_str} | Next scan: {comp.get('next_scan', 'N/A')}",
        "wrap": True, "spacing": "Small",
    })

    # Content
    cont = summary.get("content", {})
    body.append({
        "type": "TextBlock",
        "text": f"🎨 Content: {cont.get('remaining', 0)}/{cont.get('total', 0)} remaining | Images pending: {cont.get('images_pending', 0)}",
        "wrap": True, "spacing": "Small",
    })

    # Dashboard
    dash = summary.get("dashboard", {})
    roas = dash.get("roas", {})
    roas_parts = []
    for ch, data in roas.items():
        if isinstance(data, dict) and data.get("current") is not None:
            roas_parts.append(f"{ch}: {data['current']}x")
    roas_str = " | ".join(roas_parts) if roas_parts else "No data"
    body.append({
        "type": "TextBlock",
        "text": f"📊 Dashboard: {roas_str} | Last pull: {dash.get('last_pull', 'N/A')}",
        "wrap": True, "spacing": "Small",
    })

    # Alerts
    alerts = summary.get("alerts", [])
    if alerts:
        body.append({"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"})
        body.append({
            "type": "TextBlock",
            "text": f"🚨 Active Alerts: {len(alerts)}",
            "weight": "Bolder", "color": "Attention",
        })
        for a in alerts[:5]:
            body.append({
                "type": "TextBlock",
                "text": f"• [{a.get('severity', '?')}] {a.get('domain', '?')}: {a.get('message', '')}",
                "wrap": True, "spacing": "None",
            })

    # Pending tasks count
    pending = summary.get("pending_tasks", 0)
    if pending:
        body.append({
            "type": "TextBlock",
            "text": f"📝 Pending tasks: {pending}",
            "spacing": "Medium", "isSubtle": True,
        })

    return _post_card(body)


def send_weekly_report(report: dict) -> bool:
    """Send weekly performance report to Teams."""
    body = [
        {
            "type": "TextBlock",
            "text": f"📈 Weekly Report — {report.get('period', '')}",
            "weight": "Bolder",
            "size": "Medium",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
        {
            "type": "TextBlock",
            "text": f"Total actions this week: {report.get('total_actions', 0)}",
            "spacing": "Medium",
        },
    ]

    # Actions by domain
    actions = report.get("actions_by_domain", {})
    for domain, count in actions.items():
        icon = DOMAIN_ICONS.get(domain, "")
        name = DOMAIN_NAMES_KO.get(domain, domain)
        body.append({
            "type": "TextBlock",
            "text": f"{icon} {name}: {count} actions",
            "spacing": "None",
        })

    # Domain summaries
    domains = report.get("domains", {})
    body.append({"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"})

    tw = domains.get("twitter", {})
    body.append({
        "type": "TextBlock",
        "text": f"🐦 Twitter: {tw.get('tweets_this_month', '?')}/1,500 this month",
        "wrap": True, "spacing": "Small",
    })

    dash = domains.get("dashboard", {})
    roas = dash.get("roas", {})
    for ch, data in roas.items():
        if isinstance(data, dict) and data.get("current") is not None:
            status_icon = "✅" if data.get("status") != "below_target" else "⚠️"
            body.append({
                "type": "TextBlock",
                "text": f"  {status_icon} {ch}: {data['current']}x / {data.get('target', '?')}x target",
                "spacing": "None",
            })

    # Alerts & tasks
    alerts = report.get("active_alerts", [])
    tasks = report.get("pending_tasks", [])
    if alerts or tasks:
        body.append({"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"})
        if alerts:
            body.append({"type": "TextBlock", "text": f"🚨 Active alerts: {len(alerts)}", "color": "Attention"})
        if tasks:
            body.append({"type": "TextBlock", "text": f"📝 Pending tasks: {len(tasks)}"})

    return _post_card(body)


def send_domain_alert(domain: str, severity: str, message: str,
                      details: str = "") -> bool:
    """Send an alert card for a specific domain."""
    icon = DOMAIN_ICONS.get(domain, "")
    name = DOMAIN_NAMES_KO.get(domain, domain)
    color = SEVERITY_COLORS.get(severity, "Default")

    severity_label = {"info": "ℹ️ 정보", "warning": "⚠️ 경고", "critical": "🚨 긴급"}.get(severity, severity)

    body = [
        {
            "type": "TextBlock",
            "text": f"{icon} {name} — {severity_label}",
            "weight": "Bolder",
            "size": "Medium",
            "color": color,
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
        {
            "type": "TextBlock",
            "text": message,
            "wrap": True,
            "spacing": "Medium",
        },
    ]

    if details:
        body.append({
            "type": "TextBlock",
            "text": details,
            "wrap": True,
            "isSubtle": True,
            "spacing": "Small",
        })

    return _post_card(body)


def send_task_failure(domain: str, task_name: str, error_message: str) -> bool:
    """Send notification when a scheduled task fails."""
    icon = DOMAIN_ICONS.get(domain, "")
    name = DOMAIN_NAMES_KO.get(domain, domain)

    body = [
        {
            "type": "TextBlock",
            "text": f"❌ Task Failed: {icon} {name}",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Attention",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
        {
            "type": "TextBlock",
            "text": f"Task: {task_name}",
            "weight": "Bolder",
            "spacing": "Medium",
        },
        {
            "type": "TextBlock",
            "text": f"Error: {error_message[:500]}",
            "wrap": True,
            "spacing": "Small",
            "color": "Attention",
        },
        {
            "type": "TextBlock",
            "text": f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "isSubtle": True,
            "spacing": "Medium",
        },
    ]

    return _post_card(body)


# ═══════════════════════════════════════════════════════════════════════
# Master Command Result Cards
# ═══════════════════════════════════════════════════════════════════════

def send_command_result(
    command: str,
    result_text: str,
    sender: str = "",
    domain: str = "",
    success: bool = True,
) -> bool:
    """Send master command execution result back to Teams."""
    icon = DOMAIN_ICONS.get(domain, "🤖")
    status_icon = "✅" if success else "❌"
    now = datetime.now().strftime("%H:%M:%S")

    # Truncate for Adaptive Card body limit
    max_len = 3000
    display_text = result_text[:max_len]
    if len(result_text) > max_len:
        display_text += f"\n\n... ({len(result_text)} chars total)"

    body = [
        {
            "type": "TextBlock",
            "text": f"{status_icon} {icon} Command: {command}",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Good" if success else "Attention",
        },
    ]

    if sender:
        body.append({
            "type": "TextBlock",
            "text": f"Requested by: {sender} | {now}",
            "isSubtle": True,
            "spacing": "None",
        })

    body.append({"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"})

    # Use monospace for briefing/schedule/status output
    use_mono = command in ("briefing", "schedule", "status")

    # Split into chunks for Teams rendering
    chunks = [display_text[i:i+1000] for i in range(0, len(display_text), 1000)]
    for chunk in chunks:
        block = {
            "type": "TextBlock",
            "text": chunk,
            "wrap": True,
            "spacing": "Small",
        }
        if use_mono:
            block["fontType"] = "Monospace"
        body.append(block)

    return _post_card(body, use_master=True)


def send_command_help() -> bool:
    """Send the master command help card to Teams."""
    body = [
        {
            "type": "TextBlock",
            "text": "🤖 Master Agent Commands",
            "weight": "Bolder",
            "size": "Medium",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
        {
            "type": "TextBlock",
            "text": (
                "**브리핑 / briefing** — 현재 상태 브리핑\n"
                "**스케줄 / schedule** — 예정된 작업 목록\n"
                "**상태 / status [domain]** — 도메인 상태\n"
                "**실행 / run <domain>** — 도메인 작업 즉시 실행\n"
                "**태스크 추가** <domain> [priority] <desc>\n"
                "**알림 확인 / ack alert** [alert_id]\n"
                "**도움말 / help** — 이 도움말"
            ),
            "wrap": True,
            "spacing": "Medium",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━", "spacing": "Medium"},
        {
            "type": "TextBlock",
            "text": "Domains: twitter | dashboard | compliance | content",
            "isSubtle": True,
        },
        {
            "type": "TextBlock",
            "text": "예시: 실행 대시보드 / run dashboard / 상태 트위터 / 브리핑",
            "isSubtle": True,
            "spacing": "None",
        },
    ]
    return _post_card(body, use_master=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Twitter plans to Teams")
    parser.add_argument("--slot", type=int, help="Time slot (9,11,13...)")
    parser.add_argument("--tweet", type=str, help="Tweet text (Japanese)")
    parser.add_argument("--tweet-ko", type=str, help="Tweet Korean translation")
    parser.add_argument("--replies", type=str, help="Reply texts separated by |||")
    parser.add_argument("--test", action="store_true", help="Send test message")
    args = parser.parse_args()

    if args.test:
        send_action_plan(
            slot=11,
            tweet_text="テストツイート",
            tweet_ko="테스트 트윗",
            extra_note="이것은 테스트입니다.",
        )
    elif args.slot and args.tweet:
        replies = args.replies.split("|||") if args.replies else None
        send_action_plan(
            slot=args.slot,
            tweet_text=args.tweet,
            tweet_ko=args.tweet_ko or "",
            replies=replies,
        )
    else:
        parser.print_help()
