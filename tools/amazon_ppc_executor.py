"""
amazon_ppc_executor.py - Amazon PPC Campaign Executor (Approval-Based)

Analyzes Fleeters Inc (Naeiae) campaigns every 6 hours, proposes changes,
emails proposal for review, then executes only approved actions.

Usage:
    python tools/amazon_ppc_executor.py --propose              # Analyze & email proposal
    python tools/amazon_ppc_executor.py --execute              # Execute approved changes
    python tools/amazon_ppc_executor.py --status               # Show pending proposals
    python tools/amazon_ppc_executor.py --cycle                # Run 6-hour analysis cycle
    python tools/amazon_ppc_executor.py --propose --to wj.choi@orbiters.co.kr

Flow:
    1. --propose: Collect data -> Analyze -> Email proposal to user
    2. User replies with approval (or edits JSON)
    3. --execute: Execute approved items -> Log to Google Sheets -> Email confirmation
    4. --cycle: Auto-run --propose every 6 hours
"""

import argparse
import gzip
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(exist_ok=True)

# --- credentials ---
AD_CLIENT_ID     = os.getenv("AMZ_ADS_CLIENT_ID")
AD_CLIENT_SECRET = os.getenv("AMZ_ADS_CLIENT_SECRET")
AD_REFRESH_TOKEN = os.getenv("AMZ_ADS_REFRESH_TOKEN")

API_BASE = "https://advertising-api.amazon.com"

# --- ONLY Fleeters Inc (Naeiae) ---
TARGET_SELLER = "Fleeters Inc"
TARGET_BRAND  = "Naeiae"

# --- ROAS Decision Framework ---
ROAS_RULES = [
    # (min_roas, max_roas, action, bid_change_pct, budget_change_pct, priority)
    (None, 1.0,  "pause",           None, None, "urgent"),
    (1.0,  1.5,  "reduce_bid",      -30,  None, "urgent"),
    (1.5,  2.0,  "reduce_bid",      -15,  None, "high"),
    (2.0,  3.0,  "monitor",         None, None, "medium"),
    (3.0,  5.0,  "increase_budget", None, +20,  "medium"),
    (5.0,  None, "increase_budget", +10,  +30,  "high"),
]

# --- Daily budget cap (safety) ---
TOTAL_DAILY_BUDGET_USD = 120.0   # Start at $120/day, scale to $150 if performing well
MAX_SINGLE_CAMPAIGN_BUDGET = 50.0  # No single campaign exceeds this
MAX_BID_USD = 3.0                  # Bid safety cap

# --- Manual vs Auto optimization targets ---
# Manual campaigns: higher ROAS expected (tighter keyword control)
# Auto campaigns: discovery + harvesting (lower ROAS acceptable initially)
TARGETING_CONFIG = {
    "MANUAL": {
        "target_acos": 25.0,    # Tighter ACOS target
        "min_roas": 2.5,        # Higher floor
        "budget_share": 0.60,   # 60% of total budget -> manual
        "description": "Manual campaigns - exact/phrase keywords, tighter control",
    },
    "AUTO": {
        "target_acos": 35.0,    # Looser ACOS for discovery
        "min_roas": 1.5,        # Lower floor (harvesting phase)
        "budget_share": 0.40,   # 40% of total budget -> auto
        "description": "Auto campaigns - keyword discovery, broader reach",
    },
}

# --- Keyword-level Bid Presets ---
BID_PRESETS = {
    "MANUAL": {
        "desired_acos": 0.25,
        "increase_by": 0.20,
        "decrease_by": 0.20,
        "max_bid": 3.00,
        "min_bid": 0.10,
        "high_acos": 0.30,
        "mid_acos": 0.25,
        "click_limit": 10,
        "impression_limit": 200,
        "step_up": 0.05,
    },
    "AUTO": {
        "desired_acos": 0.35,
        "increase_by": 0.20,
        "decrease_by": 0.20,
        "max_bid": 2.00,
        "min_bid": 0.05,
        "high_acos": 0.35,
        "mid_acos": 0.30,
        "click_limit": 15,
        "impression_limit": 300,
        "step_up": 0.03,
    },
}

# --- Search Term Harvesting Thresholds ---
HARVEST_MIN_CLICKS = 10
HARVEST_MIN_SALES = 1
HARVEST_BID_MULTIPLIER = 1.10   # Set harvested keyword bid at 110% of search term CPC
NEGATIVE_ZERO_SALES_SPEND_MULT = 3.0   # spend > 3x target CPA with 0 sales -> negate
NEGATIVE_HIGH_ACOS_MULT = 2.0          # ACOS > 2x desired -> negate candidate
MAX_KEYWORD_CHANGES_PER_CYCLE = 50     # API rate limit safety


# ===========================================================================
# Auth (reuse pattern from run_amazon_ppc_daily.py)
# ===========================================================================

def get_access_token() -> str:
    resp = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": AD_REFRESH_TOKEN,
            "client_id": AD_CLIENT_ID,
            "client_secret": AD_CLIENT_SECRET,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


class TokenManager:
    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def get(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        self._token = get_access_token()
        self._expires_at = time.time() + 3600
        return self._token


TM = TokenManager()


def _headers(profile_id: int) -> Dict:
    return {
        "Authorization": f"Bearer {TM.get()}",
        "Amazon-Advertising-API-ClientId": AD_CLIENT_ID,
        "Amazon-Advertising-API-Scope": str(profile_id),
    }


def _headers_sp(profile_id: int) -> Dict:
    h = _headers(profile_id)
    h["Accept"] = "application/vnd.spCampaign.v3+json"
    h["Content-Type"] = "application/vnd.spCampaign.v3+json"
    return h


def _headers_reporting(profile_id: int) -> Dict:
    h = _headers(profile_id)
    h["Accept"] = "application/vnd.adreporting.v3+json"
    h["Content-Type"] = "application/vnd.adreporting.v3+json"
    return h


# ===========================================================================
# Data Collection (Fleeters Inc only)
# ===========================================================================

def get_fleeters_profile() -> Optional[Dict]:
    resp = requests.get(
        f"{API_BASE}/v2/profiles",
        headers={
            "Authorization": f"Bearer {TM.get()}",
            "Amazon-Advertising-API-ClientId": AD_CLIENT_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()
    for p in resp.json():
        if (p.get("countryCode") == "US"
            and p.get("accountInfo", {}).get("type") == "seller"
            and p.get("accountInfo", {}).get("name") == TARGET_SELLER):
            return {
                "profile_id": p["profileId"],
                "seller": p["accountInfo"]["name"],
            }
    return None


def fetch_campaigns(profile_id: int) -> List[Dict]:
    """Fetch all SP campaigns with their current state, budget, bid info."""
    headers = _headers_sp(profile_id)
    campaigns = []
    start_index = 0
    deadline = time.time() + 60

    while time.time() < deadline:
        resp = requests.post(
            f"{API_BASE}/sp/campaigns/list",
            headers=headers,
            json={
                "stateFilter": {"include": ["ENABLED", "PAUSED"]},
                "startIndex": start_index,
                "count": 1000,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        camps = data.get("campaigns", []) if isinstance(data, dict) else data
        items = camps if isinstance(camps, list) else camps.get("items", [])

        for c in items:
            campaigns.append({
                "campaignId": c.get("campaignId"),
                "name": c.get("name", ""),
                "state": c.get("state", ""),
                "dailyBudget": float(c.get("budget", {}).get("budget", 0) if isinstance(c.get("budget"), dict) else c.get("dailyBudget", 0)),
                "targetingType": c.get("targetingType", ""),
                "startDate": c.get("startDate", ""),
            })

        if len(items) < 1000:
            break
        start_index += 1000

    return campaigns


def fetch_sp_report(profile_id: int, start: date, end: date) -> List[Dict]:
    """Fetch SP campaign daily metrics for date range."""
    all_rows = []
    cur = start

    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=6))
        print(f"  [Report] {cur} ~ {chunk_end}")

        body = {
            "name": f"PPC exec {cur}~{chunk_end}",
            "startDate": cur.strftime("%Y-%m-%d"),
            "endDate": chunk_end.strftime("%Y-%m-%d"),
            "configuration": {
                "adProduct": "SPONSORED_PRODUCTS",
                "groupBy": ["campaign"],
                "columns": ["date", "campaignId", "impressions", "clicks",
                            "cost", "sales14d", "purchases14d"],
                "reportTypeId": "spCampaigns",
                "timeUnit": "DAILY",
                "format": "GZIP_JSON",
            },
        }

        headers = _headers_reporting(profile_id)
        resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
        if resp.status_code == 425:
            print("  [425] Rate limited, waiting 30s...")
            time.sleep(30)
            resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        report_id = resp.json()["reportId"]

        # Poll
        deadline_t = time.time() + 600
        while time.time() < deadline_t:
            time.sleep(15)
            st = requests.get(f"{API_BASE}/reporting/reports/{report_id}",
                              headers=_headers_reporting(profile_id), timeout=30)
            st.raise_for_status()
            info = st.json()
            if info.get("status") == "COMPLETED":
                url = info.get("url")
                if url:
                    dl = requests.get(url, timeout=300)
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
                    all_rows.extend(rows)
                break
            if info.get("status") == "FAILED":
                print(f"  [WARN] Report {report_id} failed")
                break

        cur = chunk_end + timedelta(days=1)
        if cur <= end:
            time.sleep(5)

    return all_rows


# ===========================================================================
# Search Term Report & Keyword-Level Data
# ===========================================================================

def fetch_search_term_report(profile_id: int, start: date, end: date) -> List[Dict]:
    """Fetch SP search term report for keyword harvesting & negative analysis."""
    all_rows = []
    cur = start

    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=6))
        print(f"  [SearchTermReport] {cur} ~ {chunk_end}")

        body = {
            "name": f"PPC ST {cur}~{chunk_end}",
            "startDate": cur.strftime("%Y-%m-%d"),
            "endDate": chunk_end.strftime("%Y-%m-%d"),
            "configuration": {
                "adProduct": "SPONSORED_PRODUCTS",
                "groupBy": ["searchTerm"],
                "columns": [
                    "campaignId", "adGroupId", "keywordId",
                    "searchTerm", "impressions", "clicks", "cost",
                    "sales14d", "purchases14d",
                ],
                "reportTypeId": "spSearchTerm",
                "timeUnit": "SUMMARY",
                "format": "GZIP_JSON",
            },
        }

        headers = _headers_reporting(profile_id)
        resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
        if resp.status_code == 425:
            print("  [425] Rate limited, waiting 30s...")
            time.sleep(30)
            resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        report_id = resp.json()["reportId"]

        deadline_t = time.time() + 600
        while time.time() < deadline_t:
            time.sleep(15)
            st = requests.get(f"{API_BASE}/reporting/reports/{report_id}",
                              headers=_headers_reporting(profile_id), timeout=30)
            st.raise_for_status()
            info = st.json()
            if info.get("status") == "COMPLETED":
                url = info.get("url")
                if url:
                    dl = requests.get(url, timeout=300)
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
                    all_rows.extend(rows)
                break
            if info.get("status") == "FAILED":
                print(f"  [WARN] Search term report {report_id} failed")
                break

        cur = chunk_end + timedelta(days=1)
        if cur <= end:
            time.sleep(5)

    return all_rows


def fetch_keyword_report(profile_id: int, start: date, end: date) -> List[Dict]:
    """Fetch SP keyword-level metrics for bid optimization."""
    all_rows = []
    cur = start

    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=6))
        print(f"  [KeywordReport] {cur} ~ {chunk_end}")

        body = {
            "name": f"PPC KW {cur}~{chunk_end}",
            "startDate": cur.strftime("%Y-%m-%d"),
            "endDate": chunk_end.strftime("%Y-%m-%d"),
            "configuration": {
                "adProduct": "SPONSORED_PRODUCTS",
                "groupBy": ["adGroup"],
                "columns": [
                    "campaignId", "adGroupId", "keywordId",
                    "keywordText", "matchType",
                    "impressions", "clicks", "cost",
                    "sales14d", "purchases14d",
                ],
                "reportTypeId": "spKeywords",
                "timeUnit": "SUMMARY",
                "format": "GZIP_JSON",
            },
        }

        headers = _headers_reporting(profile_id)
        resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
        if resp.status_code == 425:
            time.sleep(30)
            resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        report_id = resp.json()["reportId"]

        deadline_t = time.time() + 600
        while time.time() < deadline_t:
            time.sleep(15)
            st = requests.get(f"{API_BASE}/reporting/reports/{report_id}",
                              headers=_headers_reporting(profile_id), timeout=30)
            st.raise_for_status()
            info = st.json()
            if info.get("status") == "COMPLETED":
                url = info.get("url")
                if url:
                    dl = requests.get(url, timeout=300)
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
                    all_rows.extend(rows)
                break
            if info.get("status") == "FAILED":
                print(f"  [WARN] Keyword report {report_id} failed")
                break

        cur = chunk_end + timedelta(days=1)
        if cur <= end:
            time.sleep(5)

    return all_rows


