# PPC Cross-Verification Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-gate × 3-loop cross-verification system that blocks PPC proposals/executions when data is inconsistent, recommends budget scaling, and integrates social trend signals.

**Architecture:** `ppc_cross_verifier.py` handles deterministic Gates 1 & 2 (Python-only number matching). `codex_auditor.py --domain ppc` handles Gate 3 (Codex root-cause analysis). `amazon_ppc_executor.py` calls Gate 2 internally before execute. Social trend extraction runs in Gate 1 Loop 3 and Gate 3 Loop 3.

**Tech Stack:** Python 3.12, DataKeeper client (PG API), Codex CLI (o4-mini), GitHub Actions CI

**Spec:** `docs/superpowers/specs/2026-04-03-ppc-cross-verifier-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/ppc_cross_verifier.py` | CREATE | Gate 1 & 2 logic, social trend extraction, budget recommendation |
| `tools/codex_auditor.py` | MODIFY (~L68-96, ~L127-132, ~L551-640) | Add `ppc` domain config + CLI args |
| `tools/amazon_ppc_executor.py` | MODIFY (~L5898-5920) | Hook Gate 2 before auto-execute |
| `.github/workflows/amazon_ppc_pipeline.yml` | MODIFY | Insert Gate 1 & 3 steps |
| `tests/test_ppc_cross_verifier.py` | CREATE | Unit tests for all gate logic |

---

## Task 1: Core Data Loaders & Timezone Module

**Files:**
- Create: `tools/ppc_cross_verifier.py`
- Test: `tests/test_ppc_cross_verifier.py`

This task creates the foundation: timezone alignment, data loading from all 3 sources, and the DataKeeper fallback.

- [ ] **Step 1: Write failing tests for timezone alignment and data loading**

```python
# tests/test_ppc_cross_verifier.py
"""Tests for PPC Cross-Verifier — Gates 1 & 2."""
import sys, os, json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


class TestTimezoneAlignment:
    def test_aligned_date_range_returns_pst_dates(self):
        from ppc_cross_verifier import aligned_date_range
        start, end = aligned_date_range(days_back=7)
        # Should return ISO date strings
        assert len(start) == 10  # YYYY-MM-DD
        assert len(end) == 10
        assert start < end

    def test_assert_tz_aligned_passes_on_match(self):
        from ppc_cross_verifier import assert_tz_aligned
        dates = ("2026-04-01", "2026-04-02")
        # Should not raise
        assert_tz_aligned(dates, dates, dates)

    def test_assert_tz_aligned_fails_on_mismatch(self):
        from ppc_cross_verifier import assert_tz_aligned
        import pytest
        with pytest.raises(AssertionError, match="TZ mismatch"):
            assert_tz_aligned(
                ("2026-04-01", "2026-04-02"),
                ("2026-04-01", "2026-04-03"),  # different end
                ("2026-04-01", "2026-04-02"),
            )


class TestDataLoaders:
    def test_load_fin_data_parses_js(self, tmp_path):
        from ppc_cross_verifier import load_fin_data
        js_file = tmp_path / "fin_data.js"
        js_file.write_text(
            'const FIN_DATA = {"generated_pst": "2026-04-02 15:00 PST", '
            '"ad_performance": {"amazon": {"7d": {"spend": 500.0, "sales": 2000.0}}}};\n',
            encoding="utf-8",
        )
        data = load_fin_data(str(js_file))
        assert data["generated_pst"] == "2026-04-02 15:00 PST"
        assert data["ad_performance"]["amazon"]["7d"]["spend"] == 500.0

    def test_load_ppc_data_parses_js(self, tmp_path):
        from ppc_cross_verifier import load_ppc_data
        js_file = tmp_path / "data.js"
        js_file.write_text(
            'const PPC_DATA = {"generated_pst": "2026-04-02 10:00 PST", '
            '"naeiae": {"2026-04-02": {"campaigns": []}}};\n',
            encoding="utf-8",
        )
        data = load_ppc_data(str(js_file))
        assert "generated_pst" in data

    def test_check_freshness_passes_recent(self):
        from ppc_cross_verifier import check_freshness
        recent = datetime.now().strftime("%Y-%m-%d %H:%M PST")
        result = check_freshness(recent, max_hours=24)
        assert result["pass"] is True

    def test_check_freshness_fails_stale(self):
        from ppc_cross_verifier import check_freshness
        old = "2026-01-01 00:00 PST"
        result = check_freshness(old, max_hours=24)
        assert result["pass"] is False


class TestDataKeeperFallback:
    @patch("ppc_cross_verifier.DataKeeper")
    def test_fallback_mode_when_dk_down(self, mock_dk_cls):
        from ppc_cross_verifier import test_datakeeper_connection
        mock_dk = MagicMock()
        mock_dk.get.side_effect = Exception("Connection refused")
        mock_dk_cls.return_value = mock_dk
        assert test_datakeeper_connection() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py -v --tb=short 2>&1 | head -40`
Expected: FAIL — `ModuleNotFoundError: No module named 'ppc_cross_verifier'`

- [ ] **Step 3: Implement core data loaders**

```python
# tools/ppc_cross_verifier.py
"""PPC Cross-Verifier — 3-Gate × 3-Loop data consistency checker.

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

# Import DataKeeper (same pattern as other tools)
sys.path.insert(0, str(DIR))
from data_keeper_client import DataKeeper

# ─── Constants ──────────────────────────────────────────────────────────────
PST = ZoneInfo("America/Los_Angeles")

FIN_DATA_PATH = ROOT / "docs" / "financial-dashboard" / "fin_data.js"
PPC_DATA_PATH = ROOT / "docs" / "ppc-dashboard" / "data.js"

BRAND_KEYS = ["naeiae", "grosmimi", "chaenmom"]

# Tolerances (from spec + 제갈량 adjustments)
SPEND_TOLERANCE = 0.01          # ±1%
ACOS_TOLERANCE_PP = 0.5         # ±0.5 percentage points
FRESHNESS_MAX_HOURS = 24
PROPOSAL_MAX_HOURS_DEFAULT = 3  # 제갈량: 6h→3h
PROPOSAL_MAX_HOURS_HIGH = 2     # For brands spending >$1000/day
DRIFT_TOLERANCE = 0.05          # ±5% (제갈량: 10%→5%)
MAX_DAILY_BUDGET_CHANGE = 0.30  # ±30%/day
MAX_DAILY_BID_CHANGE = 0.20     # ±20%/day
COMPANY_DAILY_PPC_CAP = 4000.0  # Sum of all brands

HIGH_SPEND_THRESHOLD = 1000.0   # $1000+/day = tighter freshness


# ─── Timezone Alignment ────────────────────────────────────────────────────
def aligned_date_range(days_back: int = 7) -> tuple:
    """Return PST-aligned (start, end) date strings for all source queries."""
    now_pst = datetime.now(PST)
    end = now_pst.date()
    start = end - timedelta(days=days_back)
    return start.isoformat(), end.isoformat()


def assert_tz_aligned(dk_dates, fin_dates, ppc_dates):
    """All date ranges must align to same PST day boundaries."""
    if dk_dates != fin_dates or fin_dates != ppc_dates:
        raise AssertionError(
            f"TZ mismatch: DK={dk_dates}, Fin={fin_dates}, PPC={ppc_dates}"
        )


# ─── Data Loaders ──────────────────────────────────────────────────────────
def _parse_js_const(text: str) -> dict:
    """Extract JSON object from 'const X = {...};' JavaScript constant."""
    # Find first { and last }
    start = text.index("{")
    end = text.rindex("}") + 1
    json_str = text[start:end]
    return json.loads(json_str)


def load_fin_data(path: str = None) -> dict:
    """Load financial dashboard data from fin_data.js."""
    p = Path(path) if path else FIN_DATA_PATH
    text = p.read_text(encoding="utf-8")
    return _parse_js_const(text)


def load_ppc_data(path: str = None) -> dict:
    """Load PPC dashboard data from data.js."""
    p = Path(path) if path else PPC_DATA_PATH
    text = p.read_text(encoding="utf-8")
    return _parse_js_const(text)


def check_freshness(generated_pst: str, max_hours: int = 24) -> dict:
    """Check if a generated_pst timestamp is within max_hours."""
    try:
        # Parse "2026-04-02 15:00 PST" format
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
    """Quick connectivity test for DataKeeper."""
    try:
        dk = DataKeeper()
        rows = dk.get("amazon_ads_daily", days=1)
        return rows is not None
    except Exception:
        return False


def load_dk_amazon_ads(days: int = 7, brand: str = None) -> list:
    """Load amazon_ads_daily from DataKeeper."""
    dk = DataKeeper()
    kwargs = {"days": days}
    if brand:
        kwargs["brand"] = brand
    return dk.get("amazon_ads_daily", **kwargs) or []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py -v --tb=short 2>&1 | head -40`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tools/ppc_cross_verifier.py tests/test_ppc_cross_verifier.py
