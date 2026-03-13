# Workflow Optimizer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/run_workflow_optimizer.py` — calls Claude API to generate numbered fix proposals from WAT framework issues, emails them, and applies approved ones via `--execute --proposal-id N`.

**Architecture:** Standalone tool that imports issue-collection functions from the existing `run_workflow_analyzer.py`, feeds issues + file contents to Claude API in a single batch call, stores proposals as JSON, emails an HTML report, and applies selected proposals with diff preview + git commit.

**Tech Stack:** Python 3.11, `anthropic` SDK (0.83+), `requests`, `subprocess` (send_gmail.py), `difflib` (unified diffs), existing `env_loader.py`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/run_workflow_optimizer.py` | Create | Main tool — all logic |
| `tests/test_workflow_optimizer.py` | Create | Unit tests |

---

## Chunk 1: Data Pipeline (collect → read → generate → save)

### Task 1: Skeleton + CLI + issue collection

**Files:**
- Create: `tools/run_workflow_optimizer.py`
- Create: `tests/test_workflow_optimizer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_optimizer.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

def test_import():
    import run_workflow_optimizer  # must not crash
    assert hasattr(run_workflow_optimizer, "collect_issues")

def test_collect_issues_returns_list():
    from run_workflow_optimizer import collect_issues
    issues = collect_issues(days=7)
    assert isinstance(issues, list)
    # each item has .type, .severity, .source, .detail
    for issue in issues:
        assert hasattr(issue, "type")
        assert hasattr(issue, "severity")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "c:/SynologyDrive/ORBI CLAUDE_0223/ORBITERS CLAUDE/ORBITERS CLAUDE/WJ Test1"
python -m pytest tests/test_workflow_optimizer.py::test_import -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the skeleton**

```python
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
_spec.loader.exec_module(_analyzer)
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_workflow_optimizer.py::test_import tests/test_workflow_optimizer.py::test_collect_issues_returns_list -v
```
Expected: PASS (both tests green)

- [ ] **Step 5: Commit**

```bash
git add tools/run_workflow_optimizer.py tests/test_workflow_optimizer.py
git commit -m "feat(optimizer): skeleton + CLI + issue collection (Task 1)"
```

---

### Task 2: File content reader

**Files:**
- Modify: `tools/run_workflow_optimizer.py`
- Modify: `tests/test_workflow_optimizer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_read_file_contents_returns_dict():
    from run_workflow_optimizer import read_file_contents, collect_issues
    issues = collect_issues(days=7)
    contents = read_file_contents(issues)
    assert isinstance(contents, dict)
    # keys are relative path strings (e.g. "workflows/foo.md")
    for k, v in contents.items():
        assert isinstance(k, str)
        assert isinstance(v, str)

def test_read_file_contents_skips_large_files(tmp_path, monkeypatch):
    from run_workflow_optimizer import read_file_contents, Issue, MAX_FILE_BYTES
    # Create a large fake file
    big = tmp_path / "tools" / "big.py"
    big.parent.mkdir(parents=True)
    big.write_text("x" * (MAX_FILE_BYTES + 1))
    issue = Issue(type="ORPHAN_TOOL", severity="medium", source="big.py", detail="orphan")
    monkeypatch.setattr("run_workflow_optimizer.PROJECT_ROOT", tmp_path)
    contents = read_file_contents([issue])
    assert "tools/big.py" in contents
    assert "[SKIPPED" in contents["tools/big.py"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_workflow_optimizer.py::test_read_file_contents_returns_dict -v
```
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement `read_file_contents()`**

Add after `collect_issues()`:

```python
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
        elif issue.type in ("ORPHAN_TOOL", "EMPTY_WORKFLOW"):
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
        # Apply tool_code cap
        if str(path).endswith(".py"):
            tool_code_count += 1
            if tool_code_count > MAX_TOOL_CODE_PROPOSALS:
                contents[rel] = f"[SKIPPED: tool_code cap of {MAX_TOOL_CODE_PROPOSALS} reached]"
                continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            contents[rel] = f"[SKIPPED: file too large ({size} bytes > {MAX_FILE_BYTES})]"
        else:
            contents[rel] = path.read_text(encoding="utf-8", errors="ignore")

    return contents
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_workflow_optimizer.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tools/run_workflow_optimizer.py tests/test_workflow_optimizer.py
git commit -m "feat(optimizer): file content reader with size + cap limits (Task 2)"
```

---

### Task 3: Claude API proposal generator

