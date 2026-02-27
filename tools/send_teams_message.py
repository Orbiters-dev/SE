"""
Teams Notification Tool
=======================
Send notifications to Microsoft Teams via Incoming Webhook (Workflows).
Supports trigger-based message templates: tool_success, tool_error, weekly_report.

Usage (CLI):
    python tools/send_teams_message.py --type tool_success --title "CIPL Done" --body "25 items"
    python tools/send_teams_message.py --type tool_error --title "Sync Failed" --body "API timeout"
    python tools/send_teams_message.py --dry-run --type weekly_report --title "Week 9" --body "Report ready"

Usage (import):
    from send_teams_message import notify_teams
    success, error = notify_teams("tool_success", "CIPL Done", "25 items processed")
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

import requests
from env_loader import load_env

# Windows UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_env()

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")

# Template config per message type
TEMPLATES = {
    "tool_success": {
        "color": "Good",       # Green accent
        "label": "SUCCESS",
        "icon": "[OK]",
    },
    "tool_error": {
        "color": "Attention",  # Red accent
        "label": "ERROR",
        "icon": "[!!]",
    },
    "weekly_report": {
        "color": "Accent",     # Blue accent
        "label": "REPORT",
        "icon": "[i]",
    },
}

# Map template color names to hex for the color stripe
COLOR_HEX = {
    "Good": "#2DC72D",
    "Attention": "#D13438",
    "Accent": "#0078D4",
}


def build_adaptive_card(msg_type, title, body, details=None):
    """Build an Adaptive Card payload for Teams Workflows webhook.

    Args:
        msg_type: One of 'tool_success', 'tool_error', 'weekly_report'
        title: Message title
        body: Message body text
        details: Optional dict of key-value pairs for extra info

    Returns:
        dict: Payload ready to POST to Teams webhook
    """
    tpl = TEMPLATES.get(msg_type, TEMPLATES["tool_success"])
    color = COLOR_HEX.get(tpl["color"], "#0078D4")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    card_body = [
        {
            "type": "Container",
            "style": "emphasis",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"{tpl['icon']} {tpl['label']}",
                    "weight": "Bolder",
                    "size": "Medium",
                    "color": tpl["color"],
                }
            ],
            "bleed": True,
        },
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": body,
            "wrap": True,
            "spacing": "Small",
        },
        {
            "type": "ColumnSet",
            "separator": True,
            "spacing": "Medium",
            "columns": [
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"Time: {now}",
                            "isSubtle": True,
                            "size": "Small",
                        }
                    ],
                }
            ],
        },
    ]

    # Add detail facts if provided
    if details:
        facts = [{"title": k, "value": str(v)} for k, v in details.items()]
        card_body.insert(3, {
            "type": "FactSet",
            "facts": facts,
            "spacing": "Medium",
        })

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": card_body,
                },
            }
        ],
    }

    return card


def send_to_teams(payload, webhook_url=None, max_retries=3):
    """POST the payload to Teams webhook with retry logic.

    Args:
        payload: Adaptive Card dict
        webhook_url: Override webhook URL (defaults to env var)
        max_retries: Number of retry attempts

    Returns:
        tuple: (success: bool, error: str|None)
    """
    url = webhook_url or TEAMS_WEBHOOK_URL
    if not url:
        return False, "TEAMS_WEBHOOK_URL not set in .env"

    headers = {"Content-Type": "application/json"}

    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2))
                print(f"    Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            if resp.status_code in (200, 202):
                return True, None

            # Teams Workflows returns 200/202 on success; anything else is an error
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)
            else:
                return False, f"All {max_retries} attempts failed. Last error: {e}"

    return False, "Max retries exceeded"


def notify_teams(msg_type, title, body, details=None, webhook_url=None, dry_run=False):
    """High-level function to send a Teams notification.

    Args:
        msg_type: 'tool_success', 'tool_error', or 'weekly_report'
        title: Notification title
        body: Notification body
        details: Optional dict of extra key-value info
        webhook_url: Override webhook URL
        dry_run: If True, print payload without sending

    Returns:
        tuple: (success: bool, error: str|None)
    """
    if msg_type not in TEMPLATES:
        return False, f"Unknown message type: {msg_type}. Use: {list(TEMPLATES.keys())}"

    payload = build_adaptive_card(msg_type, title, body, details)

    if dry_run:
        print("\n[DRY RUN] Would send the following payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return True, None

    return send_to_teams(payload, webhook_url=webhook_url)


def main():
    parser = argparse.ArgumentParser(
        description="Send notifications to Microsoft Teams via Incoming Webhook"
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=list(TEMPLATES.keys()),
        help="Message type: tool_success, tool_error, weekly_report",
    )
    parser.add_argument("--title", required=True, help="Notification title")
    parser.add_argument("--body", required=True, help="Notification body text")
    parser.add_argument(
        "--detail",
        action="append",
        metavar="KEY=VALUE",
        help="Extra detail (repeatable). Example: --detail 'Items=25' --detail 'Tool=generate_cipl'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the message without sending",
    )
    args = parser.parse_args()

    # Parse --detail KEY=VALUE pairs
    details = None
    if args.detail:
        details = {}
        for item in args.detail:
            if "=" in item:
                k, v = item.split("=", 1)
                details[k.strip()] = v.strip()

    print("=" * 50)
    print("Teams Notification Tool")
    print("=" * 50)

    tpl = TEMPLATES[args.type]
    print(f"\n[1] Type: {tpl['label']} ({args.type})")
    print(f"    Title: {args.title}")
    print(f"    Body: {args.body}")
    if details:
        for k, v in details.items():
            print(f"    {k}: {v}")

    print(f"\n[2] Sending{'  (DRY RUN)' if args.dry_run else ''}...")

    success, error = notify_teams(
        args.type, args.title, args.body, details=details, dry_run=args.dry_run
    )

    print(f"\n{'=' * 50}")
    if success:
        print("DONE! Message sent successfully." if not args.dry_run else "DONE! Dry run complete.")
    else:
        print(f"FAILED: {error}")
    print("=" * 50)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
