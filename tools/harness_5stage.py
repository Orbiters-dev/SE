"""
Harness — 3-LLM Generator-Evaluator Orchestrator.

Architecture (Anthropic Harness Design pattern):
  Claude (Generator) → Codex (Policy Evaluator) → Gemini (Numeric Evaluator) → Consensus → verdict

The Harness is the entry point for any ORBI agent/skill that wants automatic
cross-AI verification. It orchestrates:
  1. Save the draft/artifact to disk
  2. Run Codex audit (policy/spec/code-quality)
  3. Run Gemini audit (numeric/factual/cross-reference)
  4. Resolve consensus
  5. If FAIL: return feedback to caller for revision
  6. If PASS: return green light

Usage (programmatic — from agent code):
    from harness import Harness

    h = Harness()
    result = h.run(
        task_type="dm",               # or "code", "workflow", "report", "ppc", ...
        draft=draft_text,
        context={"influencer": "みき様"},
        max_loops=2,                  # Codex Evaluator 2회 루프 rule
    )
    if result["status"] == "PASS":
        # proceed
        print(result["final_draft"])
    else:
        print(result["feedback"])     # for manual review

Usage (CLI):
    # Audit a file with 3-LLM consensus
    python tools/harness.py --type code --file tools/data_keeper.py

    # Audit with CFO domain
    python tools/harness.py --type report --file .tmp/cfo_sessions/golmani_output.json --domain cfo

    # Show status
    python tools/harness.py --status
"""

import argparse
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Fix Windows cp949 encoding crash — force UTF-8 stdout/stderr.
# Codex Loop 2 fix: guard against environments where stdout/stderr lack
# `.buffer` (e.g. StringIO, some IDEs, pytest capture). Silently skip —
# the calling environment already handles encoding.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / ".tmp" / "harness_results"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Load .env
# Codex Loop 2 fix: tolerate malformed lines (no crash on bad .env).
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
            # skip malformed lines silently — never crash harness init
            continue

PYTHON = sys.executable or "python"

# ─── Task type → domain mapping ──────────────────────────────

# Each task type maps to a domain (for evaluator prompt selection).
TASK_DOMAIN_MAP = {
    "dm": "general",
    "code": "general",
    "workflow": "general",
    "ig_plan": "general",
    "report": "cfo",
    "kpi": "cfo",
    "financial": "cfo",
    "ppc": "general",
    "pipeline": "pipeliner",
    "e2e": "pipeliner",
    "datakeeper": "general",  # 18-channel collection result audits
}


# ─── Harness class ───────────────────────────────────────────

