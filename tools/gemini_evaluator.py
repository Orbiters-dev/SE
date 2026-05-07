"""
Gemini Evaluator — Cross-AI Harness Evaluator #2 (Claude=Generator, Gemini=Numeric/Factual Validator).

Role in the 3-LLM harness:
  - Claude Opus 4.6  = Generator (main work)
  - Codex (GPT-4.1)  = Evaluator 1 — Policy/Code/Spec auditor (tools/codex_evaluator.py)
  - Gemini 2.5 Pro   = Evaluator 2 — Numeric/Factual validator (this file)

Gemini's strengths leveraged here:
  1. 1M token context window — can read entire Excel/report in one pass for cross-table checks
  2. Strong numeric/arithmetic reasoning — financial model audits
  3. Multimodal — can verify charts, screenshots, dashboards (not yet enabled, stub)
  4. Low latency — faster than Codex for short audits

Supports 3 domain-specific audit modes (same as codex_evaluator for parity):
  - general: Numeric sanity, cross-reference checks, factual verification
  - cfo: Financial numeric cross-check (1M context = whole workbook in-context)
  - pipeliner: E2E data consistency across systems

Usage:
    # General numeric/factual audit
    python tools/gemini_evaluator.py audit --files tools/data_keeper.py

    # CFO financial audit (골만이 output 숫자 전수검사)
    python tools/gemini_evaluator.py --domain cfo audit --files .tmp/cfo_sessions/golmani_output.json

    # Pipeliner E2E audit
    python tools/gemini_evaluator.py --domain pipeliner audit --files .tmp/dual_test/run_latest/merged_report.html

    # Sprint contract verify
    python tools/gemini_evaluator.py verify --contract .tmp/sprint_contract.md

    # Free-form question
    python tools/gemini_evaluator.py --domain cfo ask "Q1 P&L에서 Gross Margin 숫자 정합성 체크"

    # JSON output
    python tools/gemini_evaluator.py audit --files tools/*.py --json

Env:
    GEMINI_API_KEY — Google AI Studio API key (from .env)
"""

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

# Fix Windows cp949 encoding crash — force UTF-8 stdout/stderr
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL_DEFAULT = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / ".tmp" / "gemini_evaluator"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# ─── LightRAG Integration ────────────────────────────────────────
# Mirrors codex_evaluator.py but with Gemini-specific namespace tags
# so retrieval is biased toward past Gemini (numeric/factual) audits,
# not Codex (structural) audits. Prevents cross-contamination of
# evaluator-specific false-positive patterns.

LIGHTRAG_URL = os.environ.get("LIGHTRAG_URL", "http://localhost:9621")
RAG_NAMESPACE_TAG = "gemini-numeric-factual"


def _rag_healthy() -> bool:
    """Check if LightRAG server is reachable."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{LIGHTRAG_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "healthy"
    except Exception:
        return False


def _rag_query(text: str, mode: str = "hybrid", top_k: int = 5) -> str:
    """Query LightRAG for related numeric/factual context. Empty on failure."""
    try:
        import urllib.request
        # Bias retrieval toward Gemini's own past audits + factual notes
        biased = f"[{RAG_NAMESPACE_TAG} / numeric factual arithmetic cross-reference] {text}"
        payload = json.dumps({"query": biased, "mode": mode, "top_k": top_k,
                              "only_need_context": True}).encode("utf-8")
        req = urllib.request.Request(f"{LIGHTRAG_URL}/query", data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                return data.get("response", data.get("result", ""))
            return str(data)
    except Exception:
        return ""


def _rag_index_result(result: dict, domain: str, ts: str):
    """Index Gemini audit result into LightRAG (fire-and-forget).

    Namespaced header ensures Codex retrieval won't preferentially surface
    Gemini's verdicts (prevents evaluator self-reinforcement).
    """
    if not _rag_healthy():
        return
    try:
        import urllib.request
        content = result.get("content", "")
        if not content or len(content) < 50:
            return
        # Namespace tag in header biases future Gemini-side retrieval
        doc = (f"# Gemini Numeric Audit [{domain.upper()}] [{RAG_NAMESPACE_TAG}] — {ts}\n\n"
               f"{content[:3000]}")
        payload = json.dumps({"text": doc}).encode("utf-8")
        req = urllib.request.Request(f"{LIGHTRAG_URL}/documents/text", data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        print(f"[RAG] Indexed Gemini audit result ({len(doc)} chars)", file=sys.stderr)
    except Exception as e:
        print(f"[RAG] Index failed (non-blocking): {e}", file=sys.stderr)

# ─── Evaluator system prompts (Gemini's focus = numbers/facts) ─────────

AUDIT_SYSTEM = """You are a skeptical NUMERIC and FACTUAL auditor for the ORBI system.
Your peer auditor (Codex) handles structure/policy/security — do NOT repeat their work.

