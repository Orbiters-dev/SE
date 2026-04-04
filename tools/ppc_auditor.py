"""
PPC Pipeline Auditor — 2-Round Config & Execution Validator
=============================================================
Runs after propose (Round 1) and execute (Round 2) to catch config drift,
budget cap violations, and phantom changes before they reach production.

Usage:
    python tools/ppc_auditor.py --round 1            # Post-propose audit
    python tools/ppc_auditor.py --round 2            # Post-execute audit
    python tools/ppc_auditor.py --round 1 --recheck  # Re-audit after auto-fix
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# ─── Encoding fix (Windows cp949) ────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
TMP = ROOT / ".tmp"
AUDIT_DIR = TMP / "ppc_audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

BRAND_KEYS = ["naeiae", "grosmimi", "chaenmom"]


# ─── Verdict Schema ──────────────────────────────────────────────────────────

def make_verdict(round_num, checks, recheck=False):
    failures = [c for c in checks if c["status"] == "FAIL"]
    warnings = [c for c in checks if c["status"] == "WARN"]
    passed = [c for c in checks if c["status"] == "PASS"]

    critical = [f for f in failures if f.get("severity") == "CRITICAL"]
    high = [f for f in failures if f.get("severity") == "HIGH"]

    if critical or high:
        verdict = "FAIL"
    elif failures:
        verdict = "DEGRADED"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "domain": "ppc_pipeline",
        "round": round_num,
        "recheck": recheck,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks_passed": len(passed),
        "checks_total": len(checks),
        "failures": [{"check": f["name"], "expected": f.get("expected", ""),
                       "actual": f.get("actual", ""), "severity": f.get("severity", "HIGH"),
                       "brand": f.get("brand", "")} for f in failures],
        "warnings": [{"check": w["name"], "detail": w.get("detail", ""),
                       "brand": w.get("brand", "")} for w in warnings],
        "checks": checks,
    }


def check(name, status, brand="", **kwargs):
    return {"name": name, "status": status, "brand": brand, **kwargs}


# ─── Round 1: Propose Validation ─────────────────────────────────────────────

def audit_round1(recheck=False):
    """Validate config override application and proposal integrity."""
    print(f"\n{'='*60}")
    print(f"  PPC Audit Round 1 — Propose Validation {'(RECHECK)' if recheck else ''}")
    print(f"{'='*60}\n")

    checks = []

    # CHECK: DataKeeper search term freshness (global, not per-brand)
    try:
        from dotenv import load_dotenv
        load_dotenv()
        import os, requests as _req
        dk_user = os.getenv("ORBITOOLS_USER", "")
        dk_pass = os.getenv("ORBITOOLS_PASS", "")
        if dk_user:
            dk_r = _req.get("https://orbitools.orbiters.co.kr/api/datakeeper/status/",
                            auth=(dk_user, dk_pass), timeout=10)
            dk_status = dk_r.json().get("status", dk_r.json())
            for ch_name in ["amazon_ads_search_terms", "amazon_ads_keywords"]:
                ch_info = dk_status.get(ch_name, {})
                latest = ch_info.get("latest_collected", "")[:10]
                if latest:
                    from datetime import timedelta
                    days_stale = (date.today() - date.fromisoformat(latest)).days
                    if days_stale > 3:
                        checks.append(check(f"datakeeper_{ch_name}_fresh", "FAIL",
                                            severity="CRITICAL",
                                            expected="<= 3 days stale",
                                            actual=f"{days_stale} days stale (last: {latest})"))
                        print(f"  [FAIL] DataKeeper {ch_name}: {days_stale} days stale!")
                    else:
                        checks.append(check(f"datakeeper_{ch_name}_fresh", "PASS",
                                            detail=f"last collected {latest} ({days_stale}d ago)"))
    except Exception as e:
        print(f"  [WARN] DataKeeper freshness check skipped: {e}")

    # Load dashboard config override
    override_path = TMP / "dashboard_config_override.json"
    override = {}
    if override_path.exists():
        try:
            override = json.loads(override_path.read_text(encoding="utf-8"))
            print(f"  [OK] Dashboard config override loaded ({len(override)} brands)")
        except Exception as e:
            checks.append(check("override_loadable", "FAIL", severity="HIGH",
                                expected="valid JSON", actual=str(e)))
    else:
        print("  [INFO] No dashboard config override (using hardcoded defaults)")

    for brand_key in BRAND_KEYS:
        print(f"\n  --- {brand_key} ---")

        # Load audit context (written by executor after propose)
        ctx_path = TMP / f"ppc_audit_context_{brand_key}.json"
        if not ctx_path.exists():
            checks.append(check("audit_context_exists", "WARN", brand=brand_key,
                                detail="No audit context — propose may not have run for this brand"))
            continue

        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        applied = ctx.get("config_applied", {})
        print(f"    Config applied: budget=${applied.get('total_daily_budget')}, "
              f"camp_cap=${applied.get('max_single_campaign_budget')}, "
              f"manual_acos={applied.get('manual_acos')}%")

        # CHECK 0: Search term & keyword data availability (CRITICAL — prevents silent blind spots)
        st_count = ctx.get("search_term_rows", 0)
        kw_count = ctx.get("keyword_rows", 0)
        if st_count == 0:
            checks.append(check("search_term_data_available", "FAIL", brand=brand_key,
                                severity="CRITICAL",
                                expected=">0 search term rows",
                                actual="0 rows — keyword harvest/negate/bid optimization DISABLED"))
            print(f"    [FAIL] Search term data: 0 rows — all keyword optimization disabled!")
        else:
            checks.append(check("search_term_data_available", "PASS", brand=brand_key,
                                detail=f"{st_count} search term rows, {kw_count} keyword rows"))
            print(f"    [OK] Search term data: {st_count} rows, keyword data: {kw_count} rows")

        # CHECK 1: Config override fields match
        brand_override = override.get(brand_key, {})
        if brand_override:
            field_map = {
                "daily_budget": "total_daily_budget",
                "max_campaign": "max_single_campaign_budget",
                "max_bid": "max_bid",
                "manual_acos": "manual_acos",
                "auto_acos": "auto_acos",
            }
            for ui_key, ctx_key in field_map.items():
                if ui_key in brand_override:
                    expected = float(brand_override[ui_key])
                    actual = float(applied.get(ctx_key, 0))
                    if abs(expected - actual) > 0.01:
                        checks.append(check(f"config_override_{ui_key}", "FAIL",
                                            brand=brand_key, severity="CRITICAL",
                                            expected=str(expected), actual=str(actual)))
                        print(f"    [FAIL] {ui_key}: expected={expected}, actual={actual}")
                    else:
                        checks.append(check(f"config_override_{ui_key}", "PASS", brand=brand_key))
        else:
            checks.append(check("config_override_present", "PASS", brand=brand_key,
                                detail="No override for this brand (using defaults)"))

        # CHECK 2: Load proposal and validate budget caps
        today_str = date.today().strftime("%Y%m%d")
        proposal_path = TMP / f"ppc_proposal_{brand_key}_{today_str}.json"
        if not proposal_path.exists():
            # Try any recent proposal
            proposals_glob = sorted(TMP.glob(f"ppc_proposal_{brand_key}_*.json"), reverse=True)
            if proposals_glob:
                proposal_path = proposals_glob[0]
            else:
                checks.append(check("proposal_exists", "WARN", brand=brand_key,
                                    detail="No proposal JSON found"))
                continue

        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        camp_cap = applied.get("max_single_campaign_budget", 100)

        for p in proposal.get("proposals", []):
            new_bud = p.get("new_daily_budget")
            if new_bud and new_bud > camp_cap:
                checks.append(check("budget_cap_respected", "FAIL", brand=brand_key,
                                    severity="CRITICAL",
                                    expected=f"<= ${camp_cap}",
                                    actual=f"${new_bud} for {p.get('campaignName')}"))
                print(f"    [FAIL] {p.get('campaignName')}: budget ${new_bud} > cap ${camp_cap}")
            elif new_bud:
                checks.append(check("budget_cap_respected", "PASS", brand=brand_key))

        # CHECK 3: ACOS targets in proposal reasons
        manual_acos = applied.get("manual_acos", 25)
        auto_acos = applied.get("auto_acos", 35)
        for p in proposal.get("proposals", []):
            reason = p.get("reason", "")
            camp_type = p.get("campaignType", "MANUAL")
            expected_acos = auto_acos if camp_type == "AUTO" else manual_acos
            if f"target ACOS {expected_acos}" in reason or f"target ACOS {expected_acos:.0f}" in reason:
                checks.append(check("acos_target_in_reason", "PASS", brand=brand_key))
            elif "target ACOS" in reason:
                # Extract the ACOS value from reason
                import re
                m = re.search(r"target ACOS ([\d.]+)%", reason)
                if m:
                    found_acos = float(m.group(1))
                    if abs(found_acos - expected_acos) > 0.1:
                        checks.append(check("acos_target_in_reason", "FAIL", brand=brand_key,
                                            severity="HIGH",
                                            expected=f"{expected_acos}%",
                                            actual=f"{found_acos}% in {p.get('campaignName')}"))
                    else:
                        checks.append(check("acos_target_in_reason", "PASS", brand=brand_key))

        # CHECK 4: Grosmimi safeguard — no auto_approved
        if brand_key == "grosmimi":
            auto_approved = [p for p in proposal.get("proposals", []) if p.get("auto_approved")]
            if auto_approved:
                checks.append(check("grosmimi_safeguard", "FAIL", brand="grosmimi",
                                    severity="CRITICAL",
                                    expected="0 auto-approved",
                                    actual=f"{len(auto_approved)} auto-approved"))
            else:
                checks.append(check("grosmimi_safeguard", "PASS", brand="grosmimi"))

        print(f"    Proposal: {proposal.get('total_proposals', 0)} campaigns, "
              f"{proposal.get('total_keyword_proposals', 0)} keywords")

    verdict = make_verdict(1, checks, recheck=recheck)
    suffix = "_recheck" if recheck else ""
    verdict_path = AUDIT_DIR / f"verdict_round1{suffix}.json"
    verdict_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(f"\n  Verdict: {verdict['verdict']} ({verdict['checks_passed']}/{verdict['checks_total']} passed)")
    print(f"  Saved: {verdict_path}")

    # Write flag file if FAIL (triggers re-propose in workflow)
    flag_path = TMP / "ppc_audit" / "round1_needs_fix.flag"
    if verdict["verdict"] == "FAIL" and not recheck:
        flag_path.write_text(json.dumps(verdict["failures"], indent=2), encoding="utf-8")
        print(f"  [FLAG] Round 1 FAIL — re-propose will be triggered")
    elif flag_path.exists():
        flag_path.unlink()

    return verdict


# ─── Round 2: Execute Validation ─────────────────────────────────────────────

def audit_round2():
    """Validate execution results and check for phantoms."""
    print(f"\n{'='*60}")
    print(f"  PPC Audit Round 2 — Execute Validation")
    print(f"{'='*60}\n")

    checks = []
    today_str = date.today().strftime("%Y%m%d")

    # Load today's execution log
    exec_path = TMP / f"ppc_executed_{today_str}.json"
    if not exec_path.exists():
        # Try any recent
        exec_files = sorted(TMP.glob("ppc_executed_*.json"), reverse=True)
        if exec_files:
            exec_path = exec_files[0]
        else:
            print("  [INFO] No execution log found — nothing to audit")
            checks.append(check("exec_log_exists", "PASS", detail="No executions today"))
            verdict = make_verdict(2, checks)
            verdict_path = AUDIT_DIR / "verdict_round2.json"
            verdict_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
            return verdict

    exec_data = json.loads(exec_path.read_text(encoding="utf-8"))
    if isinstance(exec_data, list):
        entries = exec_data
    else:
        entries = exec_data.get("executions", [])

    print(f"  Execution log: {len(entries)} entries from {exec_path.name}")

    # CHECK 1: All result_status
    ok_count = sum(1 for e in entries if e.get("result_status") == "OK")
    err_entries = [e for e in entries if e.get("result_status", "").startswith("ERROR")]
    skip_entries = [e for e in entries if e.get("result_status") == "SKIPPED"]

    if err_entries:
        for e in err_entries:
            checks.append(check("exec_result_ok", "FAIL",
                                brand=e.get("brand_key", ""),
                                severity="HIGH",
                                expected="OK",
                                actual=f"ERROR: {e.get('result_status')} on {e.get('campaignName', e.get('keyword', '?'))}"))
    else:
        checks.append(check("exec_result_ok", "PASS",
                            detail=f"{ok_count} OK, {len(skip_entries)} skipped"))

    # CHECK 2: Budget cap not exceeded in executions
    for brand_key in BRAND_KEYS:
        ctx_path = TMP / f"ppc_audit_context_{brand_key}.json"
        if not ctx_path.exists():
            continue
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        camp_cap = ctx.get("config_applied", {}).get("max_single_campaign_budget", 100)

        brand_execs = [e for e in entries if e.get("brand_key") == brand_key]
        for e in brand_execs:
            new_bud = e.get("new_budget")
            if new_bud and float(new_bud) > camp_cap:
                checks.append(check("exec_budget_cap", "FAIL", brand=brand_key,
                                    severity="CRITICAL",
                                    expected=f"<= ${camp_cap}",
                                    actual=f"${new_bud}"))

    # CHECK 3: Persistent exec_log.json consistency
    persistent_path = ROOT / "docs" / "ppc-dashboard" / "exec_log.json"
    if persistent_path.exists():
        try:
            persistent = json.loads(persistent_path.read_text(encoding="utf-8"))
            total_persistent = sum(len(v) if isinstance(v, list) else 0
                                  for v in persistent.values())
            checks.append(check("persistent_log_readable", "PASS",
                                detail=f"{total_persistent} total records"))
        except Exception as e:
            checks.append(check("persistent_log_readable", "FAIL",
                                severity="HIGH", expected="valid JSON", actual=str(e)))
    else:
        checks.append(check("persistent_log_exists", "WARN",
                            detail="exec_log.json not found"))

    # CHECK 4: No phantom flag from verify step
    # The verify step prints "[verify] Done: X verified OK, Y PHANTOM detected"
    # We check if any PHANTOM entries exist in exec_log
    if persistent_path.exists():
        persistent = json.loads(persistent_path.read_text(encoding="utf-8"))
        for brand_key, brand_entries in persistent.items():
            if not isinstance(brand_entries, list):
                continue
            phantoms = [e for e in brand_entries if e.get("result_status") == "PHANTOM"]
            recent_phantoms = [p for p in phantoms
                               if p.get("exec_date", "") >= (date.today().isoformat())]
            if recent_phantoms:
                checks.append(check("no_phantom_today", "FAIL", brand=brand_key,
                                    severity="CRITICAL",
                                    expected="0 phantoms",
                                    actual=f"{len(recent_phantoms)} phantom changes"))
            else:
                checks.append(check("no_phantom_today", "PASS", brand=brand_key))

    verdict = make_verdict(2, checks)
    verdict_path = AUDIT_DIR / "verdict_round2.json"
    verdict_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    print(f"\n  Verdict: {verdict['verdict']} ({verdict['checks_passed']}/{verdict['checks_total']} passed)")
    print(f"  Saved: {verdict_path}")

    return verdict


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PPC Pipeline Auditor")
    parser.add_argument("--round", type=int, required=True, choices=[1, 2],
                        help="Audit round (1=propose, 2=execute)")
    parser.add_argument("--recheck", action="store_true",
                        help="Round 1 recheck after auto-fix")
    args = parser.parse_args()

    if args.round == 1:
        verdict = audit_round1(recheck=args.recheck)
    else:
        verdict = audit_round2()

    # Exit with error code if FAIL (allows workflow to detect)
    if verdict["verdict"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
