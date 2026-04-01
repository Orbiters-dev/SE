#!/usr/bin/env python3
"""
Session Briefer — PreToolUse hook that provides context on session start.
Inspired by Claude Code's KAIROS daily context awareness.

On the FIRST tool call of each session, reads yesterday+today's daily log
and outputs a brief summary as systemMessage. Subsequent calls are no-ops.

Hook registration (settings.json):
  PreToolUse → matcher: "Bash|Write|Edit" → timeout: 3
"""
import sys
import json
import os
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_LOG_DIR = os.path.join(ROOT, "memory", "daily_log")
TMP_DIR = os.path.join(ROOT, ".tmp")
OPERATIONAL_SUMMARY = os.path.join(ROOT, "memory", "operational_summary.md")


def get_marker_path(session_id):
    """Session marker to ensure one-time briefing."""
    os.makedirs(TMP_DIR, exist_ok=True)
    return os.path.join(TMP_DIR, f".session_briefed_{session_id[:16]}")


def read_daily_log(date_str):
    """Read a daily JSONL log file, return list of entries."""
    log_file = os.path.join(DAILY_LOG_DIR, f"{date_str}.jsonl")
    if not os.path.exists(log_file):
        return []

    entries = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass
    return entries


def summarize_entries(entries, label):
    """Create a brief summary of log entries."""
    if not entries:
        return f"  {label}: (no activity)"

    # Group by tool
    tool_counts = {}
    errors = 0
    key_actions = []

    for e in entries:
        tool = e.get("tool", "?")
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
        if e.get("error"):
            errors += 1
        # Collect skill/agent invocations as key actions
        summary = e.get("summary", "")
        if tool in ("Skill", "Agent") or (tool == "Bash" and "deploy" in summary.lower()):
            key_actions.append(f"{e.get('ts', '?')} {summary[:60]}")

    tools_str = ", ".join(f"{t}:{c}" for t, c in sorted(tool_counts.items(), key=lambda x: -x[1])[:5])
    lines = [f"  {label}: {len(entries)} actions ({tools_str})"]

    if errors:
        lines.append(f"    errors: {errors}")

    for action in key_actions[:5]:
        lines.append(f"    - {action}")

    return "\n".join(lines)


def build_briefing():
    """Build the session startup briefing."""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_entries = read_daily_log(today)
    yesterday_entries = read_daily_log(yesterday)

    parts = []
    parts.append("[Session Context — Daily Log]")
    parts.append(summarize_entries(yesterday_entries, f"Yesterday ({yesterday})"))
    parts.append(summarize_entries(today_entries, f"Today ({today})"))

    # Add operational summary if exists
    if os.path.exists(OPERATIONAL_SUMMARY):
        try:
            with open(OPERATIONAL_SUMMARY, "r", encoding="utf-8") as f:
                summary = f.read().strip()
            if summary and len(summary) < 500:
                parts.append(f"\n[Operational Summary]\n{summary[:400]}")
        except Exception:
            pass

    return "\n".join(parts)


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    session_id = data.get("session_id", "unknown")
    marker = get_marker_path(session_id)

    # Already briefed this session? Skip.
    if os.path.exists(marker):
        sys.exit(0)

    # Check if there's any daily log data worth briefing about
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today_entries = read_daily_log(today)
    yesterday_entries = read_daily_log(yesterday)

    if not today_entries and not yesterday_entries:
        # No log data yet, just mark as briefed and skip
        try:
            with open(marker, "w") as f:
                f.write(datetime.now().isoformat())
        except Exception:
            pass
        sys.exit(0)

    # Build and output briefing
    briefing = build_briefing()

    # Mark as briefed
    try:
        with open(marker, "w") as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass

    # Output as systemMessage
    output = {"systemMessage": briefing}
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
