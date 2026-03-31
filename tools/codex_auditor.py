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
CODEX_BIN = "codex"
CODEX_MODEL = "o4-mini"  # Verified working 2026-04-01

VERDICT_SCHEMA = """{{"verdict": "PASS|FAIL|DEGRADED", "domain": "{domain}", "round": {round}, "timestamp": "ISO8601", "checks_passed": N, "checks_total": N, "failures": [{{"check": "name", "expected": "...", "actual": "...", "severity": "CRITICAL|HIGH|MEDIUM|LOW"}}], "warnings": [], "notes": "summary"}}"""


# ═════════════════════════════════════════════════════════════════════════════
# Prompt Builders — domain-specific
# ═════════════════════════════════════════════════════════════════════════════

def _base_context(domain):
    tool = TOOLS.get(domain, {})
    return f"""You are an independent verification agent (Codex Verifier).
Your job is to run audit scripts, analyze results, and report findings.
You must be SKEPTICAL — assume nothing works until you prove it.

Domain: {tool.get('label', domain)}
Python: {PYTHON}
Script: {tool.get('script', 'N/A')}
Working dir: {ROOT}
"""


def build_prompt_pipeline(mode, **kw):
    ctx = _base_context("pipeline")
    script = TOOLS["pipeline"]["script"]
    rnd = kw.get("round", 0)
    schema = VERDICT_SCHEMA.format(domain="pipeline", round=rnd)

    if mode == "audit":
        wf = kw.get("workflows", "")
        wf_flag = f" --workflows {wf}" if wf else ""
        return f"""{ctx}
TASK: Full audit of all Pathlight PROD n8n workflows.
1. Run: {PYTHON} "{script}" --audit{wf_flag}
2. Analyze each FAIL — explain impact
3. Output ONLY JSON verdict: {schema}"""

    elif mode == "health":
        return f"""{ctx}
TASK: Quick health check of n8n workflows.
1. Run: {PYTHON} "{script}" --health
2. Output ONLY JSON verdict: {schema}"""

    elif mode == "verify-round":
        run_id = kw.get("run_id", "")
        run_dir = DUAL_DIR / run_id if run_id else ""
        return f"""{ctx}
TASK: Verify Pipeliner round {rnd} results.
1. Run: {PYTHON} "{script}" --audit
2. If exists, read {run_dir}/executor_log.json and verifier_log.json
3. Cross-check Maker claims vs actual system state — be skeptical
4. Output ONLY JSON verdict: {schema}"""

    elif mode == "diff":
        return f"""{ctx}
TASK: Compare workflow snapshots.
1. Run: {PYTHON} "{script}" --diff --before "{kw.get('before', '')}" --after "{kw.get('after', '')}"
2. Flag regressions
3. Output ONLY JSON verdict: {schema}"""


def build_prompt_finance(mode, **kw):
    ctx = _base_context("finance")
    script = TOOLS["finance"]["script"]
    rnd = kw.get("round", 0)
    schema = VERDICT_SCHEMA.format(domain="finance", round=rnd)
    target_file = kw.get("file", "")
    audit_report = kw.get("audit_report", "")

    checks = """
6-Point Audit Checklist:
  A: Arithmetic — 소계 → 합계 일치
  B: Cross-Table — 다중 출처 수치 일치
  C: Period Consistency — 동일 기간 데이터
  D: Sign Conventions — 부호 일관성
  E: Accounting Standards — GAAP/K-GAAP 준수
  F: Materiality & Sanity — 벤치마크 대비 이상치"""

    if mode == "audit":
        file_flag = f" --audit-file \"{target_file}\"" if target_file else ""
        report_flag = f" (existing report: {audit_report})" if audit_report else ""
        return f"""{ctx}{checks}

TASK: Independent financial audit{report_flag}.
1. {"Read audit report: " + audit_report if audit_report else f'Run: {PYTHON} "{script}"{file_flag}'}
2. Apply ALL 6 checks (A-F) independently
3. For each check: PASS, WARN, or FAIL with specific evidence
4. Severity: CRITICAL (>1% error) > MAJOR (formula) > MINOR (formatting) > INFO
5. Output ONLY JSON verdict: {schema}

IMPORTANT: You are the independent auditor. Do NOT trust Golmani's numbers without verifying."""

    elif mode == "verify-round":
        return f"""{ctx}{checks}

TASK: Re-audit after CFO-directed corrections (round {rnd}).
1. Run: {PYTHON} "{script}" --audit-file "{target_file}"
2. Verify corrections actually fixed the flagged issues
3. Check for new regressions introduced by fixes
4. Output ONLY JSON verdict: {schema}"""


