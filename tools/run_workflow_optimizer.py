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
import difflib
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
IGNORE_FILE = PROJECT_ROOT / ".optimizer_ignore"


def load_ignored_stems() -> set[str]:
    """
    Load workflow stems to permanently exclude from .optimizer_ignore.
    Lines starting with '#' and blank lines are ignored.
    """
    if not IGNORE_FILE.exists():
        return set()
    lines = IGNORE_FILE.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")}


def collect_issues(days: int = 7) -> tuple[list[Issue], set[str]]:
    """
    Collect WAT framework issues (static + GitHub Actions).
    Filters out workflow MD issues for stems listed in .optimizer_ignore.
    Returns (issues, skipped_stems).
    """
    all_issues = run_static_analysis()
    all_issues += run_github_analysis(days)

    ignored = load_ignored_stems()
    WORKFLOW_ISSUE_TYPES = {"BROKEN_REF", "EMPTY_WORKFLOW", "NO_GH_ACTION"}

    filtered, skipped_stems = [], set()
    for issue in all_issues:
        if issue.type in WORKFLOW_ISSUE_TYPES:
            stem = issue.source.removesuffix(".md")
            if stem in ignored:
                skipped_stems.add(stem)
                continue
        filtered.append(issue)
    return filtered, skipped_stems


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
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences: find first newline after opening ```, take everything,
        # strip trailing ``` — robust against nested backticks in replacement values
        if raw.startswith("```"):
            first_newline = raw.find("\n")
            raw = raw[first_newline + 1:] if first_newline != -1 else raw[3:]
            if raw.rstrip().endswith("```"):
                raw = raw.rstrip()[:-3].rstrip()
        proposals = json.loads(raw)
        if not isinstance(proposals, list):
            print("WARNING: Claude returned non-list JSON -- ignoring")
            return []
        return proposals
    except Exception as e:
        print(f"WARNING: proposal generation failed: {e}")
        return []


_BADGE = {
    "BROKEN_REF":      "🔴",
    "ORPHAN_TOOL":     "🟡",
    "EMPTY_WORKFLOW":  "🟡",
    "NO_GH_ACTION":    "ℹ️",
    "LOW_SUCCESS":     "🔴",
    "CONSECUTIVE_FAIL":"🔴",
    "SLOW_WORKFLOW":   "🟡",
    "INACTIVE":        "ℹ️",
}
_TYPE_COLOR = {
    "workflow_md":    "#1a73e8",
    "gh_action_yaml": "#e65100",
    "tool_code":      "#2e7d32",
}


