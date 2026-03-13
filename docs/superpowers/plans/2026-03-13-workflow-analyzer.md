# Workflow Analyzer Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/run_workflow_analyzer.py` — a daily automated agent that analyzes WAT framework health (workflow↔tool connectivity + GitHub Actions execution patterns) and emails an HTML report, with an `--execute` flag that applies safe additive doc fixes.

**Architecture:** Two analysis modules (static filesystem + GitHub API) feed a shared HTML builder, then dispatch via the existing `send_gmail.py`. A separate GitHub Actions workflow triggers it daily. The `--execute` flag adds a diff-preview → apply step for additive-only workflow MD fixes.

**Tech Stack:** Python 3.11 (GitHub Actions) / 3.14 (local), `requests`, `pathlib`, `re`, `argparse`, existing `env_loader.py` + `send_gmail.py`

**Spec:** `docs/superpowers/specs/2026-03-13-workflow-analyzer-design.md`

---

## Chunk 1: Static Analysis Module

### Task 1: Scaffold the tool with CLI

**Files:**
- Create: `tools/run_workflow_analyzer.py`

- [ ] **Step 1: Create the file with imports and CLI skeleton**

```python
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
```

- [ ] **Step 2: Verify the file runs without crashing (stubs not yet defined)**

```bash
/c/Users/user/AppData/Local/Programs/Python/Python314/python.exe tools/run_workflow_analyzer.py --dry-run
```
Expected: `NameError: name 'run_static_analysis' is not defined` (that's fine — scaffold works)

- [ ] **Step 3: Commit scaffold**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): scaffold CLI with argparse"
```

---

### Task 2: Parse workflow MDs for tool references

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `parse_workflow_tools()`

- [ ] **Step 1: Add the parser function**

```python
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
```

- [ ] **Step 2: Quick manual verification**

```python
# Add to bottom of file temporarily, remove after check:
if __name__ == "__main__":
    wf = parse_workflow_tools()
    for k, v in list(wf.items())[:3]:
        print(f"{k}: {v}")
```

Run: `python tools/run_workflow_analyzer.py`
Expected: Each workflow stem maps to a set of `.py` filenames (some may be empty sets for doc-only workflows)

- [ ] **Step 3: Remove the debug print and commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): parse workflow MD tool references"
```

---

### Task 3: Scan actual tools

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `scan_actual_tools()`

- [ ] **Step 1: Add the scanner**

```python
def scan_actual_tools() -> set[str]:
    """Returns set of .py filenames that exist in tools/."""
    return {f.name for f in TOOLS_DIR.glob("*.py")}
```

- [ ] **Step 2: Also add `scan_gh_action_files()`**

```python
def scan_gh_action_files() -> set[str]:
    """Returns set of .yml filenames in .github/workflows/."""
    return {f.name for f in GH_ACTIONS_DIR.glob("*.yml")}
```