**Files:**
- Modify: `tools/run_workflow_optimizer.py`
- Modify: `tests/test_workflow_optimizer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_generate_proposals_structure(monkeypatch):
    """Test with a mock anthropic client to avoid real API calls."""
    import unittest.mock as mock
    import run_workflow_optimizer as opt
    from run_workflow_optimizer import generate_proposals, Issue

    monkeypatch.setattr(opt, "ANTHROPIC_KEY", "fake-key")

    fake_proposals = [
        {
            "id": 1,
            "issue_type": "BROKEN_REF",
            "source": "test_workflow",
            "rationale": "foo.py is the correct name",
            "change_type": "workflow_md",
            "file": "workflows/test_workflow.md",
            "original": "`tools/bar.py`",
            "replacement": "`tools/foo.py`"
        }
    ]
    fake_response_text = json.dumps(fake_proposals)

    with mock.patch("anthropic.Anthropic") as MockClient:
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value.content = [
            mock.MagicMock(text=fake_response_text)
        ]
        issues = [Issue("BROKEN_REF", "high", "test_workflow", "references bar.py")]
        contents = {"workflows/test_workflow.md": "| `tools/bar.py` | ..."}
        proposals = generate_proposals(issues, contents, model="haiku")

    assert len(proposals) == 1
    assert proposals[0]["id"] == 1
    assert proposals[0]["change_type"] == "workflow_md"

def test_generate_proposals_invalid_json_returns_empty(monkeypatch):
    import unittest.mock as mock
    import run_workflow_optimizer as opt
    from run_workflow_optimizer import generate_proposals, Issue

    monkeypatch.setattr(opt, "ANTHROPIC_KEY", "fake-key")

    with mock.patch("anthropic.Anthropic") as MockClient:
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value.content = [
            mock.MagicMock(text="not json at all")
        ]
        issues = [Issue("BROKEN_REF", "high", "wf", "detail")]
        proposals = generate_proposals(issues, {}, model="haiku")

    assert proposals == []
```

- [ ] **Step 2: Run tests to fail**

```bash
python -m pytest tests/test_workflow_optimizer.py::test_generate_proposals_structure -v
```
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement `generate_proposals()`**

Add after `read_file_contents()`:

```python
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
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        proposals = json.loads(raw)
        if not isinstance(proposals, list):
            print("WARNING: Claude returned non-list JSON -- ignoring")
            return []
        return proposals
    except (json.JSONDecodeError, Exception) as e:
        print(f"WARNING: proposal generation failed: {e}")
        return []
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_workflow_optimizer.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tools/run_workflow_optimizer.py tests/test_workflow_optimizer.py
git commit -m "feat(optimizer): Claude API proposal generator (Task 3)"
```

---

### Task 4: Proposal storage

**Files:**
- Modify: `tools/run_workflow_optimizer.py`
- Modify: `tests/test_workflow_optimizer.py`

- [ ] **Step 1: Write failing test**

```python
def test_save_and_load_proposals(tmp_path, monkeypatch):
    from run_workflow_optimizer import save_proposals
    import json
    monkeypatch.setattr("run_workflow_optimizer.TMP_DIR", tmp_path)

    proposals = [{"id": 1, "change_type": "workflow_md", "file": "workflows/foo.md",
                  "original": "old", "replacement": "new",
                  "issue_type": "BROKEN_REF", "source": "foo", "rationale": "test"}]
    path = save_proposals(proposals, issue_count=5)

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["issue_count"] == 5
    assert len(data["proposals"]) == 1
    assert data["proposals"][0]["id"] == 1
    assert "generated_at" in data
```

- [ ] **Step 2: Run to fail**

```bash
python -m pytest tests/test_workflow_optimizer.py::test_save_and_load_proposals -v
```
Expected: FAIL

- [ ] **Step 3: Implement `save_proposals()`**

```python
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
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_workflow_optimizer.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tools/run_workflow_optimizer.py tests/test_workflow_optimizer.py
git commit -m "feat(optimizer): proposal storage to .tmp/proposals_latest.json (Task 4)"
```

---

## Chunk 2: Output (email + execute mode)

### Task 5: HTML email builder

**Files:**
- Modify: `tools/run_workflow_optimizer.py`
- Modify: `tests/test_workflow_optimizer.py`

- [ ] **Step 1: Write failing test**

```python
def test_build_proposal_email_contains_proposals():
    from run_workflow_optimizer import build_proposal_email
    proposals = [
        {
            "id": 1, "issue_type": "BROKEN_REF", "change_type": "workflow_md",
            "source": "test_wf", "file": "workflows/test_wf.md",
            "original": "old_ref", "replacement": "new_ref",
            "rationale": "new_ref.py exists in tools/"
        },
        {
            "id": 2, "issue_type": "ORPHAN_TOOL", "change_type": "workflow_md",
            "source": "orphan.py", "file": "workflows/foo.md",
            "original": "", "replacement": "## Tools\n...",
            "rationale": "orphan tool needs reference"
        }
    ]
    html = build_proposal_email(proposals, issue_count=10, date_str="2026-03-14")
    assert "Proposal #1" in html
    assert "Proposal #2" in html
    assert "BROKEN_REF" in html
    assert "proposal-id 1" in html
    assert "proposal-id 1,2" in html  # footer "apply all"
    assert "2026-03-14" in html
```