def build_proposal_email(
    proposals: list[dict],
    issue_count: int,
    date_str: str | None = None,
) -> str:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    type_counts: dict[str, int] = {}
    for p in proposals:
        type_counts[p["change_type"]] = type_counts.get(p["change_type"], 0) + 1

    summary_parts = [
        f"{v} {k.replace('_', ' ')}" for k, v in sorted(type_counts.items())
    ]
    summary = " &nbsp;|&nbsp; ".join(summary_parts) if summary_parts else "No proposals"

    cards_html = ""
    for p in proposals:
        badge = _BADGE.get(p["issue_type"], "•")
        color = _TYPE_COLOR.get(p["change_type"], "#555")
        orig_escaped  = p["original"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        repl_escaped  = p["replacement"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cards_html += f"""
        <div style="border:1px solid #ddd;border-radius:8px;padding:16px;margin-bottom:16px;">
          <div style="font-size:15px;font-weight:600;margin-bottom:6px;">
            {badge} Proposal #{p['id']} &nbsp;
            <span style="color:{color};font-size:12px;font-weight:500;
                         background:#f0f0f0;padding:2px 8px;border-radius:4px;">
              {p['change_type']}
            </span>
          </div>
          <div style="color:#555;font-size:13px;margin-bottom:4px;">
            <b>Issue:</b> {p['issue_type']} — {p['source']}
          </div>
          <div style="color:#555;font-size:13px;margin-bottom:4px;">
            <b>File:</b> <code style="background:#f5f5f5;padding:1px 4px;">{p['file']}</code>
          </div>
          <div style="color:#555;font-size:13px;margin-bottom:8px;">
            <b>Why:</b> {p['rationale']}
          </div>
          <div style="background:#fff8e1;border-radius:4px;padding:8px;font-size:12px;
                      font-family:monospace;white-space:pre-wrap;margin-bottom:4px;">
            <span style="color:#b71c1c;">- {orig_escaped}</span>
          </div>
          <div style="background:#e8f5e9;border-radius:4px;padding:8px;font-size:12px;
                      font-family:monospace;white-space:pre-wrap;margin-bottom:10px;">
            <span style="color:#1b5e20;">+ {repl_escaped}</span>
          </div>
          <div style="font-size:12px;color:#888;">
            To apply this fix:
            <code style="background:#f5f5f5;padding:1px 6px;">
              python tools/run_workflow_optimizer.py --execute --proposal-id {p['id']}
            </code>
          </div>
        </div>"""

    all_ids = ",".join(str(p["id"]) for p in proposals)
    apply_all_cmd = f"python tools/run_workflow_optimizer.py --execute --proposal-id {all_ids}"

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#333;">
  <h2 style="color:#1a73e8;border-bottom:2px solid #1a73e8;padding-bottom:8px;">
    ORBI Workflow Optimizer — {date_str}
  </h2>
  <div style="background:#f8f9fa;border-radius:8px;padding:12px 16px;margin-bottom:20px;">
    <b>{len(proposals)} proposals</b> from {issue_count} issues &nbsp;|&nbsp; {summary}
  </div>
  {cards_html}
  <div style="background:#e3f2fd;border-radius:8px;padding:12px 16px;margin-top:20px;font-size:13px;">
    <b>Apply all proposals:</b><br>
    <code style="background:#fff;padding:4px 8px;border-radius:4px;display:inline-block;margin-top:6px;">
      {apply_all_cmd}
    </code>
  </div>
  <p style="color:#aaa;font-size:11px;margin-top:24px;">
    ORBI Workflow Optimizer &nbsp;·&nbsp; WAT Framework
  </p>
</body></html>"""


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


def send_proposal_email(html: str, date_str: str, proposal_count: int) -> None:
    """Send the proposal HTML via send_gmail.py."""
    TMP_DIR.mkdir(exist_ok=True)
    tmp_html = TMP_DIR / "workflow_optimizer_preview.html"
    tmp_html.write_text(html, encoding="utf-8")
    subject = f"[ORBI Optimizer] {proposal_count} proposals -- {date_str}"
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "send_gmail.py"),
         "--to", RECIPIENT,
         "--sender", SENDER,
         "--subject", subject,
         "--body-file", str(tmp_html)],
        check=True,
    )


def execute_proposals(proposal_id_str: str) -> None:
    """
    Load proposals from .tmp/proposals_latest.json and apply the specified IDs.
    Prints unified diff before each change. Commits if any changes applied.
    """
    proposals_path = TMP_DIR / "proposals_latest.json"
    if not proposals_path.exists():
        print("ERROR: No proposals file found. Run without --execute first.")
        sys.exit(1)

    data = json.loads(proposals_path.read_text(encoding="utf-8"))

    # Staleness check
    generated_at = datetime.fromisoformat(data["generated_at"])
    age_hours = (datetime.now(timezone.utc) - generated_at).total_seconds() / 3600
    if age_hours > 24:
        print(f"WARNING: proposals are {age_hours:.1f}h old (>24h). Consider re-running without --execute first.")

    all_proposals = {p["id"]: p for p in data["proposals"]}

    # Parse requested IDs
    requested_ids: list[int] = []
    for part in proposal_id_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            requested_ids.append(int(part))
        except ValueError:
            print(f"WARNING: invalid proposal ID '{part}' -- skipping")

    applied: list[int] = []
    changed_files: list[str] = []

    for pid in requested_ids:
        if pid not in all_proposals:
            print(f"WARNING: proposal ID {pid} not found -- skipping")
            continue

        p = all_proposals[pid]
        file_path = PROJECT_ROOT / p["file"]

        if not file_path.exists():
            print(f"SKIP #{pid}: file not found: {p['file']}")
            continue

        original_text = file_path.read_text(encoding="utf-8")
        if p["original"] not in original_text:
            print(f"SKIP #{pid}: original text not found in {p['file']} (file may have changed)")
            continue

        new_text = original_text.replace(p["original"], p["replacement"], 1)

        # Print unified diff
        diff_lines = list(difflib.unified_diff(
            original_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{p['file']}",
            tofile=f"b/{p['file']}",
        ))
        print(f"\n--- Proposal #{pid}: {p['issue_type']} ({p['change_type']}) ---")
        print(f"    {p['rationale']}")
        print("".join(diff_lines) if diff_lines else "  (no diff)")

        file_path.write_text(new_text, encoding="utf-8")
        applied.append(pid)
        changed_files.append(p["file"])
        print(f"APPLIED #{pid}: {p['file']}")

    if not applied:
        print("\nNo proposals applied (all skipped or not found).")
        return

    # Git commit
    applied_str = ",".join(str(i) for i in applied)
    commit_msg = f"feat(optimizer): apply proposals #{applied_str}"
    try:
        subprocess.run(["git", "add"] + changed_files, cwd=str(PROJECT_ROOT), check=True)
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(PROJECT_ROOT), check=True
        )
        print(f"\nCommitted: {commit_msg}")
    except subprocess.CalledProcessError as e:
        print(f"WARNING: git commit failed: {e}")

    print(f"\nSummary: applied {len(applied)}/{len(requested_ids)} proposals: #{applied_str}")


def main():
    parser = argparse.ArgumentParser(description="ORBI Workflow Optimizer")
    parser.add_argument("--dry-run",  action="store_true", help="No email, print summary")
    parser.add_argument("--preview",  action="store_true", help="Save HTML to .tmp/")
    parser.add_argument("--model",    default="haiku",     help="haiku or sonnet")
    parser.add_argument("--days",       type=int, default=7,  help="GitHub Actions window")
    parser.add_argument("--stale-days", type=int, default=60, help="Skip workflow MDs not modified in last N days (non-bulk commits)")
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
        execute_proposals(args.proposal_id)
        return

    print("=== ORBI Workflow Optimizer ===")
    issues, skipped_stems = collect_issues(days=args.days, stale_days=args.stale_days)
    if skipped_stems:
        print(f"Skipped stale workflows (>{args.stale_days}d no meaningful commit): {', '.join(sorted(skipped_stems))}")
    print(f"Collected {len(issues)} issues")

    file_contents = read_file_contents(issues)
    print(f"Loaded {len(file_contents)} file(s) for context")

    proposals = generate_proposals(issues, file_contents, model=args.model)
    print(f"Generated {len(proposals)} proposals")

    if not proposals:
        print("No proposals generated. Exiting.")
        return

    save_proposals(proposals, issue_count=len(issues))
    print("Proposals saved to .tmp/proposals_latest.json")

    date_str = datetime.now().strftime("%Y-%m-%d")
    html = build_proposal_email(proposals, issue_count=len(issues), date_str=date_str)

    if args.preview or args.dry_run:
        preview_path = TMP_DIR / "workflow_optimizer_preview.html"
        TMP_DIR.mkdir(exist_ok=True)
        preview_path.write_text(html, encoding="utf-8")
        print(f"Preview saved to {preview_path}")

    if args.dry_run:
        print("[dry-run] Email not sent.")
        return

    send_proposal_email(html, date_str, proposal_count=len(proposals))
    print("Proposal email sent.")


if __name__ == "__main__":
    main()