- [ ] **Step 3: Commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): scan actual tools and GH action files"
```

---

### Task 4: Cross-reference and build static issues list

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `run_static_analysis()`

- [ ] **Step 1: Add issue dataclass and cross-reference logic**

```python
from dataclasses import dataclass, field

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

        # NO_GH_ACTION — only flag if workflow MD has 'automated: true' front-matter
        md_text = (WORKFLOWS_DIR / f"{wf_stem}.md").read_text(encoding="utf-8", errors="ignore")
        if "automated: true" in md_text.lower():
            matching_yml = f"{wf_stem}.yml"
            if matching_yml not in gh_actions:
                issues.append(Issue(
                    type="NO_GH_ACTION", severity="info",
                    source=wf_stem,
                    detail=f"workflows/{wf_stem}.md is marked automated:true but no .github/workflows/{wf_stem}.yml found"
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
```

- [ ] **Step 2: Wire into main() and test**

Replace the stub call in `main()`:
```python
static_issues = run_static_analysis()
```

Run: `python tools/run_workflow_analyzer.py --dry-run`
Expected: Prints something like `Static analysis: 2 high, 15 medium, 0 info`

- [ ] **Step 3: Commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): static cross-reference analysis (BROKEN_REF, ORPHAN, EMPTY)"
```

---

## Chunk 2: GitHub Actions Analysis Module

### Task 5: Fetch GitHub Actions run history (paginated)

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `fetch_gh_runs()`

- [ ] **Step 1: Add paginated GitHub API fetch**

```python
import requests

def fetch_gh_runs(days: int) -> list[dict]:
    """
    Fetches all workflow runs from the last `days` days via GitHub API.
    Handles pagination automatically.
    Returns list of run dicts (workflow_path, conclusion, created_at, run_duration_s).
    """
    if not GH_TOKEN or not GH_REPO:
        print("Warning: GH_TOKEN or GH_REPO not set — skipping GitHub analysis")
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
        if not runs:
            break

        for run in runs:
            created = run.get("created_at", "")
            updated = run.get("updated_at", "")
            # duration in seconds
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
                "workflow_file": Path(run.get("path", "")).name,  # e.g. communicator.yml
                "name":          run.get("name", ""),
                "conclusion":    run.get("conclusion"),  # success|failure|cancelled|None
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
```

- [ ] **Step 2: Quick smoke test**

```bash
GH_PAT=your_token GITHUB_REPOSITORY=Orbiters11-dev/orbi-main \
  python -c "
import sys; sys.path.insert(0,'tools')
from env_loader import load_env; load_env()
from run_workflow_analyzer import fetch_gh_runs
runs = fetch_gh_runs(7)
print(len(runs), 'runs')
print(runs[0] if runs else 'no runs')
"
```
Expected: prints count > 0 and first run dict

- [ ] **Step 3: Commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): paginated GitHub Actions run fetcher"
```

---

### Task 6: Calculate metrics and detect issues

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `run_github_analysis()`

- [ ] **Step 1: Add metric calculation and issue detection**

```python
def run_github_analysis(days: int) -> list[Issue]:
    """
    Analyzes GitHub Actions run history for:
    - LOW_SUCCESS: <80% success rate
    - CONSECUTIVE_FAIL: >=2 consecutive failures (most recent runs)
    - SLOW_WORKFLOW: top 3 by avg duration
    - INACTIVE: 0 runs in period
    """
    issues = []
    runs = fetch_gh_runs(days)
    if not runs:
        return issues

    known_yml = scan_gh_action_files()

    # Group runs by workflow file
    from collections import defaultdict
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

        # CONSECUTIVE_FAIL — check most recent N runs in order
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
```

- [ ] **Step 2: Test end-to-end analysis**

```bash
python tools/run_workflow_analyzer.py --dry-run
```
Expected: Both analysis steps print summaries, no crash.

- [ ] **Step 3: Commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): GitHub Actions metrics and issue detection"
```

---

## Chunk 3: HTML Report + Email

### Task 7: Build HTML report

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `build_html()`

- [ ] **Step 1: Add HTML builder**

```python
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
```

- [ ] **Step 2: Test HTML output**

```bash
python tools/run_workflow_analyzer.py --preview
```

Then open `.tmp/workflow_analysis.html` in a browser.
Expected: Clean HTML with all 4 connectivity sections + 4 GH Actions sections. Data populated.

- [ ] **Step 3: Commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): HTML report builder"
```

---

### Task 8: Wire up email dispatch

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `send_report()`

- [ ] **Step 1: Add send function (mirrors run_communicator.py pattern)**

```python
RECIPIENT = os.getenv("COMMUNICATOR_RECIPIENT", "wj.choi@orbiters.co.kr")
SENDER    = os.getenv("GMAIL_SENDER", "orbiters11@gmail.com")


def send_report(html: str) -> None:
    """Send HTML report via send_gmail.py."""
    import subprocess
    import tempfile

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
```

- [ ] **Step 2: Fix `--dry_run` typo in main() — argparse stores `--dry-run` as `dry_run`**

Check `main()` uses `args.dry_run` (with underscore), not `args.dry-run`.

- [ ] **Step 3: End-to-end dry-run test**

```bash
python tools/run_workflow_analyzer.py --dry-run --preview
```
Expected: Analysis runs, HTML saved to `.tmp/`, "Email not sent." printed, no errors.

- [ ] **Step 4: Commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): email dispatch via send_gmail.py"
```

---

## Chunk 4: `--execute` Mode

### Task 9: Implement execute_fixes() with diff preview

**Files:**
- Modify: `tools/run_workflow_analyzer.py` — add `execute_fixes()`

- [ ] **Step 1: Add the execute function**

