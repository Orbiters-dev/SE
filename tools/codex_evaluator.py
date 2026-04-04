"""
Codex Evaluator — Cross-AI Harness Evaluator (Claude=Generator, Codex=Evaluator).

Supports 3 domain-specific audit modes:
  - general: Code quality, security, logic errors (제갈량 harness)
  - cfo: Financial model verification, AICPA/KICPA 6-point checklist (CFO harness)
  - pipeliner: E2E pipeline dual-test verification, Maker-Checker cross-system (Pipeliner harness)

Usage:
    # General code audit
    python tools/codex_evaluator.py audit --files tools/data_keeper.py

    # CFO financial audit (골만이 output 검증)
    python tools/codex_evaluator.py --domain cfo audit --files .tmp/cfo_sessions/golmani_output.json

    # Pipeliner E2E audit (dual test results 검증)
    python tools/codex_evaluator.py --domain pipeliner audit --files .tmp/dual_test/run_latest/merged_report.html

    # Sprint contract 검증
    python tools/codex_evaluator.py verify --contract .tmp/sprint_contract.md

    # 도메인 특화 질문
    python tools/codex_evaluator.py --domain cfo ask "Grosmimi Q1 Gross Margin이 85%로 나오는데 정상인가?"

    # JSON 출력 (파이프라인용)
    python tools/codex_evaluator.py --domain pipeliner audit --files report.json --json

Env:
    OPENAI_API_KEY  — OpenAI API key (from .env)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Load .env
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() not in os.environ:
                os.environ[k.strip()] = v

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / ".tmp" / "codex_evaluator"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# ─── Evaluator system prompts ───────────────────────────────────────

AUDIT_SYSTEM = """You are a skeptical code auditor for the ORBI system.
Your job is to find real bugs, security issues, and logic errors.
Do NOT be generous. Do NOT praise code that is merely "okay".

Grading criteria (hard thresholds):
1. FUNCTIONALITY (weight: CRITICAL) — Does it work as intended? Any broken feature = FAIL.
2. DATA INTEGRITY (weight: HIGH) — Are numbers correct? Any data inconsistency = FAIL.
3. CODE QUALITY (weight: MEDIUM) — Error handling, security, performance.
4. DESIGN (weight: LOW) — Is it maintainable? Clear naming?

For each file, output:
- Score per criterion (0-10)
- PASS/FAIL per criterion (FUNCTIONALITY < 8 = FAIL, DATA INTEGRITY < 9 = FAIL)
- Specific issues with line numbers
- Overall verdict: PASS or FAIL

Be specific. Quote code. Give line numbers. No vague praise."""

VERIFY_SYSTEM = """You are a sprint contract verifier for the ORBI system.
Given a sprint contract (scope + acceptance criteria), verify whether the
implementation meets every criterion.

For each criterion:
- PASS: fully implemented, tested, working
- FAIL: missing, broken, or incomplete (with specific evidence)
- PARTIAL: implemented but with caveats (list them)

Output a scorecard table and overall verdict."""

# ─── Domain-specific Evaluator prompts ────────────────────────────

CFO_AUDIT_SYSTEM = """You are an independent financial auditor (AICPA/KICPA dual-certified) for ORBI.
You audit the output of "Golmani" (VP of Financial Modeling) with ZERO trust.
Do NOT rely on Golmani's explanations — verify every number independently.

## 6-Point Audit Checklist (ALL mandatory):

A. ARITHMETIC — Every subtotal must sum to its parent total.
   Revenue components = Total Revenue. Gross Profit = Revenue - COGS.
   Percentages must match numerator/denominator (±0.1% rounding tolerance).

B. CROSS-TABLE CONSISTENCY — Same metric across multiple tables must match.
   P&L Revenue = Channel Breakdown Total = DataKeeper raw sum.
   Any $1K+ discrepancy = MAJOR. Any $10K+ = CRITICAL.

