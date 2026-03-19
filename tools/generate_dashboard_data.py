"""Generate data.js for PPC Dashboard from proposal JSONs + execution JSONs.

Reads .tmp/ppc_proposal_*.json and .tmp/ppc_executed_*.json,
generates docs/ppc-dashboard/data.js with all brands/dates.

Usage:
    python tools/generate_dashboard_data.py
    python tools/generate_dashboard_data.py --push   # Also git push to trigger GitHub Pages
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
PROPOSAL_DIR = ROOT / ".tmp"
EXEC_DIR = ROOT / ".tmp"
OUTPUT = ROOT / "docs" / "ppc-dashboard" / "data.js"
BT_OUTPUT = ROOT / "docs" / "ppc-dashboard" / "bt_data.js"
EXEC_LOG = ROOT / "docs" / "ppc-dashboard" / "exec_log.json"

PDT = timezone(timedelta(hours=-7))

BRAND_LABELS = {"grosmimi": "Grosmimi", "naeiae": "Naeiae", "chaenmom": "CHA&MOM"}


def _sanitize_bud_after(bud_after, bud_before):
    """Never let bud_after be less than bud_before (prevents legacy budget decrease bugs)."""
    if bud_after is None:
        return None
    if bud_before and bud_after < bud_before:
        return None  # Treat as no-change
    if bud_before and bud_after == bud_before:
        return None  # Same = no real change
    return bud_after


def detect_brand(item):
    bk = item.get("brand_key", "")
    if bk:
        return bk
    cn = (item.get("campaignName", "") or "").lower()
    if "cha&mom" in cn or "cha_mom" in cn:
        return "chaenmom"
    if "grosmimi" in cn:
        return "grosmimi"
    return "naeiae"


def _load_existing_data_js():
    """Read existing data.js to preserve old dates not in .tmp/ anymore."""
    if not OUTPUT.exists():
        return {}
    try:
        text = OUTPUT.read_text(encoding="utf-8")
        # Strip "const PPC_DATA = " prefix and ";" suffix
        json_str = text.replace("const PPC_DATA = ", "", 1).rstrip().rstrip(";")
        data = json.loads(json_str)
        return data.get("brands", {})
    except Exception as e:
        print(f"  [WARN] Could not read existing data.js: {e}")
        return {}


def load_proposals():
    """Load proposal JSONs by brand and date, merging with existing data.js."""
    brands = defaultdict(lambda: defaultdict(dict))

    # ── Phase 0: Load existing data.js to preserve old dates ──
    existing = _load_existing_data_js()
    for bk in ["grosmimi", "naeiae", "chaenmom"]:
        if bk in existing:
            old_dates = existing[bk].get("dates", {})
            for dt, dt_data in old_dates.items():
                brands[bk][dt] = dt_data
            # Preserve execution_log from existing data
            old_exec_log = existing[bk].get("execution_log", [])
            if old_exec_log:
                brands[bk]["execution_log"] = old_exec_log
    if existing:
        old_count = sum(len(v.get("dates", {})) for v in existing.values())
        print(f"  Loaded {old_count} existing date(s) from data.js")

    # ── Phase 1: Overlay new proposals from .tmp/ JSONs (newer wins) ──
    for f in sorted(glob.glob(str(PROPOSAL_DIR / "ppc_proposal_*_*.json"))):
        try:
            raw = json.loads(Path(f).read_text(encoding="utf-8"))
            # Support both list format (legacy) and dict format (new save_proposal)
            if isinstance(raw, dict):
                data = raw.get("proposals", [])
                # Merge all_campaigns: add any campaigns not already in proposals
                all_camps = raw.get("all_campaigns", [])
                if all_camps:
                    proposal_names = {p.get("campaignName", "") for p in data}
                    for c in all_camps:
                        if c.get("campaignName", "") not in proposal_names:
                            data.append(c)
            elif isinstance(raw, list):
                data = raw
            else:
                continue
            if not data:
                continue
            # Extract brand and date from filename: ppc_proposal_{brand}_{date}.json
            stem = Path(f).stem  # ppc_proposal_naeiae_20260315
            parts = stem.replace("ppc_proposal_", "").split("_")
            if len(parts) >= 2:
                bk = parts[0]
                dt_str = parts[1][:8]
                dt = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
            else:
                continue

            # Parse proposals into dashboard format
            campaigns = []
            harvest = []
            negate = []

            # --- Keyword proposals (separate field in new format) ---
            kw_proposals = raw.get("keyword_proposals", []) if isinstance(raw, dict) else []
            for kw in kw_proposals:
                if not isinstance(kw, dict):
                    continue
                kw_type = kw.get("type", "") or kw.get("action", "")
                if kw_type == "harvest":
                    harvest.append({
                        "term": kw.get("searchTerm", kw.get("keyword", "")),
                        "sales": kw.get("sales", kw.get("sales_7d", 0)),
                        "cost": kw.get("cost", kw.get("spend_7d", 0)),
                        "acos": round(kw.get("acos", 0), 1) if kw.get("acos") else 0,
                        "clicks": kw.get("clicks", 0),
                        "purchases": kw.get("purchases", 0),
                        "bid": kw.get("proposed_bid", kw.get("new_bid", 0)),
                        "campaign": kw.get("sourceCampaignName", kw.get("campaignName", ""))[:30],
                        "sim_confirmed": kw.get("sim_confirmed", False),
                    })
                elif kw_type.startswith("negate"):
                    negate.append({
                        "term": kw.get("searchTerm", kw.get("keyword", "")),
                        "cost": kw.get("cost", kw.get("spend_7d", 0)),
                        "sales": kw.get("sales", kw.get("sales_7d", 0)),
                        "acos": round(kw.get("acos", 0), 1) if kw.get("acos") else 0,
                        "clicks": kw.get("clicks", 0),
                        "type": kw_type,
                        "reason": kw.get("reason", ""),
                        "campaign": kw.get("sourceCampaignName", kw.get("campaignName", ""))[:30],
                        "sim_save": kw.get("sim_save", 0),
                    })

            # --- Campaign proposals (legacy also checked via action field) ---
            for item in data:
                if not isinstance(item, dict):
                    continue
                action = item.get("action", "") or item.get("proposed_action", "")
                # Legacy: keyword proposals mixed in with campaigns
                if action in ("harvest",):
                    harvest.append({
                        "term": item.get("keyword", item.get("searchTerm", "")),
                        "sales": item.get("sales_7d", item.get("sales", 0)),
                        "cost": item.get("spend_7d", item.get("cost", 0)),
                        "acos": round(item.get("spend_7d", item.get("cost", 0)) / item.get("sales_7d", item.get("sales", 1)) * 100, 1) if item.get("sales_7d", item.get("sales")) else 0,
                        "clicks": item.get("clicks", 0),
                        "purchases": item.get("purchases", 0),
                        "bid": item.get("new_bid", item.get("proposed_bid", 0)),
                        "campaign": item.get("campaignName", item.get("sourceCampaignName", ""))[:30],
                        "sim_confirmed": item.get("sim_confirmed", False),
                    })
                elif action.startswith("negate"):
                    negate.append({
                        "term": item.get("keyword", item.get("searchTerm", "")),
                        "cost": item.get("spend_7d", item.get("cost", 0)),
                        "sales": item.get("sales_7d", item.get("sales", 0)),
                        "acos": round(item.get("spend_7d", item.get("cost", 0)) / item.get("sales_7d", item.get("sales", 1)) * 100, 1) if item.get("sales_7d", item.get("sales")) else 0,
                        "clicks": item.get("clicks", 0),
                        "type": action,
                        "reason": item.get("reason", ""),
                        "campaign": item.get("campaignName", item.get("sourceCampaignName", ""))[:30],
                        "sim_save": item.get("sim_save", 0),
                    })
                else:
                    # Campaign-level proposal
                    # Handle both old (flat) and new (nested metrics) formats
                    m7 = item.get("metrics", {}).get("7d", {})
                    roas7 = item.get("roas_7d") or m7.get("roas", 0) or 0
                    spend7 = item.get("spend_7d") or m7.get("spend", 0) or 0
                    sales7 = item.get("sales_7d") or m7.get("sales", 0) or 0
                    acos7 = round(1 / roas7 * 100, 1) if roas7 > 0 else 0
                    cpc = item.get("cpc") or m7.get("cpc", 0) or 0
                    ctr = item.get("ctr") or m7.get("ctr", 0) or 0
                    camp_type = item.get("campaign_type") or item.get("campaignType", "AUTO")
                    ad_type = item.get("adType", item.get("ad_type", "SP"))
                    campaigns.append({
                        "name": item.get("campaignName", ""),
                        "type": camp_type,
                        "ad_type": ad_type,
                        "roas7d": roas7,
                        "acos7d": acos7,
                        "spend7d": round(spend7),
                        "sales7d": round(sales7),
                        "cpc": cpc,
                        "ctr": ctr,
                        "action": action,
                        "bid_pct": item.get("bid_change_pct"),
                        "bud_before": item.get("old_budget") or item.get("currentDailyBudget"),
                        "bud_after": _sanitize_bud_after(
                            item.get("new_budget") or item.get("new_daily_budget"),
                            item.get("old_budget") or item.get("currentDailyBudget")),
                        "tier": item.get("tier", ""),
                        "reason": item.get("reason", ""),
                        "approved": item.get("approved", False),
                    })

            # Compute summary from campaign-level data
            sum_spend = sum(c.get("spend7d", 0) for c in campaigns)
            sum_sales = sum(c.get("sales7d", 0) for c in campaigns)
            sum_roas = round(sum_sales / sum_spend, 2) if sum_spend else 0
            sum_acos = f"{round(sum_spend / sum_sales * 100, 1)}%" if sum_sales else ""

            brands[bk][dt] = {
                "generated": datetime.now(PDT).strftime("%Y-%m-%dT%H:%M"),
                "executed": False,
                "executed_at": "",
                "summary_7d": {"spend": round(sum_spend), "sales": round(sum_sales), "roas": sum_roas, "acos": sum_acos},
                "campaigns": campaigns,
                "harvest": harvest,
                "negate": negate,
                "counts": {
                    "campaigns": len(campaigns),
                    "harvest": len(harvest),
                    "negate": len(negate),
                },
            }
            print(f"  {bk} {dt}: {len(campaigns)} camps, {len(harvest)}H, {len(negate)}N")
        except Exception as e:
            print(f"  [WARN] {f}: {e}")
            continue

    # Keep ALL dates per brand (accumulate proposal history)

    return brands


def inject_executions(brands):
    """Mark proposals as executed based on ppc_executed_*.json files.
    Persists execution log to exec_log.json (cumulative across runs)."""
    # Load existing persistent log
    persistent_log = {}
    if EXEC_LOG.exists():
        try:
            persistent_log = json.loads(EXEC_LOG.read_text(encoding="utf-8"))
        except Exception:
            persistent_log = {}

    # Collect new executions from .tmp/
    # Latest execution wins: for same brand+date, replace all old entries
    for f in sorted(glob.glob(str(EXEC_DIR / "ppc_executed_2026*.json"))):
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            dt_str = Path(f).stem.replace("ppc_executed_", "")[:8]
            dt = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
            # Group new items by brand
            new_by_brand = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                bk = detect_brand(item)
                item["exec_date"] = dt
                new_by_brand.setdefault(bk, []).append(item)
            # For each brand with new data, merge entries for this date (dedup by key)
            def _dedup_key(e):
                return (str(e.get("campaignId", "")), e.get("action", ""), (e.get("keyword") or "").lower())

            for bk, new_items in new_by_brand.items():
                existing = persistent_log.setdefault(bk, [])
                other_dates = [e for e in existing if e.get("exec_date", "") != dt]
                same_date = [e for e in existing if e.get("exec_date", "") == dt]
                seen = set()
                merged = []
                for e in new_items:  # New items take priority
                    k = _dedup_key(e)
                    if k not in seen:
                        seen.add(k)
                        merged.append(e)
                for e in same_date:  # Keep old items not in new batch
                    k = _dedup_key(e)
                    if k not in seen:
                        seen.add(k)
                        merged.append(e)
                persistent_log[bk] = other_dates + merged
        except Exception:
            continue

    # Save persistent log
    EXEC_LOG.write_text(json.dumps(persistent_log, ensure_ascii=False, indent=1), encoding="utf-8")

    # Inject into brands data (create brand entry if missing)
    for bk, exec_list in persistent_log.items():
        if bk not in brands:
            brands[bk] = {}
        brands[bk]["execution_log"] = exec_list
        # Mark each date that has execution records
        dates = sorted(d for d in brands[bk].keys() if d != "execution_log")
        for d in dates:
            d_execs = [e for e in exec_list if e.get("exec_date", "") == d]
            if d_execs:
                brands[bk][d]["executed"] = True
                brands[bk][d]["executed_at"] = d
                for item in d_execs:
                    cn = item.get("campaignName", "")
                    for c in brands[bk][d].get("campaigns", []):
                        if c["name"] == cn:
                            c["approved"] = True
        print(f"  {bk}: {len(exec_list)} execution records (persistent)")


def generate_bt_data():
    """Generate bt_data.js from backtest JSONs."""
    bt = {}
    for brand in ["grosmimi", "naeiae", "chaenmom"]:
        files = sorted(glob.glob(str(ROOT / ".tmp" / "ppc_simulator" / f"{brand}_backtest_*.json")))
        entries = []
        for f in files:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            if not d.get("data_inputs"):
                continue  # Skip old format
            entries.append(d)
        if entries:
            bt[brand] = entries
    output = "const BACKTEST_LOG = " + json.dumps(bt, ensure_ascii=False, indent=1) + ";"
    BT_OUTPUT.write_text(output, encoding="utf-8")
    print(f"  bt_data.js: {len(output)} chars")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true", help="Git add + commit + push after generation")
    args = parser.parse_args()

    print("=== Generating PPC Dashboard Data ===")

    print("\n[1/3] Loading proposals...")
    brands_data = load_proposals()

    print("\n[2/3] Injecting executions...")
    inject_executions(brands_data)

    print("\n[3/3] Writing data files...")

    # Build PPC_DATA
    now_pst = datetime.now(PDT).strftime("%Y-%m-%d %H:%M PST")
    ppc = {"generated_pst": now_pst, "brands": {}}
    for bk in ["grosmimi", "naeiae", "chaenmom"]:
        bd = brands_data.get(bk, {})
        exec_log = bd.pop("execution_log", [])
        ppc["brands"][bk] = {"dates": bd, "execution_log": exec_log}

    output = "const PPC_DATA = " + json.dumps(ppc, ensure_ascii=False, indent=1) + ";"
    OUTPUT.write_text(output, encoding="utf-8")
    print(f"  data.js: {len(output)} chars")

    generate_bt_data()

    if args.push:
        print("\n[Push] Committing to git...")
        os.chdir(str(ROOT))
        subprocess.run(["git", "add", "docs/ppc-dashboard/data.js", "docs/ppc-dashboard/bt_data.js"], check=True)
        subprocess.run(["git", "commit", "-m", "auto: update dashboard data.js + bt_data.js [skip ci]"], check=False)
        subprocess.run(["git", "push"], check=True)
        print("  Pushed to GitHub → Pages will rebuild in ~1 min")


if __name__ == "__main__":
    main()
