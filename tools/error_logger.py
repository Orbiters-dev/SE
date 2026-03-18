"""PostToolUse hook: auto-log errors to memory/error_log.jsonl.

Receives tool call JSON via stdin. If the tool result indicates an error,
appends a structured entry to the error log. Outputs a systemMessage so
Claude is aware the error was captured.
"""
import sys
import json
import os
import re
from datetime import datetime

# Paths
MEMORY_DIR = os.path.expanduser(
    "~/.claude/projects/c--Users-wjcho-Desktop-WJ-Test1/memory"
)
ERROR_LOG = os.path.join(MEMORY_DIR, "error_log.jsonl")

# Error patterns worth logging (regex)
ERROR_PATTERNS = [
    (r"Traceback \(most recent call last\)", "python_traceback"),
    (r"ModuleNotFoundError", "module_not_found"),
    (r"ImportError", "import_error"),
    (r"SyntaxError", "syntax_error"),
    (r"UnicodeEncodeError|UnicodeDecodeError", "encoding_error"),
    (r"PermissionError|Permission denied", "permission_error"),
    (r"FileNotFoundError", "file_not_found"),
    (r"HttpError|HTTP Error|HTTPError", "http_error"),
    (r"ConnectionError|ConnectionRefused", "connection_error"),
    (r"TimeoutError|timed out", "timeout_error"),
    (r"KeyError|IndexError|TypeError|ValueError|AttributeError", "python_type_error"),
    (r"ENOENT|EACCES|EPERM", "os_error"),
    (r"npm ERR!", "npm_error"),
    (r"fatal:", "git_fatal"),
    (r"curl: \(\d+\)", "curl_error"),
]

# Patterns to SKIP (expected/normal errors)
SKIP_PATTERNS = [
    r"File does not exist\. Note:",           # Read tool checking existence
    r"No such file or directory.*ls",          # ls checking if dir exists
    r"Sibling tool call errored",             # Parallel tool dependency
    r"grep.*No such file",                     # grep on missing file
    r"warning:",                               # Warnings, not errors
    r"DeprecationWarning",                     # Python deprecation
]


def classify_error(text: str) -> str | None:
    """Return error category or None if not worth logging."""
    if not text:
        return None

    # Skip noise
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return None

    # Classify
    for pattern, category in ERROR_PATTERNS:
        if re.search(pattern, text):
            return category

    return None


def extract_brief(text: str, max_len: int = 200) -> str:
    """Extract the most relevant error line."""
    lines = text.strip().split("\n")

    # Find the actual error line (last line of traceback, or first error line)
    for line in reversed(lines):
        line = line.strip()
        if any(re.search(p, line) for p, _ in ERROR_PATTERNS):
            return line[:max_len]

    # Fallback: last non-empty line
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:max_len]

    return text[:max_len]


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)  # Can't parse input, skip silently

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_result = data.get("tool_result", "")

    # Only process Bash for now
    if tool_name != "Bash":
        sys.exit(0)

    result_str = str(tool_result) if tool_result else ""

    # Check if it's an error
    is_error = "<error>" in result_str or "Exit code" in result_str
    if not is_error:
        sys.exit(0)

    # Classify
    category = classify_error(result_str)
    if category is None:
        sys.exit(0)

    # Extract info
    command = tool_input.get("command", "")[:300]
    brief = extract_brief(result_str)

    # Build log entry
    entry = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "command": command,
        "brief": brief,
        "full_output_lines": len(result_str.split("\n")),
        "session_id": data.get("session_id", ""),
    }

    # Ensure directory exists
    os.makedirs(MEMORY_DIR, exist_ok=True)

    # Append to JSONL
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Count total errors
    try:
        with open(ERROR_LOG, "r", encoding="utf-8") as f:
            total = sum(1 for _ in f)
    except Exception:
        total = 1

    # Output systemMessage so Claude knows
    output = {
        "continue": True,
        "suppressOutput": False,
        "systemMessage": (
            f"[Error Logger] {category}: {brief[:100]} "
            f"(total {total} errors logged in memory/error_log.jsonl)"
        ),
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
