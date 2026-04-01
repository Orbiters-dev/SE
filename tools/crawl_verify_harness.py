#!/usr/bin/env python3
"""
Crawl Verify Harness — Dual-AI 데이터 검증 하네스
==================================================
Claude Code (Maker/1차 검증) → apify_crawl_auditor.py
Codex o4-mini (독립 2차 검증) → codex_auditor.py --domain crawl

Architecture:
  Claude Code (Orchestrator + Executor)
      │
      ├─→ Round N: apify_crawl_auditor.py → claude_audit.json
      │
      ├─→ Round N: codex_auditor.py --domain crawl → codex_verdict.json
      │
      ├─→ Reconcile: Claude vs Codex 비교
      │       ├─→ 양쪽 PASS → OK (exit)
      │       ├─→ 불일치 → 재검토 (next round)
      │       └─→ 양쪽 FAIL → 수정 시도 후 재검토
      │
      └─→ Max 3 rounds, then escalate to human

Usage:
  # Full dual verification (3-round max)
  python tools/crawl_verify_harness.py

  # Specific region
  python tools/crawl_verify_harness.py --region us

  # Dry run (show what would run, no execution)
  python tools/crawl_verify_harness.py --dry-run

  # Show last session results
  python tools/crawl_verify_harness.py --results

  # Single round (no loop)
  python tools/crawl_verify_harness.py --single
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ─── Paths ──────────────────────────────────────────────────────────────────
DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
PYTHON = r"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe"
SESSION_DIR = ROOT / ".tmp" / "crawl_verify"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

AUDITOR_SCRIPT = DIR / "apify_crawl_auditor.py"
CODEX_SCRIPT = DIR / "codex_auditor.py"

MAX_ROUNDS = 3


# ═════════════════════════════════════════════════════════════════════════════
# 1차 검증: Claude (apify_crawl_auditor.py)
# ═════════════════════════════════════════════════════════════════════════════

def run_claude_audit(region="all", round_num=1, session_dir=None):
    """Run apify_crawl_auditor.py and capture JSON report."""
    print(f"\n{'━' * 60}")
    print(f"  [Round {round_num}] 1차 검증: Claude (apify_crawl_auditor.py)")
    print(f"{'━' * 60}")

    cmd = [
        PYTHON, str(AUDITOR_SCRIPT),
        "--harness", "--json",
        "--region", region,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=300, cwd=str(ROOT),
        )

        # Parse JSON from stdout (--json flag outputs JSON after pretty print)
        report = _extract_json(result.stdout)
        if not report:
            print(f"  ✗ Failed to parse Claude audit output")
            if result.stderr:
                print(f"  stderr: {result.stderr[:300]}")
            report = _error_report("claude", "parse_error", result.stdout[:500])

        # Save to session
        if session_dir:
            out = session_dir / f"claude_audit_r{round_num}.json"
            out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  → Saved: {out.name}")

        _print_health("Claude", report)
        return report

    except subprocess.TimeoutExpired:
        print("  ✗ Claude audit timed out (300s)")
        return _error_report("claude", "timeout", "300s exceeded")
    except Exception as e:
        print(f"  ✗ Claude audit error: {e}")
        return _error_report("claude", "exception", str(e))


# ═════════════════════════════════════════════════════════════════════════════
# 2차 검증: Codex o4-mini (codex_auditor.py --domain crawl)
# ═════════════════════════════════════════════════════════════════════════════

def run_codex_audit(region="all", round_num=1, session_dir=None,
                    claude_report=None):
    """Run codex_auditor.py --domain crawl and capture verdict."""
    print(f"\n{'━' * 60}")
    print(f"  [Round {round_num}] 2차 검증: Codex o4-mini (독립 검증)")
    print(f"{'━' * 60}")

    cmd = [
        PYTHON, str(CODEX_SCRIPT),
        "--domain", "crawl",
        "--audit",
        "--json-only",
        "--round", str(round_num),
    ]
    if region and region != "all":
        cmd.extend(["--region", region])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=360, cwd=str(ROOT),
        )

        verdict = _extract_json(result.stdout)
        if not verdict:
            print(f"  ✗ Failed to parse Codex verdict")
            if result.stderr:
                print(f"  stderr: {result.stderr[:300]}")
            verdict = _error_verdict("codex", "parse_error", result.stdout[:500])

        # Save to session
        if session_dir:
            out = session_dir / f"codex_verdict_r{round_num}.json"
            out.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  → Saved: {out.name}")

        _print_verdict("Codex", verdict)
        return verdict

    except subprocess.TimeoutExpired:
        print("  ✗ Codex audit timed out (360s)")
        return _error_verdict("codex", "timeout", "360s exceeded")
    except Exception as e:
        print(f"  ✗ Codex audit error: {e}")
        return _error_verdict("codex", "exception", str(e))


# ═════════════════════════════════════════════════════════════════════════════
# Reconciliation: Claude vs Codex 비교
# ═════════════════════════════════════════════════════════════════════════════

def reconcile(claude_report, codex_verdict, round_num=1):
    """
    Compare Claude audit and Codex verdict.
    Returns: (action, details)
      action: "OK" | "RETRY" | "ESCALATE"
    """
    print(f"\n{'━' * 60}")
    print(f"  [Round {round_num}] Reconciliation: Claude vs Codex")
    print(f"{'━' * 60}")

    claude_health = claude_report.get("health", "ERROR")
    codex_verdict_str = codex_verdict.get("verdict", "ERROR")

    # Normalize to common scale
    claude_norm = _normalize_health(claude_health)
    codex_norm = _normalize_verdict(codex_verdict_str)

    print(f"  Claude: {claude_health} → {claude_norm}")
    print(f"  Codex:  {codex_verdict_str} → {codex_norm}")

    # ── Decision matrix ──
    # Both PASS → OK
    if claude_norm == "PASS" and codex_norm == "PASS":
        print(f"\n  ✓ 양쪽 PASS — 검증 완료")
        return "OK", _build_reconciliation(claude_report, codex_verdict, "MATCH_PASS", round_num)

    # Both FAIL → need fix, retry
    if claude_norm == "FAIL" and codex_norm == "FAIL":
        # Check if they agree on WHAT failed
        overlap = _find_overlapping_failures(claude_report, codex_verdict)
        print(f"\n  ✗ 양쪽 FAIL — 공통 실패 {len(overlap)}건")
        if overlap:
            for o in overlap[:5]:
                print(f"    • {o}")
        return "RETRY", _build_reconciliation(claude_report, codex_verdict, "MATCH_FAIL", round_num, overlap)

    # One PASS, one FAIL → disagreement, retry with focus
    if claude_norm != codex_norm:
        disagreements = _find_disagreements(claude_report, codex_verdict)
        print(f"\n  ⚠ 불일치 — Claude={claude_norm}, Codex={codex_norm}")
        print(f"    불일치 포인트 {len(disagreements)}건:")
        for d in disagreements[:5]:
            print(f"    • {d}")
        return "RETRY", _build_reconciliation(claude_report, codex_verdict, "DISAGREE", round_num, disagreements)

    # Both WARN → acceptable
    if claude_norm == "WARN" and codex_norm == "WARN":
        print(f"\n  △ 양쪽 WARN — 경미한 이슈만 있음, 통과 처리")
        return "OK", _build_reconciliation(claude_report, codex_verdict, "MATCH_WARN", round_num)

    # ERROR cases
    print(f"\n  ✗ 에러 상태 감지")
    return "RETRY", _build_reconciliation(claude_report, codex_verdict, "ERROR", round_num)


def _normalize_health(health):
    """Claude auditor health → PASS/WARN/FAIL."""
    return {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}.get(health, "ERROR")


def _normalize_verdict(verdict):
    """Codex verdict → PASS/WARN/FAIL."""
    return {
        "PASS": "PASS",
        "DEGRADED": "WARN",
        "WARN": "WARN",
        "FAIL": "FAIL",
    }.get(verdict, "ERROR")


def _find_overlapping_failures(claude_report, codex_verdict):
    """Find failure themes that both sides flagged."""
    claude_issues = set()
    for f in claude_report.get("findings", []):
        if f.get("severity") in ("CRITICAL", "MAJOR"):
            claude_issues.add(f.get("category", "").lower())

    codex_issues = set()
    for f in codex_verdict.get("failures", []):
        check = f.get("check", "").lower()
        codex_issues.add(check)

    # Fuzzy match: category overlap
    overlap = []
    claude_descs = [f["description"] for f in claude_report.get("findings", [])
                    if f.get("severity") in ("CRITICAL", "MAJOR")]
    codex_descs = [f"{f.get('check', '')}: {f.get('actual', '')}"
                   for f in codex_verdict.get("failures", [])]

    for cd in claude_descs[:10]:
        overlap.append(f"[Claude] {cd}")
    for cx in codex_descs[:10]:
        overlap.append(f"[Codex]  {cx}")

    return overlap


def _find_disagreements(claude_report, codex_verdict):
    """Identify where Claude and Codex disagree."""
    items = []

    claude_health = claude_report.get("health", "?")
    codex_v = codex_verdict.get("verdict", "?")
    items.append(f"Overall: Claude={claude_health}, Codex={codex_v}")

    # Claude says FAIL but Codex says PASS → Claude found issues Codex missed
    if _normalize_health(claude_health) == "FAIL" and _normalize_verdict(codex_v) == "PASS":
        for f in claude_report.get("findings", []):
            if f.get("severity") in ("CRITICAL", "MAJOR"):
                items.append(f"[Claude only] {f['category']}: {f['description']}")

    # Codex says FAIL but Claude says PASS → Codex found issues Claude missed
    if _normalize_verdict(codex_v) == "FAIL" and _normalize_health(claude_health) == "PASS":
        for f in codex_verdict.get("failures", []):
            items.append(f"[Codex only] {f.get('check', '?')}: expected={f.get('expected', '?')}, actual={f.get('actual', '?')}")

    return items


def _build_reconciliation(claude_report, codex_verdict, match_type, round_num, details=None):
    """Build reconciliation record."""
    return {
        "round": round_num,
        "timestamp": datetime.now().isoformat(),
        "match_type": match_type,
        "claude_health": claude_report.get("health", "ERROR"),
        "codex_verdict": codex_verdict.get("verdict", "ERROR"),
        "claude_summary": claude_report.get("summary", {}),
        "codex_checks": f"{codex_verdict.get('checks_passed', '?')}/{codex_verdict.get('checks_total', '?')}",
        "details": details or [],
    }


# ═════════════════════════════════════════════════════════════════════════════
# Main Loop: 3-Round Dual Verification
# ═════════════════════════════════════════════════════════════════════════════

def run_harness(region="all", max_rounds=MAX_ROUNDS, dry_run=False, single=False):
    """Orchestrate the dual-AI verification loop."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = SESSION_DIR / ts
    session_dir.mkdir(parents=True, exist_ok=True)

    effective_rounds = 1 if single else max_rounds

    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Crawl Verify Harness — Dual-AI 데이터 검증              ║")
    print(f"║  Claude (1차) + Codex o4-mini (2차) | Max {effective_rounds} rounds       ║")
    print(f"║  Region: {region.upper():>3}  |  Session: {ts}          ║")
    print("╚══════════════════════════════════════════════════════════╝")

    if dry_run:
        print("\n[DRY RUN] Would execute:")
        print(f"  1차: {PYTHON} {AUDITOR_SCRIPT} --harness --json --region {region}")
        print(f"  2차: {PYTHON} {CODEX_SCRIPT} --domain crawl --audit --json-only")
        print(f"  Rounds: up to {effective_rounds}")
        return None

    session_log = {
        "session_id": ts,
        "region": region,
        "max_rounds": effective_rounds,
        "rounds": [],
        "final_status": None,
    }

    for round_num in range(1, effective_rounds + 1):
        print(f"\n{'═' * 60}")
        print(f"  ◆ ROUND {round_num}/{effective_rounds}")
        print(f"{'═' * 60}")

        # Step 1: Claude 1차 검증
        claude_report = run_claude_audit(
            region=region, round_num=round_num, session_dir=session_dir,
        )

        # Step 2: Codex 2차 독립 검증
        codex_verdict = run_codex_audit(
            region=region, round_num=round_num, session_dir=session_dir,
            claude_report=claude_report,
        )

        # Step 3: Reconcile
        action, recon = reconcile(claude_report, codex_verdict, round_num)
        session_log["rounds"].append(recon)

        # Save round reconciliation
        recon_path = session_dir / f"reconciliation_r{round_num}.json"
        recon_path.write_text(json.dumps(recon, indent=2, ensure_ascii=False), encoding="utf-8")

        if action == "OK":
            session_log["final_status"] = "VERIFIED"
            _print_final("VERIFIED", round_num, effective_rounds, session_dir)
            break

        elif action == "RETRY" and round_num < effective_rounds:
            wait = round_num * 10
            print(f"\n  ↻ 불일치 감지 — {wait}s 후 Round {round_num + 1} 재검토...")
            time.sleep(wait)

        elif action == "RETRY" and round_num == effective_rounds:
            session_log["final_status"] = "ESCALATE"
            _print_final("ESCALATE", round_num, effective_rounds, session_dir)

        else:
            session_log["final_status"] = "ERROR"
            _print_final("ERROR", round_num, effective_rounds, session_dir)
            break

    # Save session log
    log_path = session_dir / "session_log.json"
    log_path.write_text(json.dumps(session_log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Session log: {log_path}")

    return session_log


def show_results():
    """Show the most recent session results."""
    if not SESSION_DIR.exists():
        print("No sessions found.")
        return

    sessions = sorted(SESSION_DIR.iterdir(), reverse=True)
    if not sessions:
        print("No sessions found.")
        return

    latest = sessions[0]
    log_path = latest / "session_log.json"
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
        print(f"\n{'═' * 60}")
        print(f"  Latest Session: {log.get('session_id', '?')}")
        print(f"  Region: {log.get('region', '?')}")
        print(f"  Status: {log.get('final_status', '?')}")
        print(f"  Rounds: {len(log.get('rounds', []))}/{log.get('max_rounds', '?')}")
        print(f"{'═' * 60}")

        for r in log.get("rounds", []):
            rn = r.get("round", "?")
            mt = r.get("match_type", "?")
            ch = r.get("claude_health", "?")
            cv = r.get("codex_verdict", "?")
            print(f"\n  Round {rn}: {mt}")
            print(f"    Claude: {ch} | Codex: {cv}")
            for d in r.get("details", [])[:5]:
                print(f"    • {d}")

        print(f"\n  Session dir: {latest}")
    else:
        print(f"  Session dir exists but no log: {latest}")


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _extract_json(text):
    """Extract first JSON object from text."""
    if not text:
        return None
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def _error_report(source, check, detail):
    return {
        "health": "ERROR",
        "summary": {"critical": 1, "major": 0, "minor": 0, "info": 0, "total": 1},
        "findings": [{"severity": "CRITICAL", "category": "SYSTEM",
                       "description": f"{source} {check}: {detail}"}],
    }


def _error_verdict(source, check, detail):
    return {
        "verdict": "ERROR",
        "domain": "crawl",
        "round": 0,
        "checks_passed": 0,
        "checks_total": 0,
        "failures": [{"check": check, "expected": "success", "actual": detail, "severity": "CRITICAL"}],
        "warnings": [],
        "notes": f"{source} error: {detail}",
    }


def _print_health(source, report):
    h = report.get("health", "?")
    s = report.get("summary", {})
    icon = {"PASS": "✓", "WARN": "△", "FAIL": "✗"}.get(h, "?")
    print(f"  {icon} {source}: {h} (C:{s.get('critical',0)} M:{s.get('major',0)} m:{s.get('minor',0)} i:{s.get('info',0)})")


def _print_verdict(source, verdict):
    v = verdict.get("verdict", "?")
    passed = verdict.get("checks_passed", "?")
    total = verdict.get("checks_total", "?")
    icon = {"PASS": "✓", "DEGRADED": "△", "WARN": "△", "FAIL": "✗"}.get(v, "?")
    print(f"  {icon} {source}: {v} ({passed}/{total} checks passed)")
    for f in verdict.get("failures", [])[:3]:
        print(f"    [{f.get('severity','?')}] {f.get('check','?')}: {f.get('actual','?')}")


def _print_final(status, round_num, max_rounds, session_dir):
    icons = {
        "VERIFIED": ("✓", "양쪽 AI 검증 통과"),
        "ESCALATE": ("⚠", f"{max_rounds}라운드 후에도 불일치 — 사람 확인 필요"),
        "ERROR": ("✗", "시스템 에러 발생"),
    }
    icon, msg = icons.get(status, ("?", "Unknown"))

    print(f"\n{'═' * 60}")
    print(f"  {icon} FINAL: {status}")
    print(f"  {msg}")
    print(f"  Rounds: {round_num}/{max_rounds}")
    print(f"  Session: {session_dir}")
    print(f"{'═' * 60}")


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Crawl Verify Harness — Dual-AI 데이터 검증",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Architecture:
  Claude Code (1차) → apify_crawl_auditor.py → claude_audit.json
  Codex o4-mini (2차) → codex_auditor.py → codex_verdict.json
  Reconcile → 양쪽 PASS=OK / 불일치=재검토 / 3라운드 후 에스컬레이션

Examples:
  %(prog)s                        # Full dual verification
  %(prog)s --region us            # US only
  %(prog)s --dry-run              # Show plan without running
  %(prog)s --results              # Show last session
  %(prog)s --single               # One round only
""")

    parser.add_argument("--region", default="all", choices=["us", "jp", "all"],
                        help="Region to audit (default: all)")
    parser.add_argument("--max-rounds", type=int, default=MAX_ROUNDS,
                        help=f"Max verification rounds (default: {MAX_ROUNDS})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without executing")
    parser.add_argument("--results", action="store_true",
                        help="Show most recent session results")
    parser.add_argument("--single", action="store_true",
                        help="Single round (no loop)")

    args = parser.parse_args()

    if args.results:
        show_results()
        return

    session = run_harness(
        region=args.region,
        max_rounds=args.max_rounds,
        dry_run=args.dry_run,
        single=args.single,
    )

    if session:
        status = session.get("final_status", "ERROR")
        sys.exit(0 if status == "VERIFIED" else 1 if status == "ESCALATE" else 2)


if __name__ == "__main__":
    main()
