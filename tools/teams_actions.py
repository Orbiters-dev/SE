"""
WAT Tool: Teams → Notion → Python action queue.

Handles both Twitter slot actions AND master agent commands.

Flow:
1. Bot sends plan/result to Teams
2. Team member replies in Teams (cancel/modify/approve/master commands)
3. Power Automate catches reply → HTTP POST to Notion API
4. Python polls Notion:
   - Twitter actions: twitter_scheduler.py polls during 10-min approval window
   - Master commands: master_scheduler.py polls every 30 seconds

Master commands:
    브리핑/briefing  — 현재 상태 브리핑
    스케줄/schedule  — 예정된 작업 목록
    상태/status      — 도메인별 상태
    실행/run <domain>— 도메인 작업 즉시 실행
    태스크 추가      — 태스크 큐 추가
    알림 확인        — 알림 처리
    도움말/help      — 명령어 목록

Usage:
    from teams_actions import check_pending_actions, mark_action_handled, add_action
    from teams_actions import check_pending_master_commands, classify_master_command

    python tools/teams_actions.py --process "브리핑" --sender test
    python tools/teams_actions.py --process "실행 dashboard" --sender test
    python tools/teams_actions.py --add cancel --slot 15 --message "취소해주세요"
    python tools/teams_actions.py --check --slot 15
"""

import os
import sys
import json
import argparse
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone

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

