"""
Consensus Resolver — 3-LLM Harness Arbiter.

Compares verdicts from Codex (Policy/Code) and Gemini (Numeric/Factual) evaluators,
produces a consensus decision for Claude (Generator) to act on.

Decision matrix:
  Codex=PASS, Gemini=PASS → CONSENSUS_PASS      (green light)
  Codex=FAIL, Gemini=FAIL → CONSENSUS_FAIL      (block, send both feedback to Generator)
  Codex=PASS, Gemini=FAIL → GEMINI_ONLY_FAIL    (numeric issue — block)
  Codex=FAIL, Gemini=PASS → CODEX_ONLY_FAIL     (policy issue — block)
  Either WARN, other PASS → CONSENSUS_WARN      (proceed with caveats)
  Either ERROR              → EVALUATOR_DOWN    (fallback: trust the one that worked)

Usage:
    # Run both evaluators and resolve (shell orchestration)
    python tools/codex_evaluator.py --domain cfo audit --files report.json --json > .tmp/codex_verdict.json
    python tools/gemini_evaluator.py --domain cfo audit --files report.json --json > .tmp/gemini_verdict.json
    python tools/consensus_resolver.py resolve \\
        --codex .tmp/codex_verdict.json \\
        --gemini .tmp/gemini_verdict.json \\
        --out .tmp/consensus.json

    # One-shot: audit a file with both evaluators and resolve
    python tools/consensus_resolver.py audit --files report.json --domain cfo

    # Programmatic (from Python)
    from consensus_resolver import resolve_verdicts
    consensus = resolve_verdicts(codex_result, gemini_result)
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Fix Windows cp949 encoding crash — force UTF-8 stdout/stderr
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / ".tmp" / "consensus"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Load .env for API keys
ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if k.strip() not in os.environ:
                os.environ[k.strip()] = v

PYTHON = sys.executable or "python"


# ─── Verdict extraction ──────────────────────────────────────

_STATUS_PATTERNS = [
    # JSON-like: "status": "PASS"
    re.compile(r'"status"\s*:\s*"(PASS|FAIL|WARN)"', re.IGNORECASE),
    # Verdict lines: "Overall: PASS" / "Overall verdict: FAIL"
    re.compile(r'(?:overall|verdict|final|result)[:\s]+\**?(PASS|FAIL|WARN)', re.IGNORECASE),
    # Standalone: "PASS" / "FAIL" on its own line
    re.compile(r'^\s*\**?(PASS|FAIL|WARN)\**?\s*$', re.IGNORECASE | re.MULTILINE),
]


def extract_verdict(evaluator_result: dict) -> dict:
    """Extract PASS/FAIL/WARN from evaluator result (either JSON structured or free text).

    Returns:
        {"status": "PASS|FAIL|WARN|ERROR|UNKNOWN", "summary": str, "evaluator": str,
         "findings": list, "raw": str}
    """
    evaluator = evaluator_result.get("evaluator", "unknown")

    # Error case
    if not evaluator_result.get("ok", True):
        return {
            "status": "ERROR",
            "summary": evaluator_result.get("error", "unknown error")[:200],
            "evaluator": evaluator,
            "findings": [],
            "raw": "",
        }

    content = evaluator_result.get("content", "")
    if not content:
        return {"status": "UNKNOWN", "summary": "empty content", "evaluator": evaluator,
                "findings": [], "raw": ""}

    # Priority order for verdict extraction (prevents false positives from
    # quoted code/examples in evaluator prose):
    #   1. Explicit "Overall verdict: X" marker (new Gemini contract)
    #   2. Regex on lines like "Final verdict: X" / "**PASS**"
    #   3. JSON block — ONLY if its status is in the valid verdict set
    #
    # The previous implementation grabbed the first JSON with "status" field,
    # which mis-parsed quoted sample dicts like {"status": "SKIP", ...} as
    # the evaluator's verdict. Fixed by validating the JSON-extracted status.

    VALID_STATUSES = {"PASS", "FAIL", "WARN"}
    status = None

    # Step 1 & 2: regex on verdict keywords (highest signal)
    for pat in _STATUS_PATTERNS:
        m = pat.search(content)
        if m:
            candidate = m.group(1).upper()
            if candidate in VALID_STATUSES:
                status = candidate
                break

    # Step 3: structured JSON (only if regex didn't find anything conclusive)
    findings = []
    parsed_summary = ""
    try:
        # Scan ALL {...} blocks with "status"; take the LAST valid one
        # (evaluators typically put their final verdict JSON near the end,
        # after any inline code examples).
        matches = list(re.finditer(r'\{[^{}]*"status"[^{}]*\}', content, re.DOTALL))
        for brace_match in reversed(matches):
            start = content.rfind("{", 0, brace_match.end())
            depth = 0
            end = start
            for i, ch in enumerate(content[start:], start=start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > start:
                try:
                    obj = json.loads(content[start:end])
                except Exception:
                    continue
                candidate = (obj.get("status") or "").upper()
                if candidate not in VALID_STATUSES:
                    # Skip quoted examples / intermediate-finding dicts.
                    continue
                if not status:
                    status = candidate
                if not parsed_summary and obj.get("summary"):
                    parsed_summary = obj.get("summary", "")
                if not findings and obj.get("findings"):
                    findings = obj.get("findings", []) or []
                # Found a valid JSON verdict — we can stop scanning backward.
                break
    except Exception:
        pass

    if not status:
        status = "UNKNOWN"

    # Summary fallback: first non-empty line
    summary = parsed_summary
    if not summary:
        for line in content.splitlines():
            line = line.strip()
            if line and len(line) > 5 and not line.startswith("#"):
                summary = line[:200]
                break

    return {
        "status": status,
        "summary": summary,
        "evaluator": evaluator,
        "findings": findings,
        "raw": content[:500],
    }


# ─── Consensus logic ─────────────────────────────────────────
#
# AXIS-BASED VOTING MODEL (v2 — 2026-04-17)
# -----------------------------------------
# Codex  = STRUCTURAL axis (functionality, error handling, security, design)
# Gemini = FACTUAL axis   (arithmetic, cross-reference, hardcoded values, units)
#
# Each evaluator is judged ONLY on their own axis. We never treat a Codex
# structural opinion as equivalent to a Gemini numeric verdict — they are
# orthogonal. A single-axis FAIL blocks because both axes are required.
#
# UNKNOWN handling: when one evaluator cannot determine verdict (parse fail,
# no marker), we trust the clear evaluator on their axis and proceed with
# caveats. If BOTH are UNKNOWN, we escalate to Claude meta-judge.
#
# Meta-judge trigger: whenever evaluators disagree on their own axes
# (CODEX_AXIS_FAIL vs GEMINI_AXIS_FAIL), action becomes REQUEST_META_JUDGE
# so the caller can invoke Claude as tie-breaker.

# Decision matrix — (codex_status, gemini_status) → (consensus_status, action, notes)
_DECISION_MATRIX = {
    # Both agree
    ("PASS", "PASS"):       ("CONSENSUS_PASS",        "PROCEED",                  "Both axes PASS"),
    ("FAIL", "FAIL"):       ("CONSENSUS_FAIL",        "BLOCK_AND_REVISE",         "Both axes FAIL"),

    # Single-axis failures (each axis is blocking — both required to ship)
    ("PASS", "FAIL"):       ("GEMINI_AXIS_FAIL",      "BLOCK_AND_REVISE",         "Factual/numeric issue (Gemini) — Codex cleared structure"),
    ("FAIL", "PASS"):       ("CODEX_AXIS_FAIL",       "BLOCK_AND_REVISE",         "Structural/policy issue (Codex) — Gemini cleared numbers"),

    # WARN combinations (proceed with caveats unless paired with FAIL)
    ("WARN", "PASS"):       ("CONSENSUS_WARN_STRUCT", "PROCEED_WITH_CAVEATS",     "Codex structural warning; factual axis clear"),
    ("PASS", "WARN"):       ("CONSENSUS_WARN_FACT",   "PROCEED_WITH_CAVEATS",     "Gemini factual warning; structural axis clear"),
    ("WARN", "WARN"):       ("CONSENSUS_WARN",        "PROCEED_WITH_CAVEATS",     "Both axes flagged warnings"),
    ("WARN", "FAIL"):       ("GEMINI_AXIS_FAIL",      "BLOCK_AND_REVISE",         "Factual FAIL overrides structural WARN"),
    ("FAIL", "WARN"):       ("CODEX_AXIS_FAIL",       "BLOCK_AND_REVISE",         "Structural FAIL overrides factual WARN"),

    # UNKNOWN handling — trust whichever axis delivered a clear verdict
    ("UNKNOWN", "PASS"):    ("CONSENSUS_PASS_PARTIAL","PROCEED_WITH_CAVEATS",     "Factual PASS; Codex produced no clear structural verdict"),
    ("PASS", "UNKNOWN"):    ("CONSENSUS_PASS_PARTIAL","PROCEED_WITH_CAVEATS",     "Structural PASS; Gemini produced no clear factual verdict"),
    ("UNKNOWN", "FAIL"):    ("GEMINI_AXIS_FAIL",      "BLOCK_AND_REVISE",         "Factual FAIL (Codex unclear)"),
    ("FAIL", "UNKNOWN"):    ("CODEX_AXIS_FAIL",       "BLOCK_AND_REVISE",         "Structural FAIL (Gemini unclear)"),
    ("UNKNOWN", "WARN"):    ("CONSENSUS_WARN_FACT",   "PROCEED_WITH_CAVEATS",     "Factual WARN (Codex unclear)"),
    ("WARN", "UNKNOWN"):    ("CONSENSUS_WARN_STRUCT", "PROCEED_WITH_CAVEATS",     "Structural WARN (Gemini unclear)"),
    ("UNKNOWN", "UNKNOWN"): ("CONSENSUS_UNKNOWN",     "REQUEST_META_JUDGE",       "Both axes unclear — escalate to Claude meta-judge"),

    # SKIP (one evaluator disabled via flag) — treat as PASS on that axis
    ("SKIP", "PASS"):       ("CONSENSUS_PASS_PARTIAL","PROCEED_WITH_CAVEATS",     "Codex skipped; Gemini PASS"),
    ("PASS", "SKIP"):       ("CONSENSUS_PASS_PARTIAL","PROCEED_WITH_CAVEATS",     "Gemini skipped; Codex PASS"),
    ("SKIP", "FAIL"):       ("GEMINI_AXIS_FAIL",      "BLOCK_AND_REVISE",         "Codex skipped; factual FAIL"),
    ("FAIL", "SKIP"):       ("CODEX_AXIS_FAIL",       "BLOCK_AND_REVISE",         "Gemini skipped; structural FAIL"),
    ("SKIP", "WARN"):       ("CONSENSUS_WARN_FACT",   "PROCEED_WITH_CAVEATS",     "Codex skipped; factual WARN"),
    ("WARN", "SKIP"):       ("CONSENSUS_WARN_STRUCT", "PROCEED_WITH_CAVEATS",     "Gemini skipped; structural WARN"),
    ("SKIP", "UNKNOWN"):    ("CONSENSUS_UNKNOWN",     "REQUEST_META_JUDGE",       "Codex skipped; Gemini unclear — escalate"),
    ("UNKNOWN", "SKIP"):    ("CONSENSUS_UNKNOWN",     "REQUEST_META_JUDGE",       "Gemini skipped; Codex unclear — escalate"),
    ("SKIP", "SKIP"):       ("CONSENSUS_SKIP",        "PROCEED",                  "Both evaluators disabled"),
}

# Verdicts that the main axis considers blocking
_BLOCKING_CONSENSUS = {"CONSENSUS_FAIL", "CODEX_AXIS_FAIL", "GEMINI_AXIS_FAIL"}

# Verdicts that should trigger Claude meta-judge for tie-breaking
_META_JUDGE_TRIGGERS = {
    "CONSENSUS_UNKNOWN",     # both unclear
    "CODEX_AXIS_FAIL",       # Codex blames, Gemini cleared — might be false positive
    "GEMINI_AXIS_FAIL",      # Gemini blames, Codex cleared — usually legit but verify
}


def resolve_verdicts(codex_result: dict, gemini_result: dict) -> dict:
    """Resolve Codex + Gemini verdicts into a consensus decision.

    Args:
        codex_result: output of codex_evaluator.py (dict with 'ok', 'content', etc.)
        gemini_result: output of gemini_evaluator.py (same shape)

    Returns:
        {
          "consensus": "CONSENSUS_PASS|CONSENSUS_FAIL|CONSENSUS_WARN|CODEX_ONLY_FAIL|GEMINI_ONLY_FAIL|EVALUATOR_DOWN",
          "action": "PROCEED|BLOCK_AND_REVISE|PROCEED_WITH_CAVEATS",
          "notes": str,
          "codex": {status, summary, findings},
          "gemini": {status, summary, findings},
          "generator_feedback": str  (for Claude to use in revision)
        }
    """
    codex = extract_verdict(codex_result)
    gemini = extract_verdict(gemini_result)

    # Handle evaluator errors
    if codex["status"] == "ERROR" and gemini["status"] == "ERROR":
        return {
            "consensus": "EVALUATOR_DOWN",
            "action": "BLOCK_AND_REVISE",
            "notes": "Both evaluators errored — cannot verify. Retry or escalate.",
            "codex": codex,
            "gemini": gemini,
            "generator_feedback": "Evaluators unavailable. Cannot audit. Retry later.",
        }
    if codex["status"] == "ERROR":
        # Trust Gemini alone
        return {
            "consensus": f"CODEX_DOWN_GEMINI_{gemini['status']}",
            "action": "PROCEED_WITH_CAVEATS" if gemini["status"] in ("PASS", "WARN") else "BLOCK_AND_REVISE",
            "notes": f"Codex errored ({codex['summary']}); trusting Gemini: {gemini['status']}",
            "codex": codex,
            "gemini": gemini,
            "generator_feedback": gemini["summary"] if gemini["status"] == "FAIL" else "",
        }
    if gemini["status"] == "ERROR":
        return {
            "consensus": f"GEMINI_DOWN_CODEX_{codex['status']}",
            "action": "PROCEED_WITH_CAVEATS" if codex["status"] in ("PASS", "WARN") else "BLOCK_AND_REVISE",
            "notes": f"Gemini errored ({gemini['summary']}); trusting Codex: {codex['status']}",
            "codex": codex,
            "gemini": gemini,
            "generator_feedback": codex["summary"] if codex["status"] == "FAIL" else "",
        }

    # Normal: lookup decision matrix
    key = (codex["status"], gemini["status"])
    if key not in _DECISION_MATRIX:
        # Should be rare now (matrix covers PASS/FAIL/WARN/UNKNOWN/SKIP × 2 = 25 combos).
        # Unknown status → escalate to meta-judge rather than silently downgrade.
        consensus, action, notes = ("CONSENSUS_UNKNOWN", "REQUEST_META_JUDGE",
                                    f"Unrecognized verdict combo: codex={codex['status']}, gemini={gemini['status']}")
    else:
        consensus, action, notes = _DECISION_MATRIX[key]

    # Build generator feedback for revision — axis-labeled for clarity
    feedback_parts = []
    if codex["status"] in ("FAIL", "WARN") and codex["findings"]:
        feedback_parts.append(f"## Codex — STRUCTURAL axis ({codex['status']})\n" +
                              "\n".join(f"- [{f.get('severity', '?')}] {f.get('description', '')[:200]}"
                                        for f in codex["findings"][:10]))
    elif codex["status"] in ("FAIL", "WARN") and codex["summary"]:
        feedback_parts.append(f"## Codex — STRUCTURAL axis ({codex['status']}): {codex['summary']}")

    if gemini["status"] in ("FAIL", "WARN") and gemini["findings"]:
        feedback_parts.append(f"## Gemini — FACTUAL axis ({gemini['status']})\n" +
                              "\n".join(f"- [{f.get('severity', '?')}] {f.get('description', '')[:200]}"
                                        for f in gemini["findings"][:10]))
    elif gemini["status"] in ("FAIL", "WARN") and gemini["summary"]:
        feedback_parts.append(f"## Gemini — FACTUAL axis ({gemini['status']}): {gemini['summary']}")

    return {
        "consensus": consensus,
        "action": action,
        "notes": notes,
        "codex": codex,
        "gemini": gemini,
        "generator_feedback": "\n\n".join(feedback_parts),
        "requires_meta_judge": consensus in _META_JUDGE_TRIGGERS,
        "axis_verdicts": {
            "structural": codex["status"],   # Codex's axis
            "factual":    gemini["status"],  # Gemini's axis
        },
    }


# ─── Commands ────────────────────────────────────────────────

def cmd_resolve(args):
    """Resolve pre-computed Codex + Gemini verdicts."""
    codex_path = Path(args.codex)
    gemini_path = Path(args.gemini)
    if not codex_path.exists():
        print(f"ERROR: Codex verdict not found: {args.codex}", file=sys.stderr)
        sys.exit(1)
    if not gemini_path.exists():
        print(f"ERROR: Gemini verdict not found: {args.gemini}", file=sys.stderr)
        sys.exit(1)

    codex_result = json.loads(codex_path.read_text(encoding="utf-8"))
    gemini_result = json.loads(gemini_path.read_text(encoding="utf-8"))

    consensus = resolve_verdicts(codex_result, gemini_result)

    output_json = json.dumps(consensus, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(output_json, encoding="utf-8")
        print(f"[Saved to {args.out}]", file=sys.stderr)

    if args.json_output:
        print(output_json)
    else:
        _print_summary(consensus)


def cmd_audit(args):
    """One-shot: run both evaluators on files and resolve."""
    domain_arg = ["--domain", args.domain] if args.domain else []
    ts = time.strftime("%Y%m%d_%H%M%S")

    codex_out = TMP_DIR / f"codex_{ts}.json"
    gemini_out = TMP_DIR / f"gemini_{ts}.json"

    print(f"[Consensus] Running Codex...", file=sys.stderr)
    codex_cmd = [PYTHON, str(REPO_ROOT / "tools" / "codex_evaluator.py"),
                 *domain_arg, "--json", "audit", "--files", *args.files]
    with open(codex_out, "w", encoding="utf-8") as f:
        r = subprocess.run(codex_cmd, stdout=f, stderr=subprocess.PIPE, cwd=str(REPO_ROOT))
    if r.returncode != 0:
        print(f"[WARN] Codex exit {r.returncode}: {r.stderr.decode('utf-8', 'replace')[:300]}",
              file=sys.stderr)

    print(f"[Consensus] Running Gemini...", file=sys.stderr)
    gemini_cmd = [PYTHON, str(REPO_ROOT / "tools" / "gemini_evaluator.py"),
                  *domain_arg, "--json", "audit", "--files", *args.files]
    with open(gemini_out, "w", encoding="utf-8") as f:
        r = subprocess.run(gemini_cmd, stdout=f, stderr=subprocess.PIPE, cwd=str(REPO_ROOT))
    if r.returncode != 0:
        print(f"[WARN] Gemini exit {r.returncode}: {r.stderr.decode('utf-8', 'replace')[:300]}",
              file=sys.stderr)

    # Load and resolve
    try:
        codex_result = json.loads(codex_out.read_text(encoding="utf-8"))
    except Exception as e:
        codex_result = {"ok": False, "error": f"Failed to parse codex output: {e}",
                        "evaluator": "codex"}
    try:
        gemini_result = json.loads(gemini_out.read_text(encoding="utf-8"))
    except Exception as e:
        gemini_result = {"ok": False, "error": f"Failed to parse gemini output: {e}",
                         "evaluator": "gemini"}

    consensus = resolve_verdicts(codex_result, gemini_result)

    consensus_path = TMP_DIR / f"consensus_{ts}.json"
    consensus_path.write_text(json.dumps(consensus, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"[Saved to {consensus_path}]", file=sys.stderr)

    if args.json_output:
        print(json.dumps(consensus, ensure_ascii=False, indent=2))
    else:
        _print_summary(consensus)


def _print_summary(consensus: dict):
    """Human-readable consensus summary."""
    c = consensus
    print("=" * 60)
    print(f"CONSENSUS: {c['consensus']}")
    print(f"ACTION: {c['action']}")
    print(f"NOTES: {c['notes']}")
    print("-" * 60)
    print(f"Codex  → {c['codex']['status']:6} — {c['codex']['summary'][:80]}")
    print(f"Gemini → {c['gemini']['status']:6} — {c['gemini']['summary'][:80]}")
    if c["generator_feedback"]:
        print("-" * 60)
        print("Feedback for Generator:")
        print(c["generator_feedback"][:2000])
    print("=" * 60)


# ─── CLI ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Consensus Resolver — arbitrate Codex + Gemini verdicts"
    )
    parser.add_argument("--json", dest="json_output", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", help="Resolve pre-computed verdicts")
    p_resolve.add_argument("--codex", required=True, help="Codex verdict JSON file")
    p_resolve.add_argument("--gemini", required=True, help="Gemini verdict JSON file")
    p_resolve.add_argument("--out", help="Save consensus to file")
    p_resolve.set_defaults(func=cmd_resolve)

    p_audit = sub.add_parser("audit", help="Run both evaluators on files, resolve")
    p_audit.add_argument("--files", nargs="+", required=True)
    p_audit.add_argument("--domain", choices=["general", "cfo", "pipeliner"],
                         default="general")
    p_audit.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
