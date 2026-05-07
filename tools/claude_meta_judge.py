"""
Claude Meta-Judge — 3rd Arbiter in the Harness Cross-Validation Loop.

Role in the 4-LLM harness:
  - Claude (this session)  = Generator (main work, writes the code)
  - Codex (GPT-4.1)        = Evaluator 1 — Structural/policy axis
  - Gemini (2.5 Pro)       = Evaluator 2 — Numeric/factual axis
  - Claude API (Sonnet)    = Evaluator 3 — Meta-judge, tie-breaker (THIS FILE)

When to invoke:
  consensus_resolver returns requires_meta_judge=True when:
    - Codex and Gemini disagree on their own axes (CODEX_AXIS_FAIL vs GEMINI_PASS,
      or vice versa) — one might be a false positive
    - Both evaluators produce UNKNOWN — need a decisive third opinion

The meta-judge reads:
  1. The original draft/artifact
  2. Codex's full verdict (structural axis opinion)
  3. Gemini's full verdict (factual axis opinion)
  4. (Optional) RAG-enriched past-feedback corpus showing prior false positives

Returns:
  {
    "final_verdict": "PASS | FAIL | WARN",
    "reasoning": "...",
    "codex_assessment": "VALID | FALSE_POSITIVE | MIXED",
    "gemini_assessment": "VALID | FALSE_POSITIVE | MIXED",
    "escalate_to_human": bool   # if Claude is also uncertain
  }

Usage:
    # Programmatic
    from claude_meta_judge import meta_judge
    verdict = meta_judge(draft_path, codex_result, gemini_result, domain="general")

    # CLI (for standalone testing / harness subprocess)
    python tools/claude_meta_judge.py \\
        --draft tools/meta_tester.py \\
        --codex .tmp/harness_results/SESSION/codex_loop_1.json \\
        --gemini .tmp/harness_results/SESSION/gemini_loop_1.json \\
        --domain general

Env:
    ANTHROPIC_API_KEY — Claude API key (from .env)
"""

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

# Force UTF-8 stdout/stderr (Windows cp949 safe)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / ".tmp" / "claude_meta_judge"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Load .env
ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        try:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            k = k.strip()
            if k and k not in os.environ:
                os.environ[k] = v
        except Exception:
            continue

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL_DEFAULT = os.environ.get("CLAUDE_META_JUDGE_MODEL", "claude-opus-4-7")

# ─── LightRAG Integration (meta-judge namespace) ─────────────────

LIGHTRAG_URL = os.environ.get("LIGHTRAG_URL", "http://localhost:9621")
RAG_NAMESPACE_TAG = "claude-meta-judge"


def _rag_healthy() -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(f"{LIGHTRAG_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8")).get("status") == "healthy"
    except Exception:
        return False


