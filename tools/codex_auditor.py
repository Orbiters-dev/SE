#!/usr/bin/env python3
"""
Codex Auditor — OpenAI Codex CLI 기반 독립 검증 에이전트 래퍼
=============================================================
Claude Code (Orchestrator)가 이 스크립트를 호출하면,
Codex CLI가 독립적으로 검증 스크립트를 실행하고 결과를 분석한다.

Supported Domains:
  - pipeline  : n8n Pathlight 워크플로우 감사 (flow_auditor.py)
  - finance   : 재무 데이터 감사 (CFO/감사관 6-point checklist)
  - kpi       : KPI 데이터 검증 (golmani-validator 6 layers)
  - crawl     : Apify 콘텐츠 파이프라인 감사 (apify_crawl_auditor.py)
  - datakeeper: 데이터 수집 파이프라인 freshness 검증

Architecture:
    Claude Code (Maker) ──→ codex_auditor.py ──→ Codex CLI (Verifier)
                                                      │
                                                      ├─→ domain-specific script 실행
                                                      ├─→ 결과 독립 분석
                                                      └─→ JSON verdict 반환

Usage:
    # ─── Pipeline (Flow Auditor) ───
    python tools/codex_auditor.py --domain pipeline --audit
    python tools/codex_auditor.py --domain pipeline --health
    python tools/codex_auditor.py --domain pipeline --verify-round 1 --run-id ID

    # ─── Finance (CFO/감사관) ───
    python tools/codex_auditor.py --domain finance --audit --file output.xlsx
    python tools/codex_auditor.py --domain finance --audit --audit-report audit_report.json

    # ─── KPI (검증이) ───
    python tools/codex_auditor.py --domain kpi --audit
    python tools/codex_auditor.py --domain kpi --audit --table shopify_orders_daily

    # ─── Crawl (Apify) ───
    python tools/codex_auditor.py --domain crawl --audit
    python tools/codex_auditor.py --domain crawl --audit --region us

    # ─── Data Keeper ───
    python tools/codex_auditor.py --domain datakeeper --health
    python tools/codex_auditor.py --domain datakeeper --audit --channel amazon_ads

    # ─── Custom prompt (any domain) ───
    python tools/codex_auditor.py --prompt "Amazon Ads 데이터 30일치 freshness 확인"
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ─── Paths ───────────────────────────────────────────────────────────────────
DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
TMP = ROOT / ".tmp" / "codex_audit"
TMP.mkdir(parents=True, exist_ok=True)

PYTHON = "C:/Users/wjcho/AppData/Local/Programs/Python/Python312/python.exe"
DUAL_DIR = ROOT / ".tmp" / "dual_test"

# Domain-specific tool paths
TOOLS = {
    "pipeline": {
        "script": Path("Z:/Orbiters/ORBI CLAUDE_0223/ORBITERS CLAUDE/ORBITERS CLAUDE/Shared/ONZ Creator Collab/Flow Auditor/tools/flow_auditor.py"),
        "label": "Pathlight PROD n8n Workflow Auditor",
    },
    "finance": {
        "script": ROOT / "tools" / "cfo_harness.py",
        "label": "CFO/감사관 Financial Data Auditor",
    },
    "kpi": {
        "script": ROOT / "tools" / "kpi_validator.py",
        "label": "KPI Data Validator (검증이)",
    },
    "crawl": {
        "script": ROOT / "tools" / "apify_crawl_auditor.py",
        "label": "Apify Content Pipeline Auditor",
    },
    "datakeeper": {
        "script": ROOT / "tools" / "data_keeper.py",
        "label": "Data Keeper Freshness Auditor",
    },
}

# ─── Codex exec config ──────────────────────────────────────────────────────
CODEX_BIN = os.environ.get("CODEX_BIN", "C:/Users/wjcho/AppData/Roaming/npm/codex.cmd")
CODEX_MODEL = "o4-mini"  # Verified working 2026-04-01

VERDICT_SCHEMA = """{{"verdict": "PASS|FAIL|DEGRADED", "domain": "{domain}", "round": {round}, "timestamp": "ISO8601", "checks_passed": N, "checks_total": N, "failures": [{{"check": "name", "expected": "...", "actual": "...", "severity": "CRITICAL|HIGH|MEDIUM|LOW"}}], "warnings": [], "notes": "summary"}}"""


# ═════════════════════════════════════════════════════════════════════════════
# Script Runner — executes audit scripts locally, passes output to Codex
# ═════════════════════════════════════════════════════════════════════════════

def _run_script(cmd_args, timeout=120):
    """Run an audit script locally and return (stdout, stderr, returncode)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        return result.stdout[:4000], result.stderr[:1000], result.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT after {}s".format(timeout), -1
    except FileNotFoundError as e:
        return "", f"Script not found: {e}", -2
    except Exception as e:
        return "", f"Error: {e}", -3