## YOUR SCOPE (what to evaluate)
1. NUMERIC CORRECTNESS (weight: CRITICAL) — Arithmetic, totals, percentages.
   Any calculation error = FAIL.
2. CROSS-REFERENCE CONSISTENCY (weight: HIGH) — Same value in multiple places must match.
   Docstring claims vs actual constants/arrays must align. Any >0.1% discrepancy = FAIL.
3. FACTUAL GROUNDING (weight: HIGH) — Hardcoded values (dates, thresholds, URLs) must be justified.
   Unsupported claim or stale-looking hardcoded value = FAIL.
4. UNIT/SCALE (weight: MEDIUM) — $ vs ¢, % vs ratio, monthly vs daily. Flag inconsistency.

## OUT OF YOUR SCOPE (Codex handles these — do NOT flag)
- Code architecture, modularity, separation of concerns
- Error handling style, exception propagation patterns
- Testability, naming conventions, code smells
- Security (injection, auth, secrets) unless it produces a wrong number
- Sampling strategies and performance trade-offs (these are design choices)
- "Should SKIP be FAIL?" philosophical debates
- Missing docstrings, missing unit tests

If you have a structural concern, note it as [CODEX-TERRITORY] and move on — do NOT include it in your FAIL verdict.

## CALIBRATION RULES (avoid false positives)
- If a number appears correct by your calculation, it PASSES — do not downgrade for "could be more rigorous".
- A hardcoded date is NOT automatically a bug; flag only if it creates a provable wrong answer.
- If you cannot verify a number due to missing data, mark UNKNOWN (not FAIL).

## MANDATORY OUTPUT MARKER
Your response MUST end with a line containing EXACTLY one of:
  Overall verdict: PASS
  Overall verdict: WARN
  Overall verdict: FAIL
If you cannot determine, write: Overall verdict: WARN (with reason).
This marker is parsed by consensus_resolver — missing marker = UNKNOWN.

## OUTPUT FORMAT
- Score per in-scope criterion (0-10)
- PASS/FAIL (NUMERIC < 9 or CROSS-REF < 8 = FAIL)
- Specific issues with line numbers and the exact wrong number
- Overall verdict: PASS | WARN | FAIL  (must be on its own line, see marker rule)

Be specific. Quote numbers. No vague praise. No structural nitpicks."""

VERIFY_SYSTEM = """You are a sprint contract verifier focused on NUMERIC and MEASURABLE criteria.

Your peer verifier (Codex) handles functional/qualitative criteria.
YOUR specialty: anything that can be counted, measured, or cross-referenced.

For each criterion:
- PASS: measurable and confirmed in implementation
- FAIL: measurable but NOT met or NOT measurable yet
- PARTIAL: partially measurable (with specifics)

Output a scorecard table and overall verdict.
Pay special attention to:
- Numeric thresholds (e.g. "accuracy > 85%")
- Counts (e.g. "support 10 brands")
- Timing (e.g. "respond in < 2s")
- Coverage (e.g. "9 channels")
"""

# ─── Gate-specific prompt suffixes ────────────────────────────────
# "build" gate = auditing SOURCE CODE (formulas / constants / docstrings)
# "test"  gate = auditing EXECUTION RESULTS (runtime numbers in JSON/HTML)

BUILD_GATE_SUFFIX = """

## GATE: BUILD (source code audit)
You are reading SOURCE CODE with embedded constants, formulas, and docstrings.
Verify the factual correctness of what the code WILL compute:
- Formulas are mathematically sound (ROAS = revenue/spend, CTR = clicks/impressions, etc.)
- Constants (thresholds, tax rates, cutoff dates) are justified or clearly labeled
- Docstring claims ("±5% tolerance", "9 channels", "top 20") exactly match the code
- Hardcoded dates are either recent-enough or clearly explained
Do NOT evaluate runtime outputs — no results exist yet at build time.
"""

TEST_GATE_SUFFIX = """

