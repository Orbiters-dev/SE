"""
Windows Utility — 공통 유틸리티
================================
Windows 환경에서 반복 발생하는 문제를 한 번에 해결한다.
모든 Python 스크립트 상단에서 import하면 끝.

반복 실수 방지:
  - M-001: cp949 UnicodeEncodeError → stdout/stderr utf-8 강제
  - M-003: SSL revocation check 실패 → ssl 컨텍스트 제공
  - M-004: 절대경로 하드코딩 → 프로젝트 루트 자동 탐지

Usage:
    from win_utils import setup_encoding, SSL_CTX, PROJECT_ROOT

    # 또는 import만 하면 encoding은 자동 적용:
    import win_utils
"""

import os
import sys
import ssl

# ── M-001: Windows cp949 stdout/stderr → utf-8 ──────────────────────
def setup_encoding():
    """Force utf-8 on stdout/stderr. Safe to call multiple times."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Auto-apply on import
setup_encoding()

# ── M-003: SSL context that skips revocation check ──────────────────
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# ── M-004: Project root auto-detection ──────────────────────────────
# tools/ is one level below project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR = os.path.join(PROJECT_ROOT, ".tmp")

def ensure_tmp(*subdirs: str) -> str:
    """Ensure .tmp/{subdirs} exists and return the path."""
    path = os.path.join(TMP_DIR, *subdirs)
    os.makedirs(path, exist_ok=True)
    return path
