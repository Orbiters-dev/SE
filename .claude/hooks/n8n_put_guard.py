#!/usr/bin/env python3
"""PreToolUse Bash hook — block n8n production WF mutations without plan-gate PASS.

Triggers on Bash commands that match an n8n PUT pattern. Verifies a recent
plan markdown exists in `.tmp/plan_*.md` AND its harness gate result was PASS
(or PASS_PARTIAL with Codex PASS). If not, blocks with `decision: block` and
forces the operator (me, Claude) to run plan critique first.

Why this hook exists
--------------------
2026-04-26 sim — bypassed harness twice on Reply Handler v2 production patches.
First was a Flatten node insert (had plan + gate PASS). Second was Split Threads
removal (NO plan critique — silently executed). Found an hour later. User caught
it and demanded structural prevention, not memorized rules.

n8n PUT operations don't trigger PostToolUse Edit/Write hook because n8n cloud
workflows aren't files in the repo — they're mutated via REST API from inside
Bash subprocess. This hook closes that gap.

Pattern matched
---------------
  - Bash command containing all of:
      * `n8n.orbiters.co.kr` OR `N8N_BASE_URL` OR `/api/v1/workflows/`
      * `method='PUT'` OR `method="PUT"` (Python urllib) OR `-X PUT` (curl) OR `--request PUT`
  - Excludes: GET-only commands, executions endpoint reads, `--gate plan` runs

Resolution
----------
  - Find newest `.tmp/plan_*.md` (or `vault/handoff/plan_*.md`)
  - Look up corresponding harness_results/<latest>/harness_result.json
  - Allow if status in {PASS, WARN} AND consensus contains PASS for Codex
  - Block otherwise with explanation
"""
from __future__ import annotations

import json
import os
import re
import sys
import glob
import time


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def _detect_production_mutation(cmd: str) -> str | None:
    """Return label of detected production mutation, or None.

    Covers (2026-04-26 expansion per 사용자 룰 "하네스 절대 패스 노노"):
      - n8n cloud WF mutate (PUT/DELETE/activate)
      - Shopify Admin API mutate (POST/PUT/DELETE on /admin/api/)
      - Orbitools Django API mutate (POST/PUT/PATCH/DELETE on orbitools.orbiters.co.kr)
        EXCEPT GET-shaped reads + safe-listed read endpoints
      - Send Email via SIM Send WF webhook (counts as production-facing)
    """
    if "--gate plan" in cmd or "tools/harness.py" in cmd or "n8n_put_guard" in cmd:
        return None

    # 1. n8n PRODUCTION WF mutate
    n8n_keys = ("n8n.orbiters.co.kr", "N8N_BASE_URL", "/api/v1/workflows/")
    n8n_mutate_patterns = [
        r"method\s*=\s*['\"]PUT['\"]",
        r"-X\s+PUT\b",
        r"--request\s+PUT\b",
        r"method\s*=\s*['\"]POST['\"][^)]*activate",
        r"method\s*=\s*['\"]DELETE['\"]",
    ]
    if any(k in cmd for k in n8n_keys) and any(re.search(p, cmd) for p in n8n_mutate_patterns):
        return "n8n production WF"

    # 2. n8n WEBHOOK trigger that sends real emails / creates real Shopify drafts
    if any(p in cmd for p in (
        "/webhook/sim-send-affiliates", "/webhook/influencer-gifting",
        "/webhook/shopify-fulfillment-v2", "/webhook/draft-gen",
    )) and ("POST" in cmd.upper() or "method='POST'" in cmd or 'method="POST"' in cmd or "-X POST" in cmd or "data=" in cmd):
        return "n8n webhook (real email / Shopify draft)"

    # 3. Shopify Admin API mutate
    if "myshopify.com/admin/api/" in cmd or "SHOPIFY_ACCESS_TOKEN" in cmd:
        if any(re.search(p, cmd) for p in [
            r"method\s*=\s*['\"](?:POST|PUT|DELETE|PATCH)['\"]",
            r"-X\s+(?:POST|PUT|DELETE|PATCH)\b",
            r"--request\s+(?:POST|PUT|DELETE|PATCH)\b",
        ]):
            return "Shopify Admin API mutation"

    # 4. Orbitools Django API mutate (POST/PUT/PATCH/DELETE)
    if "orbitools.orbiters.co.kr" in cmd or "ORBITOOLS" in cmd.upper():
        # Read-only allowlist: explicit GET, freshness, query/list endpoints
        is_explicit_get = bool(re.search(r"method\s*=\s*['\"]GET['\"]|-X\s+GET\b", cmd))
        # Common safe read endpoints (don't trigger guard)
        SAFE_READ = (
            "/api/datakeeper/freshness/", "/api/datakeeper/overview/",
            "/api/onzenna/pipeline/conversations/?",  # GET filter
            "/api/onzenna/pipeline/creators/?",
            "/api/onzenna/pipeline/email-config-v2/?",
            "/api/onzenna/pipeline/tracked-threads/",
            "/api/onzenna/pipeline/config/today/",
        )
        if is_explicit_get or any(s in cmd for s in SAFE_READ):
            return None
        # Check for explicit mutating verb
        if any(re.search(p, cmd) for p in [
            r"method\s*=\s*['\"](?:POST|PUT|DELETE|PATCH)['\"]",
            r"-X\s+(?:POST|PUT|DELETE|PATCH)\b",
            r"--request\s+(?:POST|PUT|DELETE|PATCH)\b",
        ]):
            # Allowlist: backfill marker (creator side-effect only) + reclassify dry-run
            if "/pipeline/backfill-batch/" in cmd and '"sim-marker' in cmd:
                return None  # marker-only, audited use
            return "Orbitools Django API mutation"

    return None


