#!/usr/bin/env python3
"""
run_workflow_analyzer.py — ORBI Workflow Analyzer

Analyzes WAT framework health:
  1. Static: workflow MD ↔ tools/ connectivity
  2. Dynamic: GitHub Actions execution patterns (last 7 days)

Outputs HTML report + email.

Usage:
    python tools/run_workflow_analyzer.py              # analyze + email
    python tools/run_workflow_analyzer.py --dry-run    # analyze only, no email
    python tools/run_workflow_analyzer.py --preview    # save HTML to .tmp/
    python tools/run_workflow_analyzer.py --execute    # analyze + apply safe fixes + email
    python tools/run_workflow_analyzer.py --days 14    # set analysis window
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
TOOLS_DIR     = PROJECT_ROOT / "tools"
GH_ACTIONS_DIR = PROJECT_ROOT / ".github" / "workflows"
TMP_DIR       = PROJECT_ROOT / ".tmp"

GH_TOKEN = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN", "")
GH_REPO  = os.getenv("GITHUB_REPOSITORY", "")


# ---------------------------------------------------------------------------
# Task 2: Workflow MD parser
# ---------------------------------------------------------------------------

def parse_workflow_tools() -> dict[str, set[str]]:
    """
    Returns {workflow_stem: {tool_filename, ...}} for each workflows/*.md.
    Extracts tool references from:
      - Markdown table cells containing .py filenames
      - Code blocks with 'python tools/...' commands
      - Inline backtick references like `tools/foo.py`
    """
    result = {}
    patterns = [
        re.compile(r'`tools/([^`\s]+\.py)`'),           # inline backtick
        re.compile(r'python\s+tools/([^\s\n]+\.py)'),   # code block command
        re.compile(r'\|\s*`?tools/([a-zA-Z0-9_/]+\.py)`?\s*\|'),  # table cell (requires tools/ prefix)
    ]

    for md_file in sorted(WORKFLOWS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        found = set()
        for pat in patterns:
            for match in pat.findall(text):
                # strip path prefix if present (e.g. tools/foo.py -> foo.py)
                found.add(Path(match).name)
        result[md_file.stem] = found

    return result


# ---------------------------------------------------------------------------
# Task 3: Scanners
# ---------------------------------------------------------------------------

def scan_actual_tools() -> set[str]:
    """Returns set of .py filenames that exist in tools/."""
    return {f.name for f in TOOLS_DIR.glob("*.py")}


def scan_gh_action_files() -> set[str]:
    """Returns set of .yml filenames in .github/workflows/."""
    return {f.name for f in GH_ACTIONS_DIR.glob("*.yml")}


# ---------------------------------------------------------------------------
# Task 4: Issue dataclass and static analysis
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    type: str          # BROKEN_REF | ORPHAN_TOOL | EMPTY_WORKFLOW | NO_GH_ACTION
    severity: str      # high | medium | info
    source: str        # workflow stem or tool filename
    detail: str        # human-readable description


def run_static_analysis() -> list[Issue]:
    issues = []
    workflow_tools = parse_workflow_tools()
    actual_tools   = scan_actual_tools()
    gh_actions     = scan_gh_action_files()

    all_referenced = set()

    for wf_stem, refs in workflow_tools.items():
        # NO_GH_ACTION — check for ALL workflows regardless of whether they have tool refs
        md_text = (WORKFLOWS_DIR / f"{wf_stem}.md").read_text(encoding="utf-8", errors="ignore")
        if "automated: true" in md_text.lower():
            matching_yml = f"{wf_stem}.yml"
            if matching_yml not in gh_actions:
                issues.append(Issue(
                    type="NO_GH_ACTION", severity="info",
                    source=wf_stem,
                    detail=f"workflows/{wf_stem}.md is marked automated:true but no .github/workflows/{wf_stem}.yml found"
                ))

        # EMPTY_WORKFLOW
        if not refs:
            issues.append(Issue(
                type="EMPTY_WORKFLOW", severity="medium",
                source=wf_stem,
                detail=f"workflows/{wf_stem}.md has no tool references"
            ))
            continue

        all_referenced.update(refs)

        # BROKEN_REF
        for tool in refs:
            if tool not in actual_tools:
                issues.append(Issue(
                    type="BROKEN_REF", severity="high",
                    source=wf_stem,
                    detail=f"workflows/{wf_stem}.md references tools/{tool} which does not exist"
                ))

    # ORPHAN_TOOL — exclude private/utility scripts starting with _
    for tool in sorted(actual_tools):
        if tool.startswith("_"):
            continue
        if tool not in all_referenced:
            issues.append(Issue(
                type="ORPHAN_TOOL", severity="medium",
                source=tool,
                detail=f"tools/{tool} is not referenced by any workflow"
            ))

    # Summary
    counts = {"high": 0, "medium": 0, "info": 0}
    for i in issues:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    print(f"Static analysis: {counts['high']} high, {counts['medium']} medium, {counts['info']} info")
    return issues


# ---------------------------------------------------------------------------
# Stubs (Tasks 5+)
# ---------------------------------------------------------------------------

def run_github_analysis(days: int) -> list[Issue]:
    print("GitHub analysis: (stub)")
    return []


def execute_fixes(static_issues: list[Issue]) -> list[str]:
    return []


def build_html(static_issues, github_issues, fixes_applied, days) -> str:
    return "<html><body>stub</body></html>"


def send_report(html: str) -> None:
    pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ORBI Workflow Analyzer")
    parser.add_argument("--dry-run",  action="store_true", help="No email send")
    parser.add_argument("--preview",  action="store_true", help="Save HTML to .tmp/")
    parser.add_argument("--execute",  action="store_true", help="Apply safe auto-fixes")
    parser.add_argument("--days",     type=int, default=7, help="GitHub Actions lookback days")
    args = parser.parse_args()

    print("=== ORBI Workflow Analyzer ===")

    static_issues  = run_static_analysis()
    github_issues  = run_github_analysis(days=args.days)

    fixes_applied = []
    if args.execute:
        fixes_applied = execute_fixes(static_issues)

    html = build_html(static_issues, github_issues, fixes_applied, days=args.days)

    if args.preview or args.dry_run:
        TMP_DIR.mkdir(exist_ok=True)
        out = TMP_DIR / "workflow_analysis.html"
        out.write_text(html, encoding="utf-8")
        print(f"Preview saved to {out}")

    if not args.dry_run:
        send_report(html)
    else:
        print("[dry-run] Email not sent.")


if __name__ == "__main__":
    main()