def _rag_query_feedback(text: str, top_k: int = 5) -> str:
    """Query LightRAG for PAST HUMAN FEEDBACK — learn which patterns were
    false positives vs real bugs."""
    try:
        import urllib.request
        biased = (f"[vault-feedback / false-positive patterns / human-validated / "
                  f"evaluator-disagreement] {text}")
        payload = json.dumps({"query": biased, "mode": "hybrid", "top_k": top_k,
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


# ─── Meta-judge system prompt ──────────────────────────────────────

META_JUDGE_SYSTEM = """You are the FINAL ARBITER in a 3-LLM cross-validation system for ORBI.

The two primary evaluators are:
  - Codex (GPT-4.1)  → STRUCTURAL axis (functionality, error handling, security, design)
  - Gemini (2.5 Pro) → FACTUAL axis   (arithmetic, cross-reference, hardcoded values)

You are invoked ONLY when they disagree or produce UNKNOWN. Your job:
  1. Read the original draft/artifact
  2. Read both evaluators' full verdicts
  3. Decide which evaluator is right, or whether both have valid points
  4. Produce ONE final verdict (PASS / FAIL / WARN)

## Your superpowers over Codex and Gemini
- You see the ORIGINAL draft AND both evaluator outputs simultaneously
- You are calibrated to the ORBI codebase conventions (see prior human feedback below if provided)
- You can recognize INTENTIONAL design choices vs accidental bugs
- You can distinguish FALSE POSITIVES from real bugs based on context

## Known evaluator failure modes
- Codex tends to flag "design philosophy" issues (sampling limits, SKIP-on-missing-file) as FAIL
  when they are often intentional trade-offs
- Gemini tends to mark UNKNOWN when the expected "Overall verdict: X" marker is missing
- Both can over-weight hardcoded values that are actually business constants

## Assessment categories
For each evaluator's verdict, classify:
- VALID          = Real issue, evaluator is correct
- FALSE_POSITIVE = Evaluator misread intent or raised non-issue
- MIXED          = Some findings valid, others false positives

## Final verdict rules
- If ANY valid structural OR factual FAIL → final PASS impossible (use WARN or FAIL)
- If all concerns are false positives → PASS
- If uncertain, escalate_to_human=true and pick the SAFER verdict (WARN over PASS)

## Output format — MUST be valid JSON, nothing else
```json
{
  "final_verdict": "PASS | FAIL | WARN",
  "reasoning": "2-3 sentences explaining the decision",
  "codex_assessment": "VALID | FALSE_POSITIVE | MIXED",
  "codex_rationale": "why you agreed/disagreed with Codex",
  "gemini_assessment": "VALID | FALSE_POSITIVE | MIXED",
  "gemini_rationale": "why you agreed/disagreed with Gemini",
  "valid_findings": ["findings that should be fixed"],
  "dismissed_findings": ["findings that were false positives"],
  "escalate_to_human": false
}
```

Be decisive. Your whole purpose is to resolve ambiguity, not to hedge."""


# ─── Claude API call ───────────────────────────────────────────────

def call_claude(system_prompt: str, user_prompt: str, model: str = None) -> dict:
    """Call Claude via Anthropic API. Uses urllib (no SDK dep)."""
    import urllib.request
    import urllib.error

    model = model or CLAUDE_MODEL_DEFAULT
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    # Opus 4.x + Sonnet 4.x no longer accept `temperature` (API 400 "deprecated").
    _body = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if not (model.startswith("claude-opus-4") or model.startswith("claude-sonnet-4")):
        _body["temperature"] = 0.1  # judgment task — low temperature
    payload = json.dumps(_body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_parts = data.get("content", [])
            content = "".join(p.get("text", "") for p in content_parts if p.get("type") == "text")
            return {
                "ok": True,
                "content": content,
                "model": data.get("model", model),
                "usage": data.get("usage", {}),
                "evaluator": "claude-meta-judge",
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body}", "evaluator": "claude-meta-judge"}
    except Exception as e:
        return {"ok": False, "error": str(e), "evaluator": "claude-meta-judge"}


# ─── Parse meta-judge response ──────────────────────────────────────

def parse_verdict(raw_content: str) -> dict:
    """Extract JSON verdict from Claude's response. Robust to surrounding text."""
    if not raw_content:
        return {"final_verdict": "WARN", "reasoning": "empty response",
                "escalate_to_human": True}

    # Try direct JSON parse first
    try:
        return json.loads(raw_content.strip())
    except Exception:
        pass

    # Extract JSON block from fenced code
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Find first balanced {...}
    start = raw_content.find("{")
    if start >= 0:
        depth = 0
        for i, ch in enumerate(raw_content[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw_content[start:i + 1])
                    except Exception:
                        break

    # Last resort — look for verdict keyword
    upper = raw_content.upper()
    for verdict in ("FAIL", "WARN", "PASS"):
        if f"FINAL_VERDICT\": \"{verdict}\"" in raw_content or f"FINAL VERDICT: {verdict}" in upper:
            return {"final_verdict": verdict, "reasoning": "parsed from text fallback",
                    "escalate_to_human": True}

    return {"final_verdict": "WARN", "reasoning": "unparseable response",
            "raw": raw_content[:500], "escalate_to_human": True}


# ─── Public API ────────────────────────────────────────────────────

def meta_judge(draft: str | Path, codex_result: dict, gemini_result: dict,
               domain: str = "general", gate: str = "build",
               use_rag: bool = True, model: str = None) -> dict:
    """Run Claude meta-judge on a Codex + Gemini disagreement.

    Args:
        draft: Path to original artifact, or content string.
        codex_result: codex_evaluator.py JSON output (dict).
        gemini_result: gemini_evaluator.py JSON output (dict).
        domain: audit domain (general / cfo / pipeliner).
        gate: build or test (passed for context).
        use_rag: if True and LightRAG healthy, enrich with past human feedback.
        model: Claude model override.

    Returns:
        {
          "ok": True,
          "verdict": { ... final_verdict, reasoning, ... },
          "raw_content": str,
          "model": str,
          "usage": {...},
          "session_dir": str,
        }
    """
    if not ANTHROPIC_API_KEY:
        return {"ok": False, "error": "ANTHROPIC_API_KEY not set",
                "verdict": {"final_verdict": "WARN", "reasoning": "no API key",
                            "escalate_to_human": True}}

    # Load draft content
    draft_content = ""
    draft_name = "(inline)"
    if isinstance(draft, Path) or (isinstance(draft, str) and Path(draft).exists()):
        p = Path(draft)
        draft_content = p.read_text(encoding="utf-8", errors="replace")
        draft_name = str(p)
    else:
        draft_content = str(draft)

    # Truncate very long drafts (Claude has big context but we keep it lean)
    lines = draft_content.splitlines()
    if len(lines) > 1500:
        draft_content = "\n".join(lines[:1500]) + f"\n\n... ({len(lines) - 1500} more lines truncated)"

    # RAG: past human feedback
    rag_context = ""
    if use_rag and _rag_healthy():
        rag_query = f"{domain} {gate} gate evaluator disagreement false positive patterns"
        raw = _rag_query_feedback(rag_query, top_k=5)
        if raw and len(raw) > 50:
            rag_context = (f"\n\n## Prior Human Feedback (from RAG vault — precedent)\n"
                           f"{raw[:3000]}\n")
            print(f"[RAG] Loaded {len(rag_context)} chars of human-feedback precedent",
                  file=sys.stderr)

    # Compose user prompt
    codex_content = codex_result.get("content", "") or str(codex_result)[:3000]
    gemini_content = gemini_result.get("content", "") or str(gemini_result)[:3000]

    user_prompt = f"""## Domain: {domain.upper()}  |  Gate: {gate.upper()}

## Original Draft ({draft_name})
```
{draft_content[:8000]}
```

## Codex Verdict (STRUCTURAL axis)
{codex_content[:4000]}

## Gemini Verdict (FACTUAL axis)
{gemini_content[:4000]}
{rag_context}

## Your Task
Read the three above (draft + both verdicts + precedent), then decide:
1. Which evaluator is correct, if either?
2. Are any findings false positives given ORBI conventions?
3. Final verdict: PASS / FAIL / WARN

Respond with ONLY the JSON object specified in your system prompt. No surrounding prose."""

    ts = time.strftime("%Y%m%d_%H%M%S")
    session_dir = TMP_DIR / ts
    session_dir.mkdir(parents=True, exist_ok=True)

    # Save inputs for audit trail
    (session_dir / "inputs.json").write_text(json.dumps({
        "draft_name": draft_name, "domain": domain, "gate": gate,
        "codex_result": codex_result, "gemini_result": gemini_result,
        "rag_enriched": bool(rag_context),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[Meta-Judge] Calling Claude on {domain}/{gate} disagreement...",
          file=sys.stderr)
    api_result = call_claude(META_JUDGE_SYSTEM, user_prompt, model=model)

    if not api_result.get("ok"):
        return {"ok": False, "error": api_result.get("error", "unknown"),
                "verdict": {"final_verdict": "WARN", "reasoning": "meta-judge API error",
                            "escalate_to_human": True},
                "session_dir": str(session_dir)}

    verdict = parse_verdict(api_result.get("content", ""))

    out = {
        "ok": True,
        "verdict": verdict,
        "raw_content": api_result.get("content", ""),
        "model": api_result.get("model"),
        "usage": api_result.get("usage", {}),
        "session_dir": str(session_dir),
    }

    (session_dir / "verdict.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Meta-Judge] Final verdict: {verdict.get('final_verdict', 'WARN')} "
          f"(escalate_to_human={verdict.get('escalate_to_human', False)})",
          file=sys.stderr)
    return out


# ─── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Claude Meta-Judge — arbitrates Codex vs Gemini disagreements"
    )
    parser.add_argument("--draft", required=True, help="Path to original draft/artifact")
    parser.add_argument("--codex", required=True, help="Path to codex_evaluator JSON output")
    parser.add_argument("--gemini", required=True, help="Path to gemini_evaluator JSON output")
    parser.add_argument("--domain", choices=["general", "cfo", "pipeliner"], default="general")
    parser.add_argument("--gate", choices=["build", "test"], default="build")
    parser.add_argument("--model", default=None, help="Claude model override")
    parser.add_argument("--no-rag", action="store_true", help="Skip RAG enrichment")
    parser.add_argument("--json", dest="json_output", action="store_true")
    args = parser.parse_args()

    codex_path = Path(args.codex)
    gemini_path = Path(args.gemini)
    for p in (codex_path, gemini_path):
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    try:
        codex_result = json.loads(codex_path.read_text(encoding="utf-8"))
        gemini_result = json.loads(gemini_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    out = meta_judge(
        draft=Path(args.draft),
        codex_result=codex_result,
        gemini_result=gemini_result,
        domain=args.domain,
        gate=args.gate,
        use_rag=not args.no_rag,
        model=args.model,
    )

    if args.json_output:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        v = out.get("verdict", {})
        print("=" * 60)
        print(f"META-JUDGE VERDICT: {v.get('final_verdict', '?')}")
        print(f"Reasoning: {v.get('reasoning', '')}")
        print(f"Codex: {v.get('codex_assessment', '?')} — {v.get('codex_rationale', '')[:200]}")
        print(f"Gemini: {v.get('gemini_assessment', '?')} — {v.get('gemini_rationale', '')[:200]}")
        if v.get("valid_findings"):
            print(f"\nValid findings (fix these):")
            for f in v["valid_findings"][:10]:
                print(f"  - {f}")
        if v.get("dismissed_findings"):
            print(f"\nDismissed (false positives):")
            for f in v["dismissed_findings"][:10]:
                print(f"  - {f}")
        if v.get("escalate_to_human"):
            print("\n⚠️  Escalate to human — meta-judge uncertain")
        print(f"\nSession: {out.get('session_dir')}")
        print("=" * 60)

    if not out.get("ok") or out.get("verdict", {}).get("final_verdict") == "FAIL":
        sys.exit(2)


if __name__ == "__main__":
    main()
