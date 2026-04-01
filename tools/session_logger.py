#!/usr/bin/env python3
"""
Session Logger — PostToolUse hook that records meaningful actions to daily log.
Inspired by Claude Code's KAIROS append-only daily log system.

Appends to memory/daily_log/YYYY-MM-DD.jsonl on every significant tool call.
Designed to be fast (<1s) and non-blocking.

Hook registration (settings.json):
  PostToolUse → matcher: "*" → timeout: 3
"""
import sys
import json
import os
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_LOG_DIR = os.path.join(ROOT, "memory", "daily_log")

# ─── Tools worth logging (skip noisy read-only tools) ────────────────────────
LOG_TOOLS = {
    "Bash", "Edit", "Write", "Skill", "Agent",
    "NotebookEdit", "WebFetch", "WebSearch",
}

# Tools to always skip
SKIP_TOOLS = {
    "Read", "Glob", "Grep", "TodoWrite", "ToolSearch",
    "AskUserQuestion", "EnterPlanMode", "ExitPlanMode",
}

# Bash commands that are read-only (skip these)
READONLY_BASH = [
    r"^(cat|head|tail|less|more|wc|ls|dir|pwd|echo|printenv|which|where)",
    r"^git (log|status|diff|show|branch|remote)",
    r"^(claude mcp list|codex --version|node --version|npm --version)",
]

import re
READONLY_PATTERNS = [re.compile(p) for p in READONLY_BASH]


def is_meaningful(tool_name, tool_input, tool_result):
    """Determine if this tool call is worth logging."""
    if tool_name in SKIP_TOOLS:
        return False

    if tool_name not in LOG_TOOLS:
        return False

    # Bash: skip read-only commands
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        for pattern in READONLY_PATTERNS:
            if pattern.match(cmd.strip()):
                return False

    return True


def extract_summary(tool_name, tool_input, tool_result):
    """Extract a concise one-line summary of the action."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Truncate long commands
        return cmd[:200] if len(cmd) > 200 else cmd

    elif tool_name == "Edit":
        fp = tool_input.get("file_path", "")
        return f"edit {os.path.basename(fp)}"

    elif tool_name == "Write":
        fp = tool_input.get("file_path", "")
        return f"write {os.path.basename(fp)}"

    elif tool_name == "Skill":
        return f"skill:{tool_input.get('skill', '?')}"

    elif tool_name == "Agent":
        return f"agent:{tool_input.get('description', '?')[:80]}"

    elif tool_name in ("WebFetch", "WebSearch"):
        url = tool_input.get("url", tool_input.get("query", ""))
        return f"{tool_name}:{url[:100]}"

    else:
        return tool_name


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_result = data.get("tool_result", "")

    if not is_meaningful(tool_name, tool_input, tool_result):
        sys.exit(0)

    # Check for errors
    result_str = str(tool_result) if tool_result else ""
    has_error = "<error>" in result_str or "Exit code" in result_str

    # Build log entry
    entry = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "tool": tool_name,
        "summary": extract_summary(tool_name, tool_input, tool_result),
        "error": has_error,
        "session": data.get("session_id", "")[:12],
    }

    # Write to daily JSONL
    os.makedirs(DAILY_LOG_DIR, exist_ok=True)
    log_file = os.path.join(DAILY_LOG_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Never block the user

    sys.exit(0)


if __name__ == "__main__":
    main()