## GATE: TEST (execution-result audit)
You are reading EXECUTION RESULTS (JSON / HTML / numeric reports), not source code.
Cross-verify the runtime numbers on the FACTUAL axis:
- Subtotals must sum to totals (ARITHMETIC) within ±0.1%
- Same metric appearing in multiple sections must match (CROSS-REFERENCE)
- Ratios / percentages must be internally consistent with their components
- Numbers must fall within ORBI business plausibility (ACOS 8–50%, Gross Margin 55–85%, etc.)
- Flag any value that is 0, NaN, None, or "N/A" where a real number is expected
Leverage your 1M context: cross-check every metric across the entire result payload.
"""

# ─── Domain-specific Evaluator prompts (numeric-focused) ────────────

CFO_AUDIT_SYSTEM = """You are an independent NUMERIC AUDITOR for ORBI's financial reports.
You audit Golmani's (VP Financial Modeling) output with ZERO trust — verify every number independently.

Unlike the peer auditor (Codex AICPA/KICPA policy checker), YOUR superpower is:
- 1M token context → read the whole workbook/sheet in one pass
- Strong arithmetic → spot calculation errors others miss
- Cross-table numeric reconciliation

## 6-Point Numeric Audit Checklist (ALL mandatory):

A. ARITHMETIC — Every subtotal must sum to its parent total.
   Revenue components = Total Revenue. Gross Profit = Revenue - COGS.
   Percentages must match numerator/denominator (±0.1% rounding tolerance).
   **Compute every formula yourself — do NOT trust the stated numbers.**

B. CROSS-TABLE CONSISTENCY — Same metric across multiple tables must match.
   P&L Revenue = Channel Breakdown Total = DataKeeper raw sum.
   Any $1K+ discrepancy = MAJOR. Any $10K+ = CRITICAL.
   **Use your long context to cross-reference every occurrence of each metric.**

C. PERIOD CONSISTENCY — All tables must use same date_from ~ date_to.
   YoY/MoM base period must be correct.

D. SIGN CONVENTIONS — Costs always positive or always negative (consistent).
   Discounts are revenue deductions. Margins must be positive.

E. ACCOUNTING STANDARDS (for cross-check with Codex auditor)
   - Revenue Recognition: Gross Revenue before platform fees (ORBI standard)
   - COGS: landed cost = FOB × 1.15 (NOT retail price)
   - Grosmimi Price Cutoff: 2025-03-01 (different prices before/after)

F. MATERIALITY & SANITY
   | Metric | Normal | WARN | CRITICAL |
   | Grosmimi Gross Margin | 68-72% | 60-80% | <55% or >85% |
   | Amazon ACOS | 15-25% | 10-35% | <8% or >50% |
   | MER | 10-20% | 8-28% | <5% or >35% |

## Severity:
- CRITICAL: Numeric error (arithmetic, wrong period). MUST fix.
- MAJOR: $10K+ cross-table diff. Should fix.
- MINOR: <$1K rounding. CFO discretion.
- INFO: Methodology notes.

## Output Format:
```json
{
  "status": "PASS | WARN | FAIL",
  "summary": "One-line numeric verdict",
  "findings": [{"id":"F001","severity":"CRITICAL","category":"A-F","section":"...","description":"...","expected":"...","actual":"...","correction_needed":"..."}],
  "corrections_required": ["F001"],
  "approved_sections": ["..."],
  "evaluator": "gemini"
}
```

$1 off = a bug. Be ruthless with numbers."""

PIPELINER_AUDIT_SYSTEM = """You are an E2E pipeline DATA CONSISTENCY specialist for ORBI's Creator Collab.

Your peer (Codex) checks stage integrity / workflow health.
YOUR focus: **data consistency across systems**.

## Pipeline Systems:
Airtable CRM ↔ Shopify (draft orders/customers) ↔ PostgreSQL ↔ n8n workflows ↔ Gmail

## Numeric/Data Verification Criteria:

### CROSS-SYSTEM ID INTEGRITY (CRITICAL)
- Airtable record ID → Shopify customer ID → PG row — does every link resolve?
- No orphaned records (e.g., Shopify customer without matching AT record)
- Email addresses byte-identical across all systems (trim, case-insensitive match OK)

### COUNT RECONCILIATION (HIGH)
- Applicants count (AT) = Customers count (Shopify draft) ± explained deltas
- Draft orders count (AT) = Draft orders count (Shopify) ± explained deltas
- Posts count (PG) = Posts count (Syncly source) ± explained deltas

### TIMESTAMP ORDERING (HIGH)
- Timestamps monotonically increase per pipeline run
- Stage N completed_at ≤ Stage N+1 started_at

