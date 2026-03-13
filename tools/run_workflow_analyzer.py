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

import requests

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
TOOLS_DIR     = PROJECT_ROOT / "tools"
GH_ACTIONS_DIR = PROJECT_ROOT / ".github" / "workflows"
TMP_DIR       = PROJECT_ROOT / ".tmp"

GH_TOKEN  = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN", "")
GH_REPO   = os.getenv("GITHUB_REPOSITORY", "")
RECIPIENT = os.getenv("COMMUNICATOR_RECIPIENT", "wj.choi@orbiters.co.kr")
SENDER    = os.getenv("GMAIL_SENDER", "orbiters11@gmail.com")


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
# Tasks 5-6: GitHub Actions fetch and analysis
# ---------------------------------------------------------------------------

def fetch_gh_runs(days: int) -> list[dict]:
    """
    Fetches all workflow runs from the last `days` days via GitHub API.
    Handles pagination via Link header.
    Returns list of run dicts.
    """
    if not GH_TOKEN or not GH_REPO:
        print("Warning: GH_TOKEN or GH_REPO not set -- skipping GitHub analysis")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    all_runs = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{GH_REPO}/actions/runs"
        params = {"per_page": 100, "page": page, "created": f">={cutoff_str}"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f"GitHub API error: {e}")
            break

        data = resp.json()
        runs = data.get("workflow_runs", [])

        for run in runs:
            created = run.get("created_at", "")
            updated = run.get("updated_at", "")
            dur_s = 0
            if created and updated:
                try:
                    fmt = "%Y-%m-%dT%H:%M:%SZ"
                    dur_s = int(
                        (datetime.strptime(updated, fmt) - datetime.strptime(created, fmt))
                        .total_seconds()
                    )
                except Exception:
                    pass

            all_runs.append({
                "workflow_file": Path(run.get("path", "")).name,
                "name":          run.get("name", ""),
                "conclusion":    run.get("conclusion"),
                "status":        run.get("status"),
                "created_at":    created,
                "duration_s":    dur_s,
                "html_url":      run.get("html_url", ""),
            })

        # Stop if GitHub signals no next page (authoritative) or empty page
        link_header = resp.headers.get("Link", "")
        if not runs or 'rel="next"' not in link_header:
            break
        page += 1

    print(f"GitHub: fetched {len(all_runs)} runs over last {days} days")
    return all_runs


