"""
Pre-execution healthcheck utility.
Prevents M-044 (ConnectionRefused) and M-051 (missing modules).

Usage:
    from healthcheck import check_server, check_module, run_checks

    check_server("https://orbitools.orbiters.co.kr")  # M-044
    check_module("playwright")  # M-051

    # Or batch:
    run_checks(servers=["https://orbitools.orbiters.co.kr"], modules=["playwright", "gspread"])
"""

import importlib
import sys
import urllib.request
from typing import List, Tuple

from win_utils import SSL_CTX

# ── M-044: Server connectivity check ────────────────────────────────

def check_server(url: str, timeout: int = 5) -> Tuple[bool, str]:
    """Try to connect to *url* with a short timeout.

    Returns (True, "OK") on success or (False, error_message) on failure.
    Uses SSL_CTX from win_utils to avoid M-003 Windows SSL issues.
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


# ── M-051: Module availability check ────────────────────────────────

def check_module(name: str) -> Tuple[bool, str]:
    """Try to import *name* via importlib.

    Returns (True, "OK") or (False, error_message).
    """
    try:
        importlib.import_module(name)
        return True, "OK"
    except ImportError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


# ── Batch runner ─────────────────────────────────────────────────────

def run_checks(
    servers: List[str] | None = None,
    modules: List[str] | None = None,
) -> bool:
    """Run all checks, print a summary, return True if everything passed."""

    servers = servers or []
    modules = modules or []
    all_ok = True

    if servers:
        print("=== Server Connectivity ===")
        for url in servers:
            ok, msg = check_server(url)
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_ok = False
            print(f"  [{status}] {url}  {'' if ok else '-- ' + msg}")

    if modules:
        print("=== Module Availability ===")
        for mod in modules:
            ok, msg = check_module(mod)
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_ok = False
            print(f"  [{status}] {mod}  {'' if ok else '-- ' + msg}")

    print()
    print(f"Overall: {'ALL PASS' if all_ok else 'SOME CHECKS FAILED'}")
    return all_ok


# ── CLI mode ─────────────────────────────────────────────────────────

DEFAULT_SERVERS = [
    "https://orbitools.orbiters.co.kr",  # DataKeeper
    "https://n8n.orbiters.co.kr",        # n8n
]

DEFAULT_MODULES = [
    "playwright",
    "gspread",
    "openpyxl",
    "dotenv",
]

if __name__ == "__main__":
    print("Healthcheck  (M-044 / M-051 prevention)\n")
    ok = run_checks(servers=DEFAULT_SERVERS, modules=DEFAULT_MODULES)
    sys.exit(0 if ok else 1)
