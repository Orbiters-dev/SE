"""
amazon_ppc_simulator.py - Amazon PPC Backtest Simulator

Pulls historical search term + keyword data from Amazon Ads API and backtests
what would have happened if 퍼포마's optimization rules were applied from day 1.

Two modules:
  1. Wasted Spend Backtest  -- negatives applied 14 days after threshold breach
  2. Bid Efficiency Backtest -- ROAS-based bid rules applied retroactively

Usage:
    python tools/amazon_ppc_simulator.py --brand grosmimi          # 90 days
    python tools/amazon_ppc_simulator.py --brand grosmimi --days 60
    python tools/amazon_ppc_simulator.py --brand grosmimi --cached # skip API, use .tmp cache
    python tools/amazon_ppc_simulator.py --brand naeiae
"""

import argparse
import gzip
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

# Reuse API auth + brand configs from executor
from amazon_ppc_executor import (
    BRAND_CONFIGS,
    get_access_token,
    get_brand_profile,
    _headers_reporting,
)

ROOT    = TOOLS_DIR.parent
TMP_DIR = ROOT / ".tmp" / "ppc_simulator"
TMP_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://advertising-api.amazon.com"

# ── 퍼포마 Rule Constants ────────────────────────────────────────────────────
WASTE_SPEND_THRESHOLD = 5.0      # $5 spent with 0 conversions in window = wasted
WASTE_WINDOW_DAYS     = 14       # 14-day look-back before adding negative
BID_REDUCE_ROAS_MAX   = 2.0      # ROAS < 2.0 → bid should be reduced
BID_SCALE_ROAS_MIN    = 5.0      # ROAS > 5.0 → bid/budget should be increased
BID_REDUCE_PCT        = 0.20     # Reduce bid by 20%
BID_SCALE_PCT         = 0.15     # Scale bid by 15%


# ── API helpers ──────────────────────────────────────────────────────────────

def _fetch_report(profile_id: int, body: dict, label: str) -> list:
    """Submit a reporting job and wait for completion. Returns list of rows."""
    token   = get_access_token()
    headers = _headers_reporting(profile_id)

    # Retry up to 5 times on 425 (concurrent report limit)
    for attempt in range(5):
        resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers,
                             json=body, timeout=60)
        if resp.status_code != 425:
            break
        wait = 60 * (attempt + 1)
        print(f"    [425 rate-limit] attempt {attempt+1}, waiting {wait}s...")
        time.sleep(wait)
    resp.raise_for_status()
    report_id = resp.json()["reportId"]
    print(f"    [{label}] report_id={report_id} - waiting...")

    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(15)
        st = requests.get(f"{API_BASE}/reporting/reports/{report_id}",
                          headers=_headers_reporting(profile_id), timeout=30)
        st.raise_for_status()
        info = st.json()
        if info.get("status") == "COMPLETED":
            url = info.get("url")
            if not url:
                print(f"    [{label}] COMPLETED but no URL")
                return []
            dl  = requests.get(url, timeout=300)
            dl.raise_for_status()
            raw = dl.content
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            rows = json.loads(raw.decode("utf-8"))
            if isinstance(rows, dict):
                for k in ("data", "results", "records"):
                    if k in rows:
                        rows = rows[k]
                        break
            print(f"    [{label}] {len(rows)} rows")
            return rows
        if info.get("status") == "FAILED":
            print(f"    [{label}] FAILED - skipping chunk")
            return []
    print(f"    [{label}] TIMEOUT - skipping chunk")
    return []


def pull_search_term_data(profile_id: int, start: date, end: date,
                          cache_path: Path, use_cache: bool) -> list:
    """Pull search term report in 7-day chunks. Caches to disk."""
    if use_cache and cache_path.exists():
        print(f"  [cache] loading {cache_path.name}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    all_rows = []
    cur = start
    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=6))
        print(f"  [SearchTerm] {cur} ~ {chunk_end}")
        body = {
            "name":          f"SIM ST {cur}~{chunk_end}",
            "startDate":     cur.strftime("%Y-%m-%d"),
            "endDate":       chunk_end.strftime("%Y-%m-%d"),
            "configuration": {
                "adProduct":    "SPONSORED_PRODUCTS",
                "groupBy":      ["searchTerm"],
                "columns":      ["campaignId", "campaignName", "adGroupId",
                                 "searchTerm", "impressions", "clicks",
                                 "cost", "sales14d", "purchases14d"],
                "reportTypeId": "spSearchTerm",
                "timeUnit":     "SUMMARY",
                "format":       "GZIP_JSON",
            },
        }
        rows = _fetch_report(profile_id, body, f"ST {cur}")
        for r in rows:
            r["_start"] = cur.strftime("%Y-%m-%d")
            r["_end"]   = chunk_end.strftime("%Y-%m-%d")
        all_rows.extend(rows)
        cur = chunk_end + timedelta(days=1)
        if cur <= end:
            time.sleep(5)

    cache_path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"  Saved {len(all_rows)} rows to {cache_path.name}")
    return all_rows