- [ ] **Step 2: Run to fail**

```bash
python -m pytest tests/test_workflow_optimizer.py::test_build_proposal_email_contains_proposals -v
```
Expected: FAIL

- [ ] **Step 3: Implement `build_proposal_email()`**

```python
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
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_workflow_optimizer.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tools/run_workflow_optimizer.py tests/test_workflow_optimizer.py
git commit -m "feat(optimizer): HTML proposal email builder (Task 5)"
```

---

### Task 6: Email sender + main propose flow

**Files:**
- Modify: `tools/run_workflow_optimizer.py`

Wire together: `collect_issues → read_file_contents → generate_proposals → save_proposals → build_proposal_email → send`.

- [ ] **Step 1: Write failing integration test**

```python
def test_main_dry_run_no_crash(monkeypatch):
    """--dry-run should run without sending email or crashing."""
    import unittest.mock as mock
    import run_workflow_optimizer as opt

    fake_proposals = [
        {"id": 1, "issue_type": "BROKEN_REF", "source": "wf", "rationale": "r",
         "change_type": "workflow_md", "file": "workflows/wf.md",
         "original": "old", "replacement": "new"}
    ]
    monkeypatch.setattr(opt, "generate_proposals",
                        lambda issues, contents, model: fake_proposals)
    monkeypatch.setattr(opt, "ANTHROPIC_KEY", "fake-key")

    import sys
    with mock.patch.object(sys, "argv",
                           ["run_workflow_optimizer.py", "--dry-run"]):
        opt.main()   # must not raise
```

- [ ] **Step 2: Run to fail**

