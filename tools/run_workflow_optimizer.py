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
