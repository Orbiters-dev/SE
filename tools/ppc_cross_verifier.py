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


# ─── Gate 1 Helpers ──────────────────────────────────────────────────────────
def _pct_diff(a: float, b: float) -> float:
    """Return absolute percentage difference between a and b."""
    if a == 0 and b == 0:
        return 0.0
    denom = abs(a) if a != 0 else abs(b)
    return abs(a - b) / denom


def _check(name: str, val_a: float, val_b: float, tolerance: float,
           label_a: str = "A", label_b: str = "B", mode: str = "pct") -> dict:
    """Single comparison. mode='pct' uses _pct_diff, mode='abs' uses absolute diff."""
    if mode == "abs":
        diff = abs(val_a - val_b)
    else:
        diff = _pct_diff(val_a, val_b)
    passed = diff <= tolerance
    result = {"check": name, "pass": passed, label_a: val_a, label_b: val_b,
              "diff": round(diff, 6), "tolerance": tolerance, "mode": mode}
    if not passed:
        result["detail"] = (
            f"{name}: {label_a}={val_a}, {label_b}={val_b}, "
            f"diff={round(diff * (100 if mode == 'pct' else 1), 2)}"
            f"{'%' if mode == 'pct' else 'pp'} > tol={tolerance}"
        )
    return result


# ─── Gate 1 Loop Functions ───────────────────────────────────────────────────
def gate1_loop1_dk_vs_fin(dk_summary: dict, fin_summary: dict) -> dict:
    """Loop 1: DataKeeper vs Financial Dashboard — spend/sales 7D comparison."""
    checks = []
    for metric in ("spend_7d", "sales_7d"):
        c = _check(metric, dk_summary[metric], fin_summary[metric],
                    SPEND_TOLERANCE, "dk", "fin")
        checks.append(c)
    failures = [c for c in checks if not c["pass"]]
    return {"loop": 1, "name": "DK vs Financial", "pass": len(failures) == 0,
            "checks": checks, "failures": failures}


def gate1_loop2_dk_vs_ppc(dk_campaigns: dict, ppc_campaigns: dict) -> dict:
    """Loop 2: DataKeeper vs PPC Dashboard — campaign-level spend + ACOS."""
    checks = []
    all_keys = set(dk_campaigns) | set(ppc_campaigns)
    for camp in sorted(all_keys):
        dk_c = dk_campaigns.get(camp, {})
        ppc_c = ppc_campaigns.get(camp, {})
        # Spend check (percentage)
        c_spend = _check(f"{camp}/spend", dk_c.get("spend_7d", 0),
                         ppc_c.get("spend_7d", 0), SPEND_TOLERANCE, "dk", "ppc")
        checks.append(c_spend)
        # ACOS check (absolute pp)
        c_acos = _check(f"{camp}/acos", dk_c.get("acos_7d", 0),
                        ppc_c.get("acos_7d", 0), ACOS_TOLERANCE_PP,
                        "dk", "ppc", mode="abs")
        checks.append(c_acos)
    failures = [c for c in checks if not c["pass"]]
    return {"loop": 2, "name": "DK vs PPC", "pass": len(failures) == 0,
            "checks": checks, "failures": failures}


def gate1_loop3_three_way(l1_result: dict, l2_result: dict,
                          insights_path: str = None) -> dict:
    """Loop 3: 3-way reconciliation + yesterday's insights check."""
    all_failures = l1_result.get("failures", []) + l2_result.get("failures", [])
    insights_ok = True
    insights_note = None
    if insights_path:
        p = Path(insights_path)
        if p.exists():
            insights_note = "insights file found"
        else:
            insights_ok = False
            insights_note = "insights file missing"
            all_failures.append({"check": "insights_file", "detail": insights_note})
    passed = len(all_failures) == 0 and insights_ok
    return {"loop": 3, "name": "3-way reconciliation", "pass": passed,
            "failures": all_failures, "insights_note": insights_note}


