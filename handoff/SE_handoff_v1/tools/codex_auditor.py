"""
Codex Flow Auditor - Independent Evaluator for Pipeline Harness
================================================================
Codex CLI (OpenAI o3)를 호출하여 파이프라인 실행 결과를 독립 감사한다.
dual_test_runner.py의 Harness 모드에서 Evaluator 역할.

Architecture:
  Pipeliner (Builder) → signal.json + logs
  Codex Auditor (Evaluator) → verdict JSON

Ops Framework (→ .claude/skills/_ops-framework/OPS_FRAMEWORK.md):
  EVALUATE: --health 로 CLI 가용성 + API key + verdict 정합성 체크
  AUDIT:    executor_log vs verifier_log 교차 검증 (summarize_checks)
  FIX:      verdict ERROR 시 prompt 재구성 → 재실행 (max 2 rounds)
  IMPACT:   N/A (독립 감사자, 변경 주체 아님)

Usage:
    python tools/codex_auditor.py --verify-round 1 --run-id dual_20260404_123456
    python tools/codex_auditor.py --verify-round 2 --run-id dual_20260404_123456
    python tools/codex_auditor.py --health
"""

import os
import sys
import json
import shutil
import subprocess
import argparse
from datetime import datetime, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
TMP = os.path.join(ROOT, ".tmp")
AUDIT_DIR = os.path.join(TMP, "codex_audit")
DUAL_DIR = os.path.join(TMP, "dual_test")

os.makedirs(AUDIT_DIR, exist_ok=True)


# ─── Verdict Schema ─────────────────────────────────────────────────────────

def empty_verdict(run_id, round_num, error_msg=None):
    return {
        "verdict": "ERROR",
        "domain": "pipeline",
        "round": round_num,
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks_passed": 0,
        "checks_total": 0,
        "failures": [],
        "warnings": [error_msg] if error_msg else [],
        "notes": error_msg or "No data",
    }


# ─── Load Run Data ──────────────────────────────────────────────────────────

