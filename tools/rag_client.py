#!/usr/bin/env python3
"""
rag_client.py -- Shared LightRAG client with 3-tier fallback.

Tier 1: LightRAG HTTP API (localhost:9621)
Tier 2: Local KV store JSON grep (lightrag/rag_storage/)
Tier 3: Vault file grep (vault/**/*.md)

Used by hooks (mistake_checker, vault_auto_index) and CLI tools (rag_query, rag_index).
"""
import glob
import json
import os
import re
import sys
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIGHTRAG_URL = os.environ.get("LIGHTRAG_URL", "http://localhost:9621")
KV_DOCS_PATH = os.path.join(PROJECT_ROOT, "lightrag", "rag_storage", "kv_store_full_docs.json")
VAULT_DIR = os.path.join(PROJECT_ROOT, "vault")
ENQUEUE_DIR = os.path.join(PROJECT_ROOT, "lightrag", "inputs", "__enqueued__")


def is_healthy(timeout=1):
    """Check if LightRAG server is reachable. Returns bool."""
    try:
        req = urllib.request.Request(f"{LIGHTRAG_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") == "healthy"
    except Exception:
        return False


def query(text, mode="hybrid", top_k=3, timeout=3):
    """Query for related context. 3-tier fallback. Returns string or empty."""
    # Tier 1: LightRAG API
    result = _query_api(text, mode, top_k, timeout)
    if result:
        return result

    # Tier 2: KV store JSON grep
    result = _query_kv_store(text, top_k)
    if result:
        return result

    # Tier 3: Vault file grep
    return _query_vault_files(text, top_k)


def index_text(text, timeout=5):
    """Index text into LightRAG. Fire-and-forget. Returns True on success."""
    if not text or len(text) < 20:
        return False
    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{LIGHTRAG_URL}/documents/text",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def index_file(filepath, timeout=5):
    """Read file and index into LightRAG. Returns True on success."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) < 20:
            return False
        return index_text(content, timeout)
    except Exception:
        return False


def enqueue_for_index(filepath):
    """Copy file to lightrag/inputs/__enqueued__/ for batch indexing later."""
    try:
        os.makedirs(ENQUEUE_DIR, exist_ok=True)
        basename = os.path.basename(filepath)
        dst = os.path.join(ENQUEUE_DIR, basename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


# ── Internal: Tier 1 - LightRAG API ──────────────────────────────

def _query_api(text, mode, top_k, timeout):
    try:
        payload = json.dumps({
            "query": text, "mode": mode,
            "top_k": top_k, "only_need_context": True
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{LIGHTRAG_URL}/query",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, str):
                return data.strip() or ""
            if isinstance(data, dict):
                return (data.get("response") or data.get("result") or "").strip()
            return ""
    except Exception:
        return ""


# ── Internal: Tier 2 - KV store JSON grep ────────────────────────

def _query_kv_store(text, top_k):
    """Search through kv_store_full_docs.json for matching documents."""
    if not os.path.exists(KV_DOCS_PATH):
        return ""
    try:
        with open(KV_DOCS_PATH, "r", encoding="utf-8") as f:
            docs = json.load(f)

        keywords = set(re.findall(r'[a-zA-Z가-힣]{2,}', text.lower()))
        if not keywords:
            return ""

        scored = []
        for doc_id, doc_data in docs.items():
            content = ""
            if isinstance(doc_data, dict):
                content = doc_data.get("content", "") or doc_data.get("content_summary", "") or str(doc_data)
            elif isinstance(doc_data, str):
                content = doc_data
            content_lower = content.lower()
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scored.append((score, content[:500]))

        scored.sort(key=lambda x: -x[0])
        results = [c for _, c in scored[:top_k]]
        return "\n---\n".join(results) if results else ""
    except Exception:
        return ""


# ── Internal: Tier 3 - Vault file grep ───────────────────────────

def _query_vault_files(text, top_k):
    """Search through vault/*.md files for matching content."""
    if not os.path.isdir(VAULT_DIR):
        return ""
    try:
        keywords = set(re.findall(r'[a-zA-Z가-힣]{2,}', text.lower()))
        if not keywords:
            return ""

        md_files = glob.glob(os.path.join(VAULT_DIR, "**", "*.md"), recursive=True)
        scored = []
        for fp in md_files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read(4096)  # read first 4KB only
            except Exception:
                continue
            content_lower = content.lower()
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scored.append((score, content[:500]))

        scored.sort(key=lambda x: -x[0])
        results = [c for _, c in scored[:top_k]]
        return "\n---\n".join(results) if results else ""
    except Exception:
        return ""
