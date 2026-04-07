#!/usr/bin/env python3
"""
Mistake Checker Hook - PreToolUse hook that warns about past mistakes.
Reads mistakes.md and pattern-matches against current tool input.
Also queries vault/LightRAG for related past issues (Karpathy auto-context loop).
"""
import sys
import json
import re
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MISTAKES_PATH = os.path.join(PROJECT_ROOT, 'memory', 'mistakes.md')

# Commands that are too trivial to warrant vault lookup
SKIP_VAULT_PATTERNS = re.compile(
    r'^(ls|cat|head|tail|echo|pwd|cd|mkdir|cp|mv|rm|wc|'
    r'git\s+(status|log|diff|branch|show|stash)|'
    r'which|whoami|hostname|date|env|set|export)(\s|$)',
    re.IGNORECASE
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


def check_vault_context(tool_name, tool_input):
    """Query vault/RAG for related past issues. Returns context string or empty."""
    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tools'))
        from rag_client import query as rag_query
    except Exception:
        return ''

    # Extract search terms based on tool type
    if tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        # Skip trivial commands
        if SKIP_VAULT_PATTERNS.match(cmd.strip()):
            return ''
        # Extract script name or key command
        script_match = re.search(r'python\S*\s+\S*?(\w+)\.py', cmd)
        if script_match:
            search_term = script_match.group(1).replace('_', ' ')
        else:
            # Use first meaningful token
            tokens = cmd.strip().split()
            search_term = tokens[0] if tokens else ''
    else:
        file_path = tool_input.get('file_path', '')
        basename = os.path.basename(file_path).replace('.py', '').replace('_', ' ')
        search_term = basename

    if not search_term or len(search_term) < 3:
        return ''

    # Query with tight timeout (1s) to avoid blocking UX
    result = rag_query(f"{search_term} error issues", mode="local", top_k=2, timeout=1)
    if result and len(result.strip()) > 20:
        # Truncate to keep systemMessage short
        return result[:400]
    return ''


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

    # Pattern-based mistake warnings
    matched = []
    if entries:
        if tool_name == 'Bash':
            matched = check_bash(tool_input.get('command', ''), entries)
        else:
            matched = check_write_edit(tool_input, entries)

    # Deduplicate
    seen = set()
    unique = [(mid, e) for mid, e in matched if mid not in seen and not seen.add(mid)]

    lines = []
    for mid, entry in unique:
        agent_tag = f" ({entry['agent']})" if entry.get('agent') else ''
        lines.append(f"[{mid}]{agent_tag} {entry['title']}")
        if entry['prevention'] and entry['prevention'] != '(확인 후 추가)':
            lines.append(f"  → {entry['prevention']}")

    # Vault/RAG context lookup (non-blocking)
    vault_ctx = ''
    try:
        vault_ctx = check_vault_context(tool_name, tool_input)
    except Exception:
        pass

    if vault_ctx:
        lines.append(f"\n📚 VAULT CONTEXT:\n{vault_ctx}")

    if not lines:
        sys.exit(0)

    print(json.dumps(
        {"systemMessage": "⚠️ MISTAKE MEMORY:\n" + "\n".join(lines)},
        ensure_ascii=False
    ))


if __name__ == '__main__':
    main()