```python
def execute_fixes(static_issues: list[Issue]) -> list[str]:
    """
    Applies safe additive-only fixes to workflows/*.md:
    - Adds '## Orphaned Tools' warning section for ORPHAN_TOOL issues
    - Adds '## Tools' template section to EMPTY_WORKFLOW files

    Prints full diff to stdout. Writes scratch copy to .tmp/workflow_analyzer_preview/.
    Never deletes files. Never modifies tools/*.py.

    Returns list of human-readable descriptions of changes applied.
    """
    import difflib

    preview_dir = TMP_DIR / "workflow_analyzer_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    applied = []

    # Fix 1: Add ## Tools template to empty workflows
    empty_wf_stems = {i.source for i in static_issues if i.type == "EMPTY_WORKFLOW"}
    for stem in sorted(empty_wf_stems):
        md_path = WORKFLOWS_DIR / f"{stem}.md"
        if not md_path.exists():
            continue
        original = md_path.read_text(encoding="utf-8")
        if "## Tools" in original:
            continue  # already has it somehow
        addition = "\n\n## Tools\n\n_No tools documented yet. Add tool references here._\n"
        updated = original.rstrip() + addition
        _apply_fix(md_path, original, updated, preview_dir, applied,
                   desc=f"Added ## Tools template to workflows/{stem}.md")

    # Fix 2: Add ## Orphaned Tools note to relevant workflows
    # Strategy: append a single ORPHANED_TOOLS.md note file (not individual workflow edits)
    orphan_tools = sorted({i.source for i in static_issues if i.type == "ORPHAN_TOOL"})
    if orphan_tools:
        note_path = WORKFLOWS_DIR / "_orphaned_tools.md"
        lines = ["# Orphaned Tools\n\n",
                 "These tools exist in `tools/` but are not referenced by any workflow.\n",
                 "Review and either document them in a workflow or remove them.\n\n"]
        for t in orphan_tools:
            lines.append(f"- `tools/{t}`\n")
        original = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
        updated = "".join(lines)
        if updated != original:
            _apply_fix(note_path, original, updated, preview_dir, applied,
                       desc=f"Updated workflows/_orphaned_tools.md ({len(orphan_tools)} orphans listed)")

    return applied


def _apply_fix(
    path: Path,
    original: str,
    updated: str,
    preview_dir: Path,
    applied: list[str],
    desc: str,
) -> None:
    """Print diff to stdout, write scratch copy, apply to original."""
    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        lineterm="",
    ))
    if not diff:
        return

    print(f"\n--- FIX: {desc} ---")
    print("".join(diff[:30]))  # show first 30 lines of diff
    if len(diff) > 30:
        print(f"  ... ({len(diff) - 30} more lines)")

    # Write scratch copy to .tmp/
    scratch = preview_dir / path.name
    scratch.write_text(updated, encoding="utf-8")

    # Apply to actual file
    path.write_text(updated, encoding="utf-8")
    applied.append(desc)
    print(f"✅ Applied: {desc}")
```

- [ ] **Step 2: Test --execute mode**

```bash
python tools/run_workflow_analyzer.py --execute --dry-run
```
Expected: Prints diffs to stdout. EMPTY_WORKFLOW files get `## Tools` appended. `workflows/_orphaned_tools.md` created/updated. Email skipped (--dry-run).

- [ ] **Step 3: Verify no tools/*.py were modified**

```bash
git diff --name-only
```
Expected: Only `workflows/*.md` files and `workflows/_orphaned_tools.md` changed.

- [ ] **Step 4: Commit**

```bash
git add tools/run_workflow_analyzer.py
git commit -m "feat(analyzer): --execute mode with stdout diff preview and additive-only fixes"
```

---

## Chunk 5: GitHub Actions Workflow + CLAUDE.md Integration

### Task 10: Create workflow_analyzer.yml

**Files:**
- Create: `.github/workflows/workflow_analyzer.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: ORBI Workflow Analyzer

on:
  schedule:
    - cron: '0 2 * * *'   # Daily ~PST 18:00 (UTC 02:00, DST-approximate)
  workflow_dispatch:
    inputs:
      days:
        description: 'GitHub Actions lookback days (default: 7)'
        required: false
        default: '7'
      execute:
        description: 'Apply auto-fixes? (true/false)'
        required: false
        default: 'false'

jobs:
  analyze:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install --quiet requests python-dotenv google-auth \
            google-auth-oauthlib google-api-python-client

      - name: Write .env
        run: |
          cat > .env <<'ENVEOF'
          GMAIL_OAUTH_CREDENTIALS_PATH=credentials/gmail_oauth_credentials.json
          GMAIL_TOKEN_PATH=credentials/gmail_token.json
          GMAIL_SENDER=orbiters11@gmail.com
          COMMUNICATOR_RECIPIENT=${{ secrets.COMMUNICATOR_RECIPIENT }}
          ENVEOF
          sed -i 's/^[[:space:]]*//' .env

      - name: Write credentials
        run: |
          mkdir -p credentials
          echo '${{ secrets.GMAIL_OAUTH_CREDENTIALS_JSON }}' > credentials/gmail_oauth_credentials.json
          echo '${{ secrets.GMAIL_TOKEN_JSON }}'             > credentials/gmail_token.json

      - name: Run Workflow Analyzer
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          mkdir -p .tmp
          DAYS=${{ github.event.inputs.days || '7' }}
          EXECUTE_FLAG=""
          if [ "${{ github.event.inputs.execute }}" = "true" ]; then
            EXECUTE_FLAG="--execute"
          fi
          python -u tools/run_workflow_analyzer.py --days $DAYS $EXECUTE_FLAG