# Domain → mistakes.md section heading keywords
DOMAIN_MISTAKE_KEYWORDS = {
    "pipeline": ["파이프라이너", "n8n"],
    "finance": ["골만이", "Financial Dashboard", "CFO"],
    "kpi": ["KPI 리포트"],
    "crawl": ["CI 팀장", "크롤러"],
    "datakeeper": ["데이터 키퍼"],
}

MISTAKES_PATH = ROOT / "memory" / "mistakes.md"


def _load_mistakes(domain):
    """Extract Core section + domain-specific section from mistakes.md."""
    if not MISTAKES_PATH.exists():
        return ""
    try:
        text = MISTAKES_PATH.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    keywords = DOMAIN_MISTAKE_KEYWORDS.get(domain, [])
    sections = []
    lines = text.splitlines()
    capture = False
    current_section = []

    for line in lines:
        if line.startswith("## "):
            # Save previous section if it was being captured
            if capture and current_section:
                sections.append("\n".join(current_section))
            # Check if this section is relevant
            heading = line[3:]
            is_core = "Core" in heading
            is_domain = any(kw in heading for kw in keywords)
            capture = is_core or is_domain
            current_section = [line] if capture else []
        elif capture:
            current_section.append(line)

    if capture and current_section:
        sections.append("\n".join(current_section))

    # Prioritize: domain section first (up to 1500), Core section (up to 500)
    core_sections = [s for s in sections if s.startswith("## Core")]
    domain_sections = [s for s in sections if not s.startswith("## Core")]
    core_text = ("\n\n".join(core_sections))[:500]
    domain_text = ("\n\n".join(domain_sections))[:1500]
    combined = "\n\n".join(filter(None, [domain_text, core_text]))
    return combined[:2000] if combined else ""


def _analysis_prompt(domain, round_num, label, script_output, script_error, returncode, extra_context=""):
    """Build a Codex analysis prompt from pre-run script output."""
    schema = VERDICT_SCHEMA.format(domain=domain, round=round_num)
    status = "SUCCESS" if returncode == 0 else f"FAILED (exit={returncode})"
    mistakes = _load_mistakes(domain)
    mistakes_section = f"\n--- PAST MISTAKES (check if recurring) ---\n{mistakes}\n--- END MISTAKES ---" if mistakes else ""
    return f"""You are an independent verification agent (Codex Verifier).
Analyze the audit script output below and produce a JSON verdict.

Domain: {label}
Script run status: {status}
{extra_context}{mistakes_section}
--- SCRIPT STDOUT ---
{script_output or "(empty)"}

--- SCRIPT STDERR ---
{script_error or "(none)"}
--- END ---

Rules:
- PASS: all checks succeeded, data is fresh and consistent
- DEGRADED: some checks failed but system is partially functional
- FAIL: critical checks failed, system is broken
- If script itself failed to run, set verdict=DEGRADED with check="script_execution"
- If a past mistake is recurring, flag it in failures with severity=HIGH
- Be specific: include actual values in failures

Output ONLY this JSON (no markdown, no extra text):
{schema}"""


# ═════════════════════════════════════════════════════════════════════════════
# Prompt Builders — domain-specific
# ═════════════════════════════════════════════════════════════════════════════


