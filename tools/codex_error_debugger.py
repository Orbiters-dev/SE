#!/usr/bin/env python3
"""
Codex Error Debugger — PostToolUse hook that offloads error analysis to Codex.

When a Bash command fails with a meaningful error, sends the traceback to
Codex o4-mini for independent analysis. Returns the diagnosis as systemMessage
so Claude can act on it without spending its own tokens analyzing the error.

Hook registration (settings.json):
  PostToolUse → matcher: "Bash" → timeout: 30
"""
import sys
import json
import os
import re
import subprocess
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, ".tmp", "codex_debug")
os.makedirs(TMP, exist_ok=True)

# Only debug these error types (skip trivial ones)
DEBUGGABLE_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"ModuleNotFoundError",
    r"ImportError",
    r"SyntaxError",
    r"KeyError|TypeError|ValueError|AttributeError",
    r"ConnectionError|ConnectionRefused|TimeoutError",
    r"HttpError|HTTP Error|HTTPError",
]

SKIP_PATTERNS = [
    r"File does not exist",
    r"No such file or directory.*ls",
    r"warning:",
    r"DeprecationWarning",
    r"Sibling tool call errored",
]

CODEX_BIN = "codex"
CODEX_MODEL = "o4-mini"


def should_debug(text):
    """Check if this error is worth sending to Codex."""
    if not text:
        return False
    for skip in SKIP_PATTERNS:
        if re.search(skip, text, re.IGNORECASE):
            return False
    for pattern in DEBUGGABLE_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def run_codex_debug(command, error_text):
    """Send error to Codex for analysis. Returns diagnosis string."""
    # Truncate to avoid huge prompts
    error_truncated = error_text[-1500:] if len(error_text) > 1500 else error_text
    cmd_truncated = command[:300]

    prompt = (
        f"Analyze this error. Be concise (3 lines max).\n"
        f"Command: {cmd_truncated}\n"
        f"Error:\n{error_truncated}\n\n"
        f"Reply with: 1) Root cause 2) Fix suggestion"
    )

    output_file = os.path.join(TMP, f"debug_{datetime.now().strftime('%H%M%S')}.txt")

    try:
        result = subprocess.run(
            [CODEX_BIN, "exec",
             "--model", CODEX_MODEL,
             "--sandbox", "read-only",
             "--skip-git-repo-check",
             "--ephemeral",
             "-o", output_file,
             prompt],
            capture_output=True, text=True,
            timeout=25,  # Must finish within hook timeout
            cwd=ROOT,
        )

        if os.path.exists(output_file):
            diagnosis = open(output_file, "r", encoding="utf-8").read().strip()
            if diagnosis and len(diagnosis) > 10:
                return diagnosis[:500]

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    return None


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    result_str = str(data.get("tool_result", ""))

    # Only on errors
    if "<error>" not in result_str and "Exit code" not in result_str:
        sys.exit(0)

    if not should_debug(result_str):
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    diagnosis = run_codex_debug(command, result_str)

    if diagnosis:
        output = {
            "systemMessage": f"[Codex Debug] {diagnosis}"
        }
        print(json.dumps(output, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    main()