def pull_keyword_data(profile_id: int, start: date, end: date,
                      cache_path: Path, use_cache: bool) -> list:
    """Pull keyword-level report in 7-day chunks."""
    if use_cache and cache_path.exists():
        print(f"  [cache] loading {cache_path.name}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    all_rows = []
    cur = start
    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=6))
        print(f"  [Keyword] {cur} ~ {chunk_end}")
        body = {
            "name":          f"SIM KW {cur}~{chunk_end}",
            "startDate":     cur.strftime("%Y-%m-%d"),
            "endDate":       chunk_end.strftime("%Y-%m-%d"),
            "configuration": {
                "adProduct":    "SPONSORED_PRODUCTS",
                "groupBy":      ["targeting"],
                "columns":      ["campaignId", "campaignName", "adGroupId",
                                 "targeting", "impressions", "clicks", "cost",
                                 "sales14d", "purchases14d"],
                "reportTypeId": "spTargeting",
                "timeUnit":     "SUMMARY",
                "format":       "GZIP_JSON",
            },
        }
        rows = _fetch_report(profile_id, body, f"KW {cur}")
        for r in rows:
            r["_start"] = cur.strftime("%Y-%m-%d")
            r["_end"]   = chunk_end.strftime("%Y-%m-%d")
        all_rows.extend(rows)
        cur = chunk_end + timedelta(days=1)
        if cur <= end:
            time.sleep(5)

    cache_path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"  Saved {len(all_rows)} rows to {cache_path.name}")
    return all_rows


# ── Module 1: Wasted Spend Backtest ─────────────────────────────────────────

def backtest_wasted_spend(st_rows: list) -> dict:
    """
    Simulate: if 퍼포마 added negatives 14 days after a search term accumulated
    WASTE_SPEND_THRESHOLD with 0 conversions, how much total spend would be saved?

    Returns dict with summary stats + per-term breakdown.
    """
    # Group rows by search term, sorted by window start date
    by_term = defaultdict(list)
    for r in st_rows:
        key = (r.get("campaignName", ""), r.get("searchTerm", ""))
        by_term[key].append(r)

    total_actual_spend   = 0.0
    total_simulated_save = 0.0
    top_waste_terms      = []

    for (camp, term), windows in by_term.items():
        # Sort windows chronologically
        windows = sorted(windows, key=lambda x: x.get("_start", ""))

        term_actual_spend   = sum(float(w.get("cost", 0)) for w in windows)
        term_conversions    = sum(int(w.get("purchases14d", 0)) for w in windows)
        total_actual_spend += term_actual_spend

        # Simulate: scan windows in order, track cumulative 0-conversion spend
        cum_zero_spend = 0.0
        negated_at     = None   # date string when we would have added negative
        sim_saved      = 0.0

        for w in windows:
            w_start = w.get("_start", "")
            spend   = float(w.get("cost", 0))
            convs   = int(w.get("purchases14d", 0))

            if negated_at is not None:
                # Already negated — this spend would be saved
                sim_saved += spend
                continue

            if convs == 0:
                cum_zero_spend += spend
                if cum_zero_spend >= WASTE_SPEND_THRESHOLD:
                    # Would have added negative after this window
                    negated_at = w_start
                    # Spend in THIS window already happened (14-day rule)
                    # Save starts from NEXT window
            else:
                # Conversion happened — reset zero-spend counter
                cum_zero_spend = 0.0

        total_simulated_save += sim_saved

        if sim_saved > 0:
            term_roas = (sum(float(w.get("sales14d", 0)) for w in windows) /
                         term_actual_spend) if term_actual_spend else 0
            top_waste_terms.append({
                "campaign":       camp,
                "search_term":    term,
                "actual_spend":   round(term_actual_spend, 2),
                "conversions":    term_conversions,
                "would_save":     round(sim_saved, 2),
                "negated_after":  negated_at,
                "windows":        len(windows),
            })

    # Sort by would_save desc
    top_waste_terms.sort(key=lambda x: x["would_save"], reverse=True)

    return {
        "total_actual_spend":   round(total_actual_spend, 2),
        "total_simulated_save": round(total_simulated_save, 2),
        "save_pct":             round(total_simulated_save / total_actual_spend * 100, 1)
                                if total_actual_spend else 0,
        "negated_terms_count":  len(top_waste_terms),
        "top_terms":            top_waste_terms[:30],
    }