def build_prompt_pipeline(mode, **kw):
    script = TOOLS["pipeline"]["script"]
    label = TOOLS["pipeline"]["label"]
    rnd = kw.get("round", 0)

    if mode == "audit":
        wf = kw.get("workflows", "")
        wf_flag = ["--workflows", wf] if wf else []
        stdout, stderr, rc = _run_script([PYTHON, str(script), "--audit"] + wf_flag)
        return _analysis_prompt("pipeline", rnd, label, stdout, stderr, rc,
                                extra_context="Analyze each workflow: check active status, recent execution success, error rates.")

    elif mode == "health":
        stdout, stderr, rc = _run_script([PYTHON, str(script), "--health"])
        return _analysis_prompt("pipeline", rnd, label, stdout, stderr, rc)

    elif mode == "verify-round":
        stdout, stderr, rc = _run_script([PYTHON, str(script), "--audit"])
        run_id = kw.get("run_id", "")
        extra = f"Run ID: {run_id}. Cross-check Maker claims vs actual state. Be skeptical." if run_id else ""
        # Try to include log files if they exist
        run_dir = DUAL_DIR / run_id if run_id else None
        if run_dir and run_dir.exists():
            for log_name in ("executor_log.json", "verifier_log.json"):
                lf = run_dir / log_name
                if lf.exists():
                    try:
                        extra += f"\n--- {log_name} ---\n{lf.read_text(encoding='utf-8')[:1000]}"
                    except Exception:
                        pass
        return _analysis_prompt("pipeline", rnd, label, stdout, stderr, rc, extra_context=extra)

    elif mode == "diff":
        stdout, stderr, rc = _run_script([PYTHON, str(script), "--diff",
                                          "--before", kw.get("before", ""),
                                          "--after", kw.get("after", "")])
        return _analysis_prompt("pipeline", rnd, label, stdout, stderr, rc,
                                extra_context="Flag any regressions between before/after snapshots.")


def build_prompt_finance(mode, **kw):
    script = TOOLS["finance"]["script"]
    label = TOOLS["finance"]["label"]
    rnd = kw.get("round", 0)
    target_file = kw.get("file", "")
    audit_report = kw.get("audit_report", "")

    checks_ctx = ("6-Point Audit: A=Arithmetic, B=Cross-Table, C=Period Consistency, "
                  "D=Sign Conventions, E=GAAP/K-GAAP Standards, F=Materiality & Sanity. "
                  "Severity: CRITICAL(>1% error) > MAJOR(formula) > MINOR(formatting) > INFO")

    if mode == "audit":
        if audit_report:
            # Read existing report instead of running script
            try:
                report_text = Path(audit_report).read_text(encoding="utf-8")[:3000]
                stdout, stderr, rc = report_text, "", 0
            except Exception as e:
                stdout, stderr, rc = "", str(e), -1
        else:
            file_flag = ["--audit-file", target_file] if target_file else []
            stdout, stderr, rc = _run_script([PYTHON, str(script)] + file_flag)
        return _analysis_prompt("finance", rnd, label, stdout, stderr, rc,
                                extra_context=checks_ctx + "\nDo NOT trust Golmani's numbers — verify independently.")

    elif mode == "verify-round":
        file_flag = ["--audit-file", target_file] if target_file else []
        stdout, stderr, rc = _run_script([PYTHON, str(script)] + file_flag)
        return _analysis_prompt("finance", rnd, label, stdout, stderr, rc,
                                extra_context=checks_ctx + f"\nRound {rnd}: verify corrections fixed prior issues. Check for regressions.")