def analyze_search_terms(
    st_rows: List[Dict],
    campaigns: List[Dict],
    existing_keywords: List[Dict],
) -> Dict[str, List[Dict]]:
    """Analyze search terms for harvesting and negative keyword opportunities.

    Returns dict with 'harvest' and 'negate' lists.
    """
    # Build set of existing exact-match keyword texts for dedup
    existing_exact = set()
    for kw in existing_keywords:
        if kw.get("matchType", "").upper() == "EXACT":
            existing_exact.add(kw.get("keywordText", "").lower().strip())

    # Build campaign name lookup (normalize to int keys for consistent matching)
    camp_map = {}
    for c in campaigns:
        try:
            camp_map[int(c["campaignId"])] = c
        except (ValueError, TypeError):
            camp_map[c["campaignId"]] = c

    # Aggregate search terms (may span multiple days/chunks)
    agg = defaultdict(lambda: {
        "impressions": 0, "clicks": 0, "cost": 0.0,
        "sales": 0.0, "purchases": 0,
        "campaignId": None, "adGroupId": None,
    })
    for r in st_rows:
        term = (r.get("searchTerm", "") or "").strip().lower()
        if not term:
            continue
        b = agg[term]
        b["impressions"] += int(r.get("impressions", 0) or 0)
        b["clicks"] += int(r.get("clicks", 0) or 0)
        b["cost"] += float(r.get("cost", 0) or 0)
        b["sales"] += float(r.get("sales14d", 0) or 0)
        b["purchases"] += int(r.get("purchases14d", 0) or 0)
        if not b["campaignId"]:
            b["campaignId"] = r.get("campaignId")
            b["adGroupId"] = r.get("adGroupId")

    harvest = []
    negate = []

    for term, m in agg.items():
        cost = m["cost"]
        sales = m["sales"]
        clicks = m["clicks"]
        impressions = m["impressions"]
        acos = (cost / sales) if sales > 0 else None
        cpc = (cost / clicks) if clicks > 0 else 0

        try:
            cid_key = int(m["campaignId"])
        except (ValueError, TypeError):
            cid_key = m["campaignId"]
        camp = camp_map.get(cid_key, {})
        camp_type = classify_targeting(camp.get("name", ""), camp.get("targetingType", ""))
        presets = BID_PRESETS.get(camp_type, BID_PRESETS["MANUAL"])

        # --- Harvesting: profitable terms not yet in exact match ---
        if (acos is not None
                and acos < presets["desired_acos"]
                and clicks >= HARVEST_MIN_CLICKS
                and m["purchases"] >= HARVEST_MIN_SALES
                and term not in existing_exact):
            harvest.append({
                "type": "harvest",
                "searchTerm": term,
                "sourceCampaignId": m["campaignId"],
                "sourceCampaignName": camp.get("name", ""),
                "sourceAdGroupId": m["adGroupId"],
                "clicks": clicks,
                "cost": round(cost, 2),
                "sales": round(sales, 2),
                "purchases": m["purchases"],
                "acos": round(acos * 100, 1) if acos else None,
                "cpc": round(cpc, 2),
                "proposed_bid": round(cpc * HARVEST_BID_MULTIPLIER, 2),
                "priority": "medium",
                "reason": f"Profitable ST: ACOS {round(acos*100,1)}% < target {presets['desired_acos']*100}%, {m['purchases']} sales",
                "approved": False,
            })

        # --- Negative: zero sales with high spend ---
        target_cpa = presets["desired_acos"] * 20  # rough estimate: $20 AOV * target ACOS
        if (clicks >= presets["click_limit"]
                and m["purchases"] == 0
                and cost > target_cpa * NEGATIVE_ZERO_SALES_SPEND_MULT):
            negate.append({
                "type": "negate_zero_sales",
                "searchTerm": term,
                "campaignId": m["campaignId"],
                "campaignName": camp.get("name", ""),
                "adGroupId": m["adGroupId"],
                "clicks": clicks,
                "cost": round(cost, 2),
                "sales": 0,
                "impressions": impressions,
                "priority": "urgent",
                "reason": f"${cost:.2f} spent, {clicks} clicks, 0 sales (>{NEGATIVE_ZERO_SALES_SPEND_MULT}x target CPA)",
                "approved": False,
            })

        # --- Negative: extremely high ACOS ---
        elif (acos is not None
                and acos > presets["desired_acos"] * NEGATIVE_HIGH_ACOS_MULT
                and clicks >= presets["click_limit"]):
            negate.append({
                "type": "negate_high_acos",
                "searchTerm": term,
                "campaignId": m["campaignId"],
                "campaignName": camp.get("name", ""),
                "adGroupId": m["adGroupId"],
                "clicks": clicks,
                "cost": round(cost, 2),
                "sales": round(sales, 2),
                "acos": round(acos * 100, 1),
                "priority": "high",
                "reason": f"ACOS {round(acos*100,1)}% > {presets['desired_acos']*NEGATIVE_HIGH_ACOS_MULT*100}% threshold",
                "approved": False,
            })

    # Sort by impact
    harvest.sort(key=lambda x: x["sales"], reverse=True)
    negate.sort(key=lambda x: x["cost"], reverse=True)

    # Cap to prevent API overload
    harvest = harvest[:MAX_KEYWORD_CHANGES_PER_CYCLE]
    negate = negate[:MAX_KEYWORD_CHANGES_PER_CYCLE]

    return {"harvest": harvest, "negate": negate}


