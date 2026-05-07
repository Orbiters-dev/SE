#!/usr/bin/env python3
"""LightRAG vault reindex helper — 지후님 회사컴 셋업 후 또는 원준 본인 환경 fix 후 사용.

쓰임:
  1. ollama pull bge-m3:latest 완료
  2. ollama pull mistral-nemo:latest 완료
  3. LightRAG server 가동 확인 (curl http://127.0.0.1:9621/health)
  4. python lightrag_reindex_helper.py [--vault-root <path>] [--lightrag-url <url>]

동작:
  - vault/(memory|rules|handoff|skills)/*.md 일괄 POST /documents/text
  - 이미 indexed 된 doc 도 LightRAG 가 dedup 처리 (file_source 기준)
  - 결과: OK / FAIL / DUP 카운트 + per-file status

본 스크립트는 지후님 회사컴 셋업 직후 단독 실행해도 OK.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request


def post_doc(lightrag_url: str, file_path: pathlib.Path, file_source: str) -> tuple[str, str]:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    payload = json.dumps({"text": text, "file_source": file_source}).encode("utf-8")
    req = urllib.request.Request(
        f"{lightrag_url}/documents/text",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            status = body.get("status", "?")
            return status, body.get("track_id", "")[:24]
    except urllib.error.HTTPError as e:
        return f"HTTP_{e.code}", ""
    except Exception as e:
        return f"ERR_{type(e).__name__}", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-root", default="vault",
                    help="vault root (default: ./vault — SE 환경)")
    ap.add_argument("--lightrag-url", default="http://127.0.0.1:9621",
                    help="LightRAG server URL")
    ap.add_argument("--include", nargs="*",
                    default=["memory", "rules", "handoff", "skills",
                            "MOC", "architecture", "errlog", "feedback", "projects"],
                    help="vault subdirs to index (SE: 5-tier + 자유 형식 5개)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list files only, no POST")
    args = ap.parse_args()

    root = pathlib.Path(args.vault_root)
    if not root.exists():
        print(f"FAIL: vault root not found: {root}")
        return 1

    files = []
    for sub in args.include:
        sub_dir = root / sub
        if sub_dir.exists():
            files.extend(sorted(sub_dir.rglob("*.md")))

    print(f"Found {len(files)} markdown files under {args.include} in {root}")
    if args.dry_run:
        for f in files:
            print(f"  {f.relative_to(root)}")
        return 0

    # health check
    try:
        with urllib.request.urlopen(f"{args.lightrag_url}/health", timeout=5) as resp:
            h = json.loads(resp.read().decode("utf-8", errors="replace"))
            if h.get("status") != "healthy":
                print(f"FAIL: LightRAG not healthy: {h}")
                return 2
    except Exception as e:
        print(f"FAIL: cannot reach {args.lightrag_url}: {e}")
        return 2

    counts = {"OK": 0, "DUP": 0, "FAIL": 0}
    for f in files:
        rel = str(f.relative_to(root)).replace("\\", "/")
        status, track = post_doc(args.lightrag_url, f, rel)
        if status in ("inserted", "success"):
            counts["OK"] += 1
            tag = "OK"
        elif status in ("duplicated", "exists"):
            counts["DUP"] += 1
            tag = "DUP"
        else:
            counts["FAIL"] += 1
            tag = "FAIL"
        print(f"  [{tag:4}] {rel}  status={status}  track={track}")
        time.sleep(0.1)  # gentle on server

    print(f"\nSummary: OK={counts['OK']}  DUP={counts['DUP']}  FAIL={counts['FAIL']}  total={len(files)}")
    print("\nNote: bge-m3 미설치 시 server 200 OK 받지만 백엔드 embed 단계에서 silent fail.")
    print("        ollama pull bge-m3:latest 가 선행되어야 actual indexing 됨.")
    print("        체크: curl http://127.0.0.1:9621/documents 또는 webui:9621 의 doc_status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