def build_prompt_kpi(mode, **kw):
    script = TOOLS["kpi"]["script"]
    label = TOOLS["kpi"]["label"]
    rnd = kw.get("round", 0)
    table = kw.get("table", "")

    layers_ctx = ("6 Layers: L1=Schema, L2=Identity(gross-discount=net±$0.02), L3=Coverage, "
                  "L4=Through-date, L5=Cross-table(≤10% variance), L6=Anomaly(MoM>50%spike/>30%dip). "
                  "Expected brands: Grosmimi, Naeiae, CHA&MOM, Onzenna, Alpremio. "
                  "Expected tables: shopify_orders_daily, amazon_sales_daily, amazon_ads_daily, "
                  "meta_ads_daily, google_ads_daily, ga4_daily, klaviyo_daily")

    table_flag = ["--table", table] if table else []
    stdout, stderr, rc = _run_script([PYTHON, str(script)] + table_flag + ["--report-only"])
    # Also try reading saved report
    report_path = ROOT / ".tmp" / "validation_report.json"
    extra = layers_ctx
    if report_path.exists():
        try:
            extra += f"\n--- validation_report.json ---\n{report_path.read_text(encoding='utf-8')[:2000]}"
        except Exception:
            pass
    return _analysis_prompt("kpi", rnd, label, stdout, stderr, rc, extra_context=extra)


def build_prompt_crawl(mode, **kw):
    script = TOOLS["crawl"]["script"]
    label = TOOLS["crawl"]["label"]
    rnd = kw.get("round", 0)
    region = kw.get("region", "")

    axes_ctx = ("6 Audit Axes: 1=GitHub Actions(apify_daily.yml), 2=Secrets(APIFY_API_TOKEN etc), "
                "3=File Freshness(<36h OK, >72h CRITICAL), 4=Sheet Rows(Posts Master>10, D+60>0), "
                "5=D+60 Structure(192-col), 6=Brand Coverage(>80%, no dup IDs)")

    region_flag = ["--region", region] if region else []
    stdout, stderr, rc = _run_script([PYTHON, str(script), "--harness"] + region_flag + ["--json"])
    return _analysis_prompt("crawl", rnd, label, stdout, stderr, rc, extra_context=axes_ctx)


def build_prompt_datakeeper(mode, **kw):
    script = TOOLS["datakeeper"]["script"]
    label = TOOLS["datakeeper"]["label"]
    rnd = kw.get("round", 0)
    channel = kw.get("channel", "")

    channels_ctx = ("9 channels: amazon_ads, amazon_sales, meta_ads, google_ads, ga4, klaviyo, "
                    "shopify, gsc, keyword_volume. Freshness: <24h=OK, 24-48h=WARN, >48h=CRITICAL")

    if mode == "health":
        stdout, stderr, rc = _run_script([PYTHON, str(script), "--status"])
        return _analysis_prompt("datakeeper", rnd, label, stdout, stderr, rc,
                                extra_context=channels_ctx + ". Flag channels >48h as CRITICAL, >24h as WARN.")

    elif mode == "audit":
        ch_flag = ["--channel", channel] if channel else []
        stdout, stderr, rc = _run_script([PYTHON, str(script)] + ch_flag + ["--days", "7", "--skip-pg"])
        return _analysis_prompt("datakeeper", rnd, label, stdout, stderr, rc,
                                extra_context=channels_ctx + ". Check completeness, row counts, date gaps, brand coverage.")


def build_prompt_custom(prompt_text):
    return f"""You are an independent verification agent (Codex Verifier).
Python: {PYTHON}
Working dir: {ROOT}

TASK: {prompt_text}

After completing, output findings as JSON:
{VERDICT_SCHEMA.format(domain="custom", round=0)}

Output ONLY JSON as your final message."""


# ═════════════════════════════════════════════════════════════════════════════
# Prompt Router
# ═════════════════════════════════════════════════════════════════════════════

PROMPT_BUILDERS = {
    "pipeline": build_prompt_pipeline,
    "finance": build_prompt_finance,
    "kpi": build_prompt_kpi,
    "crawl": build_prompt_crawl,
    "datakeeper": build_prompt_datakeeper,
}


def build_prompt(domain, mode, **kw):
    builder = PROMPT_BUILDERS.get(domain)
    if not builder:
        raise ValueError(f"Unknown domain: {domain}. Available: {list(PROMPT_BUILDERS.keys())}")
    return builder(mode, **kw)


# ═════════════════════════════════════════════════════════════════════════════
# Codex Runner
# ═════════════════════════════════════════════════════════════════════════════