class Harness:
    """3-LLM Harness orchestrator.

    Evaluators available (toggle via `evaluators` param):
      - "codex": OpenAI GPT (policy/spec/code-quality)
      - "gemini": Google Gemini (numeric/factual/cross-reference)

    Default = both → full 3-LLM consensus (Claude + Codex + Gemini).
    Pass ["codex"] only → fall back to 2-LLM (same as pre-v2).
    """

    def __init__(self, evaluators: list[str] | None = None,
                 meta_judge_enabled: bool = True):
        self.evaluators = evaluators or ["codex", "gemini"]
        self.codex_script = REPO_ROOT / "tools" / "codex_evaluator.py"
        self.gemini_script = REPO_ROOT / "tools" / "gemini_evaluator.py"
        self.consensus_script = REPO_ROOT / "tools" / "consensus_resolver.py"
        self.meta_judge_script = REPO_ROOT / "tools" / "claude_meta_judge.py"
        self.meta_judge_enabled = meta_judge_enabled and self.meta_judge_script.exists()

        # Sanity check
        for ev in self.evaluators:
            if ev == "codex" and not self.codex_script.exists():
                raise FileNotFoundError(f"codex_evaluator.py missing: {self.codex_script}")
            if ev == "gemini" and not self.gemini_script.exists():
                raise FileNotFoundError(f"gemini_evaluator.py missing: {self.gemini_script}")

        # Codex Loop 1 fix: import consensus_resolver ONCE, not per _single_pass call
        tools_dir = str(REPO_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from consensus_resolver import resolve_verdicts  # noqa: E402
        self._resolve_verdicts = resolve_verdicts

    # ------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------ #
    def run(
        self,
        task_type: str,
        draft: str | Path,
        context: dict | None = None,
        max_loops: int = 2,
        domain: str | None = None,
        gate: str = "build",
    ) -> dict:
        """Run the 3-LLM harness on a draft.

        **Loop semantics (Codex Loop 2 clarification)**:
        This harness is a single-pass auditor. On PASS/WARN it stops. On FAIL
        it stops AND returns generator_feedback so the CALLER can revise the
        draft and re-invoke `run()`. The `max_loops` parameter is the upper
        bound for evaluator re-runs on the SAME draft (not auto-revision) —
        typically max_loops=1 is correct. It exists only to match Anthropic's
        GAN pattern where evaluators can be re-sampled for stability.

        **Why not auto-revise?** Separation of concerns: Harness = audit,
        Generator (Claude / another LLM) = revise. Wiring the revision
        generator into this class would couple it to a specific LLM SDK.

        Args:
            task_type: one of TASK_DOMAIN_MAP keys (e.g. "dm", "code", "report")
            draft: Path object = file path (read from disk).
                   str = literal content (written to session_dir/draft.txt).
            context: optional context passed to evaluators
            max_loops: evaluator re-run ceiling on same draft (default 2,
                       recommended 1 for most cases).
            domain: override the auto-mapped domain from task_type

        Returns:
            {
              "status": "PASS | FAIL | WARN",
              "loops_used": int,             # evaluator passes actually run
              "final_draft": str | None,     # content if PASS/WARN
              "feedback": str,               # generator_feedback if FAIL
              "consensus_history": [...],    # per-loop consensus records
              "session_dir": str,            # .tmp/harness_results/{session_id}
            }
        """
        session_id = time.strftime("%Y%m%d_%H%M%S")
        session_dir = TMP_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Save draft to file (evaluators read files)
        # Codex Loop 1 fix: disambiguate path vs content.
        # Path objects are ALWAYS treated as file paths. Strings are ALWAYS content.
        # This avoids silent bugs when a draft string coincidentally matches a filename.
        if isinstance(draft, Path):
            if not draft.exists():
                raise FileNotFoundError(f"draft file does not exist: {draft}")
            draft_path = draft
            draft_content = draft_path.read_text(encoding="utf-8", errors="replace")
        else:
            draft_content = str(draft)
            if not draft_content.strip():
                raise ValueError("draft content is empty")
            draft_path = session_dir / "draft.txt"
            draft_path.write_text(draft_content, encoding="utf-8")

        effective_domain = domain or TASK_DOMAIN_MAP.get(task_type, "general")

        # Save context
        if context:
            (session_dir / "context.json").write_text(
                json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        consensus_history = []
        final_consensus = None

        meta_judge_result = None
        for loop in range(1, max_loops + 1):
            print(f"[Harness] Loop {loop}/{max_loops} — running evaluators on {draft_path.name} (gate={gate})",
                  file=sys.stderr)

            consensus = self._single_pass(draft_path, effective_domain, session_dir, loop, gate)
            consensus_history.append(consensus)
            final_consensus = consensus

            # Meta-judge: invoke Claude as tie-breaker when Codex/Gemini disagree
            # or both produce UNKNOWN. Overrides consensus verdict if meta-judge is clear.
            if self.meta_judge_enabled and consensus.get("requires_meta_judge"):
                meta_judge_result = self._run_meta_judge(draft_path, effective_domain, gate,
                                                         session_dir, loop)

            # Check if we should stop
            if consensus["consensus"] == "CONSENSUS_PASS":
                print(f"[Harness] PASS on loop {loop}", file=sys.stderr)
                break
            if consensus["consensus"] in ("CONSENSUS_WARN", "CONSENSUS_WARN_STRUCT",
                                           "CONSENSUS_WARN_FACT", "CONSENSUS_PASS_PARTIAL",
                                           "CONSENSUS_SKIP"):
                print(f"[Harness] {consensus['consensus']} on loop {loop} — proceeding with caveats",
                      file=sys.stderr)
                break
            # FAIL / AXIS_FAIL / UNKNOWN → stop and return feedback for caller.
            # Per docstring, this is a single-pass auditor. Caller (Generator)
            # revises the draft and re-invokes run().
            print(f"[Harness] {consensus['consensus']} — feedback for revision available",
                  file=sys.stderr)
            break  # return feedback, let caller revise

        # Determine initial status from consensus
        status = "PASS"
        fail_codes = {"CONSENSUS_FAIL", "GEMINI_AXIS_FAIL", "CODEX_AXIS_FAIL",
                      "GEMINI_ONLY_FAIL", "CODEX_ONLY_FAIL", "EVALUATOR_DOWN"}
        warn_codes = {"CONSENSUS_WARN", "CONSENSUS_WARN_STRUCT", "CONSENSUS_WARN_FACT",
                      "CONSENSUS_PASS_PARTIAL", "CONSENSUS_UNKNOWN", "CONSENSUS_SKIP"}
        if final_consensus:
            if final_consensus["consensus"] in fail_codes:
                status = "FAIL"
            elif final_consensus["consensus"] in warn_codes:
                status = "WARN"

        # Meta-judge override (authoritative when present)
        meta_verdict = None
        escalate_human = False
        if meta_judge_result and meta_judge_result.get("ok"):
            mj = meta_judge_result.get("verdict", {}) or {}
            mv = (mj.get("final_verdict") or "").upper()
            if mv in ("PASS", "FAIL", "WARN"):
                meta_verdict = mv
                status = mv
                escalate_human = bool(mj.get("escalate_to_human"))
                # Safety: if Claude itself is uncertain, never upgrade past WARN
                if escalate_human and status == "PASS":
                    status = "WARN"
                print(f"[Harness] Meta-judge verdict: {mv} "
                      f"(escalate_to_human={escalate_human}) — overriding consensus",
                      file=sys.stderr)

        result = {
            "status": status,
            "loops_used": len(consensus_history),
            "final_draft": draft_content if status in ("PASS", "WARN") else None,
            "feedback": (final_consensus or {}).get("generator_feedback", ""),
            "consensus_history": consensus_history,
            "session_dir": str(session_dir),
            "task_type": task_type,
            "domain": effective_domain,
            "gate": gate,
            "evaluators_used": self.evaluators,
            "requires_meta_judge": (final_consensus or {}).get("requires_meta_judge", False),
            "meta_judge_enabled": self.meta_judge_enabled,
            "meta_judge_result": meta_judge_result,
            "meta_judge_verdict": meta_verdict,
            "escalate_to_human": escalate_human,
        }

        # Persist final result
        (session_dir / "harness_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    # ------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------ #
    def _single_pass(self, draft_path: Path, domain: str, session_dir: Path,
                     loop: int, gate: str = "build") -> dict:
        """One evaluator pass → consensus."""
        codex_result = None
        gemini_result = None

        if "codex" in self.evaluators:
            codex_result = self._run_codex(draft_path, domain, session_dir, loop, gate)
        if "gemini" in self.evaluators:
            gemini_result = self._run_gemini(draft_path, domain, session_dir, loop, gate)

        # If only one evaluator, fake the other as PASS (skip).
        # Codex Loop 1 fix: include all fields consensus_resolver may inspect
        # (summary, raw, content) to avoid KeyError downstream.
        if codex_result is None:
            codex_result = {"ok": True, "content": '{"status": "SKIP"}',
                            "evaluator": "codex", "status": "SKIP",
                            "summary": "(skipped)", "raw": "",
                            "findings": []}
        if gemini_result is None:
            gemini_result = {"ok": True, "content": '{"status": "SKIP"}',
                             "evaluator": "gemini", "status": "SKIP",
                             "summary": "(skipped)", "raw": "",
                             "findings": []}

        # Codex Loop 1 fix: resolver imported once in __init__, not per call
        consensus = self._resolve_verdicts(codex_result, gemini_result)
        consensus["loop"] = loop

        # Persist per-loop consensus
        (session_dir / f"consensus_loop_{loop}.json").write_text(
            json.dumps(consensus, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return consensus

    def _run_codex(self, draft_path: Path, domain: str, session_dir: Path,
                   loop: int, gate: str = "build") -> dict:
        return self._run_evaluator("codex", self.codex_script, draft_path,
                                   domain, session_dir, loop, gate=gate)

    def _run_gemini(self, draft_path: Path, domain: str, session_dir: Path,
                    loop: int, gate: str = "build") -> dict:
        return self._run_evaluator("gemini", self.gemini_script, draft_path,
                                   domain, session_dir, loop, gate=gate)

    def _run_meta_judge(self, draft_path: Path, domain: str, gate: str,
                        session_dir: Path, loop: int, timeout: int = 180) -> dict | None:
        """Invoke claude_meta_judge.py as subprocess when evaluators disagree.

        Returns the parsed meta-judge result or None on failure. Non-blocking —
        meta-judge failure never prevents harness from returning.
        """
        codex_json = session_dir / f"codex_loop_{loop}.json"
        gemini_json = session_dir / f"gemini_loop_{loop}.json"
        if not codex_json.exists() or not gemini_json.exists():
            print(f"[Meta-Judge] Skipping — evaluator outputs missing", file=sys.stderr)
            return None

        out_path = session_dir / f"meta_judge_loop_{loop}.json"
        cmd = [PYTHON, str(self.meta_judge_script),
               "--draft", str(draft_path),
               "--codex", str(codex_json),
               "--gemini", str(gemini_json),
               "--domain", domain,
               "--gate", gate,
               "--json"]
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE,
                                   cwd=str(REPO_ROOT), timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[Meta-Judge] Timeout after {timeout}s", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[Meta-Judge] Launch failed: {e}", file=sys.stderr)
            return None

        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace")[:400]
            print(f"[Meta-Judge] exit {r.returncode}: {err}", file=sys.stderr)

        try:
            text = out_path.read_text(encoding="utf-8")
            if not text.strip():
                return None
            return json.loads(text)
        except Exception as e:
            print(f"[Meta-Judge] Parse failed: {e}", file=sys.stderr)
            return None

    def _run_evaluator(self, name: str, script: Path, draft_path: Path,
                       domain: str, session_dir: Path, loop: int,
                       timeout: int = 240, gate: str = "build") -> dict:
        """Run an evaluator subprocess with robust timeout/error handling.

        Codex Loop 1 fix: TimeoutExpired and invalid JSON now produce a
        structured evaluator-down dict instead of raising or returning
        misleading data.
        """
        out_path = session_dir / f"{name}_loop_{loop}.json"
        # NOTE: --json is a top-level flag (before subcommand) in both evaluators
        cmd = [PYTHON, str(script), "--domain", domain, "--gate", gate, "--json",
               "audit", "--files", str(draft_path)]
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE,
                                   cwd=str(REPO_ROOT), timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[Harness] {name} timed out after {timeout}s", file=sys.stderr)
            return {"ok": False, "status": "FAIL",
                    "error": f"{name} timeout after {timeout}s",
                    "evaluator": name, "summary": f"(timeout {timeout}s)",
                    "raw": "", "findings": []}
        except Exception as e:
            return {"ok": False, "status": "FAIL",
                    "error": f"{name} launch failed: {e}",
                    "evaluator": name, "summary": f"(launch error)",
                    "raw": "", "findings": []}

        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace")[:500]
            print(f"[Harness] {name} exit {r.returncode}: {err}", file=sys.stderr)

        # Parse output file; JSON decode failures no longer crash the harness.
        try:
            text = out_path.read_text(encoding="utf-8")
            if not text.strip():
                return {"ok": False, "status": "FAIL",
                        "error": f"{name} produced empty output",
                        "evaluator": name, "summary": "(empty output)",
                        "raw": "", "findings": []}
            return json.loads(text)
        except json.JSONDecodeError as e:
            return {"ok": False, "status": "FAIL",
                    "error": f"{name} JSON parse failed: {e}",
                    "evaluator": name, "summary": "(malformed JSON)",
                    "raw": text[:2000] if 'text' in locals() else "",
                    "findings": []}
        except Exception as e:
            return {"ok": False, "status": "FAIL",
                    "error": f"{name} output read failed: {e}",
                    "evaluator": name, "summary": "(read error)",
                    "raw": "", "findings": []}


# ─── CLI ─────────────────────────────────────────────────────

def cmd_run(args):
    """CLI entry: run harness on a file."""
    # Stage 1 plan critique (2026-04-25): Codex-only, structural axis, 1 loop.
    # Translates to build gate downstream so existing evaluators don't need a
    # new --gate value. Anti-pattern catches: hardcode drift, platform quirks,
    # cross-source-of-truth divergence.
    if getattr(args, "gate", None) == "plan":
        args.gate = "build"
        args.no_gemini = True
        args.no_meta_judge = True
        if args.max_loops > 1:
            args.max_loops = 1

    evaluators = []
    if not args.no_codex:
        evaluators.append("codex")
    if not args.no_gemini:
        evaluators.append("gemini")

    if not evaluators:
        print("ERROR: at least one evaluator required", file=sys.stderr)
        sys.exit(1)

    # Codex Loop 1 fix: validate --file exists before launching subprocesses
    draft_path = Path(args.file)
    if not draft_path.exists():
        print(f"ERROR: draft file not found: {draft_path}", file=sys.stderr)
        sys.exit(1)

    meta_judge_enabled = not getattr(args, "no_meta_judge", False)
    h = Harness(evaluators=evaluators, meta_judge_enabled=meta_judge_enabled)
    result = h.run(
        task_type=args.type,
        draft=draft_path,
        context=None,
        max_loops=args.max_loops,
        domain=args.domain,
        gate=getattr(args, "gate", "build") or "build",
    )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_result_summary(result)

    # Exit code = status
    if result["status"] == "FAIL":
        sys.exit(2)


def cmd_status(args):
    """List recent harness sessions."""
    sessions = sorted(TMP_DIR.glob("*"), reverse=True)[:10]
    if not sessions:
        print("No harness sessions found.")
        return
    for s in sessions:
        if s.is_dir():
            result_file = s / "harness_result.json"
            if result_file.exists():
                try:
                    r = json.loads(result_file.read_text(encoding="utf-8"))
                    print(f"{s.name:20} {r.get('status', '?'):6} "
                          f"{r.get('task_type', '?'):10} "
                          f"loops={r.get('loops_used', '?')} "
                          f"domain={r.get('domain', '?')}")
                except Exception:
                    print(f"{s.name:20} (unreadable)")
            else:
                print(f"{s.name:20} (no result)")


def _print_result_summary(result: dict):
    print("=" * 60)
    print(f"HARNESS RESULT: {result['status']}")
    print(f"Task: {result['task_type']} | Domain: {result['domain']}")
    print(f"Evaluators: {', '.join(result['evaluators_used'])}")
    print(f"Loops used: {result['loops_used']}")
    print(f"Session: {result['session_dir']}")
    if result["consensus_history"]:
        last = result["consensus_history"][-1]
        print(f"Consensus: {last.get('consensus', '?')}")
        # Codex Loop 1 fix: defensive .get() to avoid KeyError on malformed consensus
        codex = last.get("codex", {}) or {}
        gemini = last.get("gemini", {}) or {}
        codex_status = codex.get("status", "?")
        gemini_status = gemini.get("status", "?")
        codex_summary = (codex.get("summary") or "")[:80]
        gemini_summary = (gemini.get("summary") or "")[:80]
        print(f"Codex:  {codex_status:6} — {codex_summary}")
        print(f"Gemini: {gemini_status:6} — {gemini_summary}")
    if result["feedback"]:
        print("-" * 60)
        print("Feedback:")
        print(result["feedback"][:1500])
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Harness — 3-LLM Generator-Evaluator orchestrator"
    )
    sub = parser.add_subparsers(dest="command")

    # run (default)
    p_run = sub.add_parser("run", help="Run harness on a file")
    p_run.add_argument("--type", default="code",
                       help="Task type: dm, code, workflow, report, ppc, ...")
    p_run.add_argument("--file", required=True, help="Path to draft/artifact file")
    p_run.add_argument("--domain", choices=["general", "cfo", "pipeliner"],
                       help="Override domain (auto-mapped from type otherwise)")
    p_run.add_argument("--gate", choices=["build", "test", "plan"], default="build",
                       help="build=source code audit, test=execution-result audit, "
                            "plan=PRE-build plan critique (Codex only, 1 loop). default: build")
    p_run.add_argument("--max-loops", type=int, default=2,
                       help="Max revision loops (default 2 — Codex rule)")
    p_run.add_argument("--no-codex", action="store_true", help="Skip Codex evaluator")
    p_run.add_argument("--no-gemini", action="store_true", help="Skip Gemini evaluator")
    p_run.add_argument("--no-meta-judge", action="store_true",
                       help="Skip Claude meta-judge when evaluators disagree (cost saver)")
    p_run.add_argument("--json", dest="json_output", action="store_true")
    p_run.set_defaults(func=cmd_run)

    # status
    p_status = sub.add_parser("status", help="List recent harness sessions")
    p_status.set_defaults(func=cmd_status)

    # Support legacy flat CLI (no subcommand) — route to "run"
    parser.add_argument("--type", help=argparse.SUPPRESS)
    parser.add_argument("--file", help=argparse.SUPPRESS)
    parser.add_argument("--status", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--domain", choices=["general", "cfo", "pipeliner"],
                        help=argparse.SUPPRESS)
    parser.add_argument("--gate", choices=["build", "test", "plan"], default="build",
                        help=argparse.SUPPRESS)
    parser.add_argument("--max-loops", type=int, default=2, help=argparse.SUPPRESS)
    parser.add_argument("--no-codex", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-gemini", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-meta-judge", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.command is None:
        if args.status:
            cmd_status(args)
        elif args.file:
            args.type = args.type or "code"
            cmd_run(args)
        else:
            parser.print_help()
            sys.exit(1)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
