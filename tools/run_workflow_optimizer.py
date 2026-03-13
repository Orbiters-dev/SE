#!/usr/bin/env python3
"""
run_workflow_optimizer.py — ORBI Workflow Optimizer

Calls Claude API to generate actionable fix proposals from WAT framework issues.
Emails numbered proposals; applies approved ones via --execute --proposal-id N.

Usage:
    python tools/run_workflow_optimizer.py                        # propose + email
    python tools/run_workflow_optimizer.py --dry-run              # no email
    python tools/run_workflow_optimizer.py --preview              # save to .tmp/
    python tools/run_workflow_optimizer.py --model sonnet         # use Sonnet
    python tools/run_workflow_optimizer.py --days 14              # GH Actions window
    python tools/run_workflow_optimizer.py --execute --proposal-id 1,3,5
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

# Import analyzer functions (load_env already called above — don't call again)
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "run_workflow_analyzer",
    Path(__file__).parent / "run_workflow_analyzer.py"
)
_analyzer = importlib.util.module_from_spec(_spec)
# Patch load_env to no-op before executing the module to avoid double-load
import env_loader as _el
_orig_load = _el.load_env
_el.load_env = lambda: None
try:
    _spec.loader.exec_module(_analyzer)
finally:
    _el.load_env = _orig_load

Issue = _analyzer.Issue
run_static_analysis = _analyzer.run_static_analysis
run_github_analysis = _analyzer.run_github_analysis

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
TMP_DIR       = PROJECT_ROOT / ".tmp"
RECIPIENT     = os.getenv("COMMUNICATOR_RECIPIENT", "wj.choi@orbiters.co.kr")
SENDER        = os.getenv("GMAIL_SENDER", "orbiters11@gmail.com")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

MODEL_MAP = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

MAX_FILE_BYTES = 10_240   # 10 KB per file
MAX_TOOL_CODE_PROPOSALS = 5


def collect_issues(days: int = 7) -> list[Issue]:
    """Collect all WAT framework issues (static + GitHub Actions)."""
    issues = run_static_analysis()
    issues += run_github_analysis(days)
    return issues


def read_file_contents(issues: list[Issue]) -> dict[str, str]:
    """
    Load file contents for all files referenced in issues.
    Keys: relative path from PROJECT_ROOT (e.g. "workflows/foo.md").
    Skips files larger than MAX_FILE_BYTES — records a warning placeholder.
    """
    files_to_load: set[Path] = set()

    for issue in issues:
        if issue.type == "BROKEN_REF":
            # source is workflow stem → load the workflow MD
            md = PROJECT_ROOT / "workflows" / f"{issue.source}.md"
            files_to_load.add(md)
        elif issue.type == "ORPHAN_TOOL":
            if issue.source.endswith(".py"):
                files_to_load.add(PROJECT_ROOT / "tools" / issue.source)
        elif issue.type == "EMPTY_WORKFLOW":
            if issue.source.endswith(".py"):
                files_to_load.add(PROJECT_ROOT / "tools" / issue.source)
            else:
                files_to_load.add(PROJECT_ROOT / "workflows" / f"{issue.source}.md")
        elif issue.type in ("LOW_SUCCESS", "CONSECUTIVE_FAIL", "SLOW_WORKFLOW", "INACTIVE"):
            # source is yml filename
            files_to_load.add(PROJECT_ROOT / ".github" / "workflows" / issue.source)
        elif issue.type == "NO_GH_ACTION":
            md = PROJECT_ROOT / "workflows" / f"{issue.source}.md"
            files_to_load.add(md)

    contents: dict[str, str] = {}
    tool_code_count = 0

    for path in sorted(files_to_load):
        if not path.exists():
            continue
        rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        # Check size first — before consuming a cap slot
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            contents[rel] = f"[SKIPPED: file too large ({size} bytes > {MAX_FILE_BYTES})]"
            continue
        # Apply tool_code cap (only for files that are within size limit)
        if str(path).endswith(".py"):
            tool_code_count += 1
            if tool_code_count > MAX_TOOL_CODE_PROPOSALS:
                contents[rel] = f"[SKIPPED: tool_code cap of {MAX_TOOL_CODE_PROPOSALS} reached]"
                continue
        contents[rel] = path.read_text(encoding="utf-8", errors="ignore")

    return contents


SYSTEM_PROMPT = """\
You are a WAT framework optimizer for the ORBI e-commerce team.
WAT = Workflows (markdown SOPs in workflows/) + Agents (AI) + Tools (Python scripts in tools/).

