#!/bin/bash
# hook-stop.sh — 세션 종료 시 자동 학습 실행
# Claude Code Stop hook에서 호출됨

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$SCRIPT_DIR/../.state"
PYTHON="python"

# .state 디렉토리 확인
mkdir -p "$STATE_DIR"

# 활성화 여부 확인
ENABLED_FILE="$STATE_DIR/auto-reflection.json"
if [ -f "$ENABLED_FILE" ]; then
    ENABLED=$(python -c "import json; print(json.load(open('$ENABLED_FILE')).get('enabled', True))" 2>/dev/null)
    if [ "$ENABLED" = "False" ]; then
        exit 0
    fi
fi

# lock 체크 (10분 이내 실행됐으면 스킵)
LOCK_FILE="$STATE_DIR/reflection.lock"
if [ -f "$LOCK_FILE" ]; then
    # Windows compatible: use stat instead of date -r
    if command -v stat >/dev/null 2>&1; then
        LOCK_MTIME=$(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)
    else
        LOCK_MTIME=0
    fi
    NOW=$(date +%s)
    LOCK_AGE=$(( NOW - LOCK_MTIME ))
    if [ "$LOCK_AGE" -lt 600 ]; then
        exit 0
    fi
fi

# stdin에서 transcript_path 추출
TRANSCRIPT_PATH=""
if [ ! -t 0 ]; then
    INPUT=$(cat)
    TRANSCRIPT_PATH=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('transcript_path',''))" 2>/dev/null)
fi

if [ -z "$TRANSCRIPT_PATH" ]; then
    exit 0
fi

# 백그라운드로 reflect.py 실행 (세션 종료를 블로킹하지 않음)
TRANSCRIPT_PATH="$TRANSCRIPT_PATH" $PYTHON "$SCRIPT_DIR/reflect.py" "$TRANSCRIPT_PATH" &

exit 0