C. PERIOD CONSISTENCY — All tables must use the same date_from ~ date_to.
   YoY/MoM base period must be correct.

D. SIGN CONVENTIONS — Costs always positive or always negative (consistent).
   Discounts are revenue deductions. Margins must be positive (flag if negative).

E. ACCOUNTING STANDARDS
   - Revenue Recognition: Gross Revenue before platform fees (ORBI standard)
   - COGS: landed cost = FOB × 1.15 (NOT retail price)
   - Grosmimi Price Cutoff: 2025-03-01 (different prices before/after)
   - Operating vs Non-operating: ad spend = operating, FX = non-operating

F. MATERIALITY & SANITY
   | Metric | Normal | WARN | CRITICAL |
   | Grosmimi Gross Margin | 68-72% | 60-80% | <55% or >85% |
   | Amazon ACOS | 15-25% | 10-35% | <8% or >50% |
   | MER | 10-20% | 8-28% | <5% or >35% |

## Severity Classification:
- CRITICAL: Numbers are wrong (arithmetic error, wrong period). MUST fix.
- MAJOR: Significant inconsistency ($10K+ cross-table diff). Should fix.
- MINOR: Small inconsistency (<$1K, rounding). CFO discretion.
- INFO: Benchmark notes, methodology comments. Ignorable.

## Output Format:
```json
{
  "status": "PASS | WARN | FAIL",
  "summary": "One-line verdict",
  "findings": [{"id": "F001", "severity": "CRITICAL", "category": "A-F", "section": "...", "description": "...", "expected": "...", "actual": "...", "correction_needed": "..."}],
  "corrections_required": ["F001"],
  "approved_sections": ["..."]
}
```

Be ruthless with numbers. $1 off in a total is a bug."""

PIPELINER_AUDIT_SYSTEM = """You are an E2E pipeline verification specialist for ORBI's Creator Collab system.
You audit the Maker-Checker dual test results for the influencer gifting pipeline.

## Pipeline Architecture:
8-stage pipeline: Syncly Discovery → Email → Gifting Form → Profile Review → Sample Select → Sample Sent → Fulfillment → Content Posted
Systems: Airtable CRM, Shopify (draft orders/customers), PostgreSQL, n8n workflows, Gmail

## Verification Criteria (per stage):

### STAGE INTEGRITY (CRITICAL — any failure = FAIL)
- Executor (Maker) action completed: record created/updated in target system
- Verifier (Checker) independently confirmed: downstream state matches expected
- Cross-system consistency: Airtable ↔ Shopify ↔ PostgreSQL all agree
- Signal file written with correct stage metadata

### DATA FLOW (HIGH)
- Record IDs propagate correctly across systems (AT record ID → Shopify customer ID → PG row)
- Email addresses match across all systems (no typo propagation)
- Status transitions are valid (no skipped stages)
- Timestamps are monotonically increasing per pipeline run

### WEBHOOK/n8n HEALTH (MEDIUM)
- n8n workflows are active and responding
- Webhook response times < 15s (WARN if > 30s)
- No "Task Runner Offer Expired" errors
- Poll-based workflows (5min/30min/6hr) are on schedule

### NEGATIVE TESTS (HIGH)
- Records that should NOT exist don't exist (neg checks)
- Duplicate submissions are rejected or idempotent
- Invalid data is caught at entry (form validation)

### CLEANUP (LOW)
- Test data is cleaned up after run (unless --no-cleanup)
- No orphaned records left in Airtable/Shopify/PG

## Dual Test Stages to Verify:
| Stage | Executor Creates | Verifier Checks |
| seed | AT Creator record | AT Creator exists, AT Applicants absent, Shopify absent |
| gifting | POST webhook → AT Applicant | AT Applicant exists, AT Creator status=Needs Review, Shopify customer, PG row, email match |
| gifting2 | POST webhook → Draft Order | AT Draft Order ID present, AT Creator exists, PG updated |
| sample_sent | AT status update | AT status changed, n8n WF active |

