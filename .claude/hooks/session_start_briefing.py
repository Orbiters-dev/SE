#!/usr/bin/env python3
"""SessionStart hook — 세션 시작 시 5-stage harness 환경 자가 진단 + 룰 복창.

지후님/원준 까먹음 차단 자동화의 첫 layer. 매 Claude session 시작 시 fire.

검사 항목 (실패해도 block X — 알림만):
  1. LightRAG /health  (http://127.0.0.1:9621)
  2. Ollama bge-m3:latest 모델 설치 verify
  3. .claude/hooks/ 3종 (harness_runner / n8n_put_guard / agent_discipline_reminder) wire 확인
  4. .harness_state.json 의 current_plan 확인 (진행중 plan 있으면 path 표시)
  5. CLAUDE.md / SKILL.md 위치 reminder

출력: systemMessage 1건 (multi-line) — 사용자에게 보임.
환경변수: LIGHTRAG_URL (default http://127.0.0.1:9621)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

LIGHTRAG_URL = os.environ.get("LIGHTRAG_URL", "http://127.0.0.1:9621")
PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
HOOKS_DIR = PROJECT_DIR / ".claude" / "hooks"
STATE_FILE = PROJECT_DIR / ".claude" / ".harness_state.json"

REQUIRED_HOOKS = (
    "harness_runner.py",
    "n8n_put_guard.py",
    "agent_discipline_reminder.py",
    "session_start_briefing.py",
    "user_prompt_5stage_inject.py",
)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def _check_lightrag() -> tuple[bool, str]:
    try:
        req = urllib.request.Request(f"{LIGHTRAG_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if data.get("status") == "healthy":
                emb = data.get("configuration", {}).get("embedding_model", "?")
                return True, f"healthy (embed={emb})"
            return False, f"status={data.get('status', '?')}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"DOWN ({type(exc).__name__})"
    except Exception as exc:
        return False, f"err {type(exc).__name__}"


def _check_ollama_model(model: str = "bge-m3") -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return False, "ollama CLI fail"
        if model in (result.stdout or ""):
            return True, "installed"
        return False, "MISSING"
    except FileNotFoundError:
        return False, "ollama not in PATH"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:
        return False, f"err {type(exc).__name__}"


def _check_hooks() -> tuple[bool, list[str]]:
    missing = []
    for h in REQUIRED_HOOKS:
        if not (HOOKS_DIR / h).exists():
            missing.append(h)
    return (len(missing) == 0), missing


def _read_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def main() -> int:
    try:
        # SessionStart payload available on stdin but not required for this check
        sys.stdin.read()
    except Exception:
        pass

    rag_ok, rag_msg = _check_lightrag()
    ollama_ok, ollama_msg = _check_ollama_model("bge-m3")
    hooks_ok, hooks_missing = _check_hooks()
    state = _read_state()

    lines = []
    lines.append("🧭 ORBI 5-stage harness — session start briefing")
    lines.append("")
    lines.append(f"  LightRAG     : {'OK' if rag_ok else 'X'}  {rag_msg}")
    lines.append(f"  Ollama bge-m3: {'OK' if ollama_ok else 'X'}  {ollama_msg}")
    if hooks_ok:
        lines.append(f"  Hooks (5/5)  : OK  {', '.join(REQUIRED_HOOKS)}")
    else:
        lines.append(f"  Hooks        : X  missing: {', '.join(hooks_missing)}")

    cur_plan = state.get("current_plan")
    if cur_plan:
        pass_at = state.get("current_plan_pass_at") or "(not yet PASS)"
        lines.append(f"  Active plan  : {cur_plan}  pass_at={pass_at}")
    else:
        lines.append("  Active plan  : (none)")

    lines.append("")
    lines.append("Rules: Stage 1 PLAN -> 2 BUILD -> 3 VERIFY -> 4 META -> 5 VAULT.")
    lines.append("Plan first: write .tmp/plan_<topic>_<date>.md before code/n8n/Shopify changes.")

    if not rag_ok:
        lines.append("")
        lines.append("[FIX] LightRAG DOWN — start server or check port 9621.")
    if not ollama_ok:
        lines.append("")
        lines.append("[FIX] bge-m3 missing — run: ollama pull bge-m3:latest  (~1.2GB)")

    _emit({"systemMessage": "\n".join(lines)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
