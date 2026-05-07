"""LightRAG vault indexer — POST /documents/text helper.

Used by `.claude/hooks/harness_runner.py` for Step 5 automation:
  - Write|Edit on vault/(memory|rules|handoff|skills)/*.md
  - → auto POST to LightRAG, no manual curl needed

Per CLAUDE.md RULE 2 (vault auto-write):
  매 Phase / sub-Phase 결과 → vault/memory/ 작성 → LightRAG index 자동.

Standalone CLI:
  python tools/vault_indexer.py vault/memory/foo.md
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

LIGHTRAG_URL = os.environ.get("LIGHTRAG_URL", "http://127.0.0.1:9621")


def index_vault_doc(abs_path: str, vault_root: str = "") -> dict:
    """POST a markdown file's content to LightRAG /documents/text.

    Returns:
      {"ok": True, "file_source": "...", "status": "..."}  on success
      {"ok": False, "error": "..."}                         on failure
    """
    p = Path(abs_path)
    if not p.exists():
        return {"ok": False, "error": f"file not found: {abs_path}"}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "error": f"read failed: {exc}"}

    # Compute file_source as relative to vault root (or just basename if outside)
    if vault_root:
        try:
            file_source = str(p.relative_to(vault_root)).replace("\\", "/")
        except ValueError:
            file_source = p.name
    else:
        # Try to detect vault/ in path
        parts = list(p.parts)
        try:
            i = parts.index("vault")
            file_source = "/".join(parts[i + 1:])
        except ValueError:
            file_source = p.name

    payload = json.dumps({
        "text": text,
        "file_source": file_source,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{LIGHTRAG_URL}/documents/text",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
            return {
                "ok": True,
                "file_source": file_source,
                "status": body.get("status", "submitted"),
                "track_id": body.get("track_id"),
            }
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            err_body = ""
        return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"LightRAG unreachable: {e.reason}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def is_lightrag_healthy() -> bool:
    """Quick health check (1s timeout)."""
    try:
        req = urllib.request.Request(f"{LIGHTRAG_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python tools/vault_indexer.py <vault-md-path>", file=sys.stderr)
        sys.exit(1)
    result = index_vault_doc(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