def run_github_analysis(days: int) -> list[Issue]:
    """
    Analyzes GitHub Actions run history for:
    - LOW_SUCCESS: <80% success rate
    - CONSECUTIVE_FAIL: >=2 consecutive failures (most recent runs)
    - SLOW_WORKFLOW: top 3 by avg duration
    - INACTIVE: 0 runs in period
    """
    from collections import defaultdict

    issues = []
    runs = fetch_gh_runs(days)
    if not runs:
        return issues

    known_yml = scan_gh_action_files()

    # Group runs by workflow file
    by_wf: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        wf = r["workflow_file"]
        if wf:
            by_wf[wf].append(r)

    # INACTIVE: workflows defined but not run
    for yml in known_yml:
        if yml not in by_wf:
            issues.append(Issue(
                type="INACTIVE", severity="info",
                source=yml,
                detail=f"{yml} had 0 runs in the last {days} days"
            ))

    # Per-workflow analysis
    avg_durations = {}
    for wf, wf_runs in by_wf.items():
        completed = [r for r in wf_runs if r["conclusion"] in ("success", "failure")]
        if not completed:
            continue

        successes = sum(1 for r in completed if r["conclusion"] == "success")
        rate = successes / len(completed)

        # LOW_SUCCESS
        if rate < 0.80:
            issues.append(Issue(
                type="LOW_SUCCESS", severity="medium",
                source=wf,
                detail=f"{wf}: {successes}/{len(completed)} succeeded ({rate:.0%}) in last {days}d"
            ))

        # CONSECUTIVE_FAIL — check most recent runs in order
        sorted_runs = sorted(completed, key=lambda r: r["created_at"], reverse=True)
        consec_fail = 0
        for r in sorted_runs:
            if r["conclusion"] == "failure":
                consec_fail += 1
            else:
                break
        if consec_fail >= 2:
            issues.append(Issue(
                type="CONSECUTIVE_FAIL", severity="high",
                source=wf,
                detail=f"{wf}: {consec_fail} consecutive failures (most recent first)"
            ))

        # Avg duration for SLOW ranking
        durs = [r["duration_s"] for r in wf_runs if r["duration_s"] > 0]
        if durs:
            avg_durations[wf] = sum(durs) / len(durs)

    # SLOW_WORKFLOW: top 3
    top3 = sorted(avg_durations.items(), key=lambda x: x[1], reverse=True)[:3]
    for wf, avg_s in top3:
        mins = int(avg_s // 60)
        secs = int(avg_s % 60)
        issues.append(Issue(
            type="SLOW_WORKFLOW", severity="info",
            source=wf,
            detail=f"{wf}: avg duration {mins}m {secs}s over last {days}d"
        ))

    counts = {"high": 0, "medium": 0, "info": 0}
    for i in issues:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    print(f"GitHub analysis: {counts['high']} high, {counts['medium']} medium, {counts['info']} info")
    return issues


def execute_fixes(static_issues: list[Issue]) -> list[str]:
    return []


def _severity_badge(severity: str) -> str:
    colors = {"high": "#dc3545", "medium": "#fd7e14", "info": "#6c757d"}
    labels = {"high": "🔴 HIGH", "medium": "🟡 MEDIUM", "info": "ℹ️ INFO"}
    color = colors.get(severity, "#999")
    label = labels.get(severity, severity.upper())
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold">{label}</span>'


def _issues_table(issues: list[Issue], types: list[str]) -> str:
    filtered = [i for i in issues if i.type in types]
    if not filtered:
        return '<p style="color:#6c757d;font-style:italic">No issues found ✅</p>'
    rows = "".join(
        f'<tr><td style="padding:6px 12px">{_severity_badge(i.severity)}</td>'
        f'<td style="padding:6px 12px"><code>{i.source}</code></td>'
        f'<td style="padding:6px 12px">{i.detail}</td></tr>'
        for i in filtered
    )
    return f'''<table style="width:100%;border-collapse:collapse;font-size:14px">
    <thead><tr style="background:#f8f9fa">
      <th style="padding:6px 12px;text-align:left">Severity</th>
      <th style="padding:6px 12px;text-align:left">Source</th>
      <th style="padding:6px 12px;text-align:left">Detail</th>
    </tr></thead><tbody>{rows}</tbody></table>'''


def build_html(
    static_issues: list[Issue],
    github_issues: list[Issue],
    fixes_applied: list[str],
    days: int,
) -> str:
    all_issues = static_issues + github_issues
    n_high   = sum(1 for i in all_issues if i.severity == "high")
    n_medium = sum(1 for i in all_issues if i.severity == "medium")
    n_info   = sum(1 for i in all_issues if i.severity == "info")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    health_color = "#dc3545" if n_high else ("#fd7e14" if n_medium else "#28a745")
    health_label = "🔴 ACTION NEEDED" if n_high else ("🟡 WARNINGS" if n_medium else "🟢 HEALTHY")

    fixes_html = ""
    if fixes_applied:
        fix_items = "".join(f"<li>{f}</li>" for f in fixes_applied)
        fixes_html = f"""
        <h2 style="color:#198754">✅ Auto-Fixes Applied</h2>
        <ul style="font-size:14px">{fix_items}</ul>
        <hr>"""

    gh_repo_url = f"https://github.com/{GH_REPO}/actions" if GH_REPO else "#"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:900px;margin:0 auto;padding:20px;color:#212529}}
code{{background:#f8f9fa;padding:2px 5px;border-radius:3px}}</style>
</head><body>
<div style="background:{health_color};color:white;padding:16px 24px;border-radius:8px;margin-bottom:24px">
  <h1 style="margin:0;font-size:22px">ORBI Workflow Analyzer</h1>
  <p style="margin:4px 0 0">{now_str} &nbsp;|&nbsp; {health_label} &nbsp;|&nbsp;
    🔴 {n_high} high &nbsp; 🟡 {n_medium} medium &nbsp; ℹ️ {n_info} info</p>
</div>

{fixes_html}

<h2>1. Workflow ↔ Tool Connectivity</h2>
<h3>🔴 Broken References</h3>
{_issues_table(static_issues, ["BROKEN_REF"])}
<h3>🟡 Orphan Tools</h3>
{_issues_table(static_issues, ["ORPHAN_TOOL"])}
<h3>🟡 Empty Workflows (no tool section)</h3>
{_issues_table(static_issues, ["EMPTY_WORKFLOW"])}
<h3>ℹ️ Missing GitHub Actions (automated: true workflows)</h3>
{_issues_table(static_issues, ["NO_GH_ACTION"])}
<hr>

<h2>2. GitHub Actions Health (last {days} days)</h2>
<p style="font-size:13px"><a href="{gh_repo_url}">View all runs →</a></p>
<h3>🔴 Consecutive Failures</h3>
{_issues_table(github_issues, ["CONSECUTIVE_FAIL"])}
<h3>🟡 Low Success Rate (&lt;80%)</h3>
{_issues_table(github_issues, ["LOW_SUCCESS"])}
<h3>ℹ️ Slowest Workflows (top 3)</h3>
{_issues_table(github_issues, ["SLOW_WORKFLOW"])}
<h3>ℹ️ Inactive Workflows (0 runs)</h3>
{_issues_table(github_issues, ["INACTIVE"])}

<hr>
<p style="font-size:12px;color:#6c757d">
Generated by <code>run_workflow_analyzer.py</code> ·
<a href="https://github.com/{GH_REPO}">GitHub</a>
</p>
</body></html>"""


def send_report(html: str) -> None:
    """Send HTML report via send_gmail.py."""
    import subprocess

    TMP_DIR.mkdir(exist_ok=True)
    html_path = TMP_DIR / "workflow_analysis_email.html"
    html_path.write_text(html, encoding="utf-8")

    now_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"[ORBI Workflow Analyzer] {now_str}"

    cmd = [
        sys.executable,
        str(TOOLS_DIR / "send_gmail.py"),
        "--to", RECIPIENT,
        "--subject", subject,
        "--body-file", str(html_path),
    ]
    print(f"Sending to {RECIPIENT}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Email sent successfully.")
    else:
        print(f"Email failed: {result.stderr}")
        sys.exit(1)


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