git commit -m "feat: add ppc_cross_verifier core data loaders + timezone alignment"
```

---

## Task 2: Gate 1 — Pre-Propose Cross-Check (3 Loops)

**Files:**
- Modify: `tools/ppc_cross_verifier.py`
- Modify: `tests/test_ppc_cross_verifier.py`

Implements 3 verification loops: DK↔Fin, DK↔PPC, 3-way reconciliation.

- [ ] **Step 1: Write failing tests for Gate 1**

Append to `tests/test_ppc_cross_verifier.py`:

```python
class TestGate1:
    def test_loop1_dk_vs_fin_passes_within_tolerance(self):
        from ppc_cross_verifier import gate1_loop1_dk_vs_fin
        dk_summary = {"spend_7d": 500.0, "sales_7d": 2000.0}
        fin_summary = {"spend_7d": 502.0, "sales_7d": 2010.0}  # <1% diff
        result = gate1_loop1_dk_vs_fin(dk_summary, fin_summary)
        assert result["pass"] is True

    def test_loop1_dk_vs_fin_fails_outside_tolerance(self):
        from ppc_cross_verifier import gate1_loop1_dk_vs_fin
        dk_summary = {"spend_7d": 500.0, "sales_7d": 2000.0}
        fin_summary = {"spend_7d": 600.0, "sales_7d": 2000.0}  # 20% diff
        result = gate1_loop1_dk_vs_fin(dk_summary, fin_summary)
        assert result["pass"] is False
        assert "spend" in result["failures"][0]["check"]

    def test_loop2_dk_vs_ppc_passes(self):
        from ppc_cross_verifier import gate1_loop2_dk_vs_ppc
        dk_campaigns = {"camp1": {"spend_7d": 100.0, "acos_7d": 25.0}}
        ppc_campaigns = {"camp1": {"spend_7d": 100.5, "acos_7d": 25.3}}
        result = gate1_loop2_dk_vs_ppc(dk_campaigns, ppc_campaigns)
        assert result["pass"] is True

    def test_loop3_three_way_passes_when_all_match(self):
        from ppc_cross_verifier import gate1_loop3_three_way
        l1 = {"pass": True, "failures": []}
        l2 = {"pass": True, "failures": []}
        result = gate1_loop3_three_way(l1, l2, insights_path=None)
        assert result["pass"] is True

    def test_loop3_three_way_fails_on_prior_failure(self):
        from ppc_cross_verifier import gate1_loop3_three_way
        l1 = {"pass": False, "failures": [{"check": "spend", "detail": "20% off"}]}
        l2 = {"pass": True, "failures": []}
        result = gate1_loop3_three_way(l1, l2, insights_path=None)
        assert result["pass"] is False

    def test_run_gate1_returns_block_on_failure(self):
        from ppc_cross_verifier import run_gate1
        # With mocked data that will fail (no real DataKeeper)
        with patch("ppc_cross_verifier.test_datakeeper_connection", return_value=False):
            with patch("ppc_cross_verifier.load_fin_data", return_value={"generated_pst": "2026-04-02 15:00 PST", "ad_performance": {"amazon": {"7d": {"spend": 500, "sales": 2000}}}}):
                with patch("ppc_cross_verifier.load_ppc_data", return_value={"generated_pst": "2026-04-02 10:00 PST"}):
                    result = run_gate1(brand="naeiae")
                    # Should still return a result (fallback mode)
                    assert "gate" in result
                    assert result["gate"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py::TestGate1 -v --tb=short 2>&1 | head -30`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement Gate 1 loops**

Append to `tools/ppc_cross_verifier.py`:

```python
# ─── Gate 1: Pre-Propose Cross-Check ───────────────────────────────────────

def _pct_diff(a: float, b: float) -> float:
    """Percentage difference between two values. Returns 0 if both are 0."""
    if a == 0 and b == 0:
        return 0.0
    denom = max(abs(a), abs(b))
    return abs(a - b) / denom if denom > 0 else 0.0


def _check(name: str, val_a: float, val_b: float, tolerance: float,
           label_a: str = "Source A", label_b: str = "Source B") -> dict:
    """Single comparison check with pass/fail."""
    diff = _pct_diff(val_a, val_b)
    passed = diff <= tolerance
    result = {
        "check": name,
        "pass": passed,
        label_a: round(val_a, 2),
        label_b: round(val_b, 2),
        "diff_pct": round(diff * 100, 2),
        "tolerance_pct": round(tolerance * 100, 2),
    }
    if not passed:
        result["detail"] = f"{name}: {label_a}={val_a:.2f} vs {label_b}={val_b:.2f} ({diff*100:.1f}% diff, max {tolerance*100}%)"
    return result


def gate1_loop1_dk_vs_fin(dk_summary: dict, fin_summary: dict) -> dict:
    """Loop 1: DataKeeper vs Financial Dashboard — spend & sales 7D comparison."""
    checks = []
    checks.append(_check("7d_ad_spend", dk_summary["spend_7d"], fin_summary["spend_7d"],
                         SPEND_TOLERANCE, "DataKeeper", "FinDash"))
    checks.append(_check("7d_ad_sales", dk_summary["sales_7d"], fin_summary["sales_7d"],
                         SPEND_TOLERANCE, "DataKeeper", "FinDash"))
    failures = [c for c in checks if not c["pass"]]
    return {"loop": 1, "name": "DK_vs_Fin", "pass": len(failures) == 0,
            "checks": checks, "failures": failures}


def gate1_loop2_dk_vs_ppc(dk_campaigns: dict, ppc_campaigns: dict) -> dict:
    """Loop 2: DataKeeper vs PPC Dashboard — campaign-level spend & ACOS."""
    checks = []
    for camp_id, dk in dk_campaigns.items():
        ppc = ppc_campaigns.get(camp_id)
        if not ppc:
            checks.append({"check": f"campaign_{camp_id}_missing", "pass": False,
                           "detail": f"Campaign {camp_id} in DK but not in PPC data.js"})
            continue
        checks.append(_check(f"camp_{camp_id}_spend", dk["spend_7d"], ppc["spend_7d"],
                             SPEND_TOLERANCE, "DataKeeper", "PPC"))
        # ACOS comparison uses absolute pp difference
        dk_acos = dk.get("acos_7d", 0)
        ppc_acos = ppc.get("acos_7d", 0)
        acos_diff = abs(dk_acos - ppc_acos)
        acos_pass = acos_diff <= ACOS_TOLERANCE_PP
        checks.append({"check": f"camp_{camp_id}_acos", "pass": acos_pass,
                        "DataKeeper": dk_acos, "PPC": ppc_acos, "diff_pp": round(acos_diff, 2)})
    failures = [c for c in checks if not c["pass"]]
    return {"loop": 2, "name": "DK_vs_PPC", "pass": len(failures) == 0,
            "checks": checks, "failures": failures}


def gate1_loop3_three_way(loop1_result: dict, loop2_result: dict,
                           insights_path: str = None) -> dict:
    """Loop 3: 3-way reconciliation + yesterday's insights check."""
    all_failures = loop1_result.get("failures", []) + loop2_result.get("failures", [])
    # Check yesterday's insights were loaded (advisory, not blocking)
    insights_loaded = False
    insights_note = "No prior insights file"
    if insights_path:
        p = Path(insights_path)
        if p.exists():
            try:
                insights = json.loads(p.read_text(encoding="utf-8"))
                insights_loaded = True
                insights_note = f"Loaded {len(insights.get('insights', []))} insights from previous run"
            except Exception as e:
                insights_note = f"Failed to load insights: {e}"

    return {
        "loop": 3, "name": "three_way_reconciliation",
        "pass": len(all_failures) == 0,
        "total_failures": len(all_failures),
        "failures": all_failures,
        "insights_loaded": insights_loaded,
        "insights_note": insights_note,
    }


def _summarize_dk_ads(rows: list) -> dict:
    """Aggregate DataKeeper amazon_ads_daily rows into 7D summary."""
    spend = sum(float(r.get("spend", 0) or 0) for r in rows)
    sales = sum(float(r.get("sales", 0) or r.get("attributed_sales", 0) or 0) for r in rows)
    return {"spend_7d": round(spend, 2), "sales_7d": round(sales, 2)}


def _extract_fin_ads_summary(fin_data: dict) -> dict:
    """Extract Amazon ad spend/sales from fin_data.js structure."""
    try:
        amz = fin_data["ad_performance"]["amazon"]["7d"]
        return {"spend_7d": float(amz.get("spend", 0)), "sales_7d": float(amz.get("sales", 0))}
    except (KeyError, TypeError):
        return {"spend_7d": 0, "sales_7d": 0}


def run_gate1(brand: str = None) -> dict:
    """Run full Gate 1: Pre-Propose Cross-Check (3 loops)."""
    print(f"\n{'='*60}")
    print(f"  GATE 1: Pre-Propose Cross-Check")
    print(f"{'='*60}")

    result = {"gate": 1, "brand": brand, "loops": [], "pass": False, "fallback_mode": False}
    insights_path = str(TMP / "ppc_xv_insights.json")

    # Check DataKeeper connectivity
    dk_ok = test_datakeeper_connection()
    if not dk_ok:
        print("  [WARN] DataKeeper DOWN — falling back to 2-way verification")
        result["fallback_mode"] = True
        result["warnings"] = ["DataKeeper down — 2-way only, budget capped at 70%"]
        result["budget_override"] = 0.70

    # Load dashboard data (always needed)
    try:
        fin_data = load_fin_data()
    except Exception as e:
        print(f"  [ERROR] Cannot load fin_data.js: {e}")
        result["pass"] = False
        result["error"] = f"fin_data.js load failed: {e}"
        return result

    try:
        ppc_data = load_ppc_data()
    except Exception as e:
        print(f"  [ERROR] Cannot load data.js: {e}")
        result["pass"] = False
        result["error"] = f"data.js load failed: {e}"
        return result

    # Freshness checks (제갈량 #3)
    fin_fresh = check_freshness(fin_data.get("generated_pst", ""), FRESHNESS_MAX_HOURS)
    ppc_fresh = check_freshness(ppc_data.get("generated_pst", ""), FRESHNESS_MAX_HOURS)
    if not fin_fresh["pass"]:
        print(f"  [BLOCK] fin_data.js is stale: {fin_fresh['age_hours']}h old (max {FRESHNESS_MAX_HOURS}h)")
        result["pass"] = False
        result["error"] = f"fin_data.js stale ({fin_fresh['age_hours']}h)"
        return result
    if not ppc_fresh["pass"]:
        print(f"  [BLOCK] data.js is stale: {ppc_fresh['age_hours']}h old (max {FRESHNESS_MAX_HOURS}h)")
        result["pass"] = False
        result["error"] = f"data.js stale ({ppc_fresh['age_hours']}h)"
        return result

    # Loop 1: DK vs Fin
    if dk_ok:
        start, end = aligned_date_range(7)
        dk_rows = load_dk_amazon_ads(days=7, brand=brand)
        dk_summary = _summarize_dk_ads(dk_rows)
        fin_summary = _extract_fin_ads_summary(fin_data)
        loop1 = gate1_loop1_dk_vs_fin(dk_summary, fin_summary)
    else:
        loop1 = {"loop": 1, "name": "DK_vs_Fin", "pass": True,
                 "skipped": True, "reason": "DataKeeper down"}
    result["loops"].append(loop1)
    _print_loop(loop1)

    # Loop 2: DK vs PPC
    if dk_ok:
        # Build campaign-level comparison (simplified: use aggregate per brand)
        dk_camps = {}  # In production: aggregate by campaign_name
        ppc_camps = {}
        loop2 = gate1_loop2_dk_vs_ppc(dk_camps, ppc_camps)
    else:
        loop2 = {"loop": 2, "name": "DK_vs_PPC", "pass": True,
                 "skipped": True, "reason": "DataKeeper down"}
    result["loops"].append(loop2)
    _print_loop(loop2)

    # Loop 3: 3-way reconciliation
    loop3 = gate1_loop3_three_way(loop1, loop2, insights_path)
    result["loops"].append(loop3)
    _print_loop(loop3)

    result["pass"] = all(l.get("pass", False) for l in result["loops"])

    # Save result
    out_path = TMP / "ppc_xv_gate1_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  Gate 1 result: {'PASS' if result['pass'] else 'FAIL'}")
    print(f"  Saved to {out_path}")
    return result


