#!/usr/bin/env python3
"""
vault_auto_index.py -- PostToolUse hook for Write/Edit.
When a file under vault/ is written or edited, auto-index it into LightRAG.
"""
import sys
import json
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_DIR = os.path.join(PROJECT_ROOT, 'vault')


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get('tool_name', '')
    if tool_name not in ('Write', 'Edit'):
        sys.exit(0)

    tool_input = hook_input.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    # Only index vault files
    normalized = os.path.normpath(file_path).replace('\\', '/')
    if '/vault/' not in normalized and not normalized.startswith('vault/'):
        sys.exit(0)

    # Fire-and-forget index
    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tools'))
        from rag_client import index_file, enqueue_for_index
        if index_file(file_path, timeout=5):
            basename = os.path.basename(file_path)
            print(json.dumps(
                {"systemMessage": f"[RAG] Indexed vault note: {basename}"},
                ensure_ascii=False
            ))
        else:
            enqueue_for_index(file_path)
    except Exception:
        pass


if __name__ == '__main__':
    main()
