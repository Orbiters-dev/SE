#!/usr/bin/env python3
"""
Mistake Checker Hook - PreToolUse hook that warns about past mistakes.
Reads mistakes.md, pattern-matches against current tool input, returns warnings.
"""
import sys
import json
import re
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MISTAKES_PATH = os.path.expanduser(
    '~/.claude/projects/c--Users-wjcho-Desktop-WJ-Test1/memory/mistakes.md'
)

# Pattern -> mistake IDs mapping
# Each key is a regex or substring to match against tool input
TOOL_PATTERNS = {
    # Bash patterns
    'Bash': [
        # M-001: cp949 - python script without encoding guard
        (r'python.*\.py', ['M-001'], 'cp949 encoding'),
        # M-002: inline python -c with quotes
        (r'python3?\s+-c\s+', ['M-002'], 'python -c quote nesting'),
        # M-003: curl without -sk
        (r'curl\s+(?!.*-[sk]{2})(?!.*-ks)https?://', ['M-003'], 'curl SSL'),
        # M-009: n8n POST with active field
        (r'curl.*n8n.*POST', ['M-009'], 'n8n POST active field'),
        # M-010: n8n JSON encoding
        (r'n8n.*json', ['M-010'], 'n8n JSON cp949'),
    ],
    # Write/Edit patterns (checked against file content + path)
    'Write': [
        # M-001: Python file without reconfigure
        (r'\.py$', ['M-001'], 'path'),
        # M-005: wrong embedding model
        (r'text-embedding-004', ['M-005'], 'content'),
        # M-006: deprecated genai import
        (r'import google\.generativeai', ['M-006'], 'content'),
        (r'google\.generativeai', ['M-006'], 'content'),
        # M-004: Sheets range without quotes
        (r"[A-Za-z ]+![A-Z]\d", ['M-004'], 'content'),
    ],
}
TOOL_PATTERNS['Edit'] = TOOL_PATTERNS['Write']


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
        title = match.group(2)
        agent = ''
        prevention = ''
        for line in section.split('\n'):
            if '**\uc5d0\uc774\uc804\ud2b8**' in line:  # 에이전트
                agent = line.split('**\uc5d0\uc774\uc804\ud2b8**:')[-1].strip()
            if '**\uc608\ubc29**' in line:  # 예방
                prevention = line.split('**\uc608\ubc29**:')[-1].strip()

        entries[mid] = {'title': title, 'agent': agent, 'prevention': prevention}

    return entries


def check_bash(command, entries):
    """Check Bash command against known mistake patterns."""
    warnings = []

    for pattern, mids, _tag in TOOL_PATTERNS.get('Bash', []):
        if re.search(pattern, command, re.IGNORECASE):
            # M-003: only warn if curl is missing -sk
            if 'M-003' in mids:
                if re.search(r'-[a-z]*s[a-z]*k|--insecure', command):
                    continue
            for mid in mids:
                if mid in entries:
                    warnings.append((mid, entries[mid]))

    return warnings


def check_write_edit(tool_input, entries):
    """Check Write/Edit against known mistake patterns."""
    warnings = []
    file_path = tool_input.get('file_path', '')
    content = tool_input.get('content', '') or tool_input.get('new_string', '')

    for pattern, mids, match_target in TOOL_PATTERNS.get('Write', []):
        target = file_path if match_target == 'path' else content
        if re.search(pattern, target, re.IGNORECASE):
            # M-001: only warn for .py files that have print() but no reconfigure
            if 'M-001' in mids and match_target == 'path':
                if file_path.endswith('.py') and 'print(' in content:
                    if 'reconfigure' not in content:
                        for mid in mids:
                            if mid in entries:
                                warnings.append((mid, entries[mid]))
                continue

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

    if tool_name not in ('Write', 'Edit', 'Bash'):
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
    unique = []
    for mid, entry in matched:
        if mid not in seen:
            seen.add(mid)
            unique.append((mid, entry))

    if not unique:
        sys.exit(0)

    lines = []
    for mid, entry in unique:
        agent_tag = f" ({entry['agent']})" if entry.get('agent') else ''
        lines.append(f"[{mid}]{agent_tag} {entry['title']}")
        if entry['prevention']:
            lines.append(f"  -> {entry['prevention']}")

    output = {
        "systemMessage": "MISTAKE MEMORY:\n" + "\n".join(lines)
    }

    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
