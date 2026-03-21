#!/usr/bin/env python3
"""
Mistake Checker Hook - PreToolUse hook that warns about past mistakes.
Reads mistakes.md and pattern-matches against current tool input.
"""
import sys
import json
import re
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MISTAKES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'memory', 'mistakes.md'
)

# Bash command patterns → mistake IDs to warn about
BASH_WARN_PATTERNS = [
    (r'python.*\.py', ['M-001'], 'cp949 encoding 주의'),
    (r'python3?\s+-c\s+', ['M-002'], 'python -c 따옴표 중첩 주의'),
    (r'curl\s+https?://', ['M-003'], 'curl -sk 플래그 확인'),
    (r'curl.*n8n.*(?:POST|PUT|-X POST|-X PUT)', ['M-009'], 'n8n active 필드 제거 확인'),
    (r'n8n.*json|json.*n8n', ['M-010'], 'n8n JSON 인코딩 확인'),
]

# Write/Edit content patterns → mistake IDs
CONTENT_WARN_PATTERNS = [
    (r'text-embedding-004', ['M-005'], 'content'),
    (r'import google\.generativeai|google\.generativeai', ['M-006'], 'content'),
    (r"[A-Za-z ]+![A-Z]\d", ['M-004'], 'content'),
]

# Write/Edit path patterns → mistake IDs
PATH_WARN_PATTERNS = [
    (r'\.py$', ['M-001'], 'path'),  # only warn if print() without reconfigure
]


def parse_mistakes(filepath):
    """Parse mistakes.md into structured entries."""
    if not os.path.exists(filepath):
        return {}

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = {}
    sections = re.split(r'(?=### M-\d+)', content)

    for section in sections:
        match = re.match(r'### (M-\d+): (.+)', section)
        if not match:
            continue
        mid = match.group(1)
        title = match.group(2).strip()
        agent = prevention = ''
        for line in section.split('\n'):
            if '**에이전트**' in line:
                agent = line.split('**에이전트**:')[-1].strip()
            if '**예방**' in line:
                prevention = line.split('**예방**:')[-1].strip()
        entries[mid] = {'title': title, 'agent': agent, 'prevention': prevention}

    return entries


def check_bash(command, entries):
    warnings = []
    for pattern, mids, tag in BASH_WARN_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            # M-003: only warn if -sk is missing
            if 'M-003' in mids:
                if re.search(r'-[a-z]*s[a-z]*k|--insecure', command):
                    continue
            # M-001: only warn if py file but not checking encoding here (too complex for bash)
            for mid in mids:
                if mid in entries:
                    warnings.append((mid, entries[mid]))
    return warnings


def check_write_edit(tool_input, entries):
    warnings = []
    file_path = tool_input.get('file_path', '')
    content = tool_input.get('content', '') or tool_input.get('new_string', '')

    # Content patterns
    for pattern, mids, _ in CONTENT_WARN_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            for mid in mids:
                if mid in entries:
                    warnings.append((mid, entries[mid]))

    # Path patterns
    for pattern, mids, _ in PATH_WARN_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            if 'M-001' in mids:
                if 'print(' in content and 'reconfigure' not in content:
                    for mid in mids:
                        if mid in entries:
                            warnings.append((mid, entries[mid]))

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

    entries = parse_mistakes(MISTAKES_PATH)
    if not entries:
        sys.exit(0)

    if tool_name == 'Bash':
        matched = check_bash(tool_input.get('command', ''), entries)
    else:
        matched = check_write_edit(tool_input, entries)

    # Deduplicate
    seen = set()
    unique = [(mid, e) for mid, e in matched if mid not in seen and not seen.add(mid)]

    if not unique:
        sys.exit(0)

    lines = []
    for mid, entry in unique:
        agent_tag = f" ({entry['agent']})" if entry.get('agent') else ''
        lines.append(f"[{mid}]{agent_tag} {entry['title']}")
        if entry['prevention'] and entry['prevention'] != '(확인 후 추가)':
            lines.append(f"  → {entry['prevention']}")

    print(json.dumps(
        {"systemMessage": "⚠️ MISTAKE MEMORY:\n" + "\n".join(lines)},
        ensure_ascii=False
    ))


if __name__ == '__main__':
    main()