# ── Module 2: Bid Efficiency Backtest ───────────────────────────────────────

def backtest_bid_efficiency(kw_rows: list, brand_key: str) -> dict:
    """
    Simulate: if 퍼포마's ROAS-based bid rules were applied from day 1,
    what would the estimated ROAS improvement be?

    For low-ROAS keywords: bid reduction → lower CPC → higher ROAS on same conversion volume
    For high-ROAS keywords: bid increase → more volume (conservatively +15% impressions)
    """
    cfg        = BRAND_CONFIGS[brand_key]
    target_roas = cfg["targeting"]["MANUAL"]["min_roas"]

    # Aggregate by keyword across all windows
    by_kw = defaultdict(lambda: {"spend": 0.0, "sales": 0.0, "clicks": 0,
                                 "impressions": 0, "purchases": 0, "campaign": "",
                                 "keyword": "", "match_type": ""})
    for r in kw_rows:
        kw_id = r.get("targeting", r.get("keywordId", r.get("keywordText", "?")))
        by_kw[kw_id]["spend"]       += float(r.get("cost", 0))
        by_kw[kw_id]["sales"]       += float(r.get("sales14d", 0))
        by_kw[kw_id]["clicks"]      += int(r.get("clicks", 0))
        by_kw[kw_id]["impressions"] += int(r.get("impressions", 0))
        by_kw[kw_id]["purchases"]   += int(r.get("purchases14d", 0))
        by_kw[kw_id]["campaign"]     = r.get("campaignName", "")
        by_kw[kw_id]["keyword"]      = r.get("targeting", r.get("keywordText", str(kw_id)))
        by_kw[kw_id]["match_type"]   = r.get("matchType", "")

    total_actual_spend  = 0.0
    total_actual_sales  = 0.0
    total_sim_spend     = 0.0
    total_sim_sales     = 0.0
    underperformers     = []
    scalable            = []

    for kw_id, kw in by_kw.items():
        spend  = kw["spend"]
        sales  = kw["sales"]
        clicks = kw["clicks"]
        if spend < 1.0 or clicks < 2:
            continue  # Not enough data

        roas   = sales / spend if spend else 0
        cpc    = spend / clicks if clicks else 0
        total_actual_spend += spend
        total_actual_sales += sales

        if roas < BID_REDUCE_ROAS_MAX:
            # Simulate bid reduction: CPC drops by BID_REDUCE_PCT
            # Assume conversion rate stays same, but we spend less per click
            # (Conservative: impressions/clicks stay the same, just CPC drops)
            new_cpc    = cpc * (1 - BID_REDUCE_PCT)
            new_spend  = new_cpc * clicks
            new_sales  = sales  # conversion volume stays same
            saved      = spend - new_spend
            new_roas   = new_sales / new_spend if new_spend else 0
            total_sim_spend += new_spend
            total_sim_sales += new_sales
            underperformers.append({
                "campaign":    kw["campaign"],
                "keyword":     kw["keyword"],
                "match_type":  kw["match_type"],
                "actual_roas": round(roas, 2),
                "actual_spend": round(spend, 2),
                "actual_sales": round(sales, 2),
                "sim_spend":   round(new_spend, 2),
                "sim_roas":    round(new_roas, 2),
                "estimated_save": round(saved, 2),
                "action":      f"reduce_bid -{int(BID_REDUCE_PCT*100)}%",
            })

        elif roas >= BID_SCALE_ROAS_MIN:
            # Simulate bid increase: +15% more impressions → +15% more clicks/spend/sales
            scale      = 1 + BID_SCALE_PCT
            new_spend  = spend * scale
            new_sales  = sales * scale
            extra_profit = (new_sales - new_spend) - (sales - spend)
            total_sim_spend += new_spend
            total_sim_sales += new_sales
            scalable.append({
                "campaign":       kw["campaign"],
                "keyword":        kw["keyword"],
                "match_type":     kw["match_type"],
                "actual_roas":    round(roas, 2),
                "actual_spend":   round(spend, 2),
                "actual_sales":   round(sales, 2),
                "sim_spend":      round(new_spend, 2),
                "sim_sales":      round(new_sales, 2),
                "extra_profit":   round(extra_profit, 2),
                "action":         f"scale_bid +{int(BID_SCALE_PCT*100)}%",
            })

        else:
            # In-range: keep as-is
            total_sim_spend += spend
            total_sim_sales += sales

    underperformers.sort(key=lambda x: x["estimated_save"], reverse=True)
    scalable.sort(key=lambda x: x["extra_profit"], reverse=True)

    actual_roas = total_actual_sales / total_actual_spend if total_actual_spend else 0
    sim_roas    = total_sim_sales / total_sim_spend if total_sim_spend else 0

    return {
        "total_actual_spend":  round(total_actual_spend, 2),
        "total_actual_sales":  round(total_actual_sales, 2),
        "actual_roas":         round(actual_roas, 2),
        "total_sim_spend":     round(total_sim_spend, 2),
        "total_sim_sales":     round(total_sim_sales, 2),
        "sim_roas":            round(sim_roas, 2),
        "roas_delta":          round(sim_roas - actual_roas, 2),
        "underperformers":     underperformers[:30],
        "scalable":            scalable[:20],
        "underperformer_count": len(underperformers),
        "scalable_count":       len(scalable),
    }