def analyze_keyword_bids(
    kw_rows: List[Dict],
    campaigns: List[Dict],
) -> List[Dict]:
    """Apply preset-based bid adjustment logic per keyword."""
    camp_map = {}
    for c in campaigns:
        try:
            camp_map[int(c["campaignId"])] = c
        except (ValueError, TypeError):
            camp_map[c["campaignId"]] = c
    proposals = []

    for kw in kw_rows:
        clicks = int(kw.get("clicks", 0) or 0)
        impressions = int(kw.get("impressions", 0) or 0)
        cost = float(kw.get("cost", 0) or 0)
        sales = float(kw.get("sales14d", 0) or 0)
        current_bid = float(kw.get("keywordBid", 0) or 0)
        kw_id = kw.get("keywordId")
        kw_text = kw.get("keywordText", "")

        if not kw_id or current_bid <= 0:
            continue

        try:
            cid_key = int(kw.get("campaignId"))
        except (ValueError, TypeError):
            cid_key = kw.get("campaignId")
        camp = camp_map.get(cid_key, {})
        camp_type = classify_targeting(camp.get("name", ""), camp.get("targetingType", ""))
        p = BID_PRESETS.get(camp_type, BID_PRESETS["MANUAL"])

        acos = (cost / sales) if sales > 0 else None
        action = None
        new_bid = current_bid
        reason = ""

        # Case 1: Strong performer
        if acos is not None and acos < p["mid_acos"] and clicks >= p["click_limit"] and sales > 0:
            new_bid = round(current_bid * (1 + p["increase_by"]), 2)
            new_bid = min(new_bid, p["max_bid"])
            action = "increase_bid"
            reason = f"ACOS {acos*100:.1f}% < {p['mid_acos']*100}% (strong), +{p['increase_by']*100:.0f}%"

        # Case 2: Inefficient
        elif acos is not None and acos > p["high_acos"] and clicks >= p["click_limit"]:
            new_bid = round(current_bid * (1 - p["decrease_by"]), 2)
            new_bid = max(new_bid, p["min_bid"])
            action = "decrease_bid"
            reason = f"ACOS {acos*100:.1f}% > {p['high_acos']*100}% (high), -{p['decrease_by']*100:.0f}%"

        # Case 3: Spending with no sales
        elif clicks >= p["click_limit"] and sales == 0 and cost > 0:
            new_bid = round(current_bid * 0.70, 2)
            new_bid = max(new_bid, p["min_bid"])
            action = "decrease_bid"
            reason = f"{clicks} clicks, $0 sales -> -30%"

        # Case 4: Low visibility bump
        elif impressions < p["impression_limit"] and clicks < 3 and impressions > 0:
            new_bid = round(current_bid + p["step_up"], 2)
            new_bid = min(new_bid, p["max_bid"])
            action = "increase_bid"
            reason = f"Low visibility ({impressions} impr, {clicks} clicks), +${p['step_up']}"

        # Case 5: Zero impressions -> pause
        elif impressions == 0:
            action = "pause_keyword"
            new_bid = current_bid
            reason = "0 impressions in period -> pause"

        if action and new_bid != current_bid:
            proposals.append({
                "type": "keyword_bid",
                "keywordId": kw_id,
                "keywordText": kw_text,
                "matchType": kw.get("matchType", ""),
                "campaignId": kw.get("campaignId"),
                "campaignName": camp.get("name", ""),
                "adGroupId": kw.get("adGroupId"),
                "current_bid": current_bid,
                "new_bid": round(new_bid, 2),
                "action": action,
                "clicks": clicks,
                "impressions": impressions,
                "cost": round(cost, 2),
                "sales": round(sales, 2),
                "acos_pct": round(acos * 100, 1) if acos else None,
                "priority": "high" if action == "decrease_bid" and sales == 0 else "medium",
                "reason": reason,
                "approved": False,
            })

    # Sort: decreases first (stop bleeding), then increases
    proposals.sort(key=lambda x: (0 if "decrease" in x["action"] else 1, -x["cost"]))
    return proposals[:MAX_KEYWORD_CHANGES_PER_CYCLE]


# ===========================================================================
# Analysis & Proposal Generation
# ===========================================================================

def classify_targeting(campaign_name: str, targeting_type: str) -> str:
    """Classify campaign as MANUAL or AUTO based on name and targeting type."""
    name_lower = campaign_name.lower()
    if "auto" in name_lower or targeting_type.upper() == "AUTO":
        return "AUTO"
    return "MANUAL"


def compute_budget_allocation(campaigns: List[Dict], agg_7d: Dict) -> Dict[str, float]:
    """Compute optimal budget split: manual vs auto within $150/day total."""
    manual_budget = TOTAL_DAILY_BUDGET_USD * TARGETING_CONFIG["MANUAL"]["budget_share"]
    auto_budget = TOTAL_DAILY_BUDGET_USD * TARGETING_CONFIG["AUTO"]["budget_share"]

    # Count active campaigns per type
    manual_camps = []
    auto_camps = []
    for c in campaigns:
        if c["state"] != "ENABLED":
            continue
        ctype = classify_targeting(c["name"], c.get("targetingType", ""))
        m = agg_7d.get(c["campaignId"], {})
        roas = 0
        cost = m.get("cost", 0)
        sales = m.get("sales", 0)
        if cost > 0:
            roas = sales / cost
        entry = {"campaign": c, "roas": roas, "spend_7d": cost}
        if ctype == "MANUAL":
            manual_camps.append(entry)
        else:
            auto_camps.append(entry)

    # If one type has no campaigns, give full budget to the other
    if not manual_camps and auto_camps:
        auto_budget = TOTAL_DAILY_BUDGET_USD
    elif not auto_camps and manual_camps:
        manual_budget = TOTAL_DAILY_BUDGET_USD

    return {
        "MANUAL": {"budget": round(manual_budget, 2), "campaigns": len(manual_camps)},
        "AUTO": {"budget": round(auto_budget, 2), "campaigns": len(auto_camps)},
        "total": TOTAL_DAILY_BUDGET_USD,
    }