Given a list of framework issues and relevant file contents, generate specific actionable fixes.
Rules:
- For tool_code changes: ONLY add code (error handling, constants). Never delete or refactor.
- For workflow_md changes: fix broken references, add missing sections (additive preferred).
- For gh_action_yaml changes: fix timeouts, cron expressions, missing env vars only.
- Only suggest changes you are highly confident about.
- Return a JSON array only — no markdown fences, no explanation outside the JSON.

Each item in the array must have these exact fields:
  id (integer, 1-based), issue_type (string), source (string), rationale (string),
  change_type (workflow_md|gh_action_yaml|tool_code), file (relative path from repo root),
  original (exact text to find), replacement (exact text to replace it with)
"""


def generate_proposals(
    issues: list[Issue],
    file_contents: dict[str, str],
    model: str = "haiku",
) -> list[dict]:
    """
    Call Claude API with all issues + file contents.
    Returns list of proposal dicts (or [] on failure).
    """
    if not ANTHROPIC_KEY:
        print("WARNING: ANTHROPIC_API_KEY not set -- skipping proposal generation")
        return []

    model_id = MODEL_MAP[model]
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    issues_text = "\n".join(
        f"- [{i.type}|{i.severity}] source={i.source}: {i.detail}"
        for i in issues
    )
    files_text = "\n\n".join(
        f"=== {path} ===\n{content}"
        for path, content in file_contents.items()
    )
    user_message = f"Issues:\n{issues_text}\n\nFile contents:\n{files_text}"

    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences (```json ... ``` or ``` ... ```)
        import re as _re
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
        if fence_match:
            raw = fence_match.group(1)
        proposals = json.loads(raw)
        if not isinstance(proposals, list):
            print("WARNING: Claude returned non-list JSON -- ignoring")
            return []
        return proposals
    except Exception as e:
        print(f"WARNING: proposal generation failed: {e}")
        return []


def save_proposals(proposals: list[dict], issue_count: int) -> Path:
    """Save proposals to .tmp/proposals_latest.json. Returns the path."""
    TMP_DIR.mkdir(exist_ok=True)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "issue_count": issue_count,
        "proposals": proposals,
    }
    path = TMP_DIR / "proposals_latest.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="ORBI Workflow Optimizer")
    parser.add_argument("--dry-run",  action="store_true", help="No email, print summary")
    parser.add_argument("--preview",  action="store_true", help="Save HTML to .tmp/")
    parser.add_argument("--model",    default="haiku",     help="haiku or sonnet")
    parser.add_argument("--days",     type=int, default=7, help="GitHub Actions window")
    parser.add_argument("--execute",  action="store_true", help="Apply proposals")
    parser.add_argument("--proposal-id", default="",      help="Comma-separated IDs to apply")
    args = parser.parse_args()

    if args.model not in MODEL_MAP:
        print(f"ERROR: --model must be one of: {', '.join(MODEL_MAP)}")
        sys.exit(1)

    if args.execute:
        if not args.proposal_id:
            print("ERROR: --execute requires --proposal-id (e.g. --proposal-id 1,3,5)")
            sys.exit(1)
        # execute_proposals() will be implemented in Task 7
        print("--execute not yet implemented")
        return

    print("=== ORBI Workflow Optimizer ===")
    issues = collect_issues(days=args.days)
    print(f"Collected {len(issues)} issues")


if __name__ == "__main__":
    main()
