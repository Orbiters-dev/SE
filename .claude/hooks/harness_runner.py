#!/usr/bin/env python3
"""PostToolUse hook — auto-runs 3-LLM harness on tools/*.py edits.

Receives tool-call JSON on stdin (PostToolUse contract). Filters to
tools/*.py files. Invokes harness with build gate, 2 loops, no meta-judge
(cost saver). Outputs hook-control JSON: PASS = brief confirm, WARN =
proceed, FAIL = block + reason for Claude to fix.

Why no exceptions:
- "n8n/JSON cutover script" rationale was source of 2026-04-23 incidents.
- Build gate is cheap relative to runtime sending pilot incidents.
"""
import json
import os
import re
import subprocess
import sys


def _emit(payload: dict) -> None:
    # ensure_ascii=True so cp949 console (Windows default) doesn't crash on emoji.
    # Claude Code reads JSON regardless of escape format.
    print(json.dumps(payload, ensure_ascii=True))


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    fp = (data.get("tool_input") or {}).get("file_path") or ""
    if not fp:
        return 0

    fp_norm = fp.replace("\\", "/")
    # ─── 5-stage path classification per CLAUDE.md RULE 1+2 (2026-04-25) ───
    # Step 2 (plan critique):  .tmp/plan_*.md OR vault/handoff/plan_*.md
    # Step 5 (vault index):    vault/(memory|rules|handoff|skills)/*.md
    # Step 4 (build gate):     tools/*.py / Django app / migrations / n8n WFs
    PLAN_PATTERNS = [
        r"(^|/)\.tmp/plan_.+\.md$",
        r"(^|/)vault/handoff/plan_.+\.md$",
    ]
    VAULT_PATTERNS = [
        r"(^|/)vault/(memory|rules|handoff|skills)/.+\.md$",
    ]
    HARNESS_PATTERNS = [
        r"(^|/)tools/.+\.py$",
        r"(^|/)(onzenna|django_phases)/.+\.py$",
        r"(^|/)(views|models|urls)\.py$",
        r"(^|/)migrations/.+\.py$",
        r"(^|/)n8n_workflows/.+\.json$",
        r"(^|/)management/commands/.+\.py$",
        # 2026-04-28: 자가 일관성 — hook 자체도 build gate watch.
        r"(^|/)\.claude/hooks/.+\.py$",
    ]

    is_plan = any(re.search(p, fp_norm) for p in PLAN_PATTERNS)
    is_vault = any(re.search(p, fp_norm) for p in VAULT_PATTERNS)
    is_code = any(re.search(p, fp_norm) for p in HARNESS_PATTERNS)

    if not (is_plan or is_vault or is_code):
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    project_norm = project_dir.replace("\\", "/")
    if fp_norm.startswith(project_norm):
        rel = fp_norm[len(project_norm) + 1:]
        abs_target = os.path.join(project_dir, rel)
    else:
        # Cross-repo edit (e.g., WONGI). Run harness with absolute path.
        rel = fp_norm
        abs_target = fp_norm
    if not os.path.exists(abs_target):
        return 0

    # ─── Step 5: Vault auto-index (LightRAG POST) ───
    if is_vault:
        try:
            sys.path.insert(0, os.path.join(project_dir, "tools"))
            from vault_indexer import index_vault_doc, is_lightrag_healthy  # type: ignore
            if not is_lightrag_healthy():
                _emit({
                    "systemMessage": (
                        f"⚠️ Vault auto-index skipped on {rel}: LightRAG DOWN "
                        f"(http://127.0.0.1:9621). Manual index later."
                    ),
                })
                return 0
            result = index_vault_doc(abs_target)
            if result.get("ok"):
                _emit({
                    "systemMessage": (
                        f"🗄️ Vault indexed: {result.get('file_source', rel)} "
                        f"(track={result.get('track_id', '?')[:24]})"
                    ),
                })
            else:
                _emit({
                    "systemMessage": f"⚠️ Vault index failed on {rel}: {result.get('error', '')[:160]}",
                })
        except Exception as exc:
            _emit({"systemMessage": f"⚠️ Vault index exception on {rel}: {exc}"})
        return 0

    # ─── Step 2: Plan critique (--gate plan) ───
    if is_plan:
        cmd = [
            sys.executable,
            "tools/harness.py",
            "run",
            "--gate", "plan",
            "--file", rel,
            "--max-loops", "1",
            "--json",
        ]
    else:
        # ─── Step 4: Code build gate (--gate build) ───
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
        _emit({
            "systemMessage": f"Harness timeout (>300s) on {rel} — verdict unknown, proceed cautiously",
        })
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
            "systemMessage": f"🔴 Harness FAIL on {rel} (loops={loops}) — fix required",
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
        _emit({
            "systemMessage": f"🟡 Harness WARN on {rel} (loops={loops}) — proceed aware",
        })
        return 0

    if status == "PASS":
        # ─── A3: plan-first state lock — plan PASS 시 .harness_state.json 갱신 ───
        if is_plan:
            try:
                import datetime as _dt
                state_path = os.path.join(project_dir, ".claude", ".harness_state.json")
                state = {}
                if os.path.exists(state_path):
                    try:
                        with open(state_path, "r", encoding="utf-8") as f:
                            state = json.load(f) or {}
                    except Exception:
                        state = {}
                state["current_plan"] = rel
                state["current_plan_pass_at"] = _dt.datetime.now().isoformat(timespec="seconds")
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=True, indent=2)
            except Exception:
                pass
        _emit({"systemMessage": f"✅ Harness PASS on {rel} (loops={loops})"})
        return 0

    err_tail = (result.stderr or result.stdout or "")[-300:].strip()
    _emit({
        "systemMessage": f"⚠️ Harness verdict UNKNOWN on {rel}: {err_tail[:200]}",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