def run_codex(prompt, output_file=None, model=None, timeout=300):
    """Execute Codex CLI in non-interactive mode and capture output."""

    if output_file is None:
        output_file = TMP / f"codex_verdict_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    cmd = [
        CODEX_BIN, "exec",
        "--model", model or CODEX_MODEL,
        "--dangerously-bypass-approvals-and-sandbox",
        "-C", str(ROOT),
        "--skip-git-repo-check",
        "-o", str(output_file),
        "-",  # read prompt from stdin
    ]

    print(f"[codex-auditor] Launching Codex verifier (model={model or CODEX_MODEL})...")
    print(f"[codex-auditor] Output → {output_file}")

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
            env={**os.environ, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "")},
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            print(f"[codex-auditor] Codex exited with code {result.returncode}")
            if result.stderr:
                print(f"[codex-auditor] stderr: {result.stderr[:500]}")

        # Read output file
        if Path(output_file).exists():
            raw = Path(output_file).read_text(encoding="utf-8").strip()
            verdict = _extract_json(raw)
            if verdict:
                clean_path = TMP / f"verdict_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                clean_path.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"[codex-auditor] Verdict saved → {clean_path}")
                return verdict
            else:
                print(f"[codex-auditor] Could not parse JSON from Codex output")
                print(f"[codex-auditor] Raw output: {raw[:500]}")
                return _error_verdict("codex_parse_error", "valid JSON", raw[:200],
                                      "Codex output was not valid JSON", raw[:2000])
        else:
            print(f"[codex-auditor] No output file produced")
            return _error_verdict("codex_no_output", "output file", "missing",
                                  f"stdout: {result.stdout[:500]}")

    except subprocess.TimeoutExpired:
        return _error_verdict("codex_timeout", f"<{timeout}s", "timeout",
                              f"Codex timed out after {timeout}s")
    except FileNotFoundError:
        return _error_verdict("codex_not_found", "codex binary", "not found",
                              "Run: npm install -g @openai/codex")


def _error_verdict(check, expected, actual, notes, raw_output=None):
    v = {
        "verdict": "ERROR",
        "domain": "system",
        "round": 0,
        "timestamp": datetime.now().isoformat(),
        "checks_passed": 0,
        "checks_total": 0,
        "failures": [{"check": check, "expected": expected, "actual": actual, "severity": "CRITICAL"}],
        "warnings": [],
        "notes": notes,
    }
    if raw_output:
        v["raw_output"] = raw_output
    return v


def _extract_json(text):
    """Extract JSON object from text, handling markdown fences and extra text."""
    try:
        return json.loads(text)
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


def print_verdict(verdict):
    """Pretty-print the verdict."""
    v = verdict.get("verdict", "UNKNOWN")
    d = verdict.get("domain", "?")
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "DEGRADED": "[DEGRADED]", "ERROR": "[ERROR]"}.get(v, "[?]")

    print(f"\n{'='*60}")
    print(f"  CODEX AUDITOR VERDICT: {marker} {v}")
    print(f"  Domain: {d} | Round: {verdict.get('round', '?')}")
    print(f"  Checks: {verdict.get('checks_passed', '?')}/{verdict.get('checks_total', '?')}")
    print(f"{'='*60}")

    for f in verdict.get("failures", []):
        print(f"  [{f.get('severity','?')}] {f.get('check','?')}: expected={f.get('expected','?')}, actual={f.get('actual','?')}")

    for w in verdict.get("warnings", []):
        print(f"  [WARN] {w}")

    notes = verdict.get("notes", "")
    if notes:
        print(f"  Notes: {notes}")

    print("\n--- JSON ---")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Codex Auditor — Multi-domain Independent Verification via OpenAI Codex CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Domains:
  pipeline    n8n Pathlight workflow audit
  finance     CFO/감사관 financial data audit
  kpi         KPI data validation (검증이)
  crawl       Apify content pipeline audit
  datakeeper  Data collection freshness audit

