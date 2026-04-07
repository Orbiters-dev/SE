#!/usr/bin/env python3
"""
rag_query.py -- CLI tool to query the LightRAG knowledge base.

Usage:
    python tools/rag_query.py "PPC config error"
    python tools/rag_query.py "pipeline accuracy" --mode local
    python tools/rag_query.py "n8n active field" --mode hybrid --top-k 5
"""
import argparse
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_client import query, is_healthy


def main():
    parser = argparse.ArgumentParser(description='Query LightRAG knowledge base')
    parser.add_argument('query_text', help='Search query')
    parser.add_argument('--mode', default='hybrid', choices=['hybrid', 'local', 'naive'],
                        help='Search mode (default: hybrid)')
    parser.add_argument('--top-k', type=int, default=5, help='Number of results (default: 5)')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds (default: 30)')
    args = parser.parse_args()

    healthy = is_healthy(timeout=2)
    tier = "LightRAG API" if healthy else "fallback (KV/vault grep)"
    print(f"[Search via {tier}]")
    print(f"Query: {args.query_text}")
    print(f"Mode: {args.mode} | Top-K: {args.top_k}")
    print("=" * 60)

    result = query(args.query_text, mode=args.mode, top_k=args.top_k, timeout=args.timeout)
    if result:
        print(result)
    else:
        print("(No results found)")


if __name__ == '__main__':
    main()