### FIELD-LEVEL MATCH (MEDIUM)
- Key fields (name, email, handle, order_value) byte-match across systems
- Currency/unit consistency ($ vs ¢)

## Output Format:
```json
{
  "status": "PASS | WARN | FAIL",
  "summary": "One-line data consistency verdict",
  "cross_system_checks": [{"check":"...","at_value":"...","shopify_value":"...","pg_value":"...","match":true/false}],
  "count_reconciliation": [{"metric":"...","system_a":"...","system_b":"...","diff":0,"explained":true}],
  "findings": [...],
  "evaluator": "gemini"
}
```

Silent data drift is worse than loud failures. Byte-exact match preferred."""

# ─── Gemini API call ────────────────────────────────────────────

def call_gemini(system_prompt: str, user_prompt: str, model: str = None) -> dict:
    """Call Gemini via Google AI Studio Generative Language API (REST, no SDK needed)."""
    import urllib.request
    import urllib.error

    model = model or GEMINI_MODEL_DEFAULT

    # Gemini API endpoint — v1beta supports system_instruction + generateContent
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

    headers = {"Content-Type": "application/json"}
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
            "responseMimeType": "text/plain",
        },
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Extract text from response
            candidates = data.get("candidates", [])
            if not candidates:
                return {"ok": False, "error": "No candidates in Gemini response",
                        "raw": data}
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)
            usage = data.get("usageMetadata", {})
            return {
                "ok": True,
                "content": content,
                "model": model,
                "usage": {
                    "input_tokens": usage.get("promptTokenCount", 0),
                    "output_tokens": usage.get("candidatesTokenCount", 0),
                    "total_tokens": usage.get("totalTokenCount", 0),
                },
                "evaluator": "gemini",
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body}", "evaluator": "gemini"}
    except Exception as e:
        return {"ok": False, "error": str(e), "evaluator": "gemini"}


# ─── Commands ───────────────────────────────────────────────────

DOMAIN_PROMPTS = {
    "general": AUDIT_SYSTEM,
    "cfo": CFO_AUDIT_SYSTEM,
    "pipeliner": PIPELINER_AUDIT_SYSTEM,
}


def _get_domain_prompt(args) -> str:
    domain = getattr(args, "domain", "general") or "general"
    base = DOMAIN_PROMPTS.get(domain, AUDIT_SYSTEM)
    gate = (getattr(args, "gate", None) or "build").lower()
    if gate == "test":
        body = base + TEST_GATE_SUFFIX
    else:
        body = base + BUILD_GATE_SUFFIX
    # ─── Anti-stale-knowledge guard ──────────────────────────────────
    # Gemini's training cutoff predates current dates seen in our codebase.
    # Inject today's date so dates near/before "today" are NOT flagged as future.
    # Without this, real-time data points (e.g. "2026-04-25") trigger false FAILs.
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    today_clause = (
        f"\n\n## CURRENT DATE\n"
        f"Today's date (system clock, UTC): **{today}**.\n"
        f"Treat this as 'now'. Dates ON or BEFORE today are NOT 'in the future'.\n"
        f"Only flag a date as 'in the future' if it is strictly AFTER {today}.\n"
        f"Do NOT use your training cutoff as the reference for 'now'.\n"
    )
    return body + today_clause


def cmd_audit(args):
    """Audit specified files as numeric/factual Evaluator."""
    file_contents = []
    total_chars = 0
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            p = REPO_ROOT / fp
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")
            # Gemini has 1M context — we can afford larger files than Codex
            lines = content.splitlines()
            if len(lines) > 2000:
                content = "\n".join(lines[:2000]) + f"\n\n... ({len(lines) - 2000} more lines truncated)"
            total_chars += len(content)
            file_contents.append(f"### {fp}\n```\n{content}\n```")
        else:
            file_contents.append(f"### {fp}\n(FILE NOT FOUND)")

    system_prompt = _get_domain_prompt(args)
    domain = getattr(args, "domain", "general") or "general"

    # RAG: enrich with past numeric-audit context if available
    rag_context = ""
    if not getattr(args, "no_rag", False) and _rag_healthy():
        rag_query_text = f"{domain} numeric factual audit: " + " ".join(args.files[:3])
        rag_context = _rag_query(rag_query_text, mode="hybrid", top_k=3)
        if rag_context and len(rag_context) > 50:
            rag_context = f"\n\n## Prior Numeric Context (from RAG — Gemini namespace)\n{rag_context[:2000]}\n"
            print(f"[RAG] Enriched with {len(rag_context)} chars of prior factual context", file=sys.stderr)

    user_prompt = (
        f"[{domain.upper()} AUDIT — GEMINI NUMERIC/FACTUAL CHECK] "
        f"Audit the following files with your numeric/cross-reference strength.\n\n"
        + "\n\n".join(file_contents)
        + rag_context
    )

    print(f"[Gemini] Auditing {len(args.files)} file(s), {total_chars:,} chars total...",
          file=sys.stderr)
    result = call_gemini(system_prompt, user_prompt, model=args.model)
    _output(result, args)


def cmd_verify(args):
    """Verify sprint contract — numeric/measurable criteria."""
    contract_path = Path(args.contract)
    if not contract_path.exists():
        contract_path = REPO_ROOT / args.contract
    if not contract_path.exists():
        print(f"ERROR: Contract file not found: {args.contract}", file=sys.stderr)
        sys.exit(1)

    contract = contract_path.read_text(encoding="utf-8")
    domain = getattr(args, "domain", "general") or "general"
    user_prompt = (
        f"[{domain.upper()} VERIFY — GEMINI NUMERIC] Verify this sprint contract.\n\n"
        f"## Sprint Contract\n{contract}\n\n"
        "For each criterion report PASS/FAIL/PARTIAL with measurable evidence."
    )

    result = call_gemini(VERIFY_SYSTEM, user_prompt, model=args.model)
    _output(result, args)


def cmd_ask(args):
    """Free-form question to Gemini."""
    system_prompt = _get_domain_prompt(args)
    prompt = args.prompt

    # RAG: enrich with related numeric/factual context
    if not getattr(args, "no_rag", False) and _rag_healthy():
        rag_context = _rag_query(prompt, mode="hybrid", top_k=5)
        if rag_context and len(rag_context) > 50:
            prompt = f"{prompt}\n\n## Related Numeric Context (from RAG — Gemini namespace)\n{rag_context[:2000]}"
            print(f"[RAG] Enriched question with {len(rag_context)} chars", file=sys.stderr)

    result = call_gemini(system_prompt, prompt, model=args.model)
    _output(result, args)


# ─── Output helper ──────────────────────────────────────────

def _output(result: dict, args):
    import io, sys as _sys
    if _sys.stdout.encoding and _sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
        _sys.stderr = io.TextIOWrapper(_sys.stderr.buffer, encoding="utf-8", errors="replace")

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

    # Save
    save_path = TMP_DIR / f"eval_{ts}.json"
    save_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[Saved to {save_path}]", file=sys.stderr)

    usage = result.get("usage", {})
    if usage:
        total = usage.get("total_tokens", 0)
        print(f"[Gemini Tokens: {total}]", file=sys.stderr)

    # RAG: auto-index successful audit results for future retrieval
    # (namespaced so Codex retrieval does not preferentially hit these)
    if result.get("ok") and not getattr(args, "no_rag", False):
        domain = getattr(args, "domain", "general") or "general"
        _rag_index_result(result, domain, ts)


# ─── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gemini Evaluator — 제갈량 3-LLM harness Evaluator #2 (numeric/factual)"
    )
    parser.add_argument("--model", default=GEMINI_MODEL_DEFAULT,
                        help=f"Gemini model (default: {GEMINI_MODEL_DEFAULT})")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="JSON output")
    parser.add_argument("--domain", choices=["general", "cfo", "pipeliner"],
                        default="general",
                        help="Domain-specific audit mode (default: general)")
    parser.add_argument("--gate", choices=["build", "test"], default="build",
                        help="Gate context: build=source code audit, test=execution-result audit (default: build)")
    parser.add_argument("--no-rag", action="store_true",
                        help="Disable LightRAG context enrichment and auto-indexing")

    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="Audit code/data files (numeric/factual)")
    p_audit.add_argument("--files", nargs="+", required=True)
    p_audit.set_defaults(func=cmd_audit)

    p_verify = sub.add_parser("verify", help="Verify sprint contract (numeric)")
    p_verify.add_argument("--contract", required=True)
    p_verify.set_defaults(func=cmd_verify)

    p_ask = sub.add_parser("ask", help="Free-form numeric/factual question")
    p_ask.add_argument("prompt")
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()

    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set in .env or environment", file=sys.stderr)
        print("Get one at: https://aistudio.google.com/app/apikey", file=sys.stderr)
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