def analyze_campaigns(campaigns: List[Dict], report_rows: List[Dict]) -> List[Dict]:
    """Apply ROAS Decision Framework with manual/auto split within $150/day."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    d7_start = today - timedelta(days=7)
    d30_start = today - timedelta(days=30)

    # Aggregate by campaign for yd, 7d, 30d
    def agg(rows, from_d, to_d):
        bucket = defaultdict(lambda: {"cost": 0.0, "sales": 0.0, "clicks": 0, "impressions": 0, "purchases": 0})
        for r in rows:
            rd = datetime.strptime(r.get("date", "")[:10], "%Y-%m-%d").date()
            if from_d <= rd <= to_d:
                cid = r.get("campaignId")
                b = bucket[cid]
                b["cost"] += float(r.get("cost", 0) or 0)
                b["sales"] += float(r.get("sales14d", 0) or 0)
                b["clicks"] += int(r.get("clicks", 0) or 0)
                b["impressions"] += int(r.get("impressions", 0) or 0)
                b["purchases"] += int(r.get("purchases14d", 0) or 0)
        return bucket

    agg_yd = agg(report_rows, yesterday, yesterday)
    agg_7d = agg(report_rows, d7_start, yesterday)
    agg_30d = agg(report_rows, d30_start, yesterday)

    # Budget allocation
    allocation = compute_budget_allocation(campaigns, agg_7d)

    proposals = []

    for camp in campaigns:
        cid = camp["campaignId"]
        if camp["state"] != "ENABLED":
            continue

        camp_type = classify_targeting(camp["name"], camp.get("targetingType", ""))
        config = TARGETING_CONFIG[camp_type]

        m7 = agg_7d.get(cid, {"cost": 0, "sales": 0, "clicks": 0, "impressions": 0, "purchases": 0})
        m30 = agg_30d.get(cid, {"cost": 0, "sales": 0, "clicks": 0, "impressions": 0, "purchases": 0})
        myd = agg_yd.get(cid, {"cost": 0, "sales": 0, "clicks": 0, "impressions": 0, "purchases": 0})

        cost_7d = m7["cost"]
        sales_7d = m7["sales"]
        roas_7d = round(sales_7d / cost_7d, 2) if cost_7d > 0 else 0
        acos_7d = round(cost_7d / sales_7d * 100, 1) if sales_7d > 0 else None

        cost_30d = m30["cost"]
        sales_30d = m30["sales"]
        roas_30d = round(sales_30d / cost_30d, 2) if cost_30d > 0 else 0

        cost_yd = myd["cost"]
        sales_yd = myd["sales"]
        roas_yd = round(sales_yd / cost_yd, 2) if cost_yd > 0 else 0

        # Skip campaigns with negligible spend
        if cost_7d < 1.0 and cost_30d < 5.0:
            continue

        # Apply ROAS Decision Framework (adjusted by campaign type)
        action = "monitor"
        bid_change_pct = None
        budget_change_pct = None
        priority = "low"
        reason = ""

        # For AUTO campaigns, use looser thresholds
        effective_roas = roas_7d
        if camp_type == "AUTO" and roas_7d >= config["min_roas"]:
            # Auto campaigns get a pass if above their min_roas
            pass

        for min_r, max_r, act, bid_pct, bud_pct, pri in ROAS_RULES:
            low_ok = (min_r is None) or (effective_roas >= min_r)
            high_ok = (max_r is None) or (effective_roas < max_r)
            if low_ok and high_ok:
                action = act
                bid_change_pct = bid_pct
                budget_change_pct = bud_pct
                priority = pri
                break

        # Zero sales with spend
        if cost_7d > 5 and sales_7d == 0 and m7["clicks"] > 5:
            action = "pause"
            priority = "urgent"
            reason = f"[{camp_type}] 7d: ${cost_7d:.1f} spent, {m7['clicks']} clicks, $0 sales"

        # ROAS-based reason
        if not reason:
            trend = ""
            if roas_30d > 0:
                pct_change = round((roas_7d - roas_30d) / roas_30d * 100, 1)
                trend = f"7d vs 30d: {'+' if pct_change >= 0 else ''}{pct_change}%"
            reason = (f"[{camp_type}] 7d ROAS {roas_7d}x (ACOS {acos_7d}%) | "
                      f"30d ROAS {roas_30d}x | target ACOS {config['target_acos']}% | {trend}")

        # Additional rule: yesterday ROAS drop 30%+ vs 7d avg
        additional_action = None
        if roas_7d > 0 and roas_yd > 0:
            drop_pct = (roas_7d - roas_yd) / roas_7d * 100
            if drop_pct >= 30:
                additional_action = f"Yesterday ROAS dropped {drop_pct:.0f}% vs 7d avg -> additional -20% bid"
                if bid_change_pct:
                    bid_change_pct = bid_change_pct - 20
                else:
                    bid_change_pct = -20

        # Budget safety cap — respect per-type allocation and per-campaign max
        type_budget = allocation[camp_type]["budget"]
        type_camp_count = max(allocation[camp_type]["campaigns"], 1)
        per_camp_share = round(type_budget / type_camp_count, 2)
        max_budget = min(per_camp_share * 2, MAX_SINGLE_CAMPAIGN_BUDGET)  # No more than 2x fair share

        new_budget = camp["dailyBudget"]
        if budget_change_pct and camp["dailyBudget"] > 0:
            new_budget = round(camp["dailyBudget"] * (1 + budget_change_pct / 100), 2)
            if new_budget > max_budget:
                new_budget = max_budget

        if action == "monitor":
            continue

        proposal = {
            "campaignId": cid,
            "campaignName": camp["name"],
            "campaignType": camp_type,
            "targetingType": camp.get("targetingType", ""),
            "currentState": camp["state"],
            "currentDailyBudget": camp["dailyBudget"],
            "metrics": {
                "yesterday": {"spend": round(cost_yd, 2), "sales": round(sales_yd, 2), "roas": roas_yd},
                "7d": {"spend": round(cost_7d, 2), "sales": round(sales_7d, 2), "roas": roas_7d, "acos": acos_7d,
                       "clicks": m7["clicks"], "impressions": m7["impressions"], "purchases": m7["purchases"]},
                "30d": {"spend": round(cost_30d, 2), "sales": round(sales_30d, 2), "roas": roas_30d},
            },
            "budget_allocation": {
                "type": camp_type,
                "type_total_budget": type_budget,
                "per_campaign_fair_share": per_camp_share,
                "max_allowed": max_budget,
            },
            "proposed_action": action,
            "bid_change_pct": bid_change_pct,
            "budget_change_pct": budget_change_pct,
            "new_daily_budget": new_budget if budget_change_pct else None,
            "priority": priority,
            "reason": reason,
            "additional": additional_action,
            "approved": False,  # User must set to True
        }
        proposals.append(proposal)

    # Sort by priority
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    proposals.sort(key=lambda x: priority_order.get(x["priority"], 9))

    return proposals


# ===========================================================================
# API Write Operations
# ===========================================================================

def pause_campaign(profile_id: int, campaign_id: int) -> Dict:
    """Pause a campaign."""
    headers = _headers_sp(profile_id)
    resp = requests.put(
        f"{API_BASE}/sp/campaigns",
        headers=headers,
        json={
            "campaigns": [{
                "campaignId": campaign_id,
                "state": "PAUSED",
            }]
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_campaign_budget(profile_id: int, campaign_id: int, new_budget: float) -> Dict:
    """Update campaign daily budget."""
    if new_budget > MAX_SINGLE_CAMPAIGN_BUDGET:
        raise ValueError(f"Budget ${new_budget} exceeds per-campaign cap ${MAX_SINGLE_CAMPAIGN_BUDGET}")

    headers = _headers_sp(profile_id)
    resp = requests.put(
        f"{API_BASE}/sp/campaigns",
        headers=headers,
        json={
            "campaigns": [{
                "campaignId": campaign_id,
                "budget": {"budget": new_budget, "budgetType": "DAILY"},
            }]
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_campaign_bid(profile_id: int, campaign_id: int, bid_change_pct: float) -> Dict:
    """Adjust default bid for a campaign's ad groups by percentage."""
    # First get ad groups for this campaign
    headers = _headers(profile_id)
    headers["Accept"] = "application/vnd.spAdGroup.v3+json"
    headers["Content-Type"] = "application/vnd.spAdGroup.v3+json"

    resp = requests.post(
        f"{API_BASE}/sp/adGroups/list",
        headers=headers,
        json={
            "campaignIdFilter": {"include": [campaign_id]},
            "stateFilter": {"include": ["ENABLED"]},
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    groups = data if isinstance(data, list) else data.get("adGroups", [])

    results = []
    for ag in groups:
        ag_id = ag.get("adGroupId")
        current_bid = float(ag.get("defaultBid", 0) or 0)
        if current_bid <= 0:
            continue

        new_bid = round(current_bid * (1 + bid_change_pct / 100), 2)
        new_bid = max(0.02, min(new_bid, MAX_BID_USD))  # Floor $0.02, cap $5.00

        resp2 = requests.put(
            f"{API_BASE}/sp/adGroups",
            headers=headers,
            json={
                "adGroups": [{
                    "adGroupId": ag_id,
                    "defaultBid": new_bid,
                }]
            },
            timeout=20,
        )
        resp2.raise_for_status()
        results.append({
            "adGroupId": ag_id,
            "oldBid": current_bid,
            "newBid": new_bid,
            "change_pct": bid_change_pct,
            "result": resp2.json(),
        })

    return {"campaign_id": campaign_id, "ad_group_updates": results}


def add_keyword(profile_id: int, campaign_id, ad_group_id, keyword_text: str,
                 match_type: str, bid: float) -> Dict:
    """Add a new keyword to an ad group (for harvested search terms)."""
    bid = min(bid, MAX_BID_USD)
    headers = _headers(profile_id)
    headers["Accept"] = "application/vnd.spKeyword.v3+json"
    headers["Content-Type"] = "application/vnd.spKeyword.v3+json"

    resp = requests.post(
        f"{API_BASE}/sp/keywords",
        headers=headers,
        json={
            "keywords": [{
                "campaignId": str(campaign_id),
                "adGroupId": str(ad_group_id),
                "keywordText": keyword_text,
                "matchType": match_type.upper(),
                "bid": bid,
                "state": "ENABLED",
            }]
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def add_negative_keyword(profile_id: int, campaign_id, ad_group_id,
                         keyword_text: str, match_type: str = "NEGATIVE_EXACT") -> Dict:
    """Add a negative keyword to block unprofitable search terms."""
    headers = _headers(profile_id)
    headers["Accept"] = "application/vnd.spNegativeKeyword.v3+json"
    headers["Content-Type"] = "application/vnd.spNegativeKeyword.v3+json"

    resp = requests.post(
        f"{API_BASE}/sp/negativeKeywords",
        headers=headers,
        json={
            "negativeKeywords": [{
                "campaignId": str(campaign_id),
                "adGroupId": str(ad_group_id),
                "keywordText": keyword_text,
                "matchType": match_type,
                "state": "ENABLED",
            }]
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_keyword_bid(profile_id: int, keyword_id, new_bid: float) -> Dict:
    """Update a specific keyword's bid."""
    new_bid = max(0.02, min(new_bid, MAX_BID_USD))
    headers = _headers(profile_id)
    headers["Accept"] = "application/vnd.spKeyword.v3+json"
    headers["Content-Type"] = "application/vnd.spKeyword.v3+json"

    resp = requests.put(
        f"{API_BASE}/sp/keywords",
        headers=headers,
        json={
            "keywords": [{
                "keywordId": keyword_id,
                "bid": new_bid,
            }]
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_asin_target_bid(profile_id: int, target_id, new_bid: float) -> Dict:
    """Update bid for an ASIN product target (SP Competitor/Product Targeting)."""
    new_bid = max(0.02, min(new_bid, MAX_BID_USD))
    headers = _headers(profile_id)
    headers["Accept"] = "application/vnd.spTargetingClause.v3+json"
    headers["Content-Type"] = "application/vnd.spTargetingClause.v3+json"

    resp = requests.put(
        f"{API_BASE}/sp/targets",
        headers=headers,
        json={"targetingClauses": [{"targetId": str(target_id), "bid": new_bid}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_asin_targets(profile_id: int, ad_group_id) -> list:
    """List ASIN product targets for an ad group."""
    headers = _headers(profile_id)
    headers["Accept"] = "application/vnd.spTargetingClause.v3+json"
    headers["Content-Type"] = "application/vnd.spTargetingClause.v3+json"

    resp = requests.post(
        f"{API_BASE}/sp/targets/list",
        headers=headers,
        json={"adGroupIdFilter": {"include": [str(ad_group_id)]}, "stateFilter": {"include": ["ENABLED"]}},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("targetingClauses", data) if isinstance(data, dict) else data


def pause_keyword(profile_id: int, keyword_id) -> Dict:
    """Pause a keyword."""
    headers = _headers(profile_id)
    headers["Accept"] = "application/vnd.spKeyword.v3+json"
    headers["Content-Type"] = "application/vnd.spKeyword.v3+json"

    resp = requests.put(
        f"{API_BASE}/sp/keywords",
        headers=headers,
        json={
            "keywords": [{
                "keywordId": keyword_id,
                "state": "PAUSED",
            }]
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ===========================================================================
# Google Sheets Change Log
# ===========================================================================

def log_to_sheets(executed_changes: List[Dict]):
    """Append executed changes to Google Sheets change log."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("[WARN] gspread not installed, skipping sheet log")
        return

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_path = ROOT / "credentials.json"
    if not creds_path.exists():
        print(f"[WARN] {creds_path} not found, skipping sheet log")
        return

    sheet_id = os.getenv("PPC_CHANGELOG_SHEET_ID")
    if not sheet_id:
        print("[WARN] PPC_CHANGELOG_SHEET_ID not set in .env, skipping sheet log")
        return

    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    tab_name = "PPC Change Log"
    try:
        ws = sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=15)
        ws.append_row([
            "Timestamp", "Brand", "Campaign", "Campaign ID",
            "Action", "Priority", "Reason",
            "Old Budget", "New Budget", "Bid Change %",
            "7d ROAS", "7d Spend", "7d Sales",
            "Result", "Approved By"
        ])

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_add = []

    for ch in executed_changes:
        rows_to_add.append([
            now,
            TARGET_BRAND,
            ch.get("campaignName", ""),
            str(ch.get("campaignId", "")),
            ch.get("action", ""),
            ch.get("priority", ""),
            ch.get("reason", ""),
            ch.get("old_budget", ""),
            ch.get("new_budget", ""),
            ch.get("bid_change_pct", ""),
            ch.get("roas_7d", ""),
            ch.get("spend_7d", ""),
            ch.get("sales_7d", ""),
            ch.get("result_status", ""),
            "wj.choi",
        ])

    if rows_to_add:
        ws.append_rows(rows_to_add)
        print(f"[Sheets] {len(rows_to_add)} rows logged to '{tab_name}'")


# ===========================================================================
# Proposal File I/O
# ===========================================================================

def save_proposal(proposals: List[Dict], profile_id: int,
                   keyword_proposals: Optional[List[Dict]] = None):
    today_str = date.today().strftime("%Y%m%d")
    filepath = TMP_DIR / f"ppc_proposal_{today_str}.json"

    kw_props = keyword_proposals or []
    payload = {
        "generated_at": datetime.now().isoformat(),
        "brand": TARGET_BRAND,
        "seller": TARGET_SELLER,
        "profile_id": profile_id,
        "total_proposals": len(proposals),
        "total_keyword_proposals": len(kw_props),
        "proposals": proposals,
        "keyword_proposals": kw_props,
        "instructions": (
            "Review each proposal. Set 'approved': true for items you want to execute. "
            "keyword_proposals contains: harvest (add exact match), negate (add negative), "
            "keyword_bid (adjust individual keyword bids). "
            "Then run: python tools/amazon_ppc_executor.py --execute"
        ),
    }
    filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[SAVED] {filepath}")
    return filepath


def load_latest_proposal() -> Optional[Dict]:
    proposals = sorted(TMP_DIR.glob("ppc_proposal_*.json"), reverse=True)
    if not proposals:
        return None
    return json.loads(proposals[0].read_text(encoding="utf-8"))


# ===========================================================================
# Pretty Print Proposal
# ===========================================================================

def print_proposal_summary(proposals: List[Dict]):
    print(f"\n{'='*70}")
    print(f"  NAEIAE (Fleeters Inc) PPC Change Proposals - {date.today()}")
    print(f"  Daily Budget Cap: ${TOTAL_DAILY_BUDGET_USD} (Manual 60% / Auto 40%)")
    print(f"{'='*70}")

    # Manual vs Auto breakdown
    manual_props = [p for p in proposals if p.get("campaignType") == "MANUAL"]
    auto_props = [p for p in proposals if p.get("campaignType") == "AUTO"]
    print(f"\n  Manual campaigns: {len(manual_props)} proposals")
    print(f"  Auto campaigns:   {len(auto_props)} proposals")

    urgent = [p for p in proposals if p["priority"] == "urgent"]
    high = [p for p in proposals if p["priority"] == "high"]
    medium = [p for p in proposals if p["priority"] == "medium"]

    if urgent:
        print(f"\n[URGENT] {len(urgent)} campaigns need immediate action:")
        for p in urgent:
            print(f"  * [{p.get('campaignType','?')}] {p['campaignName']}")
            print(f"    Action: {p['proposed_action']} | 7d ROAS: {p['metrics']['7d']['roas']}x")
            print(f"    Reason: {p['reason']}")
            if p.get("bid_change_pct"):
                print(f"    Bid change: {p['bid_change_pct']:+d}%")
            print()

    if high:
        print(f"\n[HIGH] {len(high)} campaigns:")
        for p in high:
            print(f"  * [{p.get('campaignType','?')}] {p['campaignName']}")
            print(f"    Action: {p['proposed_action']} | 7d ROAS: {p['metrics']['7d']['roas']}x")
            if p.get("budget_change_pct"):
                alloc = p.get("budget_allocation", {})
                print(f"    Budget: ${p['currentDailyBudget']} -> ${p.get('new_daily_budget', '?')} (max ${alloc.get('max_allowed', '?')})")
            if p.get("bid_change_pct"):
                print(f"    Bid change: {p['bid_change_pct']:+d}%")
            print()

    if medium:
        print(f"\n[MEDIUM] {len(medium)} campaigns:")
        for p in medium:
            print(f"  * [{p.get('campaignType','?')}] {p['campaignName']}: {p['proposed_action']} (7d ROAS {p['metrics']['7d']['roas']}x)")

    print(f"\n{'='*70}")
    print(f"Total: {len(proposals)} campaign proposals ({len(urgent)} urgent, {len(high)} high, {len(medium)} medium)")
    print(f"Review the JSON file and set 'approved': true for items to execute.")
    print(f"Then run: python tools/amazon_ppc_executor.py --execute")
    print(f"{'='*70}\n")


def print_keyword_summary(kw_proposals: List[Dict]):
    """Print summary of keyword-level proposals (harvest, negate, bid adjust)."""
    harvest = [p for p in kw_proposals if p.get("type") == "harvest"]
    negate = [p for p in kw_proposals if p.get("type", "").startswith("negate")]
    bid_adj = [p for p in kw_proposals if p.get("type") == "keyword_bid"]

    if not kw_proposals:
        print("\n[Keywords] No keyword-level changes needed.")
        return

    print(f"\n{'='*70}")
    print(f"  KEYWORD-LEVEL PROPOSALS")
    print(f"{'='*70}")

    if harvest:
        print(f"\n[HARVEST] {len(harvest)} profitable search terms -> exact match:")
        for h in harvest[:10]:
            print(f"  + '{h['searchTerm']}' | ACOS {h['acos']}% | {h['purchases']} sales | bid ${h['proposed_bid']}")
            print(f"    Source: {h['sourceCampaignName']}")
        if len(harvest) > 10:
            print(f"  ... and {len(harvest) - 10} more")

    if negate:
        print(f"\n[NEGATE] {len(negate)} unprofitable search terms -> negative exact:")
        for n in negate[:10]:
            print(f"  - '{n['searchTerm']}' | ${n['cost']} spent | {n.get('sales', 0)} sales | {n['reason']}")
        if len(negate) > 10:
            print(f"  ... and {len(negate) - 10} more")

    if bid_adj:
        increases = [b for b in bid_adj if "increase" in b.get("action", "")]
        decreases = [b for b in bid_adj if "decrease" in b.get("action", "")]
        pauses = [b for b in bid_adj if "pause" in b.get("action", "")]
        print(f"\n[BID ADJ] {len(bid_adj)} keyword bids: {len(increases)} up, {len(decreases)} down, {len(pauses)} pause")
        for b in bid_adj[:10]:
            arrow = "+" if "increase" in b.get("action", "") else "-" if "decrease" in b.get("action", "") else "X"
            print(f"  {arrow} '{b['keywordText']}' ${b['current_bid']} -> ${b['new_bid']} | {b['reason']}")
        if len(bid_adj) > 10:
            print(f"  ... and {len(bid_adj) - 10} more")

    total = len(harvest) + len(negate) + len(bid_adj)
    print(f"\n{'='*70}")
    print(f"Total keyword proposals: {total} ({len(harvest)} harvest, {len(negate)} negate, {len(bid_adj)} bid adj)")
    print(f"{'='*70}\n")


# ===========================================================================
# Execute Approved Changes
# ===========================================================================

def execute_approved(proposal_data: Dict) -> List[Dict]:
    profile_id = proposal_data["profile_id"]
    proposals = proposal_data.get("proposals", [])
    keyword_proposals = proposal_data.get("keyword_proposals", [])
    approved = [p for p in proposals if p.get("approved") is True]
    approved_kw = [p for p in keyword_proposals if p.get("approved") is True]

    total_approved = len(approved) + len(approved_kw)
    if total_approved == 0:
        print("[INFO] No approved proposals found. Set 'approved': true in the JSON file.")
        return []

    print(f"\n[EXECUTE] {total_approved} approved changes for {TARGET_BRAND}")
    print(f"  Campaign-level: {len(approved)} | Keyword-level: {len(approved_kw)}")
    print(f"{'='*50}")

    executed = []

    # --- Campaign-level actions ---
    for p in approved:
        cid = p["campaignId"]
        action = p["proposed_action"]
        name = p["campaignName"]

        print(f"\n  Executing: {action} on '{name}' (ID: {cid})")

        result_status = "OK"
        try:
            if action == "pause":
                result = pause_campaign(profile_id, cid)
                print(f"    -> Campaign PAUSED")

            elif action == "reduce_bid" and p.get("bid_change_pct"):
                result = update_campaign_bid(profile_id, cid, p["bid_change_pct"])
                n_groups = len(result.get("ad_group_updates", []))
                print(f"    -> Bid adjusted {p['bid_change_pct']:+d}% across {n_groups} ad groups")

            elif action == "increase_budget":
                if p.get("new_daily_budget"):
                    result = update_campaign_budget(profile_id, cid, p["new_daily_budget"])
                    print(f"    -> Budget: ${p['currentDailyBudget']} -> ${p['new_daily_budget']}")
                if p.get("bid_change_pct"):
                    result = update_campaign_bid(profile_id, cid, p["bid_change_pct"])
                    print(f"    -> Bid adjusted {p['bid_change_pct']:+d}%")

            else:
                print(f"    -> Skipped (unknown action: {action})")
                result_status = "SKIPPED"

        except Exception as e:
            print(f"    -> ERROR: {e}")
            result_status = f"ERROR: {e}"

        executed.append({
            "campaignId": cid,
            "campaignName": name,
            "action": action,
            "priority": p["priority"],
            "reason": p["reason"],
            "old_budget": p.get("currentDailyBudget"),
            "new_budget": p.get("new_daily_budget"),
            "bid_change_pct": p.get("bid_change_pct"),
            "roas_7d": p.get("metrics", {}).get("7d", {}).get("roas"),
            "spend_7d": p.get("metrics", {}).get("7d", {}).get("spend"),
            "sales_7d": p.get("metrics", {}).get("7d", {}).get("sales"),
            "result_status": result_status,
        })

    # --- Keyword-level actions ---
    for kp in approved_kw:
        kp_type = kp.get("type", "")
        result_status = "OK"

        try:
            if kp_type == "harvest":
                term = kp["searchTerm"]
                print(f"\n  Harvesting: '{term}' -> exact match @ ${kp['proposed_bid']}")
                # Add as exact match keyword
                result = add_keyword(
                    profile_id, kp["sourceCampaignId"], kp["sourceAdGroupId"],
                    term, "EXACT", kp["proposed_bid"],
                )
                # Add as negative in source campaign to prevent cannibalization
                add_negative_keyword(
                    profile_id, kp["sourceCampaignId"], kp["sourceAdGroupId"],
                    term, "NEGATIVE_EXACT",
                )
                print(f"    -> Added exact + negated in source")

            elif kp_type in ("negate_zero_sales", "negate_high_acos"):
                term = kp["searchTerm"]
                print(f"\n  Negating: '{term}' (${kp['cost']} spent, {kp.get('sales', 0)} sales)")
                result = add_negative_keyword(
                    profile_id, kp["campaignId"], kp["adGroupId"],
                    term, "NEGATIVE_EXACT",
                )
                print(f"    -> Negative exact added")

            elif kp_type == "keyword_bid":
                action = kp["action"]
                if action == "pause_keyword":
                    result = pause_keyword(profile_id, kp["keywordId"])
                    print(f"\n  Pausing keyword: '{kp['keywordText']}' (0 impressions)")
                else:
                    result = update_keyword_bid(profile_id, kp["keywordId"], kp["new_bid"])
                    print(f"\n  Bid: '{kp['keywordText']}' ${kp['current_bid']} -> ${kp['new_bid']}")

            else:
                print(f"\n  Skipped unknown type: {kp_type}")
                result_status = "SKIPPED"

        except Exception as e:
            print(f"    -> ERROR: {e}")
            result_status = f"ERROR: {e}"

        executed.append({
            "campaignId": kp.get("campaignId") or kp.get("sourceCampaignId"),
            "campaignName": kp.get("campaignName") or kp.get("sourceCampaignName", ""),
            "action": kp_type,
            "priority": kp.get("priority", "medium"),
            "reason": kp.get("reason", ""),
            "old_budget": None,
            "new_budget": None,
            "bid_change_pct": None,
            "keyword": kp.get("searchTerm") or kp.get("keywordText"),
            "old_bid": kp.get("current_bid"),
            "new_bid": kp.get("new_bid") or kp.get("proposed_bid"),
            "roas_7d": None,
            "spend_7d": kp.get("cost"),
            "sales_7d": kp.get("sales"),
            "result_status": result_status,
        })

    # Save execution log
    log_path = TMP_DIR / f"ppc_executed_{date.today().strftime('%Y%m%d')}.json"
    log_path.write_text(json.dumps(executed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[LOG] Execution log saved: {log_path}")

    return executed


# ===========================================================================
# Email Proposal
# ===========================================================================

DEFAULT_TO = "wj.choi@orbiters.co.kr"
DEFAULT_CC = "mj.lee@orbiters.co.kr"

def build_proposal_html(proposals: List[Dict],
                        kw_proposals: Optional[List[Dict]] = None) -> str:
    """Build HTML email showing all proposed changes for review."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    manual = [p for p in proposals if p.get("campaignType") == "MANUAL"]
    auto = [p for p in proposals if p.get("campaignType") == "AUTO"]
    urgent = [p for p in proposals if p["priority"] == "urgent"]
    high = [p for p in proposals if p["priority"] == "high"]
    medium = [p for p in proposals if p["priority"] == "medium"]

    def color(priority):
        return {"urgent": "#dc3545", "high": "#fd7e14", "medium": "#ffc107"}.get(priority, "#6c757d")

    def roas_color(roas):
        if roas >= 3.0: return "#28a745"
        if roas >= 2.0: return "#ffc107"
        return "#dc3545"

    rows_html = ""
    for p in proposals:
        m7 = p["metrics"]["7d"]
        alloc = p.get("budget_allocation", {})
        action_text = p["proposed_action"]
        if p.get("bid_change_pct"):
            action_text += f" (bid {p['bid_change_pct']:+d}%)"
        if p.get("new_daily_budget"):
            action_text += f" (budget ${p['currentDailyBudget']}->${p['new_daily_budget']})"

        rows_html += f"""
        <tr>
            <td style="padding:8px;border:1px solid #ddd;">
                <span style="background:{color(p['priority'])};color:white;padding:2px 6px;border-radius:3px;font-size:11px;">{p['priority'].upper()}</span>
            </td>
            <td style="padding:8px;border:1px solid #ddd;">[{p.get('campaignType','?')}] {p['campaignName']}</td>
            <td style="padding:8px;border:1px solid #ddd;color:{roas_color(m7['roas'])};font-weight:bold;">{m7['roas']}x</td>
            <td style="padding:8px;border:1px solid #ddd;">{m7.get('acos') or '-'}%</td>
            <td style="padding:8px;border:1px solid #ddd;">${m7['spend']:.0f}</td>
            <td style="padding:8px;border:1px solid #ddd;">${m7['sales']:.0f}</td>
            <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">{action_text}</td>
            <td style="padding:8px;border:1px solid #ddd;font-size:12px;">{p['reason']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:1200px;margin:0 auto;padding:20px;">
    <h2 style="color:#333;">Naeiae (Fleeters Inc) PPC Change Proposal</h2>
    <p style="color:#666;">{now} | Daily Budget Cap: ${TOTAL_DAILY_BUDGET_USD} (Manual 60% / Auto 40%)</p>

    <div style="display:flex;gap:20px;margin:15px 0;">
        <div style="background:#f8f9fa;padding:12px 20px;border-radius:8px;">
            <strong>{len(proposals)}</strong> total proposals
        </div>
        <div style="background:#fff3cd;padding:12px 20px;border-radius:8px;">
            <strong>{len(urgent)}</strong> urgent | <strong>{len(high)}</strong> high | <strong>{len(medium)}</strong> medium
        </div>
        <div style="background:#e8f5e9;padding:12px 20px;border-radius:8px;">
            Manual: <strong>{len(manual)}</strong> | Auto: <strong>{len(auto)}</strong>
        </div>
    </div>

    <table style="border-collapse:collapse;width:100%;margin-top:15px;">
        <tr style="background:#343a40;color:white;">
            <th style="padding:10px;border:1px solid #ddd;">Priority</th>
            <th style="padding:10px;border:1px solid #ddd;">Campaign</th>
            <th style="padding:10px;border:1px solid #ddd;">7d ROAS</th>
            <th style="padding:10px;border:1px solid #ddd;">7d ACOS</th>
            <th style="padding:10px;border:1px solid #ddd;">7d Spend</th>
            <th style="padding:10px;border:1px solid #ddd;">7d Sales</th>
            <th style="padding:10px;border:1px solid #ddd;">Proposed Action</th>
            <th style="padding:10px;border:1px solid #ddd;">Reason</th>
        </tr>
        {rows_html}
    </table>

    {_build_keyword_html(kw_proposals)}

    <div style="margin-top:25px;padding:15px;background:#fff3cd;border-radius:8px;">
        <strong>Action Required:</strong> Reply with approved campaign changes, or edit the JSON file at
        <code>.tmp/ppc_proposal_*.json</code> and run <code>--execute</code>.
    </div>

    <p style="color:#999;margin-top:20px;font-size:12px;">
        Generated by Mazone PPC Executor | 6-hour analysis cycle | Next analysis in ~6 hours
    </p>
</body>
</html>"""
    return html


def _build_keyword_html(kw_proposals: Optional[List[Dict]]) -> str:
    """Build HTML section for keyword-level proposals."""
    if not kw_proposals:
        return ""

    harvest = [p for p in kw_proposals if p.get("type") == "harvest"]
    negate = [p for p in kw_proposals if p.get("type", "").startswith("negate")]
    bid_adj = [p for p in kw_proposals if p.get("type") == "keyword_bid"]

    sections = []

    if harvest:
        rows = ""
        for h in harvest[:20]:
            rows += f"""<tr>
                <td style="padding:6px;border:1px solid #ddd;">{h['searchTerm']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{h['acos']}%</td>
                <td style="padding:6px;border:1px solid #ddd;">{h['purchases']}</td>
                <td style="padding:6px;border:1px solid #ddd;">${h['cost']}</td>
                <td style="padding:6px;border:1px solid #ddd;">${h['proposed_bid']}</td>
                <td style="padding:6px;border:1px solid #ddd;font-size:11px;">{h['sourceCampaignName']}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#28a745;margin-top:25px;">Keyword Harvesting ({len(harvest)} candidates)</h3>
        <p style="color:#666;font-size:13px;">Profitable search terms to add as exact match keywords</p>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#28a745;color:white;">
                <th style="padding:8px;">Search Term</th>
                <th style="padding:8px;">ACOS</th>
                <th style="padding:8px;">Sales</th>
                <th style="padding:8px;">Cost</th>
                <th style="padding:8px;">Proposed Bid</th>
                <th style="padding:8px;">Source Campaign</th>
            </tr>{rows}
        </table>""")

    if negate:
        rows = ""
        for n in negate[:20]:
            rows += f"""<tr>
                <td style="padding:6px;border:1px solid #ddd;">{n['searchTerm']}</td>
                <td style="padding:6px;border:1px solid #ddd;">${n['cost']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{n.get('sales', 0)}</td>
                <td style="padding:6px;border:1px solid #ddd;">{n['clicks']}</td>
                <td style="padding:6px;border:1px solid #ddd;font-size:11px;">{n['reason']}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#dc3545;margin-top:25px;">Negative Keywords ({len(negate)} candidates)</h3>
        <p style="color:#666;font-size:13px;">Unprofitable search terms to block</p>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#dc3545;color:white;">
                <th style="padding:8px;">Search Term</th>
                <th style="padding:8px;">Cost</th>
                <th style="padding:8px;">Sales</th>
                <th style="padding:8px;">Clicks</th>
                <th style="padding:8px;">Reason</th>
            </tr>{rows}
        </table>""")

    if bid_adj:
        rows = ""
        for b in bid_adj[:20]:
            color = "#28a745" if "increase" in b.get("action", "") else "#dc3545"
            rows += f"""<tr>
                <td style="padding:6px;border:1px solid #ddd;">{b['keywordText']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{b.get('matchType', '')}</td>
                <td style="padding:6px;border:1px solid #ddd;">${b['current_bid']}</td>
                <td style="padding:6px;border:1px solid #ddd;color:{color};font-weight:bold;">${b['new_bid']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{b.get('acos_pct') or '-'}%</td>
                <td style="padding:6px;border:1px solid #ddd;font-size:11px;">{b['reason']}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#fd7e14;margin-top:25px;">Keyword Bid Adjustments ({len(bid_adj)})</h3>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#fd7e14;color:white;">
                <th style="padding:8px;">Keyword</th>
                <th style="padding:8px;">Match</th>
                <th style="padding:8px;">Current Bid</th>
                <th style="padding:8px;">New Bid</th>
                <th style="padding:8px;">ACOS</th>
                <th style="padding:8px;">Reason</th>
            </tr>{rows}
        </table>""")

    return "\n".join(sections)


def send_proposal_email(proposals: List[Dict], to: str = DEFAULT_TO,
                        kw_proposals: Optional[List[Dict]] = None,
                        cc: str = DEFAULT_CC) -> Optional[str]:
    """Send proposal HTML email via send_gmail.py. Returns Gmail message ID or None."""
    html = build_proposal_html(proposals, kw_proposals)
    html_path = TMP_DIR / f"ppc_proposal_{date.today().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.html"
    html_path.write_text(html, encoding="utf-8")

    urgent_count = sum(1 for p in proposals if p["priority"] == "urgent")
    kw_count = len(kw_proposals) if kw_proposals else 0
    subject = (
        f"[Amazon PPC] {TARGET_BRAND} Proposal - {len(proposals)} campaign, "
        f"{kw_count} keyword changes"
        f" ({urgent_count} urgent) | {datetime.now().strftime('%m/%d %H:%M')}"
    )

    send_gmail_path = TOOLS_DIR / "send_gmail.py"
    if not send_gmail_path.exists():
        print(f"[WARN] {send_gmail_path} not found, email not sent. HTML saved: {html_path}")
        return None

    cmd = [sys.executable, str(send_gmail_path),
           "--to", to,
           "--subject", subject,
           "--body-file", str(html_path)]
    if cc:
        cmd += ["--cc", cc]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        print(f"[Email] Proposal sent to {to} (cc: {cc or 'none'})")
        # Parse Gmail message ID from stdout (line: "  Message ID: <id>")
        import re
        match = re.search(r"Message ID:\s*(\S+)", result.stdout)
        if match:
            msg_id = match.group(1)
            _save_proposal_email_id(msg_id, subject)
            return msg_id
    else:
        print(f"[ERROR] Email failed: {result.stderr}")
        print(f"[INFO] HTML saved at: {html_path}")
    return None


def _save_proposal_email_id(message_id: str, subject: str):
    """Save the proposal email message ID to the latest proposal JSON."""
    proposal_path = sorted(TMP_DIR.glob("ppc_proposal_*.json"), reverse=True)
    if not proposal_path:
        return
    filepath = proposal_path[0]
    data = json.loads(filepath.read_text(encoding="utf-8"))
    data["email_message_id"] = message_id
    data["email_subject"] = subject
    data["email_sent_at"] = datetime.now().isoformat()
    data["executed"] = False
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[INFO] Saved email message ID to {filepath.name}")


def send_execution_email(executed: List[Dict], to: str = DEFAULT_TO,
                         cc: str = DEFAULT_CC):
    """Send execution confirmation email."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    td = 'style="padding:6px 10px;border:1px solid #ddd;"'
    th = 'style="padding:8px 10px;text-align:left;"'

    # Separate campaign-level vs keyword-level
    campaign_rows = [c for c in executed if not c.get("keyword")]
    keyword_rows = [c for c in executed if c.get("keyword")]

    # --- Campaign-level table ---
    camp_html = ""
    if campaign_rows:
        camp_rows = ""
        for ch in campaign_rows:
            sc = "#28a745" if ch["result_status"] == "OK" else "#dc3545"
            bid_str = f'{ch["bid_change_pct"]:+d}%' if ch.get("bid_change_pct") else "-"
            budget_str = f'${ch["new_budget"]}' if ch.get("new_budget") else "-"
            camp_rows += f"""
            <tr>
                <td {td}>{ch['campaignName']}</td>
                <td {td}>{ch['action']}</td>
                <td {td}>{bid_str}</td>
                <td {td}>{budget_str}</td>
                <td {td} style="padding:6px 10px;border:1px solid #ddd;color:{sc};font-weight:bold;">{ch['result_status']}</td>
            </tr>"""
        camp_html = f"""
        <h3 style="margin-top:20px;">Campaign Changes ({len(campaign_rows)})</h3>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#343a40;color:white;">
                <th {th}>Campaign</th><th {th}>Action</th>
                <th {th}>Bid Change</th><th {th}>New Budget</th><th {th}>Status</th>
            </tr>
            {camp_rows}
        </table>"""

    # --- Keyword-level table ---
    kw_html = ""
    if keyword_rows:
        harvest = [k for k in keyword_rows if k["action"] == "harvest"]
        negates = [k for k in keyword_rows if k["action"].startswith("negate")]
        bid_changes = [k for k in keyword_rows if k["action"] == "keyword_bid"]

        sections = []
        if harvest:
            rows = ""
            for k in harvest:
                sc = "#28a745" if k["result_status"] == "OK" else "#dc3545"
                rows += f"""
                <tr>
                    <td {td}><b>{k['keyword']}</b></td>
                    <td {td}>{k.get('campaignName') or '-'}</td>
                    <td {td}>${k.get('new_bid', '-')}</td>
                    <td {td} style="padding:6px 10px;border:1px solid #ddd;color:{sc};font-weight:bold;">{k['result_status']}</td>
                </tr>"""
            sections.append(f"""
            <h3 style="margin-top:20px;color:#007bff;">Keyword Harvest ({len(harvest)})</h3>
            <p style="color:#666;font-size:13px;">Search terms promoted to Exact Match + negated in source</p>
            <table style="border-collapse:collapse;width:100%;">
                <tr style="background:#343a40;color:white;">
                    <th {th}>Keyword</th><th {th}>Source Campaign</th>
                    <th {th}>Bid</th><th {th}>Status</th>
                </tr>
                {rows}
            </table>""")

        if negates:
            rows = ""
            for k in negates:
                sc = "#28a745" if k["result_status"] == "OK" else "#dc3545"
                reason = k.get("action", "").replace("_", " ")
                spend = f'${k["spend_7d"]:.2f}' if k.get("spend_7d") is not None else "-"
                sales = f'${k["sales_7d"]:.2f}' if k.get("sales_7d") else "$0"
                rows += f"""
                <tr>
                    <td {td}><b>{k['keyword']}</b></td>
                    <td {td}>{k.get('campaignName') or '-'}</td>
                    <td {td}>{reason}</td>
                    <td {td}>{spend}</td>
                    <td {td}>{sales}</td>
                    <td {td} style="padding:6px 10px;border:1px solid #ddd;color:{sc};font-weight:bold;">{k['result_status']}</td>
                </tr>"""
            sections.append(f"""
            <h3 style="margin-top:20px;color:#dc3545;">Negative Keywords ({len(negates)})</h3>
            <p style="color:#666;font-size:13px;">Wasteful search terms blocked</p>
            <table style="border-collapse:collapse;width:100%;">
                <tr style="background:#343a40;color:white;">
                    <th {th}>Keyword</th><th {th}>Campaign</th>
                    <th {th}>Reason</th><th {th}>Spend</th><th {th}>Sales</th><th {th}>Status</th>
                </tr>
                {rows}
            </table>""")

        if bid_changes:
            rows = ""
            for k in bid_changes:
                sc = "#28a745" if k["result_status"] == "OK" else "#dc3545"
                old_bid = f'${k["old_bid"]}' if k.get("old_bid") else "-"
                new_bid = f'${k["new_bid"]}' if k.get("new_bid") else "PAUSED"
                rows += f"""
                <tr>
                    <td {td}><b>{k['keyword']}</b></td>
                    <td {td}>{k.get('campaignName') or '-'}</td>
                    <td {td}>{old_bid}</td>
                    <td {td}>{new_bid}</td>
                    <td {td} style="padding:6px 10px;border:1px solid #ddd;color:{sc};font-weight:bold;">{k['result_status']}</td>
                </tr>"""
            sections.append(f"""
            <h3 style="margin-top:20px;color:#fd7e14;">Keyword Bid Changes ({len(bid_changes)})</h3>
            <table style="border-collapse:collapse;width:100%;">
                <tr style="background:#343a40;color:white;">
                    <th {th}>Keyword</th><th {th}>Campaign</th>
                    <th {th}>Old Bid</th><th {th}>New Bid</th><th {th}>Status</th>
                </tr>
                {rows}
            </table>""")

        kw_html = "\n".join(sections)

    ok_count = sum(1 for c in executed if c["result_status"] == "OK")
    err_count = len(executed) - ok_count
    summary_color = "#28a745" if err_count == 0 else "#dc3545"
    summary_text = f"{ok_count} OK" + (f", {err_count} FAILED" if err_count else "")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:960px;margin:0 auto;padding:20px;">
    <h2 style="color:{summary_color};">Naeiae PPC Changes Executed</h2>
    <p>{now} | {len(executed)} changes applied ({summary_text})</p>
    {camp_html}
    {kw_html}
    <p style="color:#999;font-size:12px;margin-top:24px;">Logged to Google Sheets PPC Change Log</p>
</body></html>"""

    html_path = TMP_DIR / f"ppc_executed_{date.today().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.html"
    html_path.write_text(html, encoding="utf-8")

    subject = f"[Amazon PPC] EXECUTED - {len(executed)} changes applied | {now}"
    send_gmail_path = TOOLS_DIR / "send_gmail.py"
    if not send_gmail_path.exists():
        return

    cmd = [sys.executable, str(send_gmail_path),
           "--to", to, "--subject", subject, "--body-file", str(html_path)]
    if cc:
        cmd += ["--cc", cc]

    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print(f"[Email] Execution confirmation sent to {to} (cc: {cc or 'none'})")


# ===========================================================================
# 6-Hour Cycle
# ===========================================================================

CYCLE_INTERVAL_HOURS = 6

def run_cycle(args):
    """Run analysis every 6 hours, email proposals each time."""
    print(f"[Cycle] Starting 6-hour analysis cycle for {TARGET_BRAND}")
    print(f"  Budget: ${TOTAL_DAILY_BUDGET_USD}/day | Interval: {CYCLE_INTERVAL_HOURS}h")
    print(f"  Emails to: {args.to}")

    cycle = 0
    while True:
        cycle += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"\n{'='*50}")
        print(f"[Cycle {cycle}] {now}")
        print(f"{'='*50}")

        try:
            run_propose(args)
        except Exception as e:
            print(f"[ERROR] Cycle {cycle} failed: {e}")

        next_run = datetime.now() + timedelta(hours=CYCLE_INTERVAL_HOURS)
        print(f"\n[Next] {next_run.strftime('%Y-%m-%d %H:%M')}")
        time.sleep(CYCLE_INTERVAL_HOURS * 3600)


# ===========================================================================
# Email Reply Auto-Execute
# ===========================================================================

EXECUTE_KEYWORDS = {"execute", "approve", "go", "yes", "run"}


def check_email_and_execute(args):
    """Poll Gmail for 'execute' reply to the latest proposal email, then auto-execute."""
    data = load_latest_proposal()
    if not data:
        print("[check-execute] No proposal found.")
        return

    # Already executed?
    if data.get("executed"):
        print("[check-execute] Latest proposal already executed. Skipping.")
        return

    # No email tracking info?
    sent_at = data.get("email_sent_at")
    if not sent_at:
        print("[check-execute] Proposal has no email_sent_at. Was it emailed? Skipping.")
        return

    # Import search function from send_gmail
    sys.path.insert(0, str(TOOLS_DIR))
    from send_gmail import search_emails

    # --- Dedup: proposal.executed flag is primary gate (checked above at line 1922) ---
    # Gmail fallback: only check for EXECUTED emails sent on proposal date or later
    # AND verify the email timestamp is actually after this proposal was sent
    proposal_time = datetime.fromisoformat(sent_at)
    proposal_date = sent_at[:10]  # e.g. "2026-03-12"
    dedup_query = (
        f'subject:"[Amazon PPC] EXECUTED" from:orbiters11@gmail.com after:{proposal_date}'
    )
    print(f"[check-execute] Dedup check (Gmail fallback): {dedup_query}")
    existing_exec_emails = search_emails(dedup_query, max_results=5)
    if existing_exec_emails:
        # Verify at least one EXECUTED email was actually sent AFTER this proposal
        for ex_email in existing_exec_emails:
            try:
                from email.utils import parsedate_to_datetime
                ex_date = parsedate_to_datetime(ex_email.get("date", ""))
                if ex_date.tzinfo is None:
                    ex_date = ex_date.replace(tzinfo=timezone.utc)
                prop_aware = proposal_time if proposal_time.tzinfo else proposal_time.replace(tzinfo=timezone.utc)
                if ex_date > prop_aware:
                    print(f"[check-execute] Found EXECUTED email at {ex_email['date']} (after proposal at {sent_at}). Skipping.")
                    return
            except Exception:
                continue
        print(f"[check-execute] EXECUTED emails found but all predate this proposal. Proceeding.")

    # Search for replies to PPC proposal emails from the approver
    approver = args.to  # The person who receives proposals
    query = (
        f'subject:"[Amazon PPC]" from:{approver} newer_than:2d'
    )
    print(f"[check-execute] Searching Gmail: {query}")
    messages = search_emails(query, max_results=10)

    if not messages:
        print("[check-execute] No reply emails found.")
        return

    # Check if any reply contains an execute keyword
    # Only consider replies sent AFTER the proposal was emailed
    found_execute = False

    for msg in messages:
        # Parse reply date and skip if before proposal was sent
        msg_date_str = msg.get("date", "")
        try:
            from email.utils import parsedate_to_datetime
            msg_date = parsedate_to_datetime(msg_date_str)
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            prop_time_aware = proposal_time if proposal_time.tzinfo else proposal_time.replace(tzinfo=timezone.utc)
            if msg_date < prop_time_aware:
                continue  # Reply is older than proposal — ignore
        except Exception:
            pass  # If date parsing fails, still check content

        body_lower = (msg.get("body", "") + " " + msg.get("snippet", "")).lower().strip()
        # Check for execute keywords (look for the keyword as a standalone word)
        for kw in EXECUTE_KEYWORDS:
            if kw in body_lower.split() or body_lower.startswith(kw):
                print(f"[check-execute] Found '{kw}' in reply from {msg['from']}")
                print(f"  Subject: {msg['subject']}")
                print(f"  Date: {msg['date']}")
                found_execute = True
                break
        if found_execute:
            break

    if not found_execute:
        print("[check-execute] No 'execute' reply detected (after proposal sent at {}).".format(sent_at))
        return

    # Approve all proposals and execute
    print(f"\n[check-execute] Approving all proposals...")
    proposals = data.get("proposals", [])
    kw_proposals = data.get("keyword_proposals", [])
    for p in proposals:
        p["approved"] = True
    for kp in kw_proposals:
        kp["approved"] = True

    # Save approved state
    latest_path = sorted(TMP_DIR.glob("ppc_proposal_*.json"), reverse=True)[0]
    data["proposals"] = proposals
    data["keyword_proposals"] = kw_proposals
    latest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Execute
    executed = execute_approved(data)
    if executed:
        # Mark as executed
        data["executed"] = True
        data["executed_at"] = datetime.now().isoformat()
        latest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        log_to_sheets(executed)
        send_execution_email(executed, args.to, cc=args.cc)
        print(f"\n[check-execute] {len(executed)} changes auto-executed via email reply!")
    else:
        print("[check-execute] No approved items to execute.")


# ===========================================================================
# Main
# ===========================================================================

def run_propose(args):
    """Core propose logic, used by both --propose and --cycle."""
    print(f"[1/6] Finding Fleeters Inc profile...")
    profile = get_fleeters_profile()
    if not profile:
        print("[ERROR] Fleeters Inc profile not found!")
        return
    profile_id = profile["profile_id"]
    print(f"  Found: profile_id={profile_id}")

    print(f"\n[2/6] Collecting {args.days}d campaign data...")
    campaigns = fetch_campaigns(profile_id)
    print(f"  {len(campaigns)} campaigns found")

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=args.days - 1)
    report_rows = fetch_sp_report(profile_id, start_date, end_date)
    print(f"  {len(report_rows)} daily metric rows collected")

    print(f"\n[3/6] Analyzing campaigns (ROAS framework)...")
    proposals = analyze_campaigns(campaigns, report_rows)

    # --- NEW: Search Term & Keyword Analysis ---
    kw_proposals = []

    if not args.skip_keywords:
        st_start = end_date - timedelta(days=13)  # 14-day window for attribution
        print(f"\n[4/6] Fetching search term report ({st_start} ~ {end_date})...")
        try:
            st_rows = fetch_search_term_report(profile_id, st_start, end_date)
            print(f"  {len(st_rows)} search term rows")

            kw_rows = fetch_keyword_report(profile_id, st_start, end_date)
            print(f"  {len(kw_rows)} keyword rows")

            print(f"\n[5/6] Analyzing search terms & keywords...")
            st_analysis = analyze_search_terms(st_rows, campaigns, kw_rows)
            kw_bid_proposals = analyze_keyword_bids(kw_rows, campaigns)

            kw_proposals = st_analysis["harvest"] + st_analysis["negate"] + kw_bid_proposals
            print(f"  {len(st_analysis['harvest'])} harvest candidates")
            print(f"  {len(st_analysis['negate'])} negative candidates")
            print(f"  {len(kw_bid_proposals)} keyword bid adjustments")
        except Exception as e:
            print(f"  [WARN] Search term/keyword analysis failed: {e}")
            print(f"  Continuing with campaign-level proposals only.")
    else:
        print(f"\n[4/6] Skipping keyword analysis (--skip-keywords)")
        print(f"[5/6] Skipped")

    if not proposals and not kw_proposals:
        print("\n[OK] All campaigns within normal range. No changes needed.")
        return

    filepath = save_proposal(proposals, profile_id, kw_proposals)
    print_proposal_summary(proposals)
    if kw_proposals:
        print_keyword_summary(kw_proposals)

    print(f"\n[6/6] Sending proposal email...")
    send_proposal_email(proposals, args.to, kw_proposals, cc=args.cc)


def main():
    parser = argparse.ArgumentParser(description="Amazon PPC Executor (Fleeters Inc / Naeiae)")
    parser.add_argument("--propose", action="store_true", help="Analyze & email change proposals")
    parser.add_argument("--execute", action="store_true", help="Execute approved changes from latest proposal")
    parser.add_argument("--check-execute", action="store_true", help="Poll Gmail for 'execute' reply and auto-execute")
    parser.add_argument("--status", action="store_true", help="Show latest proposal status")
    parser.add_argument("--cycle", action="store_true", help="Run 6-hour analysis cycle")
    parser.add_argument("--days", type=int, default=30, help="Days of data to analyze (default: 30)")
    parser.add_argument("--to", type=str, default=DEFAULT_TO, help="Email recipient")
    parser.add_argument("--cc", type=str, default=DEFAULT_CC, help="CC email recipient")
    parser.add_argument("--skip-keywords", action="store_true",
                        help="Skip search term & keyword analysis (faster, campaign-level only)")
    args = parser.parse_args()

    if args.status:
        data = load_latest_proposal()
        if not data:
            print("[INFO] No proposals found in .tmp/")
            return
        proposals = data["proposals"]
        approved_count = sum(1 for p in proposals if p.get("approved"))
        print(f"Latest proposal: {data['generated_at']}")
        print(f"Brand: {data['brand']} ({data['seller']})")
        print(f"Total: {len(proposals)} proposals, {approved_count} approved")
        for p in proposals:
            status = "[APPROVED]" if p.get("approved") else "[pending]"
            print(f"  {status} {p['proposed_action']:>16} | [{p.get('campaignType','?')}] {p['campaignName']} | 7d ROAS {p['metrics']['7d']['roas']}x")
        return

    if args.execute:
        data = load_latest_proposal()
        if not data:
            print("[ERROR] No proposal found. Run --propose first.")
            return
        executed = execute_approved(data)
        if executed:
            # Mark proposal as executed to prevent re-execution by --check-execute
            latest_path = sorted(TMP_DIR.glob("ppc_proposal_*.json"), reverse=True)
            if latest_path:
                data["executed"] = True
                data["executed_at"] = datetime.now().isoformat()
                latest_path[0].write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            log_to_sheets(executed)
            send_execution_email(executed, args.to, cc=args.cc)
            print(f"\n[DONE] {len(executed)} changes executed, logged, and emailed.")
        return

    if args.check_execute:
        check_email_and_execute(args)
        return

    if args.cycle:
        run_cycle(args)
        return

    if args.propose:
        run_propose(args)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