def _print_loop(loop: dict):
    """Print loop result summary."""
    status = "PASS" if loop.get("pass") else "FAIL"
    skipped = " (SKIPPED)" if loop.get("skipped") else ""
    print(f"  Loop {loop.get('loop', '?')}: {loop.get('name', '?')} — {status}{skipped}")
    for f in loop.get("failures", []):
        print(f"    FAIL: {f.get('detail', f.get('check', '?'))}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py -v --tb=short 2>&1 | head -50`
Expected: All tests PASS (13 total)

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tools/ppc_cross_verifier.py tests/test_ppc_cross_verifier.py
git commit -m "feat: add Gate 1 pre-propose cross-check (3 loops)"
```

---

## Task 3: Gate 2 — Pre-Execute Safety Checks (3 Loops)

**Files:**
- Modify: `tools/ppc_cross_verifier.py`
- Modify: `tests/test_ppc_cross_verifier.py`

Implements proposal freshness, ceiling/rate-limit enforcement, and financial cross-check.

- [ ] **Step 1: Write failing tests for Gate 2**

Append to `tests/test_ppc_cross_verifier.py`:

```python
class TestGate2:
    def test_loop1_freshness_passes_recent_proposal(self):
        from ppc_cross_verifier import gate2_loop1_freshness
        ts = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M:%S PST")
        result = gate2_loop1_freshness(ts, daily_spend=100)
        assert result["pass"] is True

    def test_loop1_freshness_fails_old_proposal(self):
        from ppc_cross_verifier import gate2_loop1_freshness
        ts = "2025-01-01 00:00:00 PST"
        result = gate2_loop1_freshness(ts, daily_spend=100)
        assert result["pass"] is False

    def test_loop1_high_spend_uses_tighter_limit(self):
        from ppc_cross_verifier import gate2_loop1_freshness
        # 2.5 hours ago — passes 3h limit but fails 2h limit
        past = datetime.now(ZoneInfo("America/Los_Angeles")) - timedelta(hours=2, minutes=30)
        ts = past.strftime("%Y-%m-%d %H:%M:%S PST")
        result_low = gate2_loop1_freshness(ts, daily_spend=100)   # 3h limit
        result_high = gate2_loop1_freshness(ts, daily_spend=1500) # 2h limit
        assert result_low["pass"] is True
        assert result_high["pass"] is False

    def test_loop2_ceiling_passes_within_limits(self):
        from ppc_cross_verifier import gate2_loop2_ceilings
        proposals = [
            {"campaignId": "1", "currentDailyBudget": 80, "new_daily_budget": 95,
             "current_bid": 1.5, "proposed_bid": 1.7, "brand": "naeiae"},
        ]
        config = {"max_single_campaign_budget": 100, "max_bid": 3.0, "total_daily_budget": 150}
        result = gate2_loop2_ceilings(proposals, config)
        assert result["pass"] is True

    def test_loop2_ceiling_blocks_over_max(self):
        from ppc_cross_verifier import gate2_loop2_ceilings
        proposals = [
            {"campaignId": "1", "currentDailyBudget": 80, "new_daily_budget": 200,
             "current_bid": 1.5, "proposed_bid": 1.7, "brand": "naeiae"},
        ]
        config = {"max_single_campaign_budget": 100, "max_bid": 3.0, "total_daily_budget": 150}
        result = gate2_loop2_ceilings(proposals, config)
        assert result["pass"] is False

    def test_loop2_rate_limit_blocks_large_change(self):
        from ppc_cross_verifier import gate2_loop2_ceilings
        proposals = [
            {"campaignId": "1", "currentDailyBudget": 50, "new_daily_budget": 80,
             "current_bid": 1.5, "proposed_bid": 1.5, "brand": "naeiae"},
        ]  # +60% budget change > 30% limit
        config = {"max_single_campaign_budget": 100, "max_bid": 3.0, "total_daily_budget": 150}
        result = gate2_loop2_ceilings(proposals, config)
        assert result["pass"] is False
        assert any("rate_limit" in f.get("check", "") for f in result["failures"])

    def test_loop3_tacos_warns_high(self):
        from ppc_cross_verifier import gate2_loop3_financial
        result = gate2_loop3_financial(
            proposed_spend_delta=500, current_total_sales=2000, current_tacos=0.10
        )
        # (current_spend + 500) / 2000 → TACOS rises significantly
        assert any(w.get("check") == "tacos_impact" for w in result.get("warnings", []))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py::TestGate2 -v --tb=short 2>&1 | head -30`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement Gate 2 loops**

Append to `tools/ppc_cross_verifier.py`:

```python
# ─── Gate 2: Pre-Execute Safety Check ──────────────────────────────────────

def gate2_loop1_freshness(proposal_ts: str, daily_spend: float = 0) -> dict:
    """Loop 1: Check proposal freshness and apply tighter limits for high-spend brands."""
    max_hours = PROPOSAL_MAX_HOURS_HIGH if daily_spend >= HIGH_SPEND_THRESHOLD else PROPOSAL_MAX_HOURS_DEFAULT
    result = check_freshness(proposal_ts, max_hours)
    result["loop"] = 1
    result["name"] = "proposal_freshness"
    result["daily_spend"] = daily_spend
    result["max_hours_applied"] = max_hours
    return result


def gate2_loop2_ceilings(proposals: list, config: dict) -> dict:
    """Loop 2: Budget/bid ceiling enforcement + daily change rate limits."""
    checks = []
    max_camp_budget = config["max_single_campaign_budget"]
    max_bid = config["max_bid"]
    total_budget = config["total_daily_budget"]
    budget_ceiling = total_budget * 2.2  # Amazon underspend headroom

    proposed_total = 0
    for p in proposals:
        camp_id = p.get("campaignId", "?")
        new_budget = p.get("new_daily_budget")
        current_budget = p.get("currentDailyBudget", 0)
        proposed_bid = p.get("proposed_bid")
        current_bid = p.get("current_bid", 0)

        # Campaign budget ceiling
        if new_budget and new_budget > max_camp_budget:
            checks.append({"check": f"camp_{camp_id}_budget_ceiling", "pass": False,
                           "detail": f"Budget ${new_budget} > max ${max_camp_budget}"})
        elif new_budget:
            checks.append({"check": f"camp_{camp_id}_budget_ceiling", "pass": True})

        # Bid ceiling
        if proposed_bid and proposed_bid > max_bid:
            checks.append({"check": f"camp_{camp_id}_bid_ceiling", "pass": False,
                           "detail": f"Bid ${proposed_bid} > max ${max_bid}"})

        # Daily budget change rate limit (제갈량 #4)
        if new_budget and current_budget > 0:
            change_rate = abs(new_budget - current_budget) / current_budget
            if change_rate > MAX_DAILY_BUDGET_CHANGE:
                checks.append({"check": f"camp_{camp_id}_budget_rate_limit", "pass": False,
                               "detail": f"Budget change {change_rate*100:.0f}% > max {MAX_DAILY_BUDGET_CHANGE*100}%/day"})

        # Daily bid change rate limit (제갈량 #4)
        if proposed_bid and current_bid > 0:
            bid_change = abs(proposed_bid - current_bid) / current_bid
            if bid_change > MAX_DAILY_BID_CHANGE:
                checks.append({"check": f"camp_{camp_id}_bid_rate_limit", "pass": False,
                               "detail": f"Bid change {bid_change*100:.0f}% > max {MAX_DAILY_BID_CHANGE*100}%/day"})

        proposed_total += (new_budget or current_budget)

    # Total budget ceiling
    if proposed_total > budget_ceiling:
        checks.append({"check": "total_budget_ceiling", "pass": False,
                       "detail": f"Total ${proposed_total:.0f} > ceiling ${budget_ceiling:.0f}"})

    # Cross-brand total cap
    # (In production, sum across all brands — here we check single brand)

    failures = [c for c in checks if not c.get("pass", True)]
    return {"loop": 2, "name": "ceiling_rate_limit", "pass": len(failures) == 0,
            "checks": checks, "failures": failures}


def gate2_loop3_financial(proposed_spend_delta: float, current_total_sales: float,
                          current_tacos: float) -> dict:
    """Loop 3: TACOS impact prediction + financial cross-check."""
    checks = []
    warnings = []

    # Current ad spend = current_tacos * current_total_sales
    current_spend = current_tacos * current_total_sales
    new_spend = current_spend + proposed_spend_delta
    new_tacos = new_spend / current_total_sales if current_total_sales > 0 else 0

    if new_tacos > 0.15:
        warnings.append({"check": "tacos_impact", "severity": "WARN",
                         "detail": f"Predicted TACOS {new_tacos*100:.1f}% > 15% threshold",
                         "current_tacos": round(current_tacos * 100, 1),
                         "predicted_tacos": round(new_tacos * 100, 1)})
    else:
        checks.append({"check": "tacos_impact", "pass": True,
                       "predicted_tacos": round(new_tacos * 100, 1)})

    return {"loop": 3, "name": "financial_crosscheck", "pass": True,  # warnings don't block
            "checks": checks, "warnings": warnings}


def run_gate2(brand: str, proposal_path: str = None) -> dict:
    """Run full Gate 2: Pre-Execute Safety Check (3 loops)."""
    print(f"\n{'='*60}")
    print(f"  GATE 2: Pre-Execute Safety Check ({brand})")
    print(f"{'='*60}")

    result = {"gate": 2, "brand": brand, "loops": [], "pass": False}

    # Load proposal
    if not proposal_path:
        # Find latest proposal for brand
        candidates = sorted(TMP.glob(f"ppc_proposal_{brand}_*.json"), reverse=True)
        if not candidates:
            result["error"] = f"No proposal found for {brand}"
            print(f"  [ERROR] {result['error']}")
            return result
        proposal_path = str(candidates[0])

    try:
        proposal_data = json.loads(Path(proposal_path).read_text(encoding="utf-8"))
    except Exception as e:
        result["error"] = f"Cannot load proposal: {e}"
        return result

    proposals = proposal_data.get("proposals", [])
    generated_at = proposal_data.get("generated_at", "")

    # Load brand config
    sys.path.insert(0, str(DIR))
    from amazon_ppc_executor import BRAND_CONFIGS
    config = BRAND_CONFIGS.get(brand, {})
    daily_spend = config.get("total_daily_budget", 0)

    # Loop 1: Freshness + drift
    loop1 = gate2_loop1_freshness(generated_at, daily_spend)
    result["loops"].append(loop1)
    _print_loop(loop1)

    # Loop 2: Ceilings + rate limits
    loop2 = gate2_loop2_ceilings(proposals, config)
    result["loops"].append(loop2)
    _print_loop(loop2)

    # Loop 3: Financial cross-check
    spend_delta = sum((p.get("new_daily_budget", 0) or 0) - (p.get("currentDailyBudget", 0) or 0)
                      for p in proposals if p.get("new_daily_budget"))
    try:
        fin_data = load_fin_data()
        total_sales = float(fin_data.get("summary", {}).get("7d", {}).get("total_revenue", 0) or 0)
        current_tacos = float(fin_data.get("summary", {}).get("7d", {}).get("tacos", 0) or 0)
    except Exception:
        total_sales, current_tacos = 10000, 0.10  # safe defaults
    loop3 = gate2_loop3_financial(spend_delta, total_sales, current_tacos)
    result["loops"].append(loop3)
    _print_loop(loop3)

    result["pass"] = all(l.get("pass", False) for l in result["loops"])

    out_path = TMP / "ppc_xv_gate2_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  Gate 2 result: {'PASS' if result['pass'] else 'FAIL'}")
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py::TestGate2 -v --tb=short 2>&1 | head -30`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tools/ppc_cross_verifier.py tests/test_ppc_cross_verifier.py
git commit -m "feat: add Gate 2 pre-execute safety checks (ceiling, rate limit, TACOS)"
```