Examples:
  %(prog)s --domain pipeline --audit
  %(prog)s --domain finance --audit --file output.xlsx
  %(prog)s --domain kpi --audit --table shopify_orders_daily
  %(prog)s --domain crawl --audit --region us
  %(prog)s --domain datakeeper --health
  %(prog)s --prompt "custom verification request"
""")

    parser.add_argument("--domain", "-d", choices=list(TOOLS.keys()),
                        help="Audit domain (pipeline/finance/kpi/crawl/datakeeper)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--audit", action="store_true", help="Full audit")
    group.add_argument("--health", action="store_true", help="Quick health check")
    group.add_argument("--verify-round", type=int, metavar="N", help="Verify round N")
    group.add_argument("--diff", action="store_true", help="Compare snapshots")
    group.add_argument("--prompt", type=str, help="Custom audit prompt (no --domain needed)")

    # Shared options
    parser.add_argument("--model", type=str, default=CODEX_MODEL, help=f"Codex model (default: {CODEX_MODEL})")
    parser.add_argument("--round", type=int, default=0, help="Round number for context")
    parser.add_argument("--json-only", action="store_true", help="Output only raw JSON")
    parser.add_argument("--timeout", type=int, default=300, help="Codex timeout in seconds (default: 300)")

    # Domain-specific options
    parser.add_argument("--workflows", type=str, help="[pipeline] Comma-separated workflow keys")
    parser.add_argument("--run-id", type=str, help="[pipeline] Dual test run ID")
    parser.add_argument("--before", type=str, help="[pipeline] Before snapshot path")
    parser.add_argument("--after", type=str, help="[pipeline] After snapshot path")
    parser.add_argument("--file", type=str, help="[finance] Target file to audit")
    parser.add_argument("--audit-report", type=str, help="[finance] Existing audit report JSON")
    parser.add_argument("--table", type=str, help="[kpi] Specific table to validate")
    parser.add_argument("--region", type=str, help="[crawl] Region filter (us/jp)")
    parser.add_argument("--channel", type=str, help="[datakeeper] Specific channel")

    args = parser.parse_args()

    # Custom prompt — no domain needed
    if args.prompt:
        prompt = build_prompt_custom(args.prompt)
        verdict = run_codex(prompt, model=args.model, timeout=args.timeout)
        _output(verdict, args.json_only)
        return

    # Domain required for non-custom modes
    if not args.domain:
        parser.error("--domain is required unless using --prompt")

    # Build domain-specific prompt
    kw = {
        "round": args.round,
        "workflows": args.workflows or "",
        "run_id": args.run_id or "",
        "before": args.before or "",
        "after": args.after or "",
        "file": args.file or "",
        "audit_report": args.audit_report or "",
        "table": args.table or "",
        "region": args.region or "",
        "channel": args.channel or "",
    }

    if args.audit:
        mode = "audit"
    elif args.health:
        mode = "health"
    elif args.verify_round is not None:
        mode = "verify-round"
        kw["round"] = args.verify_round
    elif args.diff:
        mode = "diff"
        if not args.before or not args.after:
            parser.error("--diff requires --before and --after")

    prompt = build_prompt(args.domain, mode, **kw)
    verdict = run_codex(prompt, model=args.model, timeout=args.timeout)
    _output(verdict, args.json_only, domain=args.domain, mode=mode)


SCORES_FILE = ROOT / "memory" / "agent_scores.md"
SCORE_COOLDOWN_HOURS = 1  # Min hours between scorings per domain
SCORE_STATE_FILE = TMP / "score_state.json"


def _should_score(domain, mode):
    """Score after full audits (audit/verify-round), with cooldown."""
    if mode not in ("audit", "verify-round"):
        return False  # Skip health/diff — not significant enough
    state = {}
    if SCORE_STATE_FILE.exists():
        try:
            state = json.loads(SCORE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    last_ts = state.get(domain, 0)
    elapsed_hours = (datetime.now().timestamp() - last_ts) / 3600
    return elapsed_hours >= SCORE_COOLDOWN_HOURS


def _mark_scored(domain):
    state = {}
    if SCORE_STATE_FILE.exists():
        try:
            state = json.loads(SCORE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    state[domain] = datetime.now().timestamp()
    SCORE_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_recent_verdicts(domain, n=5):
    """Load last N verdict JSON files for this domain."""
    verdicts = []
    for f in sorted(TMP.glob("verdict_*.json"), reverse=True):
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
            if v.get("domain") == domain:
                verdicts.append(v)
                if len(verdicts) >= n:
                    break
        except Exception:
            continue
    return list(reversed(verdicts))  # oldest first


def _score_agent(domain):
    """Run agent scoring: analyze last 5 verdicts, write grade to agent_scores.md."""
    label = TOOLS.get(domain, {}).get("label", domain)
    verdicts = _load_recent_verdicts(domain, n=5)
    if not verdicts:
        return

    verdicts_text = json.dumps(verdicts, ensure_ascii=False, indent=2)[:3000]
    prompt = f"""You are an independent scoring agent. Analyze the last {len(verdicts)} audit verdicts for this agent and assign a grade.

