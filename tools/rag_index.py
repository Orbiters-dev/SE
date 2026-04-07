#!/usr/bin/env python3
"""
rag_index.py -- CLI tool to index vault notes into LightRAG.

Usage:
    python tools/rag_index.py --list           # Show indexing status
    python tools/rag_index.py --reindex        # Index all unindexed vault notes
    python tools/rag_index.py --file vault/errlog/errlog_ppc_config_override.md
    python tools/rag_index.py --enqueued       # Process enqueued files
"""
import argparse
import glob
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_client import (
    PROJECT_ROOT, VAULT_DIR, KV_DOCS_PATH, ENQUEUE_DIR,
    is_healthy, index_file, index_text
)


def get_indexed_docs():
    """Get set of already-indexed document content hashes from KV store."""
    if not os.path.exists(KV_DOCS_PATH):
        return set()
    try:
        with open(KV_DOCS_PATH, 'r', encoding='utf-8') as f:
            docs = json.load(f)
        # Return set of first 100 chars of each doc for fuzzy matching
        snippets = set()
        for doc_data in docs.values():
            if isinstance(doc_data, dict):
                content = doc_data.get('content', '')[:100]
            elif isinstance(doc_data, str):
                content = doc_data[:100]
            else:
                continue
            if content:
                snippets.add(content)
        return snippets
    except Exception:
        return set()


def list_status():
    """Show indexing status of all vault notes."""
    md_files = sorted(glob.glob(os.path.join(VAULT_DIR, '**', '*.md'), recursive=True))
    indexed_snippets = get_indexed_docs()
    enqueued = set()
    if os.path.isdir(ENQUEUE_DIR):
        enqueued = {f for f in os.listdir(ENQUEUE_DIR) if f.endswith('.md')}

    healthy = is_healthy(timeout=2)
    print(f"LightRAG Server: {'ONLINE' if healthy else 'OFFLINE'}")
    print(f"Vault notes: {len(md_files)}")
    print(f"KV store docs: {len(indexed_snippets)}")
    print(f"Enqueued: {len(enqueued)}")
    print("=" * 60)

    for fp in md_files:
        basename = os.path.basename(fp)
        rel = os.path.relpath(fp, PROJECT_ROOT).replace('\\', '/')
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                first100 = f.read(100)
        except Exception:
            first100 = ''

        # Check if indexed (fuzzy: first 100 chars match)
        is_indexed = any(first100[:60] in s for s in indexed_snippets) if first100 else False
        is_enqueued = basename in enqueued

        if is_indexed:
            status = 'INDEXED'
        elif is_enqueued:
            status = 'ENQUEUED'
        else:
            status = 'MISSING'

        icon = {'INDEXED': '+', 'ENQUEUED': '~', 'MISSING': '-'}[status]
        print(f"  [{icon}] {rel} ({status})")


def reindex_all():
    """Index all vault notes that aren't already indexed."""
    md_files = sorted(glob.glob(os.path.join(VAULT_DIR, '**', '*.md'), recursive=True))
    healthy = is_healthy(timeout=2)

    if not healthy:
        print("LightRAG server is OFFLINE. Enqueuing files for later indexing.")

    total = len(md_files)
    success = 0
    skipped = 0
    failed = 0

    for i, fp in enumerate(md_files, 1):
        rel = os.path.relpath(fp, PROJECT_ROOT).replace('\\', '/')
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            if len(content) < 20:
                print(f"  [{i}/{total}] SKIP {rel} (too short)")
                skipped += 1
                continue

            if healthy:
                ok = index_file(fp, timeout=10)
                if ok:
                    print(f"  [{i}/{total}] OK   {rel}")
                    success += 1
                else:
                    print(f"  [{i}/{total}] FAIL {rel} (enqueued)")
                    from rag_client import enqueue_for_index
                    enqueue_for_index(fp)
                    failed += 1
                # Small delay to avoid overwhelming the server
                time.sleep(0.5)
            else:
                from rag_client import enqueue_for_index
                enqueue_for_index(fp)
                print(f"  [{i}/{total}] ENQUEUED {rel}")
                success += 1
        except Exception as e:
            print(f"  [{i}/{total}] ERROR {rel}: {e}")
            failed += 1

    print(f"\nDone: {success} indexed, {skipped} skipped, {failed} failed out of {total}")


def index_single(filepath):
    """Index a single file."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    healthy = is_healthy(timeout=2)
    if healthy:
        ok = index_file(filepath, timeout=10)
        print(f"{'OK' if ok else 'FAIL'}: {filepath}")
    else:
        from rag_client import enqueue_for_index
        enqueue_for_index(filepath)
        print(f"ENQUEUED (server offline): {filepath}")


def process_enqueued():
    """Process all files in the enqueue directory."""
    if not os.path.isdir(ENQUEUE_DIR):
        print("No enqueue directory found.")
        return

    files = [f for f in os.listdir(ENQUEUE_DIR) if f.endswith('.md')]
    if not files:
        print("No enqueued files.")
        return

    healthy = is_healthy(timeout=2)
    if not healthy:
        print(f"LightRAG server is OFFLINE. {len(files)} files remain in queue.")
        return

    success = 0
    for fname in files:
        fp = os.path.join(ENQUEUE_DIR, fname)
        try:
            ok = index_file(fp, timeout=10)
            if ok:
                os.remove(fp)
                print(f"  OK + removed: {fname}")
                success += 1
            else:
                print(f"  FAIL (kept): {fname}")
            time.sleep(0.5)
        except Exception as e:
            print(f"  ERROR: {fname}: {e}")

    print(f"\nProcessed: {success}/{len(files)}")


def main():
    parser = argparse.ArgumentParser(description='Index vault notes into LightRAG')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true', help='Show indexing status')
    group.add_argument('--reindex', action='store_true', help='Index all unindexed vault notes')
    group.add_argument('--file', help='Index a specific file')
    group.add_argument('--enqueued', action='store_true', help='Process enqueued files')
    args = parser.parse_args()

    if args.list:
        list_status()
    elif args.reindex:
        reindex_all()
    elif args.file:
        index_single(args.file)
    elif args.enqueued:
        process_enqueued()


if __name__ == '__main__':
    main()