# ── Timeline View ────────────────────────────────────────────────────────────

def build_monthly_timeline(waste_terms: list, st_rows: list) -> list:
    """Roll up wasted spend by month to show cumulative savings over time."""
    # Map: window_start (YYYY-MM) -> wasted spend in that window
    # A term is 'wasted' in a window if it had spend, 0 conv, AND has been negated
    negated_terms = {(t["campaign"], t["search_term"]): t["negated_after"]
                     for t in waste_terms}

    monthly = defaultdict(float)
    for r in st_rows:
        key    = (r.get("campaignName", ""), r.get("searchTerm", ""))
        neg_at = negated_terms.get(key)
        if neg_at is None:
            continue
        w_start = r.get("_start", "")
        if w_start > neg_at:  # This window comes AFTER negative was added
            month = w_start[:7]  # YYYY-MM
            monthly[month] += float(r.get("cost", 0))

    months = sorted(monthly.keys())
    cumulative = 0.0
    timeline   = []
    for m in months:
        cumulative += monthly[m]
        timeline.append({
            "month":       m,
            "monthly_save": round(monthly[m], 2),
            "cumulative":   round(cumulative, 2),
        })
    return timeline


# ── Execution History Loader ──────────────────────────────────────────────────

def _load_execution_history(brand_key: str) -> list:
    """Load all ppc_executed_*.json files and filter to this brand's actions."""
    import glob
    history = []
    files = sorted(glob.glob(str(ROOT / ".tmp" / "ppc_executed_*.json")))
    brand_display = BRAND_CONFIGS[brand_key]["brand_display"]

    for fpath in files:
        try:
            data = json.loads(Path(fpath).read_text(encoding="utf-8"))
            exec_date = Path(fpath).stem.replace("ppc_executed_", "")[:8]  # YYYYMMDD
            exec_date_fmt = f"{exec_date[:4]}-{exec_date[4:6]}-{exec_date[6:8]}"
            for item in data:
                # Filter by brand (campaign name contains brand, or all if no name)
                cname = item.get("campaignName", "")
                kw = item.get("keyword", "")
                action = item.get("action", "")
                # Match brand by campaign name prefix or seller context
                is_match = (
                    brand_display.lower() in cname.lower()
                    or (brand_key == "naeiae" and ("fleeters" in cname.lower() or cname == ""))
                    or (brand_key == "chaenmom" and "cha&mom" in cname.lower())
                    or (brand_key == "grosmimi" and "grosmimi" in cname.lower())
                )
                if not is_match:
                    # Check if brand_key matches based on campaign IDs from BRAND_CONFIGS
                    pass  # Skip non-matching brands

                if is_match:
                    history.append({
                        "date": exec_date_fmt,
                        "action": action,
                        "campaign": cname[:50] if cname else "(auto)",
                        "keyword": kw,
                        "spend_7d": item.get("spend_7d", 0),
                        "sales_7d": item.get("sales_7d", 0),
                        "roas_7d": item.get("roas_7d"),
                        "bid_change": item.get("bid_change_pct"),
                        "new_budget": item.get("new_budget"),
                        "reason": item.get("reason", "")[:80],
                        "status": item.get("result_status", ""),
                    })
        except Exception:
            continue

    # Also load baseline if exists
    baseline_path = ROOT / ".tmp" / f"{brand_key}_execution_baseline.json"
    if not baseline_path.exists():
        baseline_path = ROOT / ".tmp" / "naeiae_execution_baseline.json"
    if baseline_path.exists() and brand_key in baseline_path.name.replace("_execution_baseline", ""):
        try:
            bl = json.loads(baseline_path.read_text(encoding="utf-8"))
            if bl.get("brand", "").lower() == brand_display.lower():
                history.insert(0, {
                    "type": "baseline",
                    "date": bl.get("executed_date", ""),
                    "before_roas_7d": bl.get("before", {}).get("roas_7d"),
                    "before_acos_7d": bl.get("before", {}).get("acos_7d"),
                    "negatives_added": len(bl.get("changes_executed", {}).get("negatives_added", [])),
                    "bid_reductions": len(bl.get("changes_executed", {}).get("bid_reductions", [])),
                    "keywords_harvested": len(bl.get("changes_executed", {}).get("keywords_harvested", [])),
                    "wasted_spend_blocked": bl.get("changes_executed", {}).get("wasted_spend_14d", 0),
                })
        except Exception:
            pass

    print(f"  [History] {len(history)} execution records loaded for {brand_display}")
    return history


