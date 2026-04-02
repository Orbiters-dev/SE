"""PPC Cross-Verifier — 3-Gate x 3-Loop data consistency checker.

Usage:
    python tools/ppc_cross_verifier.py --gate 1 --loops 3 --fail-action block
    python tools/ppc_cross_verifier.py --gate 2 --loops 3 --proposal-path .tmp/ppc_proposal_naeiae_2026-04-02.json
    python tools/ppc_cross_verifier.py --gate 3 --loops 3 --codex-analyze
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
TMP = ROOT / ".tmp"
TMP.mkdir(parents=True, exist_ok=True)

PYTHON = "C:/Users/wjcho/AppData/Local/Programs/Python/Python312/python.exe"

sys.path.insert(0, str(DIR))
from data_keeper_client import DataKeeper

# ─── Constants ──────────────────────────────────────────────────────────────
PST = ZoneInfo("America/Los_Angeles")

FIN_DATA_PATH = ROOT / "docs" / "financial-dashboard" / "fin_data.js"
PPC_DATA_PATH = ROOT / "docs" / "ppc-dashboard" / "data.js"

BRAND_KEYS = ["naeiae", "grosmimi", "chaenmom"]

SPEND_TOLERANCE = 0.01
ACOS_TOLERANCE_PP = 0.5
FRESHNESS_MAX_HOURS = 24
PROPOSAL_MAX_HOURS_DEFAULT = 3
PROPOSAL_MAX_HOURS_HIGH = 2
DRIFT_TOLERANCE = 0.05
MAX_DAILY_BUDGET_CHANGE = 0.30
MAX_DAILY_BID_CHANGE = 0.20
COMPANY_DAILY_PPC_CAP = 4000.0
HIGH_SPEND_THRESHOLD = 1000.0


# ─── Timezone Alignment ────────────────────────────────────────────────────
def aligned_date_range(days_back: int = 7) -> tuple:
    now_pst = datetime.now(PST)
    end = now_pst.date()
    start = end - timedelta(days=days_back)
    return start.isoformat(), end.isoformat()


def assert_tz_aligned(dk_dates, fin_dates, ppc_dates):
    if dk_dates != fin_dates or fin_dates != ppc_dates:
        raise AssertionError(
            f"TZ mismatch: DK={dk_dates}, Fin={fin_dates}, PPC={ppc_dates}"
        )


# ─── Data Loaders ──────────────────────────────────────────────────────────
def _parse_js_const(text: str) -> dict:
    start = text.index("{")
    end = text.rindex("}") + 1
    json_str = text[start:end]
    return json.loads(json_str)


def load_fin_data(path: str = None) -> dict:
    p = Path(path) if path else FIN_DATA_PATH
    text = p.read_text(encoding="utf-8")
    return _parse_js_const(text)


def load_ppc_data(path: str = None) -> dict:
    p = Path(path) if path else PPC_DATA_PATH
    text = p.read_text(encoding="utf-8")
    return _parse_js_const(text)


def check_freshness(generated_pst: str, max_hours: int = 24) -> dict:
    try:
        clean = generated_pst.replace(" PST", "").replace(" PDT", "").strip()
        ts = datetime.strptime(clean, "%Y-%m-%d %H:%M")
        ts = ts.replace(tzinfo=PST)
        age = datetime.now(PST) - ts
        age_hours = age.total_seconds() / 3600
        return {
            "pass": age_hours <= max_hours,
            "age_hours": round(age_hours, 1),
            "max_hours": max_hours,
            "timestamp": generated_pst,
        }
    except (ValueError, TypeError) as e:
        return {"pass": False, "age_hours": -1, "error": str(e)}


def test_datakeeper_connection() -> bool:
    try:
        dk = DataKeeper()
        rows = dk.get("amazon_ads_daily", days=1)
        return rows is not None
    except Exception:
        return False


def load_dk_amazon_ads(days: int = 7, brand: str = None) -> list:
    dk = DataKeeper()
    kwargs = {"days": days}
    if brand:
        kwargs["brand"] = brand
    return dk.get("amazon_ads_daily", **kwargs) or []
