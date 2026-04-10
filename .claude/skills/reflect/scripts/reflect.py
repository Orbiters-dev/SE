#!/usr/bin/env python3
"""
reflect.py — 세션 종료 시 자동 학습 + 세션 요약 저장.

1. transcript에서 교정 신호 추출
2. HIGH confidence 신호 → mistakes.md에 자동 추가
3. 세션 요약 → session_YYYYMMDD.md 저장
4. MEMORY.md 세션 요약 섹션 업데이트
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 경로 설정
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent  # 세은테스트/
MEMORY_DIR = Path(os.environ.get(
    "CLAUDE_MEMORY_DIR",
    Path.home() / ".claude" / "projects" /
    "z--ORBI-CLAUDE-0223-ORBITERS-CLAUDE-ORBITERS-CLAUDE------" / "memory"
))
STATE_DIR = SCRIPT_DIR.parent / ".state"

# 모듈 임포트
sys.path.insert(0, str(SCRIPT_DIR))
from extract_signals import extract_signals


def main():
    transcript_path = os.environ.get("TRANSCRIPT_PATH") or (sys.argv[1] if len(sys.argv) > 1 else None)

    if not transcript_path:
        print("[reflect] transcript_path 없음. 종료.", file=sys.stderr)
        return

    # lock 체크
    lock_file = STATE_DIR / "reflection.lock"
    if lock_file.exists():
        import time
        mtime = lock_file.stat().st_mtime
        if time.time() - mtime < 600:  # 10분 이내
            print("[reflect] 10분 이내 실행됨. 스킵.", file=sys.stderr)
            return

    # lock 생성
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(datetime.now().isoformat())

    try:
        # 1. 신호 추출
        signals = extract_signals(transcript_path)
        print(f"[reflect] {len(signals)}개 신호 감지", file=sys.stderr)

        if not signals:
            _save_state({"signals": 0, "updated": False})
            return

        # 2. HIGH confidence → mistakes.md 추가
        high_signals = [s for s in signals if s["confidence"] >= 0.8]
        if high_signals:
            _update_mistakes(high_signals)
            print(f"[reflect] {len(high_signals)}개 실수 기록 추가", file=sys.stderr)

        # 3. 세션 요약 저장
        today = datetime.now().strftime("%Y%m%d")
        _save_session_signals(today, signals)

        # 4. 상태 저장
        _save_state({
            "signals": len(signals),
            "high": len(high_signals),
            "updated": len(high_signals) > 0,
            "timestamp": datetime.now().isoformat(),
        })

    finally:
        # lock 해제
        if lock_file.exists():
            lock_file.unlink()


def _update_mistakes(signals: list[dict]):
    """mistakes.md에 새 실수 추가."""
    mistakes_path = MEMORY_DIR / "mistakes.md"

    if not mistakes_path.exists():
        return

    existing = mistakes_path.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    new_entries = []
    for s in signals:
        # 이미 있는 내용이면 스킵
        if s["text"][:50] in existing:
            continue

        entry = f"\n### [{today}] 자동 감지 — {s['type']}\n- 원문: {s['text'][:150]}\n"
        if "match" in s:
            entry += f"- 매칭: `{s['match']}`\n"
        new_entries.append(entry)

    if new_entries:
        with open(mistakes_path, "a", encoding="utf-8") as f:
            f.write("\n## 자동 감지 (reflect)\n")
            for entry in new_entries:
                f.write(entry)


def _save_session_signals(date_str: str, signals: list[dict]):
    """세션 신호를 .state에 JSON으로 저장."""
    output = STATE_DIR / f"signals_{date_str}.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)


def _save_state(state: dict):
    """마지막 실행 상태 저장."""
    state_file = STATE_DIR / "last-reflection.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