def _is_n8n_put(cmd: str) -> bool:
    """Backward-compat wrapper."""
    return _detect_production_mutation(cmd) is not None


def _latest_plan() -> str | None:
    """Return path to most recently modified plan markdown."""
    candidates = []
    for pat in (".tmp/plan_*.md", "vault/handoff/plan_*.md"):
        candidates.extend(glob.glob(pat))
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _latest_harness_result() -> dict | None:
    """Return parsed JSON of most recent harness_results/<dir>/harness_result.json."""
    dirs = sorted(glob.glob(".tmp/harness_results/*/"), key=os.path.getmtime, reverse=True)
    for d in dirs:
        rf = os.path.join(d, "harness_result.json")
        if os.path.exists(rf):
            try:
                with open(rf, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return None


def _claim_plan_from_cmd(cmd: str) -> str | None:
    """Extract `# claude-plan: <path>` marker from Bash command. Returns plan path or None.

    Discipline: every n8n PUT/DELETE Bash command MUST embed:
      # claude-plan: .tmp/plan_<topic>_<date>.md
    This binds the PUT to a specific plan, preventing "use any old plan as cover" loophole.
    """
    m = re.search(r"#\s*claude-plan\s*:\s*(\S+\.md)", cmd)
    return m.group(1) if m else None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool = data.get("tool_name", "")
    if tool != "Bash":
        return 0

    cmd = (data.get("tool_input") or {}).get("command", "")
    if not _is_n8n_put(cmd):
        return 0

    # Strict binding: command must declare which plan authorizes this mutation
    claimed = _claim_plan_from_cmd(cmd)
    if not claimed:
        _emit({
            "decision": "block",
            "reason": (
                "🛑 n8n PUT/DELETE blocked: no `# claude-plan: <path>` marker in command. "
                "Per CLAUDE.md HARD RULE 5-stage discipline, every n8n WF mutation requires "
                "explicit binding to a plan-gate-PASS plan. Add to your Bash command (heredoc or top-line comment):\n"
                "  # claude-plan: .tmp/plan_<topic>_<date>.md\n"
                "Then verify the plan was gated: "
                "`python tools/harness.py run --gate plan --file <path> --max-loops 1`"
            ),
            "systemMessage": "🛑 n8n PUT blocked — add `# claude-plan: <path>` marker",
        })
        return 0

    if not os.path.exists(claimed):
        _emit({
            "decision": "block",
            "reason": (
                f"🛑 n8n PUT/DELETE blocked: claimed plan `{claimed}` does not exist. "
                f"Write the plan first."
            ),
            "systemMessage": f"🛑 n8n PUT blocked — plan {claimed} not found",
        })
        return 0

    # Find the harness_result.json that audited THIS plan (final_draft must contain plan content)
    try:
        with open(claimed, encoding="utf-8") as f:
            plan_head = f.read(800)
    except Exception:
        plan_head = ""
    # First 200 chars sans whitespace as fingerprint
    plan_fingerprint = re.sub(r"\s+", "", plan_head)[:200]

    matched_result = None
    matched_dir = None
    for d in sorted(glob.glob(".tmp/harness_results/*/"), key=os.path.getmtime, reverse=True):
        rf = os.path.join(d, "harness_result.json")
        if not os.path.exists(rf):
            continue
        try:
            with open(rf, encoding="utf-8") as f:
                hr = json.load(f)
            draft = hr.get("final_draft") or ""
            draft_norm = re.sub(r"\s+", "", draft)[:300]
            if plan_fingerprint and plan_fingerprint[:150] in draft_norm:
                matched_result = hr
                matched_dir = d
                break
        except Exception:
            continue

    if not matched_result:
        _emit({
            "decision": "block",
            "reason": (
                f"🛑 n8n PUT/DELETE blocked: claimed plan `{claimed}` exists but NO harness_result "
                f"found in .tmp/harness_results/ that audited this specific plan. Run: "
                f"`python tools/harness.py run --gate plan --file {claimed} --max-loops 1`"
            ),
            "systemMessage": f"🛑 n8n PUT blocked — plan {os.path.basename(claimed)} not gated yet",
        })
        return 0

    # Inspect the matched harness result
    status = matched_result.get("status", "UNKNOWN")
    consensus = matched_result.get("consensus", "")
    # Codex status lives inside consensus_history[0].codex.status (per harness.py output schema)
    codex_verdict = ""
    history = matched_result.get("consensus_history") or []
    if history:
        codex_verdict = (history[0].get("codex") or {}).get("status", "")

    is_pass = status == "PASS"
    is_warn_with_codex_pass = status == "WARN" and codex_verdict == "PASS"

    if not (is_pass or is_warn_with_codex_pass):
        _emit({
            "decision": "block",
            "reason": (
                f"🛑 n8n PUT/DELETE blocked: plan `{claimed}` was gated but harness verdict "
                f"status={status}, codex={codex_verdict}, consensus={consensus}. "
                f"Need PASS or WARN+CodexPASS. Address feedback in the plan."
            ),
            "systemMessage": f"🛑 n8n PUT blocked — plan {os.path.basename(claimed)} gate {status}",
        })
        return 0

    # Plan-vs-gate recency: plan must NOT have been edited after the harness ran
    try:
        plan_mtime = os.path.getmtime(claimed)
        gate_mtime = os.path.getmtime(matched_dir)
    except OSError:
        plan_mtime = gate_mtime = 0

    if plan_mtime > gate_mtime + 5:  # 5s grace for clock skew
        _emit({
            "decision": "block",
            "reason": (
                f"🛑 n8n PUT/DELETE blocked: plan `{claimed}` was edited AFTER its harness gate "
                f"(plan_mtime={int(plan_mtime)}, gate_mtime={int(gate_mtime)}). Re-run: "
                f"`python tools/harness.py run --gate plan --file {claimed} --max-loops 1`"
            ),
            "systemMessage": "🛑 n8n PUT blocked — plan modified after last gate, re-run",
        })
        return 0

    # All checks pass
    _emit({
        "systemMessage": (
            f"✅ n8n PUT allowed (plan: {os.path.basename(claimed)}, "
            f"harness: {status}/{consensus}/codex={codex_verdict})"
        ),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