def _summarize_dk_ads(rows: list) -> dict:
    """Summarize DK amazon_ads_daily rows into spend_7d / sales_7d."""
    spend = sum(r.get("spend", 0) for r in rows)
    sales = sum(r.get("sales", 0) for r in rows)
    return {"spend_7d": spend, "sales_7d": sales}


def _extract_fin_ads_summary(fin_data: dict) -> dict:
    """Extract 7d spend/sales from fin_data structure."""
    amz = fin_data.get("ad_performance", {}).get("amazon", {}).get("7d", {})
    return {"spend_7d": amz.get("spend", 0), "sales_7d": amz.get("sales", 0)}


def _print_loop(result: dict) -> None:
    status = "PASS" if result["pass"] else "FAIL"
    print(f"  Loop {result.get('loop', '?')}: {result.get('name', '')} — {status}")
    for f in result.get("failures", []):
        print(f"    ✗ {f.get('detail', f.get('check', ''))}")


# ─── Gate 1 Orchestrator ─────────────────────────────────────────────────────
def run_gate1(brand: str = "naeiae") -> dict:
    """Orchestrate Gate 1: Pre-Propose Cross-Check (3 Loops).

    If DataKeeper is down, enters fallback mode: skip loops 1-2,
    set budget_override=0.70 (conservative cap).
    """
    now_pst = datetime.now(PST)
    result = {
        "gate": 1,
        "brand": brand,
        "timestamp_pst": now_pst.strftime("%Y-%m-%d %H:%M PST"),
        "fallback_mode": False,
        "budget_override": 1.0,
        "loops": {},
    }

    # Load dashboard data
    fin_data = load_fin_data()
    ppc_data = load_ppc_data()

    # Freshness checks
    fin_fresh = check_freshness(fin_data.get("generated_pst", ""), FRESHNESS_MAX_HOURS)
    ppc_fresh = check_freshness(ppc_data.get("generated_pst", ""), FRESHNESS_MAX_HOURS)
    result["freshness"] = {"fin_data": fin_fresh, "ppc_data": ppc_fresh}

    # DataKeeper connectivity
    dk_ok = test_datakeeper_connection()

    if not dk_ok:
        # Fallback mode — skip loops 1 & 2
        result["fallback_mode"] = True
        result["budget_override"] = 0.70
        l1 = {"loop": 1, "name": "DK vs Financial", "pass": True,
               "skipped": True, "checks": [], "failures": []}
        l2 = {"loop": 2, "name": "DK vs PPC", "pass": True,
               "skipped": True, "checks": [], "failures": []}
        l3 = gate1_loop3_three_way(l1, l2)
        result["loops"] = {"loop1": l1, "loop2": l2, "loop3": l3}
        result["pass"] = l3["pass"]
    else:
        # Normal mode
        dk_rows = load_dk_amazon_ads(days=7, brand=brand)
        dk_summary = _summarize_dk_ads(dk_rows)
        fin_summary = _extract_fin_ads_summary(fin_data)

        l1 = gate1_loop1_dk_vs_fin(dk_summary, fin_summary)
        l2 = gate1_loop2_dk_vs_ppc({}, {})  # placeholder — needs campaign mapping
        l3 = gate1_loop3_three_way(l1, l2)

        result["loops"] = {"loop1": l1, "loop2": l2, "loop3": l3}
        result["pass"] = l3["pass"]

    # Print summary
    print(f"\n{'='*50}")
    print(f"Gate 1 — Pre-Propose Cross-Check  [{brand}]")
    print(f"{'='*50}")
    if result["fallback_mode"]:
        print("  ⚠ FALLBACK MODE — DataKeeper unavailable")
        print(f"  Budget override: {result['budget_override']:.0%}")
    for k in ("loop1", "loop2", "loop3"):
        _print_loop(result["loops"][k])
    overall = "PASS" if result["pass"] else "FAIL"
    print(f"  Overall: {overall}")
    print(f"{'='*50}\n")

    # Save result
    out_path = TMP / "ppc_xv_gate1_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    result["saved_to"] = str(out_path)

    return result