```

- [ ] **Step 2: Commit workflow file**

```bash
git add .github/workflows/workflow_analyzer.yml
git commit -m "feat(analyzer): GitHub Actions daily schedule"
```

---

### Task 11: Add CLAUDE.md trigger section

**Files:**
- Modify: `CLAUDE.md` — add trigger section for the new agent

- [ ] **Step 1: Add trigger section to CLAUDE.md**

Append to `CLAUDE.md` (after the last existing agent section):

```markdown
## 워크플로우 분석기 (Workflow Analyzer)

"워크플로우 분석기" 또는 관련 명령이 오면 즉시 아래를 실행한다:

### 명령

| 명령 | 설명 |
|------|------|
| `python tools/run_workflow_analyzer.py --dry-run` | 분석만 (발송 없음) |
| `python tools/run_workflow_analyzer.py --preview` | HTML 프리뷰 → `.tmp/workflow_analysis.html` |
| `python tools/run_workflow_analyzer.py --execute --dry-run` | 수정 제안 diff 출력 |
| `python tools/run_workflow_analyzer.py --execute` | 안전한 문서 수정 적용 + 발송 |
| `python tools/run_workflow_analyzer.py --days 30` | 30일 GitHub Actions 이력 분석 |

### 자동화
- GitHub Actions `workflow_analyzer.yml` — 매일 UTC 02:00 자동 실행
- 수신자: `COMMUNICATOR_RECIPIENT`

### 트리거 키워드
워크플로우 분석기, workflow analyzer, 워크플로우 효율, 고아 툴, orphan tool, broken workflow, GitHub Actions 분석
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add workflow analyzer agent trigger to CLAUDE.md"
```

---

### Task 12: Final integration test

- [ ] **Step 1: Full dry-run end-to-end**

```bash
python tools/run_workflow_analyzer.py --dry-run --preview --days 7
```

Expected output:
```
=== ORBI Workflow Analyzer ===
Static analysis: N high, N medium, N info
GitHub: fetched N runs over last 7 days
GitHub analysis: N high, N medium, N info
Preview saved to .tmp/workflow_analysis.html
[dry-run] Email not sent.
```

- [ ] **Step 2: Open `.tmp/workflow_analysis.html` and verify**

All 8 sections render. Issue counts match stdout. No broken HTML.

- [ ] **Step 3: Manual dispatch from GitHub Actions**

Go to GitHub → Actions → ORBI Workflow Analyzer → Run workflow (days=7, execute=false).
Expected: Green run. Email received at `COMMUNICATOR_RECIPIENT`.

- [ ] **Step 4: Final commit tag**

```bash
git add -A
git commit -m "feat: workflow analyzer agent complete — daily report + --execute mode"
```

---

## Summary

| File | Role |
|------|------|
| `tools/run_workflow_analyzer.py` | Main tool (create) |
| `.github/workflows/workflow_analyzer.yml` | Daily schedule (create) |
| `CLAUDE.md` | Agent trigger section (modify) |
| `workflows/_orphaned_tools.md` | Auto-generated by --execute (create) |
| `docs/superpowers/specs/2026-03-13-workflow-analyzer-design.md` | Spec (already committed) |

**No new secrets required.** Reuses `GITHUB_TOKEN` (auto), `GMAIL_OAUTH_CREDENTIALS_JSON`, `GMAIL_TOKEN_JSON`, `COMMUNICATOR_RECIPIENT`.
