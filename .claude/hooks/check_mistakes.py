#!/usr/bin/env python3
"""
Mistake Checker Hook — PreToolUse
Pattern-matches tool input against behavioral rules from mistakes.md (compressed format).
"""
import sys
import json
import re
import os

sys.stdin.reconfigure(encoding='utf-8', errors='replace')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Rules: pattern → warning message ─────────────────────────
# Based on mistakes.md compressed rules. No external file parsing needed
# because CLAUDE.md + these static rules cover all known patterns.

BASH_RULES = [
    # Rule 3: Amazon Ads API
    (r'campaignId|adGroupId', lambda cmd: 'string' not in cmd,
     '[R3] Amazon Ads ID는 반드시 string으로 전송'),

    # Rule 4: bulk operations
    (r'for\s+.*\s+in\s+.*range\s*\(\s*\d{4,}', lambda _: True,
     '[R4] 대량 작업(1000+건) — 세은에게 범위 확인했는지?'),

    # Rule 5: .tmp in GitHub Actions context
    (r'\.tmp/', lambda cmd: 'actions' in cmd.lower() or 'workflow' in cmd.lower(),
     '[R5] .tmp/는 Actions에서 매번 사라짐 — git-committed 파일 또는 DB에서 로드'),

    # Rule 2: API response — partial success
    (r'curl.*-X\s*(POST|PUT|PATCH)', lambda _: True,
     '[R2] API 응답: HTTP 200이어도 body 각 item code 검증 필요'),
]

WRITE_RULES = [
    # Rule 8: shared file location
    (r'\.claude[/\\]', lambda path, _: 'memory' in path or 'data' in path,
     '[R8] 공유 파일을 ~/.claude/에 저장하면 다른 컴퓨터에서 안 보임'),

    # Rule 7: content truncation
    (r'\.{3}|truncat|자르', lambda _, content: True,
     '[R7] 콘텐츠 텍스트 절대 자르지 않기 — expandable UI 사용'),

    # Python encoding (from CLAUDE.md)
    (r'\.py$', lambda path, content: 'print(' in content and 'reconfigure' not in content,
     '[CLAUDE.md] Python print() 있으면 sys.stdout.reconfigure(encoding="utf-8") 필수'),
]


def check_bash(command):
    warnings = []
    for pattern, condition, msg in BASH_RULES:
        if re.search(pattern, command, re.IGNORECASE) and condition(command):
            warnings.append(msg)
    return warnings


def check_write_edit(tool_input):
    warnings = []
    file_path = tool_input.get('file_path', '')
    content = tool_input.get('content', '') or tool_input.get('new_string', '')

    for pattern, condition, msg in WRITE_RULES:
        if re.search(pattern, file_path, re.IGNORECASE):
            if condition(file_path, content):
                warnings.append(msg)
    return warnings


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get('tool_name', '')
    tool_input = hook_input.get('tool_input', {})

    if tool_name not in ('Bash', 'Write', 'Edit'):
        sys.exit(0)

    if tool_name == 'Bash':
        warnings = check_bash(tool_input.get('command', ''))
    else:
        warnings = check_write_edit(tool_input)

    if not warnings:
        sys.exit(0)

    print(json.dumps(
        {"systemMessage": "\n".join(warnings)},
        ensure_ascii=False
    ))


if __name__ == '__main__':
    main()
