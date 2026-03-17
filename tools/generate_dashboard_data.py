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

PDT = timezone(timedelta(hours=-7))

BRAND_LABELS = {"grosmimi": "Grosmimi", "naeiae": "Naeiae", "chaenmom": "CHA&MOM"}


def detect_brand(item):
    cn = (item.get("campaignName", "") or "").lower()
    if "cha&mom" in cn or "cha_mom" in cn:
        return "chaenmom"
    if "grosmimi" in cn:
        return "grosmimi"
    return "naeiae"


def load_proposals():
    """Load proposal JSONs by brand and date."""
    brands = defaultdict(lambda: defaultdict(dict))

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

            for item in data:
                if not isinstance(item, dict):
                    continue
                action = item.get("action", "") or item.get("proposed_action", "")
                if action in ("harvest",):
                    harvest.append({
                        "term": item.get("keyword", ""),
                        "sales": item.get("sales_7d", 0),
                        "cost": item.get("spend_7d", 0),
                        "acos": round(item["spend_7d"] / item["sales_7d"] * 100, 1) if item.get("sales_7d") else 0,
                        "clicks": item.get("clicks", 0),
                        "purchases": item.get("purchases", 0),
                        "bid": item.get("new_bid", 0),
                        "campaign": item.get("campaignName", "")[:30],
                        "sim_confirmed": item.get("sim_confirmed", False),
                    })
                elif action.startswith("negate"):
                    negate.append({
                        "term": item.get("keyword", ""),
                        "cost": item.get("spend_7d", 0),
                        "sales": item.get("sales_7d", 0),
                        "acos": round(item["spend_7d"] / item["sales_7d"] * 100, 1) if item.get("sales_7d") else 0,
                        "clicks": item.get("clicks", 0),
                        "type": action,
                        "reason": item.get("reason", ""),
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
                        "bud_after": item.get("new_budget") or item.get("new_daily_budget"),
                        "tier": item.get("tier", ""),
                        "reason": item.get("reason", ""),
                        "approved": item.get("approved", False),
                    })

            brands[bk][dt] = {
                "generated": datetime.now(PDT).strftime("%Y-%m-%dT%H:%M"),
                "executed": False,
                "executed_at": "",
                "summary_7d": {"spend": 0, "sales": 0, "roas": 0, "acos": ""},
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

    return brands


def inject_executions(brands):
    """Mark proposals as executed based on ppc_executed_*.json files."""
    exec_by_brand = defaultdict(list)

    for f in sorted(glob.glob(str(EXEC_DIR / "ppc_executed_2026*.json"))):
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            dt_str = Path(f).stem.replace("ppc_executed_", "")[:8]
            dt = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
            for item in data:
                if not isinstance(item, dict):
                    continue
                bk = detect_brand(item)
                item["exec_date"] = dt
                exec_by_brand[bk].append(item)
        except Exception:
            continue

    for bk, exec_list in exec_by_brand.items():
        if bk not in brands:
            continue
        brands[bk]["execution_log"] = exec_list
        # Mark closest date as executed
        dates = sorted(brands[bk].keys())
        dates = [d for d in dates if d != "execution_log"]
        if dates:
            latest = dates[-1]
            brands[bk][latest]["executed"] = True
            brands[bk][latest]["executed_at"] = exec_list[0].get("exec_date", "")
            # Mark campaigns as approved
            for item in exec_list:
                cn = item.get("campaignName", "")
                for c in brands[bk][latest].get("campaigns", []):
                    if c["name"] == cn:
                        c["approved"] = True
        print(f"  {bk}: {len(exec_list)} execution records injected")


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
