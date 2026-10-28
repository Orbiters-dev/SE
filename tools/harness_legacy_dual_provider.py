#!/usr/bin/env python3
"""
Harness — Builder ↔ Auditor 2-Loop Orchestrator (Multi-Provider)

Supports three auditor modes:
  openai  — OpenAI GPT-4o only (default, backward compatible)
  gemini  — Google Gemini only
  dual    — Adversarial audit: both providers audit independently,
            BOTH must pass for final PASS. Stricter = safer.

Usage:
    # Python
    from harness import Harness
    h = Harness(auditor="dual")           # adversarial mode
    result = h.run("dm", draft, context={"influencer": "みき様"})

    # CLI
    PYTHONIOENCODING=utf-8 python tools/harness.py --type dm --file draft.txt
    PYTHONIOENCODING=utf-8 python tools/harness.py --type dm --file draft.txt --auditor dual
    PYTHONIOENCODING=utf-8 python tools/harness.py --type code --file tools/new_script.py --auditor gemini
    PYTHONIOENCODING=utf-8 python tools/harness.py --status
    PYTHONIOENCODING=utf-8 python tools/harness.py --test
    PYTHONIOENCODING=utf-8 python tools/harness.py --test --auditor dual
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from codex_auditor import CodexAuditor, AUDIT_RULES
from gemini_auditor import GeminiAuditor


# ── Auditor factory ──────────────────────────────────────────

def create_auditor(provider: str = "openai", openai_model: str = "gpt-4o",
                   gemini_model: str = "gemini-2.5-flash"):
    """Create auditor instance by provider name."""
    if provider == "openai":
        return CodexAuditor(model=openai_model)
    elif provider == "gemini":
        return GeminiAuditor(model=gemini_model)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use openai/gemini.")


# ── Harness main class ──────────────────────────────────────

class Harness:
    """Builder ↔ Auditor 2-Loop Orchestrator with multi-provider support"""

    def __init__(self, auditor: str = "openai", max_loops: int = 2,
                 openai_model: str = "gpt-4o",
                 gemini_model: str = "gemini-2.5-flash"):
        """
        Args:
            auditor: "openai", "gemini", or "dual" (adversarial)
            max_loops: max audit loop iterations per provider
            openai_model: OpenAI model name
            gemini_model: Gemini model name
        """
        self.auditor_mode = auditor
        self.max_loops = max_loops
        self.openai_model = openai_model
        self.gemini_model = gemini_model

        if auditor == "dual":
            self.auditors = {
                "openai": create_auditor("openai", openai_model),
                "gemini": create_auditor("gemini", gemini_model=gemini_model),
            }
        else:
            self.auditors = {
                auditor: create_auditor(auditor, openai_model, gemini_model)
            }

        self.results_dir = Path(__file__).parent.parent / ".tmp" / "harness_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def run(self, task_type: str, content: str, context: dict = None,
            extra_rules: str = None, builder_fix_fn=None) -> dict:
        """
        Run harness. In dual mode, both auditors evaluate independently.

        Returns:
            dict with final_pass, final_score, loops (per provider), etc.
        """
        start_time = datetime.now()

        if self.auditor_mode == "dual":
            result = self._run_dual(task_type, content, context,
                                    extra_rules, builder_fix_fn)
        else:
            provider_name = self.auditor_mode
            auditor = self.auditors[provider_name]
            loop_result = auditor.audit_loop(
                task_type=task_type,
                content=content,
                context=context,
                extra_rules=extra_rules,
                max_loops=self.max_loops,
                builder_fix_fn=builder_fix_fn,
            )
            result = {
                "mode": "single",
                "provider": provider_name,
                "final_content": loop_result["final_content"],
                "final_pass": loop_result["final_pass"],
                "final_score": loop_result["final_score"],
                "loops": loop_result["loops"],
            }

        # Enrich result
        result["task_type"] = task_type
        result["task_name"] = AUDIT_RULES.get(task_type, {}).get("name", task_type)
        result["started_at"] = start_time.isoformat()
        result["finished_at"] = datetime.now().isoformat()
        result["duration_sec"] = (datetime.now() - start_time).total_seconds()
        result["auditor_mode"] = self.auditor_mode

        self._save_result(task_type, result)
        return result

    def _run_dual(self, task_type, content, context, extra_rules, builder_fix_fn):
        """
        Adversarial dual audit:
        1. OpenAI audits (2-loop) -> may produce improved content
        2. Gemini audits the IMPROVED content from OpenAI (2-loop)
        3. Final pass = BOTH must pass

        This catches blind spots: if OpenAI misses a violation,
        Gemini may catch it (and vice versa).
        """
        # Phase 1: OpenAI audit loop
        openai_auditor = self.auditors["openai"]
        openai_result = openai_auditor.audit_loop(
            task_type=task_type,
            content=content,
            context=context,
            extra_rules=extra_rules,
            max_loops=self.max_loops,
            builder_fix_fn=builder_fix_fn,
        )

        # Use OpenAI-improved content for Gemini's review
        content_for_gemini = openai_result["final_content"]

        # Phase 2: Gemini audit loop on the (possibly improved) content
        gemini_auditor = self.auditors["gemini"]
        gemini_result = gemini_auditor.audit_loop(
            task_type=task_type,
            content=content_for_gemini,
            context=context,
            extra_rules=extra_rules,
            max_loops=self.max_loops,
            builder_fix_fn=builder_fix_fn,
        )

        # Merge: BOTH must pass
        both_pass = openai_result["final_pass"] and gemini_result["final_pass"]
        avg_score = (openai_result["final_score"] + gemini_result["final_score"]) // 2
        min_score = min(openai_result["final_score"], gemini_result["final_score"])

        # Collect all unique violations from both providers
        all_violations = []
        seen = set()
        for provider_result in [openai_result, gemini_result]:
            for loop in provider_result.get("loops", []):
                for v in loop["result"].get("violations", []):
                    key = (v.get("rule", ""), v.get("location", v.get("line", v.get("node", ""))))
                    if key not in seen:
                        seen.add(key)
                        all_violations.append(v)

        return {
            "mode": "dual",
            "provider": "openai+gemini",
            "final_content": gemini_result["final_content"],
            "final_pass": both_pass,
            "final_score": min_score,  # conservative: use the lower score
            "avg_score": avg_score,
            "openai": {
                "pass": openai_result["final_pass"],
                "score": openai_result["final_score"],
                "loops": openai_result["loops"],
            },
            "gemini": {
                "pass": gemini_result["final_pass"],
                "score": gemini_result["final_score"],
                "loops": gemini_result["loops"],
            },
            "all_violations": all_violations,
        }

    def quick_check(self, task_type: str, content: str,
                    context: dict = None) -> dict:
        """Single-pass check (no loop). Uses first available auditor."""
        auditor = list(self.auditors.values())[0]
        return auditor.audit(task_type, content, context)

    def get_status(self) -> dict:
        """Recent harness run status."""
        results = sorted(self.results_dir.glob("*.json"), reverse=True)
        recent = []
        for f in results[:10]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                recent.append({
                    "file": f.name,
                    "task": data.get("task_name", "?"),
                    "mode": data.get("auditor_mode", "?"),
                    "pass": data.get("final_pass", False),
                    "score": data.get("final_score", 0),
                    "time": data.get("finished_at", "?"),
                    "duration": f"{data.get('duration_sec', 0):.1f}s"
                })
            except Exception:
                continue

        total = len(list(self.results_dir.glob("*.json")))
        pass_count = sum(1 for r in recent if r["pass"])

        return {
            "total_runs": total,
            "recent_10": recent,
            "recent_pass_rate": f"{pass_count}/{len(recent)}",
            "log_dir": str(self.results_dir)
        }

    def _save_result(self, task_type: str, result: dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode_tag = result.get("auditor_mode", "unknown")
        result_file = self.results_dir / f"harness_{task_type}_{mode_tag}_{timestamp}.json"

        save_data = result.copy()

        # Truncate long content in loops to save space
        for key in ["openai", "gemini"]:
            if key in save_data and "loops" in save_data[key]:
                for loop in save_data[key]["loops"]:
                    cb = loop.get("content_before", "")
                    if len(cb) > 2000:
                        loop["content_before"] = cb[:2000] + "... (truncated)"

        if "loops" in save_data:
            for loop in save_data["loops"]:
                cb = loop.get("content_before", "")
                if len(cb) > 2000:
                    loop["content_before"] = cb[:2000] + "... (truncated)"

        fc = save_data.get("final_content", "")
        if len(fc) > 5000:
            save_data["final_content_preview"] = fc[:5000] + "... (truncated)"
            del save_data["final_content"]

        result_file.write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


# ── Convenience functions (for Claude Code direct calls) ────

def audit_dm(draft: str, influencer_context: dict = None,
             auditor: str = "dual") -> dict:
    """DM audit (2-loop). Default: dual (adversarial)."""
    h = Harness(auditor=auditor)
    return h.run("dm", draft, context=influencer_context)


def audit_code(code: str, filename: str = None,
               auditor: str = "openai") -> dict:
    """Python code audit (2-loop)."""
    h = Harness(auditor=auditor)
    ctx = {"filename": filename} if filename else None
    return h.run("code", code, context=ctx)


def audit_workflow(workflow_json: str, env: str = "PROD",
                   auditor: str = "openai") -> dict:
    """n8n workflow audit (2-loop)."""
    h = Harness(auditor=auditor)
    return h.run("workflow", workflow_json, context={"environment": env})


def audit_report(report_data: str, report_type: str = "KPI",
                 auditor: str = "dual") -> dict:
    """Report data audit (2-loop). Default: dual."""
    h = Harness(auditor=auditor)
    return h.run("report", report_data, context={"report_type": report_type})


def audit_ig_plan(plan_text: str, week: str = None,
                  auditor: str = "openai") -> dict:
    """Instagram plan audit (2-loop)."""
    h = Harness(auditor=auditor)
    ctx = {"week": week} if week else None
    return h.run("ig_plan", plan_text, context=ctx)


def audit_ppc(execution_payload: str, auditor: str = "dual") -> dict:
    """Amazon PPC execution audit (2-loop). Default: dual."""
    h = Harness(auditor=auditor)
    return h.run("ppc", execution_payload)


# ── CLI ──────────────────────────────────────────────────────

def format_report(result: dict) -> str:
    """Terminal report formatter."""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  HARNESS REPORT — {result.get('task_name', '?')}")
    lines.append(f"{'='*60}")
    lines.append(f"  Mode     : {result.get('auditor_mode', '?')}")
    lines.append(f"  Duration : {result.get('duration_sec', 0):.1f}s")
    lines.append(f"  Final    : {'PASS' if result.get('final_pass') else 'FAIL'}")
    lines.append(f"  Score    : {result.get('final_score', 0)}/100")

    if result.get("mode") == "dual":
        lines.append(f"{'─'*60}")
        lines.append(f"  [OpenAI] {'PASS' if result['openai']['pass'] else 'FAIL'} "
                     f"(Score: {result['openai']['score']})")
        lines.append(f"  [Gemini] {'PASS' if result['gemini']['pass'] else 'FAIL'} "
                     f"(Score: {result['gemini']['score']})")

        # OpenAI loops
        for loop in result["openai"].get("loops", []):
            r = loop["result"]
            violations = r.get("violations", [])
            status = "PASS" if r.get("pass") else "FAIL"
            lines.append(f"\n  OpenAI Loop {loop['loop']}: {status} "
                         f"(Score: {r.get('score', '?')}, "
                         f"Violations: {len(violations)})")
            for v in violations[:5]:
                loc = v.get("location", v.get("line", v.get("node",
                      v.get("item", v.get("campaign", "?")))))
                lines.append(f"    [{v.get('rule', '?')}] {loc}")
                lines.append(f"      -> {v.get('fix', '')}")

        # Gemini loops
        for loop in result["gemini"].get("loops", []):
            r = loop["result"]
            violations = r.get("violations", [])
            status = "PASS" if r.get("pass") else "FAIL"
            lines.append(f"\n  Gemini Loop {loop['loop']}: {status} "
                         f"(Score: {r.get('score', '?')}, "
                         f"Violations: {len(violations)})")
            for v in violations[:5]:
                loc = v.get("location", v.get("line", v.get("node",
                      v.get("item", v.get("campaign", "?")))))
                lines.append(f"    [{v.get('rule', '?')}] {loc}")
                lines.append(f"      -> {v.get('fix', '')}")

        # Cross-provider unique violations
        if result.get("all_violations"):
            lines.append(f"\n{'─'*60}")
            lines.append(f"  Unique violations (cross-provider): "
                         f"{len(result['all_violations'])}")
            for v in result["all_violations"][:10]:
                loc = v.get("location", v.get("line", v.get("node", "?")))
                lines.append(f"    [{v.get('rule', '?')}] {loc}: {v.get('fix', '')}")

    else:
        # Single-provider mode
        lines.append(f"  Provider : {result.get('provider', '?')}")
        lines.append(f"{'─'*60}")

        for loop in result.get("loops", []):
            r = loop["result"]
            violations = r.get("violations", [])
            status = "PASS" if r.get("pass") else "FAIL"
            lines.append(f"\n  Loop {loop['loop']}: {status} "
                         f"(Score: {r.get('score', '?')}, "
                         f"Violations: {len(violations)})")
            for v in violations[:5]:
                loc = v.get("location", v.get("line", v.get("node",
                      v.get("item", v.get("campaign", "?")))))
                lines.append(f"    [{v.get('rule', '?')}] {loc}")
                lines.append(f"      -> {v.get('fix', '')}")

            for key in ["tone_check", "structure_check", "security_check",
                         "data_integrity", "seasonality_check", "summary"]:
                if key in r:
                    lines.append(f"    {key}: {r[key]}")

    lines.append(f"\n{'='*60}")

    if not result.get("final_pass") and result.get("final_content"):
        lines.append("\n--- IMPROVED VERSION ---")
        content = result["final_content"]
        if len(content) > 2000:
            content = content[:2000] + "\n... (truncated)"
        lines.append(content)

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Harness — Builder↔Auditor 2-Loop Orchestrator (Multi-Provider)")
    parser.add_argument("--type", "-t", default="general",
                       choices=list(AUDIT_RULES.keys()),
                       help="Audit type")
    parser.add_argument("--file", "-f", help="File to audit")
    parser.add_argument("--text", help="Text to audit")
    parser.add_argument("--context", "-c", help="Context JSON file")
    parser.add_argument("--auditor", "-a", default="openai",
                       choices=["openai", "gemini", "dual"],
                       help="Auditor mode (default: openai)")
    parser.add_argument("--openai-model", default="gpt-4o",
                       help="OpenAI model (default: gpt-4o)")
    parser.add_argument("--gemini-model", default="gemini-2.5-flash",
                       help="Gemini model (default: gemini-2.5-flash)")
    parser.add_argument("--no-loop", action="store_true",
                       help="Single check, no loop")
    parser.add_argument("--status", action="store_true", help="Show run status")
    parser.add_argument("--test", action="store_true", help="API connection test")
    args = parser.parse_args()

    if args.status:
        h = Harness()
        status = h.get_status()
        print(f"\nHarness Status")
        print(f"{'─'*40}")
        print(f"Total runs: {status['total_runs']}")
        print(f"Recent pass rate: {status['recent_pass_rate']}")
        print(f"\nRecent 10:")
        for r in status["recent_10"]:
            icon = "PASS" if r["pass"] else "FAIL"
            print(f"  [{icon}] {r['task']} ({r['mode']}) — "
                  f"Score: {r['score']}, {r['duration']}")
        return

    if args.test:
        print("Harness API Connection Test")
        print("─" * 40)

        providers = (["openai", "gemini"] if args.auditor == "dual"
                     else [args.auditor])

        for p in providers:
            try:
                auditor = create_auditor(p, args.openai_model, args.gemini_model)
                result = auditor.audit("general", "print('hello world')")
                score = result.get("score", "?")
                model = result.get("_model", "?")
                print(f"  [{p.upper()}] OK — Model: {model}, Score: {score}")
            except Exception as e:
                print(f"  [{p.upper()}] FAIL — {e}")
        return

    # Load content
    content = ""
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        content = args.text
    else:
        print("Error: --file or --text required")
        sys.exit(1)

    # Load context
    context = None
    if args.context:
        context = json.loads(Path(args.context).read_text(encoding="utf-8"))

    h = Harness(
        auditor=args.auditor,
        openai_model=args.openai_model,
        gemini_model=args.gemini_model,
    )

    if args.no_loop:
        result = h.quick_check(args.type, content, context)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = h.run(args.type, content, context)
        print(format_report(result))


if __name__ == "__main__":
    main()