# ── HTML Report ──────────────────────────────────────────────────────────────

HTML_TEMPLATE = ROOT / ".tmp" / "ppc_simulator" / "backtest_template.html"


def build_html_report(brand_display: str, analysis_days: int,
                      waste: dict, bid: dict, timeline: list,
                      start_date: date, end_date: date) -> str:
    """Inject real data into the premium backtest HTML template."""
    import json as _json

    # Build data payload matching template's window.BACKTEST_DATA format
    data_payload = {
        "brand": brand_display,
        "period": {"start": str(start_date), "end": str(end_date), "days": analysis_days},
        "waste_backtest": {k: v for k, v in waste.items() if k != "top_terms"},
        "bid_backtest": {k: v for k, v in bid.items()
                         if k not in ("underperformers", "scalable")},
        "timeline": timeline,
        "top_waste_terms": waste.get("top_terms", [])[:20],
    }

    template = HTML_TEMPLATE.read_text(encoding="utf-8")
    data_js = _json.dumps(data_payload, ensure_ascii=False)

    # Inject real data by replacing the demo BACKTEST_DATA block
    injection = f"window.BACKTEST_DATA = {data_js};"
    # Find and replace the demo data block
    import re
    template = re.sub(
        r'window\.BACKTEST_DATA\s*=\s*\{.*?\};',
        injection,
        template,
        count=1,
        flags=re.DOTALL,
    )

    return template



# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand",  default="grosmimi",
                        choices=list(BRAND_CONFIGS.keys()))
    parser.add_argument("--days",   type=int, default=60)
    parser.add_argument("--cached", action="store_true",
                        help="Use cached API data if available")
    args = parser.parse_args()

    brand_key = args.brand
    cfg       = BRAND_CONFIGS[brand_key]
    print(f"\n=== PPC Backtest Simulator: {cfg['brand_display']} ({args.days}d) ===\n")

    # Date range
    end_date   = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=args.days - 1)
    print(f"Period: {start_date} ~ {end_date}")

    # Get profile
    print(f"\nFetching profile for {brand_key}...")
    profile = get_brand_profile(brand_key)
    if not profile:
        print(f"ERROR: Could not find profile for {brand_key}")
        sys.exit(1)
    profile_id = profile["profile_id"]
    print(f"Profile ID: {profile_id}")

    # Cache paths
    st_cache  = TMP_DIR / f"{brand_key}_st_{start_date}_{end_date}.json"
    kw_cache  = TMP_DIR / f"{brand_key}_kw_{start_date}_{end_date}.json"

    # Pull data — prefer Data Keeper, fallback to direct API
    st_rows = []
    kw_rows = []
    try:
        from amazon_ppc_executor import fetch_search_terms_from_datakeeper, fetch_keywords_from_datakeeper
        print(f"\n[1/2] Fetching search term data from DataKeeper...")
        st_rows = fetch_search_terms_from_datakeeper(brand_key, days=args.days)
        if st_rows:
            # Convert DataKeeper format to simulator format
            for r in st_rows:
                date_range = r.get("date", "")
                if "~" in date_range:
                    r["_start"], r["_end"] = date_range.split("~")
                else:
                    r["_start"] = r["_end"] = date_range
                r["campaignName"] = r.get("campaign_id", "")
                r["searchTerm"] = r.get("search_term", "")
                r["cost"] = r.get("spend", 0)
                r["sales14d"] = r.get("sales", 0)
                r["purchases14d"] = r.get("purchases", 0)
            print(f"  DataKeeper -> {len(st_rows)} search term rows")

        print(f"\n[2/2] Fetching keyword data from DataKeeper...")
        kw_rows = fetch_keywords_from_datakeeper(brand_key, days=args.days)
        if kw_rows:
            for r in kw_rows:
                date_range = r.get("date", "")
                if "~" in date_range:
                    r["_start"], r["_end"] = date_range.split("~")
                else:
                    r["_start"] = r["_end"] = date_range
                r["campaignName"] = r.get("campaign_id", "")
                r["targeting"] = r.get("keyword_text", "")
                r["cost"] = r.get("spend", 0)
                r["sales14d"] = r.get("sales", 0)
                r["purchases14d"] = r.get("purchases", 0)
            print(f"  DataKeeper -> {len(kw_rows)} keyword rows")
    except ImportError:
        print("  [WARN] DataKeeper functions not available")

    # Fallback to direct API if DataKeeper returned nothing
    if not st_rows:
        print(f"\n[1/2] Pulling search term data from API...")
        st_rows = pull_search_term_data(profile_id, start_date, end_date,
                                        st_cache, args.cached)
    if not kw_rows:
        print(f"\n[2/2] Pulling keyword data from API...")
        kw_rows = pull_keyword_data(profile_id, start_date, end_date,
                                    kw_cache, args.cached)

    if not st_rows and not kw_rows:
        print("ERROR: No data returned.")
        sys.exit(1)

    print(f"\nData: {len(st_rows)} search term rows, {len(kw_rows)} keyword rows")

    # Run backtests
    print("\n[Backtest 1] Wasted spend analysis...")
    waste = backtest_wasted_spend(st_rows)

    print("[Backtest 2] Bid efficiency analysis...")
    bid   = backtest_bid_efficiency(kw_rows, brand_key)

    print("[Backtest 3] Building monthly timeline...")
    timeline = build_monthly_timeline(waste["top_terms"], st_rows)

    # Print summary
    print(f"\n{'='*55}")
    print(f"  {cfg['brand_display']} PPC Backtest Results ({start_date} ~ {end_date})")
    print(f"{'='*55}")
    print(f"\nModule 1 - Wasted Spend:")
    print(f"  Total search term spend analyzed:  ${waste['total_actual_spend']:>10,.2f}")
    print(f"  Simulated savings (negatives):     ${waste['total_simulated_save']:>10,.2f}  ({waste['save_pct']}%)")
    print(f"  Search terms that would be negated: {waste['negated_terms_count']}")

    if waste["top_terms"]:
        print(f"\n  Top 5 wasteful terms:")
        for t in waste["top_terms"][:5]:
            print(f"    [{t['campaign'][:30]}] '{t['search_term']}'"
                  f"  spend=${t['actual_spend']:.2f}  save=${t['would_save']:.2f}")

    print(f"\nModule 2 - Bid Efficiency:")
    print(f"  Actual ROAS:      {bid['actual_roas']}x")
    print(f"  Simulated ROAS:   {bid['sim_roas']}x  (delta: {'+' if bid['roas_delta']>=0 else ''}{bid['roas_delta']}x)")
    print(f"  Under-performers: {bid['underperformer_count']} keywords")
    print(f"  Scalable:         {bid['scalable_count']} keywords")

    if timeline:
        print(f"\nModule 3 - Cumulative Savings Timeline:")
        for t in timeline:
            bar = "#" * int(t["monthly_save"] / 100)
            print(f"  {t['month']}  ${t['monthly_save']:>8,.2f}  cumul=${t['cumulative']:>10,.2f}  {bar}")

    # Save HTML report
    html     = build_html_report(cfg["brand_display"], args.days,
                                  waste, bid, timeline, start_date, end_date)
    out_path = TMP_DIR / f"{brand_key}_backtest_{end_date}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nHTML report saved: {out_path}")

    # Load execution history for this brand
    execution_history = _load_execution_history(brand_key)

    # Save JSON summary (PST timezone)
    try:
        from zoneinfo import ZoneInfo
        now_pst = datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        # Windows without tzdata: manual UTC-8 offset
        from datetime import timezone
        now_pst = datetime.now(timezone(timedelta(hours=-7)))  # PDT (UTC-7)

    # Compute data stats for the detail view
    unique_terms = len(set((r.get("campaignName",""), r.get("searchTerm","")) for r in st_rows))
    unique_kws = len(set(r.get("targeting", r.get("keywordText","")) for r in kw_rows))
    unique_campaigns = len(set(r.get("campaignName","") or r.get("campaign_id","") for r in st_rows))

    summary = {
        "brand": brand_key,
        "brand_display": cfg["brand_display"],
        "period": {"start": str(start_date), "end": str(end_date), "days": args.days},

        # Data inputs
        "data_inputs": {
            "search_term_rows": len(st_rows),
            "keyword_rows": len(kw_rows),
            "unique_search_terms": unique_terms,
            "unique_keywords": unique_kws,
            "unique_campaigns": unique_campaigns,
            "data_source": "DataKeeper PG" if st_rows else "API Direct",
            "date_format": "7-day SUMMARY chunks",
        },

        # Module 1: Full waste analysis
        "waste_backtest": {
            **{k: v for k, v in waste.items() if k != "top_terms"},
            "rule_threshold": WASTE_SPEND_THRESHOLD,
            "rule_window_days": WASTE_WINDOW_DAYS,
            "rule_description": f"If cumulative zero-conv spend >= ${WASTE_SPEND_THRESHOLD} over {WASTE_WINDOW_DAYS}d windows → add negative. Savings start from NEXT window.",
        },
        "top_waste_terms": waste["top_terms"][:30],  # Full 30 terms

        # Module 2: Full bid analysis with individual keyword data
        "bid_backtest": {
            **{k: v for k, v in bid.items() if k not in ("underperformers", "scalable")},
            "rule_reduce_threshold": BID_REDUCE_ROAS_MAX,
            "rule_reduce_pct": BID_REDUCE_PCT,
            "rule_scale_threshold": BID_SCALE_ROAS_MIN,
            "rule_scale_pct": BID_SCALE_PCT,
            "rule_description": f"ROAS < {BID_REDUCE_ROAS_MAX}x → bid -{int(BID_REDUCE_PCT*100)}% | ROAS > {BID_SCALE_ROAS_MIN}x → bid +{int(BID_SCALE_PCT*100)}% | In-range: hold",
        },
        "bid_underperformers": bid.get("underperformers", [])[:20],
        "bid_scalable": bid.get("scalable", [])[:15],

        # Timeline
        "timeline": timeline,

        # Execution history
        "execution_history": execution_history,

        # Config used
        "config_used": {
            "brand_key": brand_key,
            "seller": cfg.get("seller_name", ""),
            "total_daily_budget": cfg.get("total_daily_budget", 0),
            "manual_target_acos": cfg["targeting"]["MANUAL"]["target_acos"],
            "auto_target_acos": cfg["targeting"]["AUTO"]["target_acos"],
        },

        "generated_at": now_pst.strftime("%Y-%m-%d %H:%M PST"),
    }
    json_path = TMP_DIR / f"{brand_key}_backtest_{end_date}.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"JSON summary saved: {json_path}")


if __name__ == "__main__":
    main()
