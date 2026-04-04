"""
Codex Evaluator — 제갈량 harness의 Evaluator 에이전트.

WJ Test1 (Claude) = Generator, OpenAI Codex = Evaluator.
Anthropic "Harness Design for Long-Running Apps" 패턴 적용.

Usage:
    # 코드 리뷰 (Evaluator)
    python tools/codex_evaluator.py audit --files tools/data_keeper.py tools/run_kpi_monthly.py

    # Sprint contract 검증
    python tools/codex_evaluator.py verify --contract .tmp/sprint_contract.md

    # 자유 프롬프트
    python tools/codex_evaluator.py ask "이 리포의 보안 취약점을 찾아줘"

    # JSON 출력 (파이프라인용)
    python tools/codex_evaluator.py audit --files tools/data_keeper.py --json

    # 이전 세션 이어서
    python tools/codex_evaluator.py resume --thread-id <id> "수정한 부분 다시 검증해줘"

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

    user_prompt = (
        "Audit the following files. Apply hard thresholds. Be skeptical.\n\n"
        + "\n\n".join(file_contents)
    )

    if args.use_codex:
        result = call_codex_exec(f"[AUDIT MODE] {user_prompt}")
    else:
        result = call_openai(AUDIT_SYSTEM, user_prompt, model=args.model)

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
    user_prompt = (
        "Verify this sprint contract against the current codebase.\n\n"
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
    prompt = args.prompt
    if args.use_codex:
        result = call_codex_exec(prompt)
    else:
        result = call_openai(AUDIT_SYSTEM, prompt, model=args.model)

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
