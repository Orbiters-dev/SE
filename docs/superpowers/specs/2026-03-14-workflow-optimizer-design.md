# Workflow Optimizer Agent — Design Spec
**Date:** 2026-03-14
**Status:** Approved

---

## Overview

A standalone Python tool (`tools/run_workflow_optimizer.py`) that:
1. **`--propose` mode (default)** — collects WAT framework issues, calls Claude API to generate specific actionable proposals, saves to `.tmp/proposals_latest.json`, emails HTML report
2. **`--execute --proposal-id 1,3,5`** — applies the specified approved proposals (workflow MD edits, GitHub Actions YAML edits, tools/*.py code edits), shows diff, commits

Complements the existing `run_workflow_analyzer.py` (health check, daily) without modifying it. Optimizer runs on-demand or weekly.

---

## Goals

- Use Claude API to generate specific, actionable fixes for each issue surfaced by the analyzer
- Email numbered proposals so the user can select which to apply
- Apply approved proposals with `--execute --proposal-id N` with full diff visibility and git commit
- Cover all three change types: workflow MDs, GitHub Actions YAML, tools/*.py

---

## Architecture

```
tools/run_workflow_optimizer.py
  ├── collect_issues()          — reuse static_analysis + github_analysis from run_workflow_analyzer
  ├── read_file_contents()      — load relevant file content for each issue
  ├── generate_proposals()      — single Claude API call, structured JSON response
  ├── save_proposals()          — .tmp/proposals_latest.json
  ├── build_proposal_email()    — HTML email with numbered proposals
  ├── send_proposal_email()     — subprocess send_gmail.py --body-file
  └── execute_proposals()       — apply diffs, print to stdout, git commit
```

**Reused from existing codebase:**
- `tools/env_loader.py` — credential loading
- `tools/send_gmail.py` — email dispatch
- `run_workflow_analyzer.run_static_analysis()` and `run_github_analysis()` — issue collection
- `GH_PAT`, `GH_REPO`, `GMAIL_*`, `COMMUNICATOR_RECIPIENT`, `ANTHROPIC_API_KEY` secrets

---

## Proposal Types

| `change_type` | Scope | Examples |
|---------------|-------|---------|
| `workflow_md` | `workflows/*.md` | Fix broken tool ref, add missing Tools section, fix path typo |
| `gh_action_yaml` | `.github/workflows/*.yml` | Fix timeout, adjust cron, add missing env var |
| `tool_code` | `tools/*.py` | Add try/except, extract hardcoded constant, fix import |

---

## Claude API Design

**Single batch call** per optimizer run (cost-efficient):

```
System: You are a WAT framework optimizer. Given a list of issues, generate specific actionable
        fixes as a JSON array. Each fix must include the exact text change (original → replacement).
        Only suggest changes you are confident about. For tool_code changes, be conservative:
        only suggest additions (error handling, constants), never deletions or refactors.

User:   Issues: [list of Issue objects with type, severity, source, detail]
        File contents: {filename: content, ...} for all referenced files

Response: [
  {
    "id": 1,
    "issue_type": "BROKEN_REF",
    "source": "workflows/influencer_outreach.md",
    "rationale": "fetch_ig_metrics.py is the correct filename",
    "change_type": "workflow_md",
    "file": "workflows/influencer_outreach.md",
    "original": "`tools/fetch_instagram_metrics.py`",
    "replacement": "`tools/fetch_ig_metrics.py`"
  },
  ...
]
```

**Model:** `claude-haiku-4-5-20251001` default. `--model sonnet` expands to `claude-sonnet-4-6`. Allowlist: `haiku` → `claude-haiku-4-5-20251001`, `sonnet` → `claude-sonnet-4-6`. Unknown values are an error.

**Token budget:** File contents are included per proposal issue. Skip any file larger than 10 KB (send filename + size warning instead). Cap total `tool_code` proposals in one batch at 5 to limit context size.

---

## Proposal Storage

`.tmp/proposals_latest.json`:
```json
{
  "generated_at": "2026-03-14T10:00:00Z",
  "issue_count": 12,
  "proposals": [
    {
      "id": 1,
      "issue_type": "BROKEN_REF",
      "source": "workflows/influencer_outreach.md",
      "rationale": "...",
      "change_type": "workflow_md",
      "file": "workflows/influencer_outreach.md",
      "original": "...",
      "replacement": "..."
    }
  ]
}
```

---

## HTML Email Structure

```
[Header] ORBI Workflow Optimizer — 2026-03-14
[Summary] 5 proposals generated (2 workflow_md, 2 gh_action_yaml, 1 tool_code)

[Proposal #1] 🔴 BROKEN_REF — workflows/influencer_outreach.md
  Issue: references tools/fetch_instagram_metrics.py (not found)
  Fix: update to tools/fetch_ig_metrics.py
  Rationale: fetch_ig_metrics.py exists in tools/ and matches purpose
  Command: python tools/run_workflow_optimizer.py --execute --proposal-id 1

[Proposal #2] 🟡 ORPHAN_TOOL — tools/_analyze_st.py
  Fix: add reference in workflows/influencer_inbound_pipeline.md
  ...

[Footer] To apply: python tools/run_workflow_optimizer.py --execute --proposal-id 1,2,4
```

---

## `--execute` Mode

```bash
python tools/run_workflow_optimizer.py --execute --proposal-id 1,3,5
```

1. Load `.tmp/proposals_latest.json`
2. For each specified ID:
   - Print unified diff to stdout
   - Apply change (in-place file edit)
3. After all changes applied: `git add` + `git commit -m "feat(optimizer): apply proposals #1,3,5"`
4. Print summary of applied changes

**Safety rules:**
- `--execute` without `--proposal-id` is an error (no silent mass-apply)
- Prints full diff before applying (no silent edits)
- `tool_code` proposals: additive only (Claude instructed to only add, never delete)
- Never modifies `.env`, `credentials/`, or secrets files
- **Staleness check:** warn (but do not abort) if `proposals_latest.json` was generated more than 24 hours ago
- **File existence check:** if `proposal.file` does not exist at apply time, skip with a warning — never create files
- **String match fallback:** if `original` text is not found in the target file, skip that proposal with a warning — no fuzzy/partial match
- **Empty commit guard:** only run `git commit` if at least one proposal was successfully applied
- **Unknown ID handling:** `--proposal-id` values that don't match any proposal ID are warned and skipped, not treated as fatal errors
- **Import note:** `run_workflow_analyzer` calls `load_env()` at module import time — optimizer must not call it again

---

## CLI Interface

```bash
python tools/run_workflow_optimizer.py                          # propose + email
python tools/run_workflow_optimizer.py --dry-run               # propose only, no email
python tools/run_workflow_optimizer.py --preview               # save HTML to .tmp/workflow_optimizer_preview.html
python tools/run_workflow_optimizer.py --model sonnet          # use Sonnet instead of Haiku
python tools/run_workflow_optimizer.py --days 14               # extend GH Actions window
python tools/run_workflow_optimizer.py --execute --proposal-id 1,3,5   # apply proposals
```

---

## Secrets Required

| Secret | Source |
|--------|--------|
| `ANTHROPIC_API_KEY` | New — add to GitHub Secrets + `~/.wat_secrets` |
| `GITHUB_TOKEN` / `GH_PAT` | Already exists |
| `GMAIL_OAUTH_CREDENTIALS_JSON` | Already exists |
| `GMAIL_TOKEN_JSON` | Already exists |
| `COMMUNICATOR_RECIPIENT` | Already exists |

---

## Out of Scope

- Feedback loop / effectiveness measurement (Phase 3)
- Auto-scheduling optimizer (remains on-demand; user controls when to run)
- Proposal approval via email reply (requires webhook infrastructure)