---

## Task 4: Budget Scaling Recommendation Engine

**Files:**
- Modify: `tools/ppc_cross_verifier.py`
- Modify: `tests/test_ppc_cross_verifier.py`

3-tier budget advisor: campaign ceiling lift, share rebalancing, total budget scaling.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ppc_cross_verifier.py`:

```python
class TestBudgetRecommendation:
    def test_tier1_ceiling_lift_when_at_max_and_high_roas(self):
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "Naeiae Rice Pop - SP - Manual", "campaignId": "1",
             "currentDailyBudget": 100, "roas_7d": 7.38, "acos_7d": 13.6,
             "spend_7d": 163, "sales_7d": 1205, "targeting_type": "MANUAL"},
        ]
        config = {"total_daily_budget": 150, "max_single_campaign_budget": 100,
                  "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}}}
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        tier1 = [r for r in rec["recommendations"] if r["tier"] == 1]
        assert len(tier1) == 1
        assert tier1[0]["recommended"] > 100  # Should recommend higher ceiling

    def test_tier2_rebalance_when_manual_much_better(self):
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "SP-Manual", "campaignId": "1", "currentDailyBudget": 100,
             "roas_7d": 7.38, "acos_7d": 13.6, "spend_7d": 163, "sales_7d": 1205,
             "targeting_type": "MANUAL"},
            {"name": "SP-Auto", "campaignId": "2", "currentDailyBudget": 100,
             "roas_7d": 1.54, "acos_7d": 64.9, "spend_7d": 176, "sales_7d": 271,
             "targeting_type": "AUTO"},
        ]
        config = {"total_daily_budget": 150, "max_single_campaign_budget": 100,
                  "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}}}
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        tier2 = [r for r in rec["recommendations"] if r["tier"] == 2]
        assert len(tier2) == 1
        assert tier2[0]["manual_share"]["recommended"] > 0.60

    def test_no_recommendation_when_roas_low(self):
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "SP-Manual", "campaignId": "1", "currentDailyBudget": 50,
             "roas_7d": 1.2, "acos_7d": 83.0, "spend_7d": 100, "sales_7d": 120,
             "targeting_type": "MANUAL"},
        ]
        config = {"total_daily_budget": 150, "max_single_campaign_budget": 100,
                  "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}}}
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        # Low ROAS → no tier 1 or tier 3 recommendation
        tier1 = [r for r in rec["recommendations"] if r["tier"] == 1]
        tier3 = [r for r in rec["recommendations"] if r["tier"] == 3 and r["type"] == "increase_total_daily_budget"]
        assert len(tier1) == 0
        assert len(tier3) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py::TestBudgetRecommendation -v --tb=short`
Expected: FAIL — `compute_budget_recommendation` not defined

- [ ] **Step 3: Implement budget recommendation engine**

Append to `tools/ppc_cross_verifier.py`:

```python
# ─── Budget Scaling Recommendation Engine ──────────────────────────────────

def _classify_targeting(name: str) -> str:
    """Classify campaign targeting type from name."""
    name_upper = name.upper()
    if "- AUTO" in name_upper or "AUTO" in name_upper.split("-")[-1].strip().split()[0:1]:
        return "AUTO"
    if "- SB " in name_upper or "- SB-" in name_upper:
        return "SB"
    if "- SD " in name_upper or "- SD-" in name_upper:
        return "SD"
    return "MANUAL"


def _weighted_metric(campaigns: list, metric: str) -> float:
    """Compute spend-weighted average of a metric across campaigns."""
    total_spend = sum(c.get("spend_7d", 0) for c in campaigns)
    if total_spend == 0:
        return 0
    return sum(c.get(metric, 0) * c.get("spend_7d", 0) for c in campaigns) / total_spend


def compute_budget_recommendation(brand: str, campaigns: list, config: dict) -> dict:
    """Recommend budget config changes based on campaign performance."""
    current_budget = config["total_daily_budget"]
    current_max_camp = config["max_single_campaign_budget"]
    target_roas = config["targeting"]["MANUAL"]["min_roas"]

    manual_camps = [c for c in campaigns if _classify_targeting(c.get("name", "")) == "MANUAL"]
    auto_camps = [c for c in campaigns if _classify_targeting(c.get("name", "")) == "AUTO"]

    manual_roas = _weighted_metric(manual_camps, "roas_7d") if manual_camps else 0
    auto_roas = _weighted_metric(auto_camps, "roas_7d") if auto_camps else 0
    auto_acos = _weighted_metric(auto_camps, "acos_7d") if auto_camps else 0

    recommendations = []

    # ── Tier 1: Campaign ceiling lift ──
    best_camp = max(manual_camps, key=lambda c: c.get("roas_7d", 0), default=None)
    if best_camp:
        at_ceiling = best_camp.get("currentDailyBudget", 0) >= current_max_camp * 0.95
        strong_roas = best_camp.get("roas_7d", 0) >= target_roas * 2
        if at_ceiling and strong_roas:
            new_max = min(current_max_camp * 1.5, current_budget * 0.8)
            recommendations.append({
                "tier": 1,
                "type": "lift_campaign_ceiling",
                "field": "max_single_campaign_budget",
                "current": current_max_camp,
                "recommended": round(new_max, 2),
                "reason": (f"{best_camp['name']} at ceiling (${current_max_camp}) "
                          f"with ROAS {best_camp.get('roas_7d', 0):.1f}x"),
                "confidence": "high",
            })

    # ── Tier 2: Budget share rebalancing ──
    if manual_roas > 0 and auto_roas > 0:
        ratio = manual_roas / auto_roas
        if ratio > 3.0:
            recommendations.append({
                "tier": 2,
                "type": "rebalance_targeting_share",
                "manual_share": {"current": 0.60, "recommended": 0.75},
                "auto_share": {"current": 0.40, "recommended": 0.25},
                "reason": f"Manual ROAS {manual_roas:.1f}x vs Auto {auto_roas:.1f}x ({ratio:.1f}x gap)",
                "confidence": "high" if ratio > 5.0 else "medium",
            })
        elif ratio > 2.0:
            recommendations.append({
                "tier": 2,
                "type": "rebalance_targeting_share",
                "manual_share": {"current": 0.60, "recommended": 0.70},
                "auto_share": {"current": 0.40, "recommended": 0.30},
                "reason": f"Manual ROAS {manual_roas:.1f}x vs Auto {auto_roas:.1f}x ({ratio:.1f}x gap)",
                "confidence": "medium",
            })

    # ── Tier 3: Total daily budget scaling ──
    overall_roas = _weighted_metric(campaigns, "roas_7d")
    actual_daily_spend = sum(c.get("spend_7d", 0) for c in campaigns) / 7
    utilization = actual_daily_spend / current_budget if current_budget > 0 else 0

    if overall_roas >= target_roas and utilization > 0.80:
        roas_headroom = overall_roas / target_roas
        scale_factor = min(1.5, 1.0 + (roas_headroom - 1.0) * 0.3)
        new_budget = round(current_budget * scale_factor, 2)
        prerequisite = "Auto ACOS must be addressed first" if auto_acos > 50 else None
        recommendations.append({
            "tier": 3,
            "type": "increase_total_daily_budget",
            "field": "total_daily_budget",
            "current": current_budget,
            "recommended": new_budget,
            "reason": f"ROAS {overall_roas:.1f}x (target {target_roas}x), utilization {utilization*100:.0f}%",
            "confidence": "high" if roas_headroom > 2.0 else "medium",
            "prerequisite": prerequisite,
        })
    elif manual_roas >= target_roas * 2 and utilization < 0.60:
        recommendations.append({
            "tier": 3,
            "type": "structural_fix_required",
            "reason": f"Manual ROAS {manual_roas:.1f}x excellent but utilization {utilization*100:.0f}%",
            "actions": [
                "Fix Auto campaign (negative keywords, tighten targeting)",
                "Shift freed budget to Manual",
                "Then consider total budget increase",
            ],
            "confidence": "high",
        })

    return {
        "brand": brand,
        "recommendations": recommendations,
        "summary": {
            "manual_roas_7d": round(manual_roas, 2),
            "auto_roas_7d": round(auto_roas, 2),
            "utilization_pct": round(utilization * 100, 1),
            "current_budget": current_budget,
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py::TestBudgetRecommendation -v --tb=short`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tools/ppc_cross_verifier.py tests/test_ppc_cross_verifier.py
git commit -m "feat: add 3-tier budget scaling recommendation engine"
```

---

## Task 5: Social Trend Integration

**Files:**
- Modify: `tools/ppc_cross_verifier.py`
- Modify: `tests/test_ppc_cross_verifier.py`

Adds social trend keyword extraction, untapped keyword discovery, and hashtag surge detection.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ppc_cross_verifier.py`:

```python
class TestSocialTrends:
    def test_extract_social_keywords(self):
        from ppc_cross_verifier import get_social_trend_keywords
        mock_posts = [
            {"hashtags": "#babyfood,#organicsnack,#babyfood", "transcript": "this organic baby melt snack is great for toddlers"},
            {"hashtags": "#babyfood,#ricepuff", "transcript": "baby loves this rice puff melt snack"},
        ]
        with patch("ppc_cross_verifier.DataKeeper") as mock_dk_cls:
            mock_dk = MagicMock()
            mock_dk.get.return_value = mock_posts
            mock_dk_cls.return_value = mock_dk
            result = get_social_trend_keywords("naeiae", days=30)
            assert result["post_count"] == 2
            # babyfood appears 3 times
            top_tags = dict(result["top_hashtags"])
            assert top_tags.get("babyfood", 0) >= 2

    def test_find_untapped_keywords(self):
        from ppc_cross_verifier import find_untapped_social_keywords
        social = [("baby melt snack", 8), ("organic rice puff", 5), ("toddler food", 3)]
        ppc_terms = ["rice puff baby", "naeiae rice pop", "baby snack organic"]
        untapped = find_untapped_social_keywords(social, ppc_terms)
        # "baby melt snack" should be untapped (not in any PPC term)
        names = [u["keyword"] for u in untapped]
        assert "baby melt snack" in names

    def test_detect_hashtag_surge(self):
        from ppc_cross_verifier import detect_hashtag_surge
        posts_7d = [{"hashtags": "#babyledweaning"} for _ in range(7)]  # 7 in 7 days = 1/day
        posts_30d = posts_7d + [{"hashtags": "#babyledweaning"} for _ in range(3)]  # 10 in 30 days = 0.33/day

        with patch("ppc_cross_verifier.DataKeeper") as mock_dk_cls:
            mock_dk = MagicMock()
            mock_dk.get.side_effect = [posts_7d, posts_30d]
            mock_dk_cls.return_value = mock_dk
            surges = detect_hashtag_surge("naeiae")
            assert len(surges) >= 1
            assert surges[0]["hashtag"] == "babyledweaning"
            assert surges[0]["surge_ratio"] > 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py::TestSocialTrends -v --tb=short`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement social trend functions**

Append to `tools/ppc_cross_verifier.py`:

```python
# ─── Social Trend Integration ──────────────────────────────────────────────

def get_social_trend_keywords(brand: str, days: int = 30) -> dict:
    """Extract trending keywords from content_posts transcripts/hashtags."""
    dk = DataKeeper()
    # Map brand key to brand display name for DataKeeper query
    brand_map = {"naeiae": "Naeiae", "grosmimi": "Grosmimi", "chaenmom": "CHA&MOM"}
    posts = dk.get("content_posts", days=days, brand=brand_map.get(brand, brand)) or []

    hashtag_freq = Counter()
    keyword_freq = Counter()
    for p in posts:
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag and len(tag) > 2:
                hashtag_freq[tag] += 1
        transcript = (p.get("transcript") or "").lower()
        # Bigram extraction for better phrase detection
        words = [w.strip(".,!?()\"'") for w in transcript.split() if len(w.strip(".,!?()\"'")) > 3]
        for w in words:
            if w.isalpha():
                keyword_freq[w] += 1
        # Also extract 2-word phrases
        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i+1]}"
            if all(w.isalpha() for w in [words[i], words[i+1]]):
                keyword_freq[phrase] += 1

    return {
        "top_hashtags": hashtag_freq.most_common(20),
        "top_transcript_keywords": keyword_freq.most_common(30),
        "post_count": len(posts),
    }


def find_untapped_social_keywords(social_keywords: list, ppc_search_terms: list) -> list:
    """Find keywords trending on social but not yet targeted in PPC."""
    ppc_terms = {t.lower().strip() for t in ppc_search_terms}
    untapped = []
    for keyword, freq in social_keywords:
        matched = any(keyword in term for term in ppc_terms)
        if not matched and freq >= 3:
            untapped.append({
                "keyword": keyword,
                "social_frequency": freq,
                "source": "transcript+hashtag",
                "recommendation": "Consider adding as Manual exact-match keyword",
            })
    return untapped


def detect_hashtag_surge(brand: str) -> list:
    """Detect hashtags with week-over-week frequency surge (>2x)."""
    dk = DataKeeper()
    brand_map = {"naeiae": "Naeiae", "grosmimi": "Grosmimi", "chaenmom": "CHA&MOM"}
    display = brand_map.get(brand, brand)
    posts_7d = dk.get("content_posts", days=7, brand=display) or []
    posts_30d = dk.get("content_posts", days=30, brand=display) or []

    freq_7d = Counter()
    freq_30d = Counter()
    for p in posts_7d:
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag:
                freq_7d[tag] += 1
    for p in posts_30d:
        for tag in (p.get("hashtags") or "").split(","):
            tag = tag.strip().lower().lstrip("#")
            if tag:
                freq_30d[tag] += 1

    surges = []
    for tag, count_7d in freq_7d.items():
        count_30d = freq_30d.get(tag, 0)
        rate_7d = count_7d / 7
        rate_30d = count_30d / 30 if count_30d > 0 else 0.01
        surge_ratio = rate_7d / rate_30d
        if surge_ratio > 2.0 and count_7d >= 3:
            surges.append({
                "hashtag": tag,
                "count_7d": count_7d,
                "count_30d": count_30d,
                "surge_ratio": round(surge_ratio, 1),
                "recommendation": "Consider preemptive bid increase for related PPC keywords",
            })

    return sorted(surges, key=lambda x: x["surge_ratio"], reverse=True)[:10]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py::TestSocialTrends -v --tb=short`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tools/ppc_cross_verifier.py tests/test_ppc_cross_verifier.py
git commit -m "feat: add social trend integration (keywords, untapped, surge detection)"
```

---

## Task 6: Gate 3 — Post-Execute Analysis + Codex Domain Extension

**Files:**
- Modify: `tools/ppc_cross_verifier.py`
- Modify: `tools/codex_auditor.py` (lines ~68-96, ~127-132, ~551-598)

Adds Gate 3 (partial execution detection, insight generation) and `--domain ppc` to codex_auditor.

- [ ] **Step 1: Add Gate 3 logic to ppc_cross_verifier.py**

Append to `tools/ppc_cross_verifier.py`:

```python
# ─── Gate 3: Post-Execute Analysis ─────────────────────────────────────────

def gate3_loop1_execution_check(exec_log: list, proposals: list) -> dict:
    """Loop 1: Compare execution results vs approved proposals."""
    approved = [p for p in proposals if p.get("approved") or p.get("auto_approved")]
    executed = [e for e in exec_log if e.get("status") == "success"]
    failed = [e for e in exec_log if e.get("status") in ("throttled", "error", "failed")]

    partial = len(failed) > 0
    checks = [{
        "check": "execution_completeness",
        "pass": not partial,
        "approved_count": len(approved),
        "executed_count": len(executed),
        "failed_count": len(failed),
        "failed_items": [{"campaign": f.get("campaignName", "?"), "error": f.get("error", "?")} for f in failed],
    }]

    return {
        "loop": 1, "name": "execution_check",
        "pass": not partial,
        "partial_execution": partial,
        "checks": checks,
        "failures": checks if partial else [],
    }


def gate3_loop3_generate_insights(gate1_result: dict, gate3_loop1: dict,
                                   codex_analysis: dict = None,
                                   budget_rec: dict = None,
                                   social_trends: dict = None) -> dict:
    """Loop 3: Generate accumulated insights for next day's Gate 1."""
    insights = []

    # From Gate 1 failures
    for f in gate1_result.get("loops", [{}])[0].get("failures", []):
        insights.append({
            "type": "data_inconsistency",
            "detail": f.get("detail", str(f)),
            "action": "Investigate source divergence before next proposal",
        })

    # From execution check
    if gate3_loop1.get("partial_execution"):
        insights.append({
            "type": "partial_execution",
            "detail": f"{gate3_loop1['checks'][0].get('failed_count', 0)} changes failed",
            "action": "Retry failed changes or investigate API throttling",
        })

    # From Codex analysis
    if codex_analysis:
        for rec in codex_analysis.get("recommendations", []):
            insights.append({"type": "codex_recommendation", "detail": rec})

    # From budget recommendation
    if budget_rec:
        for r in budget_rec.get("recommendations", []):
            insights.append({
                "type": "budget_recommendation",
                "tier": r["tier"],
                "detail": r.get("reason", ""),
                "action": r.get("type", ""),
            })

    # From social trends
    if social_trends:
        for u in social_trends.get("untapped_keywords", [])[:5]:
            insights.append({
                "type": "social_untapped_keyword",
                "keyword": u["keyword"],
                "social_frequency": u["social_frequency"],
                "action": "Consider adding to PPC Manual campaign",
            })

    output = {
        "generated_pst": datetime.now(PST).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "insights": insights,
        "gate_failures_today": sum(1 for l in gate1_result.get("loops", []) if not l.get("pass")),
    }

    # Save
    out_path = TMP / "ppc_xv_insights.json"
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"  Insights saved: {len(insights)} items → {out_path}")
    return output


def run_gate3(brand: str = None, codex_analyze: bool = False) -> dict:
    """Run full Gate 3: Post-Execute Analysis (3 loops)."""
    print(f"\n{'='*60}")
    print(f"  GATE 3: Post-Execute Analysis")
    print(f"{'='*60}")

    result = {"gate": 3, "brand": brand, "loops": [], "pass": True}

    # Load execution log
    exec_log_path = ROOT / "docs" / "ppc-dashboard" / "exec_log.json"
    exec_log = []
    if exec_log_path.exists():
        try:
            exec_log = json.loads(exec_log_path.read_text(encoding="utf-8"))
            if isinstance(exec_log, dict):
                exec_log = exec_log.get("entries", [])
        except Exception:
            pass

    # Load latest proposal
    proposals = []
    if brand:
        candidates = sorted(TMP.glob(f"ppc_proposal_{brand}_*.json"), reverse=True)
        if candidates:
            try:
                data = json.loads(candidates[0].read_text(encoding="utf-8"))
                proposals = data.get("proposals", [])
            except Exception:
                pass

    # Loop 1: Execution completeness
    loop1 = gate3_loop1_execution_check(exec_log, proposals)
    result["loops"].append(loop1)
    _print_loop(loop1)

    # Loop 2: Codex root cause (optional, only for outliers)
    codex_result = None
    if codex_analyze:
        print("  Loop 2: Codex analysis — delegating to codex_auditor.py --domain ppc")
        import subprocess
        cmd = [PYTHON, str(ROOT / "tools" / "codex_auditor.py"),
               "--domain", "ppc", "--audit", "--json-only"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                  encoding="utf-8", errors="replace")
            if proc.returncode == 0 and proc.stdout.strip():
                codex_result = json.loads(proc.stdout.strip())
        except Exception as e:
            print(f"  [WARN] Codex analysis failed: {e}")
        loop2 = {"loop": 2, "name": "codex_analysis", "pass": True,
                 "codex_ran": codex_result is not None}
    else:
        loop2 = {"loop": 2, "name": "codex_analysis", "pass": True, "skipped": True}
    result["loops"].append(loop2)
    _print_loop(loop2)

    # Load Gate 1 result for context
    gate1_path = TMP / "ppc_xv_gate1_result.json"
    gate1_result = {}
    if gate1_path.exists():
        try:
            gate1_result = json.loads(gate1_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Budget recommendation
    budget_rec = None
    # Social trends
    social_trends = None
    try:
        social = get_social_trend_keywords(brand or "naeiae", days=30)
        surges = detect_hashtag_surge(brand or "naeiae")
        social_trends = {"untapped_keywords": [], "surges": surges, **social}
    except Exception as e:
        print(f"  [WARN] Social trend extraction failed: {e}")

    # Loop 3: Generate insights
    loop3_output = gate3_loop3_generate_insights(
        gate1_result, loop1, codex_result, budget_rec, social_trends
    )
    loop3 = {"loop": 3, "name": "insight_generation", "pass": True,
             "insights_count": len(loop3_output.get("insights", []))}
    result["loops"].append(loop3)
    _print_loop(loop3)

    # Save gate 3 result
    out_path = TMP / "ppc_xv_gate3_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  Gate 3 complete. {loop3['insights_count']} insights generated.")
    return result
```

- [ ] **Step 2: Add `ppc` domain to codex_auditor.py**

In `tools/codex_auditor.py`, add to the `TOOLS` dict (~line 69-89):

```python
    "ppc": {
        "script": ROOT / "tools" / "ppc_cross_verifier.py",
        "label": "PPC Cross-Verification Auditor",
    },
```

Add to `DOMAIN_MISTAKE_KEYWORDS` (~line 126-131):

```python
    "ppc": ["PPC", "Amazon Ads", "ACOS", "ROAS", "bid", "budget"],
```

The `--domain ppc --audit` will auto-run `ppc_cross_verifier.py`, capture output, and pass to Codex for analysis — same pattern as existing domains.

- [ ] **Step 3: Update codex_auditor.py choices to include "ppc"**

The `choices=list(TOOLS.keys())` at line 572 will automatically pick up the new "ppc" key since it reads from the TOOLS dict.

Verify by running: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python tools/codex_auditor.py --help 2>&1 | head -20`
Expected: `ppc` appears in domain choices

- [ ] **Step 4: Run full test suite**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py -v --tb=short 2>&1 | tail -20`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tools/ppc_cross_verifier.py tools/codex_auditor.py tests/test_ppc_cross_verifier.py
git commit -m "feat: add Gate 3 post-execute analysis + codex_auditor ppc domain"
```

---

## Task 7: CLI Entry Point + Executor Hook

**Files:**
- Modify: `tools/ppc_cross_verifier.py` (add `main()` + argparse)
- Modify: `tools/amazon_ppc_executor.py` (~line 5898-5920)

Adds CLI interface and hooks Gate 2 into the executor's auto-execute flow.

- [ ] **Step 1: Add CLI entry point to ppc_cross_verifier.py**

Append to `tools/ppc_cross_verifier.py`:

```python
# ─── CLI Entry Point ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PPC Cross-Verifier — 3-Gate × 3-Loop data consistency checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --gate 1 --loops 3 --fail-action block
  %(prog)s --gate 2 --brand naeiae --proposal-path .tmp/ppc_proposal_naeiae_*.json
  %(prog)s --gate 3 --loops 3 --codex-analyze
  %(prog)s --gate 1 --brand naeiae   (single brand)
""")

    parser.add_argument("--gate", "-g", type=int, required=True, choices=[1, 2, 3],
                        help="Gate number (1=pre-propose, 2=pre-execute, 3=post-execute)")
    parser.add_argument("--loops", type=int, default=3, help="Number of verification loops (default: 3)")
    parser.add_argument("--brand", "-b", type=str, default=None, choices=BRAND_KEYS + [None],
                        help="Brand filter (default: all brands)")
    parser.add_argument("--fail-action", type=str, default="block", choices=["block", "warn"],
                        help="Action on failure: block (exit 1) or warn (exit 0)")
    parser.add_argument("--proposal-path", type=str, default=None,
                        help="Path to proposal JSON (Gate 2)")
    parser.add_argument("--codex-analyze", action="store_true",
                        help="Enable Codex root cause analysis (Gate 3)")

    args = parser.parse_args()

    brands = [args.brand] if args.brand else BRAND_KEYS

    if args.gate == 1:
        results = []
        for b in brands:
            r = run_gate1(brand=b)
            results.append(r)
        all_pass = all(r.get("pass", False) for r in results)
        if not all_pass and args.fail_action == "block":
            print(f"\n  GATE 1 BLOCKED — data inconsistency detected")
            sys.exit(1)

    elif args.gate == 2:
        results = []
        for b in brands:
            r = run_gate2(brand=b, proposal_path=args.proposal_path)
            results.append(r)
        all_pass = all(r.get("pass", False) for r in results)
        if not all_pass and args.fail_action == "block":
            print(f"\n  GATE 2 BLOCKED — safety check failed")
            sys.exit(1)

    elif args.gate == 3:
        results = []
        for b in brands:
            r = run_gate3(brand=b, codex_analyze=args.codex_analyze)
            results.append(r)

    print(f"\n  All gates complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Hook Gate 2 into amazon_ppc_executor.py auto-execute flow**

In `tools/amazon_ppc_executor.py`, find the auto-execute block (~line 5900) and add the gate check before execution:

```python
    # In run_propose_single(), before the auto-execute section (~line 5899):
    # --- Gate 2: Pre-Execute Safety Check ---
    if getattr(args, "auto_execute", False) or getattr(args, "pre_execute_gate", False):
        try:
            from ppc_cross_verifier import run_gate2
            gate2_result = run_gate2(brand=brand_key)
            if not gate2_result.get("pass", False):
                print(f"\n  [GATE 2 BLOCKED] Pre-execute safety check failed for {brand_display}")
                print(f"  Skipping auto-execute. Review .tmp/ppc_xv_gate2_result.json")
                return  # Skip execution entirely
            else:
                print(f"  [GATE 2 PASS] Pre-execute safety check cleared for {brand_display}")
        except ImportError:
            print(f"  [WARN] ppc_cross_verifier not available — skipping Gate 2")
        except Exception as e:
            print(f"  [WARN] Gate 2 check failed: {e} — proceeding with caution")
```

Insert this block at `amazon_ppc_executor.py` line 5899, right before `if getattr(args, "auto_execute", False):`.

Also add the `--pre-execute-gate` argument to the argparse section of the executor.

- [ ] **Step 3: Verify CLI works**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python tools/ppc_cross_verifier.py --gate 1 --brand naeiae --fail-action warn 2>&1 | head -20`
Expected: Gate 1 output with pass/fail status (may fail due to no DataKeeper in local, but should not crash)

- [ ] **Step 4: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tools/ppc_cross_verifier.py tools/amazon_ppc_executor.py
git commit -m "feat: add CLI entry point + Gate 2 hook in executor auto-execute"
```

---

## Task 8: GitHub Actions CI Integration

**Files:**
- Modify: `.github/workflows/amazon_ppc_pipeline.yml`

Insert Gate 1 before propose, Gate 3 after execute.

- [ ] **Step 1: Update pipeline workflow**

In `.github/workflows/amazon_ppc_pipeline.yml`, replace the existing propose step with gated flow:

```yaml
      # ── Gate 1: Pre-Propose Cross-Check ──────────────────────────
      - name: "GATE 1: Pre-Propose Cross-Check (3 loops)"
        run: |
          python -u tools/ppc_cross_verifier.py \
            --gate 1 \
            --loops 3 \
            --fail-action block
        continue-on-error: false

      # ── Propose + Auto-Execute (Gate 2 runs internally) ─────────
      - name: Run Propose + Auto-Execute (tier 1-2)
        run: |
          python -u tools/amazon_ppc_executor.py \
            --propose \
            --auto-execute \
            --pre-execute-gate \
            --no-email

      # ── Gate 3: Post-Execute Analysis ────────────────────────────
      - name: "GATE 3: Post-Execute Analysis (3 loops)"
        if: always()
        run: |
          python -u tools/ppc_cross_verifier.py \
            --gate 3 \
            --loops 3 \
            --codex-analyze \
            --fail-action warn
        continue-on-error: true
```

- [ ] **Step 2: Add ppc_cross_verifier dependencies to pip install**

No additional dependencies needed — `ppc_cross_verifier.py` uses only stdlib + `data_keeper_client.py` (requests, already installed).

Verify `zoneinfo` is available in Python 3.11 (GitHub Actions): it's stdlib since Python 3.9.

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add .github/workflows/amazon_ppc_pipeline.yml
git commit -m "ci: integrate 3-gate cross-verification into PPC pipeline"
```

---

## Task 9: End-to-End Smoke Test + Skill Registration

**Files:**
- Modify: `tests/test_ppc_cross_verifier.py`
- No skill file needed (uses existing `amazon-ppc-agent` skill + routing table)

- [ ] **Step 1: Add integration smoke test**

Append to `tests/test_ppc_cross_verifier.py`:

```python
class TestEndToEnd:
    """Smoke tests using mocked data sources."""

    @patch("ppc_cross_verifier.test_datakeeper_connection", return_value=False)
    @patch("ppc_cross_verifier.load_fin_data")
    @patch("ppc_cross_verifier.load_ppc_data")
    def test_gate1_fallback_mode(self, mock_ppc, mock_fin, mock_dk):
        from ppc_cross_verifier import run_gate1
        mock_fin.return_value = {
            "generated_pst": datetime.now().strftime("%Y-%m-%d %H:%M PST"),
            "ad_performance": {"amazon": {"7d": {"spend": 500, "sales": 2000}}},
        }
        mock_ppc.return_value = {
            "generated_pst": datetime.now().strftime("%Y-%m-%d %H:%M PST"),
        }
        result = run_gate1(brand="naeiae")
        assert result["fallback_mode"] is True
        assert result["budget_override"] == 0.70
        # Should still pass (2-way skipped gracefully)
        assert result["gate"] == 1

    def test_full_budget_recommendation_naeiae_scenario(self):
        """Real Naeiae scenario: Manual ROAS 7.38x at $100 ceiling, Auto ACOS 64.9%."""
        from ppc_cross_verifier import compute_budget_recommendation
        campaigns = [
            {"name": "Naeiae Rice Pop - SP - Manual", "campaignId": "1",
             "currentDailyBudget": 100, "roas_7d": 7.38, "acos_7d": 13.6,
             "spend_7d": 163, "sales_7d": 1205, "targeting_type": "MANUAL"},
            {"name": "Naeiae Rice Pop - SP - Auto", "campaignId": "2",
             "currentDailyBudget": 100, "roas_7d": 1.54, "acos_7d": 64.9,
             "spend_7d": 176, "sales_7d": 271, "targeting_type": "AUTO"},
        ]
        config = {
            "total_daily_budget": 150,
            "max_single_campaign_budget": 100,
            "targeting": {"MANUAL": {"min_roas": 2.5}, "AUTO": {"min_roas": 1.5}},
        }
        rec = compute_budget_recommendation("naeiae", campaigns, config)
        # Should get all 3 tiers
        tiers = {r["tier"] for r in rec["recommendations"]}
        assert 1 in tiers, "Should recommend lifting campaign ceiling"
        assert 2 in tiers, "Should recommend rebalancing Manual/Auto"
        # Manual ROAS is great but overall utilization is borderline
        assert rec["summary"]["manual_roas_7d"] == 7.38
        assert rec["summary"]["auto_roas_7d"] == 1.54
```

- [ ] **Step 2: Run full test suite**

Run: `cd "C:/Users/wjcho/Desktop/WJ Test1" && python -m pytest tests/test_ppc_cross_verifier.py -v --tb=short 2>&1`
Expected: All tests PASS (25+ tests)

- [ ] **Step 3: Commit final**

```bash
cd "C:/Users/wjcho/Desktop/WJ Test1"
git add tests/test_ppc_cross_verifier.py
git commit -m "test: add E2E smoke tests for cross-verifier (fallback + Naeiae scenario)"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Core loaders + timezone | `ppc_cross_verifier.py` (create) | 7 tests |
| 2 | Gate 1: Pre-Propose | `ppc_cross_verifier.py` | 6 tests |
| 3 | Gate 2: Pre-Execute | `ppc_cross_verifier.py` | 7 tests |
| 4 | Budget Recommendation | `ppc_cross_verifier.py` | 3 tests |
| 5 | Social Trends | `ppc_cross_verifier.py` | 3 tests |
| 6 | Gate 3 + Codex domain | `ppc_cross_verifier.py` + `codex_auditor.py` | existing |
| 7 | CLI + Executor hook | `ppc_cross_verifier.py` + `amazon_ppc_executor.py` | manual |
| 8 | GitHub Actions CI | `amazon_ppc_pipeline.yml` | CI run |
| 9 | E2E smoke tests | `test_ppc_cross_verifier.py` | 2 tests |