## Output Format:
```
## Pipeline Audit — [run_id]

### Stage Results
| Stage | Executor | Verifier | Cross-System | Verdict |
|-------|----------|----------|--------------|---------|
| seed | PASS/FAIL | PASS/FAIL | PASS/FAIL | PASS/FAIL |

### Issues Found
1. **[CRITICAL]** Stage X: Executor PASS but Verifier FAIL — [details]

### Overall: PASS / FAIL
```

Any executor-verifier disagreement (one PASS, other FAIL) is automatically CRITICAL.
Silent failures (no error but wrong data) are worse than loud failures."""

# ─── OpenAI API call (chat completions) ─────────────────────────────

def call_openai(system_prompt: str, user_prompt: str, model: str = "gpt-4.1") -> dict:
    """Call OpenAI Chat Completions API directly via httpx/requests."""
    import urllib.request
    import urllib.error

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "ok": True,
                "content": data["choices"][0]["message"]["content"],
                "model": data.get("model", model),
                "usage": data.get("usage", {}),
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Codex CLI (non-interactive) ────────────────────────────────────

def call_codex_exec(prompt: str, full_auto: bool = False, json_output: bool = False) -> dict:
    """Run `codex exec` non-interactively. Falls back to API if CLI not available."""
    codex_bin = "codex"  # assumes installed globally
    cmd = [codex_bin, "exec"]
    if full_auto:
        cmd.append("--full-auto")
    if json_output:
        cmd.append("--json")
    cmd.append(prompt)

    env = os.environ.copy()
    env["CODEX_API_KEY"] = OPENAI_API_KEY

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=str(REPO_ROOT), env=env,
        )
        if result.returncode == 0:
            return {"ok": True, "content": result.stdout, "stderr": result.stderr}
        else:
            return {"ok": False, "error": result.stderr or result.stdout}
    except FileNotFoundError:
        print("[INFO] codex CLI not found, falling back to OpenAI API", file=sys.stderr)
        return call_openai(AUDIT_SYSTEM, prompt)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "codex exec timed out (300s)"}


# ─── Commands ───────────────────────────────────────────────────────

DOMAIN_PROMPTS = {
    "general": AUDIT_SYSTEM,
    "cfo": CFO_AUDIT_SYSTEM,
    "pipeliner": PIPELINER_AUDIT_SYSTEM,
}


def _get_domain_prompt(args) -> str:
    """Return the system prompt for the selected domain."""
    domain = getattr(args, "domain", "general") or "general"
    return DOMAIN_PROMPTS.get(domain, AUDIT_SYSTEM)


def cmd_audit(args):
    """Audit specified files as Evaluator."""
    file_contents = []
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            p = REPO_ROOT / fp
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")
            # Truncate very large files
            lines = content.splitlines()
            if len(lines) > 500:
                content = "\n".join(lines[:500]) + f"\n\n... ({len(lines) - 500} more lines truncated)"
            file_contents.append(f"### {fp}\n```python\n{content}\n```")
        else:
            file_contents.append(f"### {fp}\n(FILE NOT FOUND)")

    system_prompt = _get_domain_prompt(args)
    domain = getattr(args, "domain", "general") or "general"
    user_prompt = (
        f"[{domain.upper()} AUDIT] Audit the following files. Apply hard thresholds. Be skeptical.\n\n"
        + "\n\n".join(file_contents)
    )

    if args.use_codex:
        result = call_codex_exec(f"[{domain.upper()} AUDIT MODE] {user_prompt}")
    else:
        result = call_openai(system_prompt, user_prompt, model=args.model)

    _output(result, args)


def cmd_verify(args):
    """Verify sprint contract against codebase."""
    contract_path = Path(args.contract)
    if not contract_path.exists():
        contract_path = REPO_ROOT / args.contract
    if not contract_path.exists():
        print(f"ERROR: Contract file not found: {args.contract}", file=sys.stderr)
        sys.exit(1)

    contract = contract_path.read_text(encoding="utf-8")
    domain = getattr(args, "domain", "general") or "general"
    user_prompt = (
        f"[{domain.upper()} VERIFY] Verify this sprint contract against the current codebase.\n\n"
        f"## Sprint Contract\n{contract}\n\n"
        "Check each acceptance criterion. Report PASS/FAIL/PARTIAL for each."
    )

    if args.use_codex:
        result = call_codex_exec(f"[VERIFY MODE] {user_prompt}")
    else:
        result = call_openai(VERIFY_SYSTEM, user_prompt, model=args.model)

    _output(result, args)


def cmd_ask(args):
    """Free-form question to Evaluator."""
    system_prompt = _get_domain_prompt(args)
    prompt = args.prompt
    if args.use_codex:
        result = call_codex_exec(prompt)
    else:
        result = call_openai(system_prompt, prompt, model=args.model)

    _output(result, args)


def cmd_resume(args):
    """Resume a previous Codex session."""
    if args.use_codex:
        # Use codex exec resume
        cmd = ["codex", "exec", "resume"]
        if args.thread_id:
            cmd.append(args.thread_id)
        else:
            cmd.append("--last")
        cmd.append(args.prompt)

        env = os.environ.copy()
        env["CODEX_API_KEY"] = OPENAI_API_KEY

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                cwd=str(REPO_ROOT), env=env,
            )
            output = {"ok": result.returncode == 0, "content": result.stdout, "stderr": result.stderr}
        except Exception as e:
            output = {"ok": False, "error": str(e)}
    else:
        output = call_openai(AUDIT_SYSTEM, args.prompt, model=args.model)

    _output(output, args)


# ─── Output helper ──────────────────────────────────────────────────

def _output(result: dict, args):
    """Print result and optionally save."""
    ts = time.strftime("%Y%m%d_%H%M%S")

    if hasattr(args, "json_output") and args.json_output:
        out = json.dumps(result, ensure_ascii=False, indent=2)
        print(out)
    else:
        if result.get("ok"):
            print(result.get("content", ""))
        else:
            print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
            sys.exit(1)

    # Always save to .tmp
    save_path = TMP_DIR / f"eval_{ts}.json"
    save_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[Saved to {save_path}]", file=sys.stderr)

    # Print usage if available
    usage = result.get("usage", {})
    if usage:
        total = usage.get("total_tokens", usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
        print(f"[Tokens: {total}]", file=sys.stderr)


# ─── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Codex Evaluator — 제갈량 harness Evaluator agent"
    )
    parser.add_argument("--model", default="gpt-4.1", help="OpenAI model (default: gpt-4.1)")
    parser.add_argument("--use-codex", action="store_true", help="Use codex CLI instead of API")
    parser.add_argument("--json", dest="json_output", action="store_true", help="JSON output")
    parser.add_argument("--domain", choices=["general", "cfo", "pipeliner"], default="general",
                        help="Domain-specific audit mode (default: general)")

    sub = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = sub.add_parser("audit", help="Audit code files")
    p_audit.add_argument("--files", nargs="+", required=True, help="Files to audit")
    p_audit.set_defaults(func=cmd_audit)

    # verify
    p_verify = sub.add_parser("verify", help="Verify sprint contract")
    p_verify.add_argument("--contract", required=True, help="Path to sprint contract MD")
    p_verify.set_defaults(func=cmd_verify)

    # ask
    p_ask = sub.add_parser("ask", help="Free-form question")
    p_ask.add_argument("prompt", help="Question for evaluator")
    p_ask.set_defaults(func=cmd_ask)

    # resume
    p_resume = sub.add_parser("resume", help="Resume previous session")
    p_resume.add_argument("--thread-id", help="Thread ID to resume")
    p_resume.add_argument("prompt", help="Follow-up prompt")
    p_resume.set_defaults(func=cmd_resume)

    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set in .env or environment", file=sys.stderr)
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
