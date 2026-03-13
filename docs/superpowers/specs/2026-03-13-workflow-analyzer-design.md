# Workflow Analyzer Agent — Design Spec
**Date:** 2026-03-13
**Status:** Approved

---

## Overview

A single Python tool (`tools/run_workflow_analyzer.py`) that:
1. **Daily** — analyzes WAT framework health and emails a report of improvement opportunities
2. **On-demand with `--execute`** — auto-applies safe improvements (doc fixes), flags unsafe ones (code deletion) for human approval

Follows the existing `run_communicator.py` pattern exactly: collect → build HTML → send via `send_gmail.py`.

---

## Goals

- Identify disconnects between `workflows/*.md` documentation and `tools/*.py` implementations
- Surface GitHub Actions execution problems (failures, slowness, inactivity)
- Allow one-command execution of safe auto-fixes
- Require no new secrets — reuse all existing credentials

---

## Architecture

```
tools/run_workflow_analyzer.py
  ├── Module 1: static_analysis()      — filesystem-based, no external calls
  │     ├── parse_workflow_tools()     — extract tool refs from workflows/*.md
  │     ├── scan_actual_tools()        — list tools/*.py
  │     └── cross_reference()         — find broken links + orphans
  │
  ├── Module 2: github_analysis()      — GitHub API (reuses GH_PAT + GH_REPO)
  │     ├── fetch_recent_runs()        — last N days of workflow runs
  │     ├── calc_success_rates()       — per-workflow success %, avg duration
  │     └── detect_issues()           — flag failing, slow, inactive
  │
  ├── build_html()                     — render HTML report
  ├── execute_fixes()                  — apply safe fixes (--execute only)
  └── main()                           — CLI entrypoint
```

**Reused from existing codebase:**
- `tools/env_loader.py` — credential loading
- `tools/send_gmail.py` — email dispatch
- `GH_PAT`, `GH_REPO`, `GMAIL_*`, `COMMUNICATOR_RECIPIENT` secrets

---

## Module 1: Static Connectivity Analysis

### Tool Reference Extraction
Parse each `workflows/*.md` file for tool references:
- Markdown table rows containing `tools/` paths (e.g. `| \`process_influencer_order.py\``)
- Code block commands (e.g. `python tools/fetch_influencer_orders.py`)
- Inline backtick references (e.g. `` `tools/sync_influencer_notion.py` ``)

### Cross-Reference Checks

| Issue Type | Description | Severity |
|------------|-------------|----------|
| `BROKEN_REF` | Workflow references tool that doesn't exist in `tools/` | 🔴 High |
| `ORPHAN_TOOL` | Tool exists but no workflow references it | 🟡 Medium |
| `EMPTY_WORKFLOW` | Workflow MD has no tool references at all | 🟡 Medium |
| `NO_GH_ACTION` | Workflow MD exists but no matching GitHub Action — expected for agent-driven SOPs, only meaningful if `automated: true` front-matter is present | ℹ️ Info |

---

## Module 2: GitHub Actions Analysis

**API:** `GET /repos/{owner}/{repo}/actions/runs?per_page=100` with pagination loop until exhausted
**Period:** Last N days (default: **7**, configurable via `--days`). 7 days keeps result counts manageable without pagination issues; use `--days 30` for deeper analysis.

### Checks

| Issue Type | Threshold | Description |
|------------|-----------|-------------|
| `LOW_SUCCESS` | < 80% | Workflow success rate below threshold |
| `CONSECUTIVE_FAIL` | ≥ 2 | Currently failing consecutively |
| `SLOW_WORKFLOW` | Top 3 | Workflows with highest avg duration |
| `INACTIVE` | 0 runs | Workflow defined but never run in period |

---

## HTML Report Structure

```
[Header] ORBI Workflow Analyzer — 2026-03-13
[Summary] 🔴 2 critical  🟡 5 warnings  ℹ️ 3 info

[Section 1] Workflow ↔ Tool Connectivity
  ├── 🔴 BROKEN_REF: process_influencer_order.md → missing tool xyz.py
  ├── 🟡 ORPHAN_TOOL: _analyze_st.py (referenced by 0 workflows)
  └── 🟡 EMPTY_WORKFLOW: no_polar_financial_model.md (no tools listed)

[Section 2] GitHub Actions Health (last 30 days)
  ├── 🔴 CONSECUTIVE_FAIL: apify_daily.yml (3 consecutive failures)
  ├── 🟡 LOW_SUCCESS: some_workflow.yml (60% success rate)
  └── ℹ️ SLOW: data_keeper.yml avg 18min

[Section 3] Auto-Fix Summary (--execute mode only)
  ├── ✅ Fixed: updated workflow MD references (3 files)
  └── ⚠️ Needs approval: 2 orphan tools flagged for deletion
```

---

## `--execute` Mode

### Safe Auto-Fixes (runs automatically)
- Add `## Orphaned Tools` warning section to relevant workflow MDs (additive only)
- Add missing `## Tools` template section to empty workflows (additive only)

**Safety mechanism:** `--execute` prints the full diff to stdout before applying any changes. A copy is also written to `.tmp/workflow_analyzer_preview/` as disposable scratch (per CLAUDE.md, `.tmp/` is regenerable). The operator must review the stdout diff in the same session. `.tmp/` copy is not a persistent review artifact.

### Requires Human Approval (listed in report, not auto-applied)
- Fix broken tool references in workflow MDs — path correction algorithm is ambiguous; CLAUDE.md prohibits overwriting workflows without explicit permission

### Requires Human Approval (listed in report, not auto-applied)
- Fix broken tool references in workflow MDs (path corrections — correction algorithm is ambiguous)
- Deleting orphan tool `.py` files
- Modifying tool source code
- Disabling or deleting GitHub Action workflows

### Safety Rules
- All auto-fixes are git-diffable (text file edits only)
- Never delete files automatically
- Never modify `tools/*.py` source code
- Print summary of changes made to stdout

---

## CLI Interface

```bash
python tools/run_workflow_analyzer.py              # analyze + email report
python tools/run_workflow_analyzer.py --dry-run    # analyze only, no email
python tools/run_workflow_analyzer.py --preview    # save to .tmp/workflow_analysis.html
python tools/run_workflow_analyzer.py --execute    # analyze + auto-fix safe issues + email
python tools/run_workflow_analyzer.py --days 14    # set analysis window (default: 30)
```

---

## Daily Automation

```yaml
# .github/workflows/workflow_analyzer.yml
name: Workflow Analyzer
on:
  schedule:
    - cron: '0 2 * * *'   # Daily ~PST 18:00 (UTC 02:00, DST-approximate)
  workflow_dispatch:        # Manual trigger
```

**Required Secrets (all existing):**
- `GITHUB_TOKEN` (auto-injected by runner, no manual secret needed)
- `GMAIL_OAUTH_CREDENTIALS_JSON` — Gmail auth
- `GMAIL_TOKEN_JSON` — Gmail token
- `COMMUNICATOR_RECIPIENT` — email recipient

---

## Out of Scope (Phase 2)

- Claude API-powered natural language suggestions
- Workflow auto-improvement agent (`--execute` on code, not just docs)
- Performance benchmarking beyond GitHub Actions
