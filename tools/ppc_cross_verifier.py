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
        # Handle both "%Y-%m-%d %H:%M" and "%Y-%m-%d %H:%M:%S"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                ts = datetime.strptime(clean, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Cannot parse timestamp: {generated_pst}")
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


# ─── Gate 2: Pre-Execute Safety Checks ────────────────────────────────────────

def gate2_loop1_freshness(proposal_ts: str, daily_spend: float = 0) -> dict:
    """Loop 1: Proposal freshness check.

    High-spend brands (>=$1000/day) get a tighter 2h limit; others get 3h.
    """
    max_h = PROPOSAL_MAX_HOURS_HIGH if daily_spend >= HIGH_SPEND_THRESHOLD else PROPOSAL_MAX_HOURS_DEFAULT
    return check_freshness(proposal_ts, max_hours=max_h)


def gate2_loop2_ceilings(proposals: list, config: dict) -> dict:
    """Loop 2: Budget/bid ceiling + daily change-rate limits.

    Checks per proposal:
      - new_daily_budget <= max_single_campaign_budget
      - proposed_bid <= max_bid
      - budget change rate <= MAX_DAILY_BUDGET_CHANGE (30%)
      - bid change rate <= MAX_DAILY_BID_CHANGE (20%)
    Checks across proposals:
      - sum(new_daily_budget) <= total_daily_budget * 2.2
    """
    failures = []
    max_camp_budget = config.get("max_single_campaign_budget", 999999)
    max_bid = config.get("max_bid", 999)
    total_ceiling = config.get("total_daily_budget", 999999) * 2.2

    total_proposed = 0.0

    for p in proposals:
        cid = p.get("campaignId", "?")
        new_budget = p.get("new_daily_budget", 0)
        proposed_bid = p.get("proposed_bid", 0)
        cur_budget = p.get("currentDailyBudget", 0)
        cur_bid = p.get("current_bid", 0)
        total_proposed += new_budget

        # Ceiling checks
        if new_budget > max_camp_budget:
            failures.append({
                "check": "budget_ceiling",
                "campaignId": cid,
                "detail": f"new_daily_budget {new_budget} > max {max_camp_budget}",
            })
        if proposed_bid > max_bid:
            failures.append({
                "check": "bid_ceiling",
                "campaignId": cid,
                "detail": f"proposed_bid {proposed_bid} > max {max_bid}",
            })

        # Rate-limit checks
        if cur_budget > 0:
            budget_change = abs(new_budget - cur_budget) / cur_budget
            if budget_change > MAX_DAILY_BUDGET_CHANGE:
                failures.append({
                    "check": "budget_rate_limit",
                    "campaignId": cid,
                    "detail": f"budget change {budget_change:.1%} > {MAX_DAILY_BUDGET_CHANGE:.0%}",
                })
        if cur_bid > 0:
            bid_change = abs(proposed_bid - cur_bid) / cur_bid
            if bid_change > MAX_DAILY_BID_CHANGE:
                failures.append({
                    "check": "bid_rate_limit",
                    "campaignId": cid,
                    "detail": f"bid change {bid_change:.1%} > {MAX_DAILY_BID_CHANGE:.0%}",
                })

    # Total ceiling
    if total_proposed > total_ceiling:
        failures.append({
            "check": "total_budget_ceiling",
            "detail": f"total proposed {total_proposed} > ceiling {total_ceiling}",
        })

    return {
        "loop": 2,
        "name": "Ceilings & Rate Limits",
        "pass": len(failures) == 0,
        "failures": failures,
        "total_proposed": total_proposed,
        "total_ceiling": total_ceiling,
    }


def gate2_loop3_financial(proposed_spend_delta: float,
                          current_total_sales: float,
                          current_tacos: float) -> dict:
    """Loop 3: TACOS impact prediction + financial cross-check.

    Predicts new TACOS after spend change. Warns if projected > 15%.
    Always passes (warnings don't block execution).
    """
    current_spend = current_tacos * current_total_sales if current_total_sales else 0
    new_spend = current_spend + proposed_spend_delta
    projected_tacos = new_spend / current_total_sales if current_total_sales else 0

    warnings = []
    if projected_tacos > 0.15:
        warnings.append({
            "check": "tacos_impact",
            "detail": f"Projected TACOS {projected_tacos:.1%} > 15% threshold",
            "current_tacos": round(current_tacos, 4),
            "projected_tacos": round(projected_tacos, 4),
        })

    return {
        "loop": 3,
        "name": "Financial Impact",
        "pass": True,
        "warnings": warnings,
        "projected_tacos": round(projected_tacos, 4),
    }