def build_prompt_kpi(mode, **kw):
    ctx = _base_context("kpi")
    script = TOOLS["kpi"]["script"]
    rnd = kw.get("round", 0)
    schema = VERDICT_SCHEMA.format(domain="kpi", round=rnd)
    table = kw.get("table", "")

    layers = """
6 Validation Layers:
  L1: Schema — column types, nulls, ranges (Pandera)
  L2: Identity — gross - discount = net (±$0.02)
  L3: Coverage — all brands/channels present
  L4: Through-date — cross-table date alignment
  L5: Cross-table — Amazon reconciliation, discount sanity (≤10% variance)
  L6: Anomaly — MoM >50% spike / >30% dip (seasonal adjustment)"""

    table_flag = f" --table {table}" if table else ""
    return f"""{ctx}{layers}

TASK: Independent KPI data validation.
1. Run: {PYTHON} "{script}"{table_flag} --report-only
2. Read the validation report from .tmp/validation_report.json
3. Apply all 6 layers independently — don't trust prior results
4. Expected brands: Grosmimi, Naeiae, CHA&MOM, Onzenna, Alpremio
5. Expected tables: shopify_orders_daily, amazon_sales_daily, amazon_ads_daily, meta_ads_daily, google_ads_daily, ga4_daily, klaviyo_daily
6. Output ONLY JSON verdict: {schema}

IMPORTANT: Cross-check actual data, not just script output."""


def build_prompt_crawl(mode, **kw):
    ctx = _base_context("crawl")
    script = TOOLS["crawl"]["script"]
    rnd = kw.get("round", 0)
    schema = VERDICT_SCHEMA.format(domain="crawl", round=rnd)
    region = kw.get("region", "")

    axes = """
6 Audit Axes:
  1. GitHub Actions — apify_daily.yml execution status
  2. Secrets — APIFY_API_TOKEN, GOOGLE_SERVICE_ACCOUNT, META_GRAPH_IG_TOKEN
  3. File Freshness — Data Storage JSON (<36h OK, >72h CRITICAL)
  4. Sheet Rows — 6 tabs, Posts Master >10 rows, D+60 >0 rows
  5. D+60 Structure — 192-column format, D+0 headers
  6. Brand Coverage — >80% classification, no duplicate Post IDs"""

    region_flag = f" --region {region}" if region else ""
    return f"""{ctx}{axes}

TASK: Apify content pipeline audit.
1. Run: {PYTHON} "{script}" --harness{region_flag} --json
2. Read JSON output
3. Verify all 6 axes independently
4. Output ONLY JSON verdict: {schema}"""


def build_prompt_datakeeper(mode, **kw):
    ctx = _base_context("datakeeper")
    script = TOOLS["datakeeper"]["script"]
    rnd = kw.get("round", 0)
    schema = VERDICT_SCHEMA.format(domain="datakeeper", round=rnd)
    channel = kw.get("channel", "")

    channels = """
9 Data Channels:
  amazon_ads, amazon_sales, meta_ads, google_ads, ga4, klaviyo, shopify, gsc, keyword_volume
Freshness thresholds: <24h OK, 24-48h WARN, >48h CRITICAL"""

    if mode == "health":
        return f"""{ctx}{channels}

TASK: Data Keeper freshness health check.
1. Run: {PYTHON} "{script}" --status
2. Check last_updated timestamp for each channel
3. Flag any channel >48h stale as CRITICAL, >24h as WARN
4. Output ONLY JSON verdict: {schema}"""

    elif mode == "audit":
        ch_flag = f" --channel {channel}" if channel else ""
        return f"""{ctx}{channels}

TASK: Data Keeper full audit.
1. Run: {PYTHON} "{script}"{ch_flag} --days 7 --skip-pg
2. Check data completeness, row counts, date gaps
3. Verify brand coverage per channel
4. Output ONLY JSON verdict: {schema}"""


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
        "--sandbox", "read-only",
        "-C", str(ROOT),
        "--skip-git-repo-check",
        "-o", str(output_file),
        prompt,
    ]

    print(f"[codex-auditor] Launching Codex verifier (model={model or CODEX_MODEL})...")
    print(f"[codex-auditor] Output → {output_file}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
            env={**os.environ, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "")},
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
    _output(verdict, args.json_only)


def _output(verdict, json_only):
    if json_only:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
    else:
        print_verdict(verdict)
    v = verdict.get("verdict", "ERROR")
    sys.exit(0 if v == "PASS" else 1 if v == "FAIL" else 2)


if __name__ == "__main__":
    main()
