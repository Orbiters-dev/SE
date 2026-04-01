#!/usr/bin/env python3
"""
Codex Code Reviewer — PostToolUse hook that auto-reviews code changes.

After Write/Edit to .py files, sends the changes to Codex for quick review.
Catches bugs, security issues, and logic errors before they become problems.

Hook registration (settings.json):
  PostToolUse → matcher: "Write|Edit" → timeout: 30
"""
import sys
import json
import os
import subprocess
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, ".tmp", "codex_review")
os.makedirs(TMP, exist_ok=True)

# Only review these file types
REVIEWABLE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".yml", ".yaml"}

# Skip these paths (config files, docs, etc.)
SKIP_PATHS = ["memory/", ".tmp/", "Data Storage/", "CLAUDE.md", "SKILL.md", ".gitkeep"]

# Track reviewed files in session to avoid re-reviewing
SESSION_MARKER_DIR = os.path.join(TMP, "session_markers")
os.makedirs(SESSION_MARKER_DIR, exist_ok=True)

CODEX_BIN = "codex"
CODEX_MODEL = "o4-mini"


def should_review(file_path):
    """Check if this file change is worth reviewing."""
    if not file_path:
        return False

    _, ext = os.path.splitext(file_path)
    if ext not in REVIEWABLE_EXTENSIONS:
        return False

    for skip in SKIP_PATHS:
        if skip in file_path.replace("\\", "/"):
            return False

    # Don't re-review same file in same session
    marker = os.path.join(SESSION_MARKER_DIR, os.path.basename(file_path) + ".reviewed")
    if os.path.exists(marker):
        # Check if marker is from today
        try:
            mtime = os.path.getmtime(marker)
            if (datetime.now().timestamp() - mtime) < 3600:  # Within 1 hour
                return False
        except Exception:
            pass

    return True


def mark_reviewed(file_path):
    """Mark file as reviewed for this session."""
    marker = os.path.join(SESSION_MARKER_DIR, os.path.basename(file_path) + ".reviewed")
    try:
        with open(marker, "w") as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass


def run_codex_review(file_path):
    """Send file to Codex for quick review."""
    basename = os.path.basename(file_path)
    output_file = os.path.join(TMP, f"review_{basename}_{datetime.now().strftime('%H%M%S')}.txt")

    prompt = (
        f"Quick code review of {basename}. Read the file and check for:\n"
        f"1) Bugs or logic errors\n"
        f"2) Security issues (injection, hardcoded secrets)\n"
        f"3) Missing error handling that could crash\n\n"
        f"If all clean, say 'LGTM'. Otherwise list issues (max 3 lines).\n"
        f"File: {file_path}"
    )

    try:
        result = subprocess.run(
            [CODEX_BIN, "exec",
             "--model", CODEX_MODEL,
             "--sandbox", "read-only",
             "-C", ROOT,
             "--skip-git-repo-check",
             "--ephemeral",
             "-o", output_file,
             prompt],
            capture_output=True, text=True,
            timeout=25,
            cwd=ROOT,
        )

        if os.path.exists(output_file):
            review = open(output_file, "r", encoding="utf-8").read().strip()
            if review and len(review) > 3:
                return review[:400]

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    return None


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not should_review(file_path):
        sys.exit(0)

    review = run_codex_review(file_path)
    mark_reviewed(file_path)

    if review and "LGTM" not in review.upper():
        output = {
            "systemMessage": f"[Codex Review] {os.path.basename(file_path)}: {review}"
        }
        print(json.dumps(output, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    main()