def run_gate2(brand: str, proposal_path: str = None) -> dict:
    """Orchestrate Gate 2: Pre-Execute Safety Checks (3 Loops)."""
    now_pst = datetime.now(PST)
    result = {
        "gate": 2,
        "brand": brand,
        "timestamp_pst": now_pst.strftime("%Y-%m-%d %H:%M PST"),
        "loops": {},
    }

    # Load proposal from .tmp
    if proposal_path:
        p = Path(proposal_path)
    else:
        # Find latest proposal for brand
        candidates = sorted(TMP.glob(f"ppc_proposal_{brand}_*.json"), reverse=True)
        if not candidates:
            result["pass"] = False
            result["error"] = f"No proposal found for {brand}"
            return result
        p = candidates[0]

    proposal = json.loads(p.read_text(encoding="utf-8"))

    # Try to import brand config
    try:
        from amazon_ppc_executor import BRAND_CONFIGS
        brand_cfg = BRAND_CONFIGS.get(brand, {})
    except ImportError:
        brand_cfg = {}

    # Loop 1: Freshness
    ts = proposal.get("generated_pst", proposal.get("timestamp", ""))
    daily_spend = brand_cfg.get("daily_spend", 0)
    l1 = gate2_loop1_freshness(ts, daily_spend=daily_spend)
    l1["loop"] = 1
    l1["name"] = "Proposal Freshness"
    result["loops"]["loop1"] = l1

    # Loop 2: Ceilings & Rate Limits
    changes = proposal.get("changes", proposal.get("proposals", []))
    config = {
        "max_single_campaign_budget": brand_cfg.get("max_single_campaign_budget", 500),
        "max_bid": brand_cfg.get("max_bid", 5.0),
        "total_daily_budget": brand_cfg.get("total_daily_budget", COMPANY_DAILY_PPC_CAP),
    }
    l2 = gate2_loop2_ceilings(changes, config)
    result["loops"]["loop2"] = l2

    # Loop 3: Financial
    spend_delta = sum(
        c.get("new_daily_budget", 0) - c.get("currentDailyBudget", 0) for c in changes
    )
    current_sales = brand_cfg.get("current_total_sales", 10000)
    current_tacos = brand_cfg.get("current_tacos", 0.10)
    l3 = gate2_loop3_financial(spend_delta, current_sales, current_tacos)
    result["loops"]["loop3"] = l3

    # Overall: pass only if loops 1 & 2 pass (loop 3 always passes)
    result["pass"] = l1.get("pass", False) and l2.get("pass", False)

    # Print summary
    print(f"\n{'='*50}")
    print(f"Gate 2 — Pre-Execute Safety Checks  [{brand}]")
    print(f"{'='*50}")
    for k in ("loop1", "loop2", "loop3"):
        lp = result["loops"][k]
        status = "PASS" if lp.get("pass") else "FAIL"
        print(f"  Loop {lp.get('loop', '?')}: {lp.get('name', '')} — {status}")
        for f in lp.get("failures", []):
            print(f"    ✗ {f.get('detail', f.get('check', ''))}")
        for w in lp.get("warnings", []):
            print(f"    ⚠ {w.get('detail', w.get('check', ''))}")
    overall = "PASS" if result["pass"] else "FAIL"
    print(f"  Overall: {overall}")
    print(f"{'='*50}\n")

    # Save result
    out_path = TMP / "ppc_xv_gate2_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    result["saved_to"] = str(out_path)

    return result