NOTION_TOKEN = os.getenv("NOTION_API_TOKEN")
DB_ID = os.getenv("TWITTER_ACTIONS_NOTION_DB_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

NOTION_API = "https://api.notion.com/v1"

# Keywords for Twitter action detection
CANCEL_KEYWORDS = ["취소", "cancel", "キャンセル", "중지", "stop", "삭제"]
MODIFY_KEYWORDS = ["수정", "modify", "변경", "change", "바꿔", "고쳐"]
APPROVE_KEYWORDS = ["확인", "승인", "approve", "ok", "좋아", "ㅇㅋ", "고"]

# ── Master command keywords (multilingual) ───────────────────────────
MASTER_COMMANDS = {
    "briefing": ["브리핑", "briefing", "ブリーフィング", "현황", "현재상태",
                 "오늘 업데이트", "업데이트", "update", "today", "오늘"],
    "schedule": ["스케줄", "schedule", "スケジュール", "일정"],
    "run": ["실행", "run", "実行", "돌려", "돌려줘"],
    "add_task": ["태스크 추가", "add task", "タスク追加", "할일 추가", "할일추가"],
    "ack_alert": ["알림 확인", "ack alert", "アラート確認", "알림 처리", "알림처리"],
    "status": ["상태", "status", "ステータス"],
    "help": ["도움말", "help", "ヘルプ", "명령어"],
}

DOMAIN_ALIASES = {
    "twitter": ["twitter", "트위터", "ツイッター", "tw"],
    "dashboard": ["dashboard", "대시보드", "ダッシュボード", "dash", "대쉬보드"],
    "compliance": ["compliance", "컴플라이언스", "コンプライアンス", "comp"],
    "content": ["content", "콘텐츠", "コンテンツ", "cont", "컨텐츠"],
}


def _resolve_domain(text: str) -> str:
    """Resolve a domain name from multilingual aliases."""
    lower = text.lower().strip()
    for domain, aliases in DOMAIN_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                return domain
    return ""


def classify_master_command(text: str) -> tuple:
    """Classify a Teams message as a master command.

    Returns:
        tuple: (command_name, params_dict)
        command_name is "" if not a master command.
    """
    lower = text.lower().strip()
    params = {}

    for cmd, keywords in MASTER_COMMANDS.items():
        for kw in keywords:
            if kw in lower:
                # Extract remainder after keyword
                idx = lower.index(kw) + len(kw)
                remainder = text[idx:].strip()
                if remainder.startswith(":") or remainder.startswith("："):
                    remainder = remainder[1:].strip()

                if cmd == "run":
                    params["domain"] = _resolve_domain(remainder)

                elif cmd == "add_task":
                    parts = remainder.split(maxsplit=2)
                    if len(parts) >= 1:
                        params["domain"] = _resolve_domain(parts[0])
                    if len(parts) >= 2 and parts[1] in ("low", "medium", "high", "critical"):
                        params["priority"] = parts[1]
                        params["description"] = parts[2] if len(parts) >= 3 else ""
                    elif len(parts) >= 2:
                        params["priority"] = "medium"
                        params["description"] = " ".join(parts[1:])
                    else:
                        params["description"] = remainder

                elif cmd == "ack_alert":
                    if remainder:
                        params["alert_id"] = remainder

                elif cmd == "status":
                    if remainder:
                        params["domain"] = _resolve_domain(remainder)

                return cmd, params

    return "", {}


def classify_message(text: str) -> str:
    """Classify a Teams message into an action type.

    Checks master commands first, then Twitter actions.
    Returns 'master_command' for master agent commands.
    """
    # Master commands take priority
    cmd, _ = classify_master_command(text)
    if cmd:
        return "master_command"

    # Twitter action classification
    lower = text.lower().strip()
    for kw in CANCEL_KEYWORDS:
        if kw in lower:
            return "cancel"
    for kw in MODIFY_KEYWORDS:
        if kw in lower:
            return "modify"
    for kw in APPROVE_KEYWORDS:
        if kw in lower:
            return "approve"
    return "comment"


def add_action(
    action_type: str,
    message: str = "",
    sender: str = "teams",
    slot: int = 0,
    domain: str = "",
) -> str:
    """Add an action to the Notion queue.

    Args:
        domain: "master" for master commands, "" for Twitter actions (backward compat)

    Returns:
        Page ID of the created entry, or empty string on failure.
    """
    if not NOTION_TOKEN or not DB_ID:
        logger.error("Notion credentials not configured")
        return ""

    properties = {
        "Action": {"title": [{"text": {"content": action_type}}]},
        "Message": {"rich_text": [{"text": {"content": message[:2000]}}]},
        "Sender": {"rich_text": [{"text": {"content": sender}}]},
        "Slot": {"number": slot},
        "Status": {"select": {"name": "pending"}},
    }
    if domain:
        properties["Domain"] = {"rich_text": [{"text": {"content": domain}}]}

    page = {
        "parent": {"database_id": DB_ID},
        "properties": properties,
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/pages", headers=HEADERS, json=page, timeout=10
        )
        if resp.status_code == 200:
            page_id = resp.json().get("id", "")
            logger.info(f"Action added: [{action_type}] {message[:50]}... (id: {page_id[:8]})")
            return page_id
        else:
            logger.error(f"Failed to add action: {resp.status_code} {resp.text[:200]}")
            return ""
    except Exception as e:
        logger.error(f"Notion API error: {e}")
        return ""


def check_pending_actions(slot: int = 0, max_age_minutes: int = 30) -> list[dict]:
    """Check Notion for pending actions.

    Args:
        slot: Filter by time slot (0 = all slots)
        max_age_minutes: Only return actions newer than this

    Returns:
        List of action dicts with keys: id, type, message, sender, slot, created
    """
    if not NOTION_TOKEN or not DB_ID:
        return []

    filters = [
        {"property": "Status", "select": {"equals": "pending"}},
    ]

    if slot > 0:
        filters.append({"property": "Slot", "number": {"equals": slot}})

    query = {
        "filter": {"and": filters} if len(filters) > 1 else filters[0],
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": 10,
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/databases/{DB_ID}/query",
            headers=HEADERS,
            json=query,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"Notion query failed: {resp.status_code}")
            return []

        results = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

        for page in resp.json().get("results", []):
            props = page["properties"]

            # Extract created time
            created_str = page.get("created_time", "")
            if created_str:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created < cutoff:
                    continue

            action_title = props["Action"]["title"]
            action_type = action_title[0]["text"]["content"] if action_title else ""

            message_rt = props["Message"]["rich_text"]
            message = message_rt[0]["text"]["content"] if message_rt else ""

            sender_rt = props["Sender"]["rich_text"]
            sender = sender_rt[0]["text"]["content"] if sender_rt else ""

            slot_val = props["Slot"]["number"] or 0

            results.append(
                {
                    "id": page["id"],
                    "type": action_type,
                    "message": message,
                    "sender": sender,
                    "slot": slot_val,
                    "created": created_str,
                }
            )

        return results

    except Exception as e:
        logger.error(f"Notion query error: {e}")
        return []


def mark_action_handled(page_id: str) -> bool:
    """Mark an action as handled in Notion."""
    if not NOTION_TOKEN:
        return False

    try:
        resp = requests.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=HEADERS,
            json={"properties": {"Status": {"select": {"name": "handled"}}}},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def process_teams_message(text: str, sender: str = "teams", slot: int = 0) -> dict:
    """Process a raw Teams message: classify and add to queue.

    Routes master commands to Domain='master' in Notion.
    Routes Twitter actions as before.

    Returns:
        Dict with action details.
    """
    action_type = classify_message(text)

    # Master command routing
    if action_type == "master_command":
        cmd, params = classify_master_command(text)
        page_id = add_action(
            action_type=cmd,
            message=text,
            sender=sender,
            slot=0,
            domain="master",
        )
        return {
            "action": "master_command",
            "command": cmd,
            "params": params,
            "message": text,
            "page_id": page_id,
        }

    # Twitter action routing (existing behavior)
    message = text
    if action_type == "modify":
        for kw in MODIFY_KEYWORDS:
            if kw in text.lower():
                idx = text.lower().index(kw) + len(kw)
                rest = text[idx:].strip()
                if rest.startswith(":") or rest.startswith("："):
                    rest = rest[1:].strip()
                if rest:
                    message = rest
                break

    page_id = add_action(
        action_type=action_type,
        message=message,
        sender=sender,
        slot=slot,
    )

    return {
        "action": action_type,
        "message": message,
        "page_id": page_id,
    }


# ═══════════════════════════════════════════════════════════════════════
# Master Command Polling
# ═══════════════════════════════════════════════════════════════════════

def check_pending_master_commands(max_age_minutes: int = 30) -> list:
    """Check Notion for pending master commands (Domain='master').

    Returns:
        List of command dicts: {id, command, params, message, sender, created}
    """
    if not NOTION_TOKEN or not DB_ID:
        return []

    query = {
        "filter": {
            "and": [
                {"property": "Status", "select": {"equals": "pending"}},
                {"property": "Domain", "rich_text": {"equals": "master"}},
            ]
        },
        "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
        "page_size": 10,
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/databases/{DB_ID}/query",
            headers=HEADERS, json=query, timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"Notion master query failed: {resp.status_code}")
            return []

        results = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

        for page in resp.json().get("results", []):
            props = page["properties"]
            created_str = page.get("created_time", "")
            if created_str:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created < cutoff:
                    continue

            message_rt = props["Message"]["rich_text"]
            raw_message = message_rt[0]["text"]["content"] if message_rt else ""

            sender_rt = props["Sender"]["rich_text"]
            sender = sender_rt[0]["text"]["content"] if sender_rt else ""

            # Re-classify to extract command + params
            cmd, params = classify_master_command(raw_message)
            if not cmd:
                action_title = props["Action"]["title"]
                cmd = action_title[0]["text"]["content"] if action_title else "unknown"

            results.append({
                "id": page["id"],
                "command": cmd,
                "params": params,
                "message": raw_message,
                "sender": sender,
                "created": created_str,
            })

        return results

    except Exception as e:
        logger.error(f"Notion master command query error: {e}")
        return []


def reclassify_untagged_actions(max_age_minutes: int = 30) -> int:
    """Scan pending actions with no Domain set, reclassify master commands.

    Power Automate may not set Domain. This function catches untagged actions
    and tags master commands with Domain='master' in Notion.

    Returns number of actions reclassified.
    """
    if not NOTION_TOKEN or not DB_ID:
        return 0

    query = {
        "filter": {
            "and": [
                {"property": "Status", "select": {"equals": "pending"}},
                {"property": "Domain", "rich_text": {"is_empty": True}},
                {"property": "Slot", "number": {"equals": 0}},
            ]
        },
        "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
        "page_size": 20,
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/databases/{DB_ID}/query",
            headers=HEADERS, json=query, timeout=10,
        )
        if resp.status_code != 200:
            return 0

        count = 0
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

        for page in resp.json().get("results", []):
            created_str = page.get("created_time", "")
            if created_str:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created < cutoff:
                    continue

            props = page["properties"]
            message_rt = props["Message"]["rich_text"]
            message = message_rt[0]["text"]["content"] if message_rt else ""

            cmd, _ = classify_master_command(message)
            if cmd:
                requests.patch(
                    f"{NOTION_API}/pages/{page['id']}",
                    headers=HEADERS,
                    json={"properties": {
                        "Domain": {"rich_text": [{"text": {"content": "master"}}]},
                        "Action": {"title": [{"text": {"content": cmd}}]},
                    }},
                    timeout=10,
                )
                count += 1
                logger.info(f"Reclassified as master command: {cmd} (page {page['id'][:8]})")

        return count

    except Exception as e:
        logger.error(f"Reclassification error: {e}")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Teams action queue via Notion")
    parser.add_argument("--add", type=str, help="Add action (cancel/modify/approve)")
    parser.add_argument("--message", type=str, default="", help="Action message")
    parser.add_argument("--sender", type=str, default="cli", help="Sender name")
    parser.add_argument("--slot", type=int, default=0, help="Time slot")
    parser.add_argument("--check", action="store_true", help="Check pending actions")
    parser.add_argument("--process", type=str, help="Process raw Teams message text")
    args = parser.parse_args()

    if args.add:
        page_id = add_action(
            action_type=args.add,
            message=args.message,
            sender=args.sender,
            slot=args.slot,
        )
        if page_id:
            print(f"Added: {page_id}")
        else:
            print("Failed to add action")
            sys.exit(1)

    elif args.check:
        actions = check_pending_actions(slot=args.slot)
        if actions:
            for a in actions:
                print(f"  [{a['type']}] {a['message'][:60]} (from: {a['sender']}, slot: {a['slot']})")
        else:
            print("No pending actions")

    elif args.process:
        result = process_teams_message(args.process, sender=args.sender, slot=args.slot)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()
