# -*- coding: utf-8 -*-
"""판정 보드 claude.ai 아티팩트용 HTML 빌더.

아티팩트 샌드박스는 외부 fetch 를 CSP 로 차단(2026-10-12 공개 페이지 렌더 실측)
→ actions.json 을 window.__ACTIONS_INLINE 으로 HTML 안에 구워 넣어 탭이 뜨게 한다.
아티팩트는 스냅샷 — 데이터는 빌드 시점 기준 (라이브 = https://jp-perf-board.vercel.app).

사용: PYTHONIOENCODING=utf-8 python tools/build_board_artifact.py
출력: .tmp/jp_perf_actions/board_artifact.html (+ 클립보드 적재는 호출측에서)
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SRC_HTML = BASE / "web" / "jp_perf_board" / "index.html"
SRC_JSON = BASE / ".tmp" / "jp_perf_actions" / "actions.json"
OUT = BASE / ".tmp" / "jp_perf_actions" / "board_artifact.html"

html = SRC_HTML.read_text(encoding="utf-8")
data = json.loads(SRC_JSON.read_text(encoding="utf-8"))

marker = "</head>"
if marker not in html:
    raise SystemExit("</head> 마커 없음 — index.html 구조 변경됨")
inline = ("<script>/* 아티팩트용 인라인 데이터 (빌드 시점 스냅샷) */\n"
          "window.__ACTIONS_INLINE = " + json.dumps(data, ensure_ascii=False) + ";</script>\n")
html = html.replace(marker, inline + marker, 1)

OUT.write_text(html, encoding="utf-8")
print(f"산출: {OUT} ({OUT.stat().st_size / 1024:.1f}KB) — 데이터 기준 {data.get('generated_at')}")