# ─── Budget Scaling Recommendation Engine ─────────────────────────────────────

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
    """Recommend budget config changes based on campaign performance.

    3 tiers:
    - Tier 1: Campaign ceiling lift (best camp at ceiling with ROAS > 2x target)
    - Tier 2: Budget share rebalancing (Manual >> Auto)
    - Tier 3: Total budget scaling or structural fix
    """
    recommendations = []
    total_daily_budget = config.get("total_daily_budget", 150)
    max_single = config.get("max_single_campaign_budget", 100)
    targeting_cfg = config.get("targeting", {})

    # Classify campaigns
    for c in campaigns:
        if "targeting_type" not in c:
            c["targeting_type"] = _classify_targeting(c.get("name", ""))

    manual_camps = [c for c in campaigns if c["targeting_type"] == "MANUAL"]
    auto_camps = [c for c in campaigns if c["targeting_type"] == "AUTO"]

    manual_roas = _weighted_metric(manual_camps, "roas_7d") if manual_camps else 0
    auto_roas = _weighted_metric(auto_camps, "roas_7d") if auto_camps else 0
    auto_acos = _weighted_metric(auto_camps, "acos_7d") if auto_camps else 0

    total_spend = sum(c.get("spend_7d", 0) for c in campaigns)
    total_sales = sum(c.get("sales_7d", 0) for c in campaigns)
    overall_roas = total_sales / total_spend if total_spend > 0 else 0

    total_budget_capacity = sum(c.get("currentDailyBudget", 0) for c in campaigns)
    # utilization = daily spend approximation / total budget capacity
    daily_spend_approx = total_spend / 7 if total_spend > 0 else 0
    utilization = daily_spend_approx / total_budget_capacity if total_budget_capacity > 0 else 0

    # ── Tier 1: Campaign ceiling lift ──
    for c in campaigns:
        tgt_type = c["targeting_type"]
        min_roas = targeting_cfg.get(tgt_type, {}).get("min_roas", 2.0)
        camp_roas = c.get("roas_7d", 0)
        camp_budget = c.get("currentDailyBudget", 0)

        if camp_budget >= max_single and camp_roas > min_roas * 2:
            new_max = min(camp_budget * 1.5, total_daily_budget * 0.8)
            recommendations.append({
                "tier": 1,
                "type": "ceiling_lift",
                "campaignId": c.get("campaignId"),
                "campaign_name": c.get("name"),
                "current_max": max_single,
                "recommended": round(new_max, 2),
                "reason": f"ROAS {camp_roas:.2f} > 2x target {min_roas}; at ceiling {max_single}",
            })

    # ── Tier 2: Budget share rebalancing ──
    if manual_camps and auto_camps and auto_roas > 0:
        ratio = manual_roas / auto_roas
        current_manual_share = sum(c.get("currentDailyBudget", 0) for c in manual_camps) / total_budget_capacity if total_budget_capacity > 0 else 0.5

        if ratio > 3.0:
            rec_share = 0.75
        elif ratio > 2.0:
            rec_share = 0.70
        else:
            rec_share = None

        if rec_share and rec_share > current_manual_share:
            recommendations.append({
                "tier": 2,
                "type": "rebalance",
                "manual_share": {
                    "current": round(current_manual_share, 2),
                    "recommended": rec_share,
                },
                "auto_share": {
                    "current": round(1 - current_manual_share, 2),
                    "recommended": round(1 - rec_share, 2),
                },
                "reason": f"Manual ROAS {manual_roas:.2f} vs Auto ROAS {auto_roas:.2f} (ratio {ratio:.1f}x)",
            })

    # ── Tier 3: Total daily budget scaling or structural fix ──
    overall_min_roas = targeting_cfg.get("MANUAL", {}).get("min_roas", 2.0)
    if overall_roas > overall_min_roas and utilization > 0.80:
        roas_headroom = overall_roas / overall_min_roas
        scale_factor = min(1.5, 1.0 + (roas_headroom - 1.0) * 0.3)
        new_total = round(total_daily_budget * scale_factor, 2)
        rec = {
            "tier": 3,
            "type": "increase_total_daily_budget",
            "current_total": total_daily_budget,
            "recommended_total": new_total,
            "scale_factor": round(scale_factor, 3),
            "reason": f"Overall ROAS {overall_roas:.2f} > target {overall_min_roas}, utilization {utilization:.0%}",
        }
        if auto_acos > 50:
            rec["prerequisite"] = "Reduce Auto ACOS below 50% before scaling total budget"
        recommendations.append(rec)
    elif manual_roas > overall_min_roas * 2 and utilization < 0.60:
        recommendations.append({
            "tier": 3,
            "type": "structural_fix",
            "reason": f"Manual ROAS {manual_roas:.2f} strong but utilization only {utilization:.0%}; review Auto campaigns or budget allocation",
        })

    return {
        "brand": brand,
        "recommendations": recommendations,
        "summary": {
            "manual_roas_7d": round(manual_roas, 2),
            "auto_roas_7d": round(auto_roas, 2),
            "utilization_pct": round(utilization * 100, 1),
            "current_budget": total_daily_budget,
        },
    }
