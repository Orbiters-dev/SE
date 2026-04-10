#!/usr/bin/env python3
"""Stop hook: warn if today's session was not saved to memory."""
import json
import os
from datetime import datetime

today = datetime.now().strftime("%Y%m%d")
session_file = os.path.join(
    os.path.dirname(__file__), "..", "..", "memory",
    f"session_{today}.md"
)

if not os.path.exists(session_file):
    # No session file for today — warn the user
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": (
                "SESSION_SAVE_WARNING: 오늘 세션 요약이 아직 저장되지 않았습니다. "
                "세은에게: /reflect 입력하면 저장됩니다."
            )
        }
    }))