Agent: {label}
Domain: {domain}

--- LAST {len(verdicts)} VERDICTS ---
{verdicts_text}
--- END ---

Scoring criteria:
- A: All PASS, no recurring issues, improving trend
- B: Mostly PASS, minor issues, stable
- C: Mix of PASS/DEGRADED, some recurring issues
- D: Frequent FAIL or DEGRADED, critical recurring issues

Output ONLY this JSON:
{{"domain": "{domain}", "grade": "A|B|C|D", "trend": "improving|stable|declining", "pass_rate": "X/5", "top_issues": ["issue1", "issue2"], "notes": "1-sentence summary", "scored_at": "ISO8601"}}"""

    output_file = TMP / f"score_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    cmd = [
        CODEX_BIN, "exec",
        "--model", CODEX_MODEL,
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--ephemeral",
        "-o", str(output_file),
        "-",
    ]
    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                timeout=60, encoding="utf-8", errors="replace",
                                env={**os.environ, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "")})
    except Exception:
        return

    if not output_file.exists():
        return
    raw = output_file.read_text(encoding="utf-8").strip()
    score = _extract_json(raw)
    if not score or "grade" not in score:
        return

    # Write to agent_scores.md
    grade = score.get("grade", "?")
    trend = score.get("trend", "?")
    pass_rate = score.get("pass_rate", "?")
    issues = ", ".join(score.get("top_issues", []))
    notes = score.get("notes", "")
    scored_at = score.get("scored_at", datetime.now().isoformat())[:10]

    entry = f"\n### {label} — {scored_at}\n- **Grade**: {grade} | **Trend**: {trend} | **Pass Rate**: {pass_rate}\n- **Top Issues**: {issues or 'none'}\n- {notes}\n"

    existing = ""
    if SCORES_FILE.exists():
        existing = SCORES_FILE.read_text(encoding="utf-8")
    if not existing:
        existing = "# Agent Scores\n\nPeriodic scoring by Codex Auditor (every 5 runs per domain).\n"

    # Insert/update domain section
    section_header = f"\n## {domain}\n"
    if section_header in existing:
        # Append entry under existing domain section
        idx = existing.index(section_header) + len(section_header)
        existing = existing[:idx] + entry + existing[idx:]
    else:
        existing = existing.rstrip() + f"\n{section_header}{entry}"

    SCORES_FILE.write_text(existing, encoding="utf-8")
    print(f"[codex-auditor] Agent scored: {label} → {grade} ({trend}, {pass_rate})")


def _output(verdict, json_only, domain=None, mode=None):
    if json_only:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
    else:
        print_verdict(verdict)
    # Score after significant audits (audit/verify-round), with 1h cooldown
    if domain and mode and verdict.get("verdict") in ("PASS", "FAIL", "DEGRADED"):
        if _should_score(domain, mode):
            print(f"[codex-auditor] Significant audit complete — scoring agent...")
            _score_agent(domain)
            _mark_scored(domain)
    v = verdict.get("verdict", "ERROR")
    sys.exit(0 if v == "PASS" else 1 if v == "FAIL" else 2)


if __name__ == "__main__":
    main()