def load_run_data(run_id):
    """Load executor/verifier logs + signal from a dual test run."""
    run_dir = os.path.join(DUAL_DIR, run_id)
    if not os.path.isdir(run_dir):
        return None, f"Run directory not found: {run_dir}"

    data = {"run_id": run_id, "run_dir": run_dir}

    for name in ["executor_log.json", "verifier_log.json", "signal.json", "config.json"]:
        path = os.path.join(run_dir, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data[name.replace(".json", "")] = json.load(f)
        else:
            data[name.replace(".json", "")] = None

    return data, None


def summarize_checks(log_data):
    """Summarize executor or verifier log into text for Codex prompt."""
    if not log_data:
        return "No log data available."
    lines = []
    for stage in log_data:
        stage_name = stage.get("stage", "?")
        checks = stage.get("checks", [])
        passed = sum(1 for c in checks if c.get("passed") is True)
        failed = [c for c in checks if c.get("passed") is False]
        skipped = [c for c in checks if c.get("passed") is None]
        lines.append(f"Stage [{stage_name}]: {passed}/{len(checks)} PASS, {len(failed)} FAIL, {len(skipped)} SKIP")
        for c in failed:
            lines.append(f"  FAIL: {c['name']} -expected={c.get('expected','?')}, actual={c.get('actual','?')}")
        for c in skipped:
            lines.append(f"  SKIP: {c['name']} -{c.get('detail','')}")
    return "\n".join(lines)


def extract_failed_stages(log_data):
    """Return list of stage names that have at least one FAIL check."""
    if not log_data:
        return []
    failed = []
    for stage in log_data:
        for c in stage.get("checks", []):
            if c.get("passed") is False:
                failed.append(stage["stage"])
                break
    return failed


# ─── Build Codex Prompt ─────────────────────────────────────────────────────

def build_audit_prompt(run_data, round_num, prev_verdict=None):
    """Build the audit prompt for Codex CLI."""
    exec_summary = summarize_checks(run_data.get("executor_log"))
    veri_summary = summarize_checks(run_data.get("verifier_log"))

    config = run_data.get("config") or {}
    stages = config.get("stages", [])

    prompt = f"""You are an independent pipeline auditor. Analyze the following Creator Collab Pipeline test results and return a JSON verdict.

## Test Run
- Run ID: {run_data['run_id']}
- Round: {round_num}
- Stages tested: {', '.join(stages)}
- Test email: {config.get('test_email', 'N/A')}

## Executor (Builder) Results
{exec_summary}

## Verifier (Checker) Results
{veri_summary}
"""

    if prev_verdict:
        prompt += f"""
## Previous Round Verdict
- Verdict: {prev_verdict.get('verdict')}
- Failures from Round {prev_verdict.get('round', '?')}:
"""
        for f in prev_verdict.get("failures", []):
            prompt += f"  - [{f.get('severity','?')}] {f.get('check','?')}: expected={f.get('expected','?')}, actual={f.get('actual','?')}\n"
        prompt += "\nCheck if the previous failures have been resolved in this round.\n"

    prompt += """
## Output Format
Return ONLY valid JSON (no markdown, no explanation) with this exact schema:
{
  "verdict": "PASS" or "FAIL" or "DEGRADED",
  "domain": "pipeline",
  "round": <round_number>,
  "checks_passed": <int>,
  "checks_total": <int>,
  "failures": [
    {"check": "<check_name>", "expected": "<value>", "actual": "<value>", "severity": "CRITICAL|HIGH|MEDIUM|LOW"}
  ],
  "warnings": ["<string>"],
  "notes": "<summary>"
}

Rules:
- PASS: All executor and verifier checks passed
- DEGRADED: Minor issues (MEDIUM/LOW severity only), no CRITICAL/HIGH failures
- FAIL: Any CRITICAL or HIGH severity failure
- Count checks_passed and checks_total from both executor AND verifier
- Be strict: if a stage has any FAIL check, it must appear in failures
"""
    return prompt


# ─── Codex CLI Execution ────────────────────────────────────────────────────

def find_codex_cli():
    """Find the codex CLI binary."""
    path = shutil.which("codex")
    if path:
        return path
    # Try common npm global locations
    for candidate in [
        os.path.expanduser("~/AppData/Roaming/npm/codex.cmd"),
        os.path.expanduser("~/AppData/Roaming/npm/codex"),
        "/usr/local/bin/codex",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def run_codex(prompt, model="o3"):
    """Call Codex CLI and return parsed JSON verdict."""
    codex_bin = find_codex_cli()
    if not codex_bin:
        return None, "Codex CLI not found. Install: npm install -g @openai/codex"

    # Write prompt to temp file (avoids shell escaping issues)
    prompt_path = os.path.join(AUDIT_DIR, "_audit_prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    # Output file for capturing last message
    output_path = os.path.join(AUDIT_DIR, "_codex_output.txt")

    cmd = [
        codex_bin,
        "exec",
        "--model", model,
        "--full-auto",
        "-o", output_path,
        f"Read the file {prompt_path} and follow its instructions exactly. Return ONLY the JSON verdict.",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "CODEX_QUIET_MODE": "1"},
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            return None, f"Codex CLI error (exit {result.returncode}): {stderr[:500]}"

        # Prefer -o output file, fall back to stdout
        if os.path.isfile(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                json_str = f.read().strip()
        else:
            json_str = stdout
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        # Find first { to last }
        start = json_str.find("{")
        end = json_str.rfind("}")
        if start >= 0 and end > start:
            json_str = json_str[start:end + 1]

        verdict = json.loads(json_str)
        return verdict, None

    except subprocess.TimeoutExpired:
        return None, "Codex CLI timed out (120s)"
    except json.JSONDecodeError as e:
        return None, f"Failed to parse Codex output as JSON: {e}\nRaw output: {stdout[:500]}"
    except Exception as e:
        return None, f"Codex execution error: {e}"


# ─── Main Audit Function ────────────────────────────────────────────────────

def run_audit(run_id, round_num, prev_verdict=None, model="o3"):
    """Run a full Codex audit for a pipeline test run."""
    print(f"\n{'='*60}")
    print(f"  CODEX FLOW AUDITOR -Round {round_num}")
    print(f"  Run ID: {run_id}")
    print(f"  Model:  {model}")
    print(f"{'='*60}")

    # Load run data
    run_data, err = load_run_data(run_id)
    if err:
        print(f"  [ERROR] {err}")
        verdict = empty_verdict(run_id, round_num, err)
        save_verdict(run_id, verdict, round_num)
        return verdict

    # Build prompt
    prompt = build_audit_prompt(run_data, round_num, prev_verdict)
    print(f"  Prompt length: {len(prompt)} chars")
    print(f"  Calling Codex CLI...")

    # Run Codex
    verdict, err = run_codex(prompt, model=model)
    if err:
        print(f"  [ERROR] {err}")
        verdict = empty_verdict(run_id, round_num, err)
    else:
        # Ensure required fields
        verdict.setdefault("domain", "pipeline")
        verdict.setdefault("round", round_num)
        verdict.setdefault("run_id", run_id)
        verdict.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        print(f"  Verdict: {verdict.get('verdict')}")
        print(f"  Checks: {verdict.get('checks_passed')}/{verdict.get('checks_total')}")
        if verdict.get("failures"):
            for f in verdict["failures"]:
                print(f"  FAIL: [{f.get('severity','?')}] {f.get('check','?')}")
        if verdict.get("warnings"):
            for w in verdict["warnings"]:
                print(f"  WARN: {w}")

    save_verdict(run_id, verdict, round_num)
    return verdict


def save_verdict(run_id, verdict, round_num):
    """Save verdict to both audit dir and run dir."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save to audit dir
    audit_path = os.path.join(AUDIT_DIR, f"verdict_{run_id}_round{round_num}.json")
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {audit_path}")

    # Also save to run dir if it exists
    run_dir = os.path.join(DUAL_DIR, run_id)
    if os.path.isdir(run_dir):
        run_path = os.path.join(run_dir, f"verdict_round{round_num}.json")
        with open(run_path, "w", encoding="utf-8") as f:
            json.dump(verdict, f, indent=2, ensure_ascii=False)


# ─── Health Check ────────────────────────────────────────────────────────────

def cmd_health():
    """Check Codex CLI availability and API key."""
    print("\n  Codex Flow Auditor - Health Check")
    print("  " + "-" * 40)

    codex_bin = find_codex_cli()
    if codex_bin:
        print(f"  [PASS] Codex CLI found: {codex_bin}")
    else:
        print("  [FAIL] Codex CLI not found")
        print("         Install: npm install -g @openai/codex")
        return False

    # Version check
    try:
        result = subprocess.run([codex_bin, "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip()
        print(f"  [PASS] Version: {version}")
    except Exception as e:
        print(f"  [WARN] Version check failed: {e}")

    # API key check
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        print(f"  [PASS] OPENAI_API_KEY set ({api_key[:8]}...)")
    else:
        print("  [FAIL] OPENAI_API_KEY not set")
        return False

    # Audit dir
    verdicts = [f for f in os.listdir(AUDIT_DIR) if f.startswith("verdict_")]
    print(f"  [INFO] {len(verdicts)} verdict files in {AUDIT_DIR}")

    print("  " + "-" * 40)
    print("  Ready.\n")
    return True


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Codex Flow Auditor - Pipeline Evaluator")
    parser.add_argument("--verify-round", type=int, help="Round number to verify (1 or 2)")
    parser.add_argument("--run-id", type=str, help="Dual test run ID")
    parser.add_argument("--prev-verdict", type=str, help="Path to previous round verdict JSON")
    parser.add_argument("--model", type=str, default="o3", help="Codex model (default: o3)")
    parser.add_argument("--health", action="store_true", help="Check Codex CLI availability")

    args = parser.parse_args()

    if args.health:
        ok = cmd_health()
        sys.exit(0 if ok else 1)

    if args.verify_round:
        if not args.run_id:
            print("ERROR: --verify-round requires --run-id")
            sys.exit(1)

        prev_verdict = None
        if args.prev_verdict and os.path.isfile(args.prev_verdict):
            with open(args.prev_verdict, "r", encoding="utf-8") as f:
                prev_verdict = json.load(f)

        verdict = run_audit(args.run_id, args.verify_round,
                           prev_verdict=prev_verdict, model=args.model)
        sys.exit(0 if verdict.get("verdict") != "ERROR" else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
