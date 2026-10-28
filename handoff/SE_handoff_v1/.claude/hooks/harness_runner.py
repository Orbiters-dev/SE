#!/usr/bin/env python3
"""PostToolUse hook — auto-runs 3-LLM harness on tools/*.py edits.

Receives tool-call JSON on stdin (PostToolUse contract). Filters to
files matching HARNESS_PATTERNS. Invokes harness with build gate, 2 loops,
no meta-judge (cost saver). Outputs hook-control JSON:
  PASS = brief confirm, WARN = proceed, FAIL = block + reason for Claude to fix.

Customize HARNESS_PATTERNS for your repo layout (Django app names, n8n folders, etc).
"""
import json
import os
import re
import subprocess
import sys


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


# ─── Customize for your repo ────────────────────────────────────────────
# Add patterns for files that should trigger the harness build gate.
HARNESS_PATTERNS = [
    r"(^|/)tools/.+\.py$",
    r"(^|/)(views|models|urls)\.py$",
    r"(^|/)migrations/.+\.py$",
    r"(^|/)n8n_workflows/.+\.json$",
    r"(^|/)management/commands/.+\.py$",
    r"(^|/)\.claude/hooks/.+\.py$",
    # Add your Django app folders / service modules here, e.g.:
    # r"(^|/)(your_app_name)/.+\.py$",
]
# ─────────────────────────────────────────────────────────────────────────


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    fp = (data.get("tool_input") or {}).get("file_path") or ""
    if not fp:
        return 0

    fp_norm = fp.replace("\\", "/")
    if not any(re.search(p, fp_norm) for p in HARNESS_PATTERNS):
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    project_norm = project_dir.replace("\\", "/")
    if fp_norm.startswith(project_norm):
        rel = fp_norm[len(project_norm) + 1:]
        abs_target = os.path.join(project_dir, rel)
    else:
        rel = fp_norm
        abs_target = fp_norm
    if not os.path.exists(abs_target):
        return 0

    cmd = [
        sys.executable,
        "tools/harness.py",
        "run",
        "--type", "code",
        "--file", rel,
        "--gate", "build",
        "--max-loops", "2",
        "--no-meta-judge",
        "--json",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        _emit({"systemMessage": f"Harness timeout (>300s) on {rel} — verdict unknown, proceed cautiously"})
        return 0
    except Exception as exc:
        _emit({"systemMessage": f"Harness launch failed on {rel}: {exc}"})
        return 0

    try:
        verdict = json.loads(result.stdout) if result.stdout.strip() else {}
    except Exception:
        verdict = {}

    status = verdict.get("status", "UNKNOWN")
    loops = verdict.get("loops_used", 0)

    if status == "FAIL":
        feedback = (verdict.get("feedback") or "")[:1500]
        _emit({
            "systemMessage": f"Harness FAIL on {rel} (loops={loops}) — fix required",
            "decision": "block",
            "reason": (
                f"3-LLM harness verdict: FAIL (loops={loops})\n\n"
                f"{feedback}\n\n"
                f"Required: address feedback, re-edit {rel}. "
                f"Hook will re-verify automatically."
            ),
        })
        return 0

    if status == "WARN":
        _emit({"systemMessage": f"Harness WARN on {rel} (loops={loops}) — proceed aware"})
        return 0

    if status == "PASS":
        _emit({"systemMessage": f"Harness PASS on {rel} (loops={loops})"})
        return 0

    err_tail = (result.stderr or result.stdout or "")[-300:].strip()
    _emit({"systemMessage": f"Harness verdict UNKNOWN on {rel}: {err_tail[:200]}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())