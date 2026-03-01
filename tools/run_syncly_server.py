"""
Syncly 로컬 웹훅 서버
======================
n8n Schedule Trigger → HTTP Request → 이 서버 → 스크립트 백그라운드 실행

POST /sync  → 즉시 202 응답 후 백그라운드에서 fetch + sync 실행
             (ngrok 30초 제한 우회)
GET  /health → 서버 상태 확인
GET  /status → 마지막 실행 결과 확인

실행:
  py tools/run_syncly_server.py
  py tools/run_syncly_server.py --port 5050
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE   = sys.executable
SHEET_ID     = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"
LOG_FILE     = PROJECT_ROOT / ".tmp" / "syncly_run.log"

# 마지막 실행 상태 (메모리)
_last_status = {"running": False, "last_run": None, "success": None, "summary": ""}
_lock = threading.Lock()


def run_sync_background():
    """백그라운드 스레드에서 fetch → sync 순차 실행."""
    with _lock:
        _last_status["running"] = True
        _last_status["last_run"] = datetime.now().isoformat()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"\n{'='*50}", f"[{ts}] 동기화 시작"]
    success = True

    # ── Step 1: Syncly 다운로드 ──
    lines.append("[1/2] fetch_syncly_export.py 실행...")
    try:
        r1 = subprocess.run(
            [PYTHON_EXE, str(PROJECT_ROOT / "tools" / "fetch_syncly_export.py")],
            capture_output=True, timeout=180,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        out1 = (r1.stdout + r1.stderr).decode("utf-8", errors="replace")[-600:]
        lines.append(out1)
        if r1.returncode != 0:
            lines.append("[ERROR] fetch 실패")
            success = False
        else:
            lines.append("[1/2] fetch 완료")
    except subprocess.TimeoutExpired:
        lines.append("[ERROR] fetch 타임아웃 (180s)")
        success = False
    except Exception as e:
        lines.append(f"[ERROR] fetch 예외: {e}")
        success = False

    # ── Step 2: Google Sheets 동기화 ──
    if success:
        lines.append("[2/2] sync_syncly_to_sheets.py 실행...")
        cmd = [PYTHON_EXE, str(PROJECT_ROOT / "tools" / "sync_syncly_to_sheets.py")]
        if SHEET_ID:
            cmd += ["--sheet-id", SHEET_ID]
        try:
            r2 = subprocess.run(
                cmd, capture_output=True, timeout=300,
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            out2 = (r2.stdout + r2.stderr).decode("utf-8", errors="replace")[-600:]
            lines.append(out2)
            if r2.returncode != 0:
                lines.append("[ERROR] sync 실패")
                success = False
            else:
                lines.append("[2/2] sync 완료")
        except subprocess.TimeoutExpired:
            lines.append("[ERROR] sync 타임아웃 (300s)")
            success = False
        except Exception as e:
            lines.append(f"[ERROR] sync 예외: {e}")
            lines.append(traceback.format_exc())
            success = False

    status_str = "SUCCESS" if success else "FAILED"
    lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] 완료 - {status_str}")

    log_text = "\n".join(lines)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_text + "\n")
    try:
        print(log_text)
    except UnicodeEncodeError:
        print(log_text.encode("ascii", errors="replace").decode("ascii"))

    with _lock:
        _last_status["running"] = False
        _last_status["success"] = success
        _last_status["summary"] = status_str


class SyncHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
            })
        elif self.path == "/status":
            self._json(200, dict(_last_status))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/sync":
            self.send_response(404)
            self.end_headers()
            return

        with _lock:
            already_running = _last_status["running"]

        if already_running:
            self._json(409, {"accepted": False, "reason": "already running"})
            return

        # 즉시 202 응답 → 백그라운드에서 실행
        self._json(202, {
            "accepted": True,
            "message": "sync started in background",
            "timestamp": datetime.now().isoformat(),
            "status_url": "/status",
        })

        t = threading.Thread(target=run_sync_background, daemon=True)
        t.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] /sync 요청 수신 -> 백그라운드 실행 시작")

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, format, *args):
        pass  # 기본 HTTP 로그 억제


def main():
    global SHEET_ID
    parser = argparse.ArgumentParser(description="Syncly 로컬 웹훅 서버")
    parser.add_argument("--port",     type=int, default=5050)
    parser.add_argument("--sheet-id", default=SHEET_ID)
    args   = parser.parse_args()
    SHEET_ID = args.sheet_id

    server = HTTPServer(("0.0.0.0", args.port), SyncHandler)
    print("=" * 55)
    print("  Syncly 웹훅 서버")
    print("=" * 55)
    print(f"  POST /sync    → 동기화 실행 (즉시 202 응답)")
    print(f"  GET  /health  → 서버 상태")
    print(f"  GET  /status  → 마지막 실행 결과")
    print(f"  Port : {args.port}")
    print(f"  Sheet: {SHEET_ID}")
    print(f"  Log  : {LOG_FILE}")
    print(f"  종료 : Ctrl+C")
    print("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] 종료")


if __name__ == "__main__":
    main()