```bash
python -m pytest tests/test_workflow_optimizer.py::test_main_dry_run_no_crash -v
```
Expected: FAIL (main() doesn't call generate_proposals yet)

- [ ] **Step 3: Implement `send_proposal_email()` and wire `main()`**

Replace the `main()` function and add `send_proposal_email()`:

```python
def send_proposal_email(html: str, date_str: str, proposal_count: int) -> None:
    """Send the proposal HTML via send_gmail.py."""
    TMP_DIR.mkdir(exist_ok=True)
    tmp_html = TMP_DIR / "workflow_optimizer_preview.html"
    tmp_html.write_text(html, encoding="utf-8")
    subject = f"[ORBI Optimizer] {proposal_count} proposals — {date_str}"
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "send_gmail.py"),
         "--to", RECIPIENT,
         "--sender", SENDER,
         "--subject", subject,
         "--body-file", str(tmp_html)],
        check=True,
    )


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
        execute_proposals(args.proposal_id)
        return

    print("=== ORBI Workflow Optimizer ===")
    issues = collect_issues(days=args.days)
    print(f"Collected {len(issues)} issues")

    file_contents = read_file_contents(issues)
    print(f"Loaded {len(file_contents)} file(s) for context")

    proposals = generate_proposals(issues, file_contents, model=args.model)
    print(f"Generated {len(proposals)} proposals")

    if not proposals:
        print("No proposals generated. Exiting.")
        return

    save_proposals(proposals, issue_count=len(issues))
    print(f"Proposals saved to .tmp/proposals_latest.json")

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
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_workflow_optimizer.py -v
```
Expected: All PASS

- [ ] **Step 5: Smoke test (dry-run)**

```bash
python tools/run_workflow_optimizer.py --dry-run --preview
```
Expected output:
```
=== ORBI Workflow Optimizer ===
Collected N issues
Loaded M file(s) for context
WARNING: ANTHROPIC_API_KEY not set -- skipping proposal generation
No proposals generated. Exiting.
```
(No crash. If ANTHROPIC_API_KEY is set, you'll see actual proposals.)

- [ ] **Step 6: Commit**

```bash
git add tools/run_workflow_optimizer.py
git commit -m "feat(optimizer): email sender + main propose flow wired (Task 6)"
```

---

### Task 7: Execute mode

**Files:**
- Modify: `tools/run_workflow_optimizer.py`
- Modify: `tests/test_workflow_optimizer.py`

- [ ] **Step 1: Write failing tests**

```python
def test_execute_proposals_applies_change(tmp_path, monkeypatch):
    import json
    from run_workflow_optimizer import execute_proposals

    # Set up fake proposals file
    proposals_file = tmp_path / "proposals_latest.json"
    target = tmp_path / "workflows" / "test.md"
    target.parent.mkdir(parents=True)
    target.write_text("See `tools/old_tool.py` for details.", encoding="utf-8")

    from datetime import datetime, timezone
    proposals_file.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "issue_count": 1,
        "proposals": [{
            "id": 1,
            "issue_type": "BROKEN_REF",
            "source": "test",
            "rationale": "correct name",
            "change_type": "workflow_md",
            "file": "workflows/test.md",
            "original": "`tools/old_tool.py`",
            "replacement": "`tools/new_tool.py`"
        }]
    }), encoding="utf-8")

    monkeypatch.setattr("run_workflow_optimizer.TMP_DIR", tmp_path)
    monkeypatch.setattr("run_workflow_optimizer.PROJECT_ROOT", tmp_path)

    import unittest.mock as mock
    with mock.patch("subprocess.run") as mock_run:  # mock git commands
        execute_proposals("1")

    result = target.read_text(encoding="utf-8")
    assert "`tools/new_tool.py`" in result
    assert "`tools/old_tool.py`" not in result


def test_execute_proposals_skips_missing_file(tmp_path, monkeypatch, capsys):
    import json
    from run_workflow_optimizer import execute_proposals
    from datetime import datetime, timezone

    proposals_file = tmp_path / "proposals_latest.json"
    proposals_file.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "issue_count": 1,
        "proposals": [{
            "id": 1, "issue_type": "BROKEN_REF", "source": "missing",
            "rationale": "r", "change_type": "workflow_md",
            "file": "workflows/does_not_exist.md",
            "original": "old", "replacement": "new"
        }]
    }), encoding="utf-8")

    monkeypatch.setattr("run_workflow_optimizer.TMP_DIR", tmp_path)
    monkeypatch.setattr("run_workflow_optimizer.PROJECT_ROOT", tmp_path)

    import unittest.mock as mock
    with mock.patch("subprocess.run"):
        execute_proposals("1")

    captured = capsys.readouterr()
    assert "SKIP" in captured.out or "not found" in captured.out.lower()


def test_execute_proposals_staleness_warning(tmp_path, monkeypatch, capsys):
    import json
    import unittest.mock as mock
    from run_workflow_optimizer import execute_proposals
    from datetime import datetime, timezone, timedelta

    proposals_file = tmp_path / "proposals_latest.json"
    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    proposals_file.write_text(json.dumps({
        "generated_at": old_time,
        "issue_count": 0,
        "proposals": []
    }), encoding="utf-8")

    monkeypatch.setattr("run_workflow_optimizer.TMP_DIR", tmp_path)
    monkeypatch.setattr("run_workflow_optimizer.PROJECT_ROOT", tmp_path)

    with mock.patch("subprocess.run"):
        execute_proposals("1")

    captured = capsys.readouterr()
    assert "stale" in captured.out.lower() or "old" in captured.out.lower() or "24" in captured.out
```

- [ ] **Step 2: Run to fail**

```bash
python -m pytest tests/test_workflow_optimizer.py::test_execute_proposals_applies_change -v
```
Expected: FAIL with `NameError: execute_proposals`

- [ ] **Step 3: Implement `execute_proposals()`**

Add before `main()`:

```python
def execute_proposals(proposal_id_str: str) -> None:
    """
    Load proposals from .tmp/proposals_latest.json and apply the specified IDs.
    Prints unified diff before each change. Commits if any changes applied.
    """
    import difflib

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
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/test_workflow_optimizer.py -v
```
Expected: All PASS

- [ ] **Step 5: End-to-end smoke test**

If `ANTHROPIC_API_KEY` is available:
```bash
python tools/run_workflow_optimizer.py --dry-run --preview
```
Check `.tmp/workflow_optimizer_preview.html` exists and is valid HTML with proposals.

If no API key:
```bash
python tools/run_workflow_optimizer.py --dry-run
```
Expected: No crash, ends with "No proposals generated."

- [ ] **Step 6: Commit**

```bash
git add tools/run_workflow_optimizer.py tests/test_workflow_optimizer.py
git commit -m "feat(optimizer): execute mode with all safety rules (Task 7)"
```

---

## Post-implementation checklist

- [ ] Verify `ANTHROPIC_API_KEY` is in `~/.wat_secrets` locally
- [ ] Run `python tools/run_workflow_optimizer.py --dry-run --preview` with real API key
- [ ] Open `.tmp/workflow_optimizer_preview.html` and confirm proposals render correctly
- [ ] Run `python tools/run_workflow_optimizer.py` (no flags) to send actual email
- [ ] Push to GitHub
