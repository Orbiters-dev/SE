"""
amazon_ppc_executor.py - Amazon PPC Campaign Executor (Multi-Brand, Approval-Based)

Analyzes all 3 US seller profiles (Naeiae, Grosmimi, CHA&MOM), proposes changes,
and emails a separate proposal per brand for review. Executes only approved actions.

Usage:
    python tools/amazon_ppc_executor.py --propose                        # All 3 brands
    python tools/amazon_ppc_executor.py --propose --brand naeiae         # Single brand
    python tools/amazon_ppc_executor.py --propose --brand grosmimi
    python tools/amazon_ppc_executor.py --propose --brand chaenmom
    python tools/amazon_ppc_executor.py --execute --brand naeiae         # Execute approved
    python tools/amazon_ppc_executor.py --status                         # Show pending
    python tools/amazon_ppc_executor.py --cycle                          # 6-hour cycle
    python tools/amazon_ppc_executor.py --propose --to wj.choi@orbiters.co.kr

Flow:
    1. --propose: Collect data -> Analyze -> Email proposal (per brand)
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

# ===========================================================================
# Multi-Brand Configuration
# ===========================================================================

BRAND_CONFIGS = {
    "naeiae": {
        "seller_name": "Fleeters Inc",
        "brand_display": "Naeiae",
        "total_daily_budget": 120.0,
        "max_single_campaign_budget": 50.0,
        "max_bid": 3.0,
        "targeting": {
            "MANUAL": {"target_acos": 25.0, "min_roas": 2.5, "budget_share": 0.60},
            "AUTO":   {"target_acos": 35.0, "min_roas": 1.5, "budget_share": 0.40},
        },
    },
    "grosmimi": {
        "seller_name": "GROSMIMI USA",
        "brand_display": "Grosmimi",
        "total_daily_budget": 3000.0,        # High-volume brand
        "max_single_campaign_budget": 500.0,  # Scale with budget
        "max_bid": 5.0,                       # Higher ceiling for competitive keywords
        "targeting": {
            "MANUAL": {"target_acos": 20.0, "min_roas": 3.0, "budget_share": 0.60},
            "AUTO":   {"target_acos": 30.0, "min_roas": 2.0, "budget_share": 0.40},
        },
    },
    "chaenmom": {
        "seller_name": "Orbitool",
        "brand_display": "CHA&MOM",
        "total_daily_budget": 150.0,          # Spend target $150/day
        "max_single_campaign_budget": 60.0,
        "max_bid": 3.0,
        "targeting": {
            "MANUAL": {"target_acos": 30.0, "min_roas": 2.0, "budget_share": 0.60},
            "AUTO":   {"target_acos": 40.0, "min_roas": 1.5, "budget_share": 0.40},
        },
    },
}

ALL_BRAND_KEYS = list(BRAND_CONFIGS.keys())

# --- Backward compat: default brand context (set per-iteration) ---
_active_brand_key = "naeiae"

def _cfg():
    """Get active brand config."""
    return BRAND_CONFIGS[_active_brand_key]

# --- ROAS Decision Framework (shared across brands) ---
ROAS_RULES = [
    # (min_roas, max_roas, action, bid_change_pct, budget_change_pct, priority)
    (None, 1.0,  "pause",           None, None, "urgent"),
    (1.0,  1.5,  "reduce_bid",      -30,  None, "urgent"),
    (1.5,  2.0,  "reduce_bid",      -15,  None, "high"),
    (2.0,  2.5,  "optimize",        -10,  None, "medium"),    # Not just monitor -- fine-tune bids
    (2.5,  3.0,  "optimize",        None, None, "medium"),    # Close to target, optimize keywords
    (3.0,  5.0,  "increase_budget", None, +20,  "medium"),
    (5.0,  None, "increase_budget", +10,  +30,  "high"),
]

# --- Safety caps (per-brand overridable via BRAND_CONFIGS) ---
TOTAL_DAILY_BUDGET_USD = 120.0   # Default, overridden by _cfg()
MAX_SINGLE_CAMPAIGN_BUDGET = 50.0
MAX_BID_USD = 3.0

# --- Manual vs Auto optimization targets (default, overridden by _cfg()) ---
TARGETING_CONFIG = {
    "MANUAL": {
        "target_acos": 25.0,
        "min_roas": 2.5,
        "budget_share": 0.60,
        "description": "Manual campaigns - exact/phrase keywords, tighter control",
    },
    "AUTO": {
        "target_acos": 35.0,
        "min_roas": 1.5,
        "budget_share": 0.40,
        "description": "Auto campaigns - keyword discovery, broader reach",
    },
}

def _apply_brand_config(brand_key: str):
    """Set active brand and update module-level config vars."""
    global _active_brand_key, TOTAL_DAILY_BUDGET_USD, MAX_SINGLE_CAMPAIGN_BUDGET, MAX_BID_USD, TARGETING_CONFIG
    _active_brand_key = brand_key
    cfg = BRAND_CONFIGS[brand_key]
    TOTAL_DAILY_BUDGET_USD = cfg["total_daily_budget"]
    MAX_SINGLE_CAMPAIGN_BUDGET = cfg["max_single_campaign_budget"]
    MAX_BID_USD = cfg["max_bid"]
    TARGETING_CONFIG["MANUAL"]["target_acos"] = cfg["targeting"]["MANUAL"]["target_acos"]
    TARGETING_CONFIG["MANUAL"]["min_roas"] = cfg["targeting"]["MANUAL"]["min_roas"]
    TARGETING_CONFIG["MANUAL"]["budget_share"] = cfg["targeting"]["MANUAL"]["budget_share"]
    TARGETING_CONFIG["AUTO"]["target_acos"] = cfg["targeting"]["AUTO"]["target_acos"]
    TARGETING_CONFIG["AUTO"]["min_roas"] = cfg["targeting"]["AUTO"]["min_roas"]
    TARGETING_CONFIG["AUTO"]["budget_share"] = cfg["targeting"]["AUTO"]["budget_share"]

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
# Data Collection (Multi-Brand)
# ===========================================================================

def get_all_us_profiles() -> Dict[str, Dict]:
    """Fetch all US seller profiles and map to brand keys."""
    resp = requests.get(
        f"{API_BASE}/v2/profiles",
        headers={
            "Authorization": f"Bearer {TM.get()}",
            "Amazon-Advertising-API-ClientId": AD_CLIENT_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()

    # Build reverse map: seller_name -> brand_key
    seller_to_brand = {}
    for key, cfg in BRAND_CONFIGS.items():
        seller_to_brand[cfg["seller_name"]] = key

    profiles = {}
    for p in resp.json():
        if (p.get("countryCode") == "US"
            and p.get("accountInfo", {}).get("type") == "seller"):
            seller_name = p.get("accountInfo", {}).get("name", "")
            brand_key = seller_to_brand.get(seller_name)
            if brand_key:
                profiles[brand_key] = {
                    "profile_id": p["profileId"],
                    "seller": seller_name,
                    "brand_key": brand_key,
                    "brand_display": BRAND_CONFIGS[brand_key]["brand_display"],
                }
    return profiles


def get_brand_profile(brand_key: str) -> Optional[Dict]:
    """Get a single brand's profile."""
    profiles = get_all_us_profiles()
    return profiles.get(brand_key)


def get_fleeters_profile() -> Optional[Dict]:
    """Backward compat: get Naeiae profile."""
    return get_brand_profile("naeiae")


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
                "stateFilter": {"include": ["ENABLED"]},
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


def fetch_report_from_datakeeper(brand_key: str, days: int) -> List[Dict]:
    """Fetch campaign metrics from DataKeeper (proven reliable source).

    Returns rows in the same format as fetch_sp_report() for compatibility
    with analyze_campaigns().
    """
    try:
        from data_keeper_client import DataKeeper
    except ImportError:
        print("  [WARN] DataKeeper client not available, falling back to API")
        return []

    dk = DataKeeper()
    brand_display = BRAND_CONFIGS[brand_key]["brand_display"]
    rows = dk.get("amazon_ads_daily", days=days)
    if not rows:
        print(f"  [WARN] DataKeeper returned no amazon_ads_daily data")
        return []

    # Filter by brand and convert field names to match analyze_campaigns expectations
    out = []
    for r in rows:
        if r.get("brand", "") != brand_display:
            continue
        out.append({
            "date": r.get("date", ""),
            "campaignId": r.get("campaign_id", ""),
            "campaignName": r.get("campaign_name", r.get("campaign_id", "")),
            "cost": float(r.get("spend", 0) or 0),
            "sales14d": float(r.get("sales", 0) or 0),
            "purchases14d": int(r.get("purchases", 0) or 0),
            "clicks": int(r.get("clicks", 0) or 0),
            "impressions": int(r.get("impressions", 0) or 0),
        })

    dates = sorted(set(r["date"] for r in out)) if out else []
    campaigns_n = len(set(r["campaignId"] for r in out))
    print(f"  DataKeeper -> {len(out)} rows for {brand_display} | {campaigns_n} campaigns")
    if dates:
        print(f"  Period: {dates[0]} ~ {dates[-1]}")
    return out


def fetch_sp_report(profile_id: int, start: date, end: date) -> List[Dict]:
    """Fetch SP campaign daily metrics for date range (direct API, used as fallback)."""
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
    dataforseo: Optional[Dict[str, Dict]] = None,
) -> List[Dict]:
    """Apply preset-based bid adjustment logic per keyword.

    When dataforseo data is available, uses Google CPC as a market benchmark:
    - If Amazon CPC > Google CPC * 1.5: overbidding, recommend -15% (cap)
    - If Amazon CPC < Google CPC * 0.5 and ROAS > 2: underbidding, recommend +20%
    - Adjusts bid ceiling based on Google CPC (max bid = Google CPC * 2.0)
    """
    camp_map = {}
    for c in campaigns:
        try:
            camp_map[int(c["campaignId"])] = c
        except (ValueError, TypeError):
            camp_map[c["campaignId"]] = c
    proposals = []
    dataforseo = dataforseo or {}

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
        roas = (sales / cost) if cost > 0 else 0
        amz_cpc = (cost / clicks) if clicks > 0 else 0
        action = None
        new_bid = current_bid
        reason = ""

        # --- DataForSEO Google CPC benchmark adjustment ---
        google_cpc = 0
        gdata = dataforseo.get(kw_text.lower().strip())
        if gdata:
            google_cpc = float(gdata.get("cpc", 0) or 0)

        # Case 1: Strong performer
        if acos is not None and acos < p["mid_acos"] and clicks >= p["click_limit"] and sales > 0:
            new_bid = round(current_bid * (1 + p["increase_by"]), 2)
            # If Google CPC is available and we're underbidding, be more aggressive
            if google_cpc > 0 and amz_cpc < google_cpc * 0.5 and roas > 2.0:
                bump = min(p["increase_by"] + 0.10, 0.30)  # Extra 10% bump, max 30%
                new_bid = round(current_bid * (1 + bump), 2)
                reason = f"ACOS {acos*100:.1f}% (strong) + underbidding vs Google CPC ${google_cpc:.2f}, +{bump*100:.0f}%"
            else:
                reason = f"ACOS {acos*100:.1f}% < {p['mid_acos']*100}% (strong), +{p['increase_by']*100:.0f}%"
            new_bid = min(new_bid, p["max_bid"])

        # Case 2: Inefficient
        elif acos is not None and acos > p["high_acos"] and clicks >= p["click_limit"]:
            new_bid = round(current_bid * (1 - p["decrease_by"]), 2)
            # If Google CPC confirms overbidding, be more aggressive on reduction
            if google_cpc > 0 and amz_cpc > google_cpc * 1.5:
                cut = min(p["decrease_by"] + 0.10, 0.35)  # Extra 10% cut, max 35%
                new_bid = round(current_bid * (1 - cut), 2)
                reason = f"ACOS {acos*100:.1f}% (high) + overbidding vs Google CPC ${google_cpc:.2f} by {amz_cpc/google_cpc:.1f}x, -{cut*100:.0f}%"
            else:
                reason = f"ACOS {acos*100:.1f}% > {p['high_acos']*100}% (high), -{p['decrease_by']*100:.0f}%"
            new_bid = max(new_bid, p["min_bid"])

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

        # Case 6 (NEW): Google CPC overbidding check (even if ACOS is OK)
        # If Amazon CPC > Google CPC * 1.5 and enough data, recommend reduction
        elif google_cpc > 0 and amz_cpc > google_cpc * 1.5 and clicks >= 5 and roas < 3.0:
            cut_pct = 0.15
            new_bid = round(current_bid * (1 - cut_pct), 2)
            new_bid = max(new_bid, p["min_bid"])
            action = "decrease_bid"
            reason = f"Overbidding: AMZ CPC ${amz_cpc:.2f} vs Google ${google_cpc:.2f} ({amz_cpc/google_cpc:.1f}x), ROAS {roas:.1f}x, -15%"

        if not action and new_bid != current_bid:
            action = "increase_bid" if new_bid > current_bid else "decrease_bid"

        if action and new_bid != current_bid:
            # Append Google CPC context to reason if available and not already mentioned
            if google_cpc > 0 and "Google" not in reason:
                reason += f" | Google CPC: ${google_cpc:.2f}"

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
                "google_cpc": google_cpc if google_cpc > 0 else None,
                "priority": "high" if action == "decrease_bid" and sales == 0 else "medium",
                "reason": reason,
                "approved": False,
            })

    # Sort: decreases first (stop bleeding), then increases
    proposals.sort(key=lambda x: (0 if "decrease" in x["action"] else 1, -x["cost"]))
    return proposals[:MAX_KEYWORD_CHANGES_PER_CYCLE]


def fetch_dataforseo_keywords(brand_key: str) -> Dict[str, Dict]:
    """Fetch DataForSEO/Google Ads keyword data for bid benchmarking.

    Returns dict keyed by lowercase keyword text:
      {"korean snacks": {"search_volume": 22200, "cpc": 1.28, "competition": 4, ...}}
    """
    try:
        from data_keeper_client import DataKeeper
        dk = DataKeeper()
        brand_display = BRAND_CONFIGS[brand_key]["brand_display"]
        rows = dk.get("dataforseo_keywords", days=30)
        if not rows:
            return {}
        out = {}
        for r in rows:
            if r.get("brand", "") != brand_display:
                continue
            kw = r.get("keyword", "").lower().strip()
            if kw:
                out[kw] = {
                    "search_volume": int(r.get("search_volume", 0) or 0),
                    "cpc": float(r.get("cpc", 0) or 0),
                    "competition": r.get("competition", ""),
                    "competition_index": int(r.get("competition_index", 0) or 0),
                }
        print(f"  DataForSEO: {len(out)} keywords for {brand_display}")
        return out
    except Exception as e:
        print(f"  [WARN] DataForSEO fetch failed: {e}")
        return {}


def _agg_keyword_rows(kw_rows: List[Dict], camp_map: Dict) -> Dict:
    """Aggregate keyword report rows by keywordId."""
    kw_agg = {}
    for kw in kw_rows:
        kid = kw.get("keywordId", "")
        kw_text = kw.get("keywordText", "").strip()
        if not kw_text:
            continue
        if kid not in kw_agg:
            kw_agg[kid] = {
                "keywordId": kid, "keywordText": kw_text,
                "matchType": kw.get("matchType", ""),
                "campaignId": str(kw.get("campaignId", "")),
                "adGroupId": str(kw.get("adGroupId", "")),
                "clicks": 0, "impressions": 0, "cost": 0.0, "sales": 0.0, "purchases": 0,
            }
        a = kw_agg[kid]
        a["clicks"] += int(kw.get("clicks", 0) or 0)
        a["impressions"] += int(kw.get("impressions", 0) or 0)
        a["cost"] += float(kw.get("cost", 0) or 0)
        a["sales"] += float(kw.get("sales14d", 0) or 0)
        a["purchases"] += int(kw.get("purchases14d", 0) or 0)
    for k in kw_agg.values():
        k["roas"] = round(k["sales"] / k["cost"], 2) if k["cost"] > 0 else 0
        k["acos"] = round(k["cost"] / k["sales"] * 100, 1) if k["sales"] > 0 else None
        k["ctr"] = round(k["clicks"] / k["impressions"] * 100, 2) if k["impressions"] > 0 else 0
        k["cpc"] = round(k["cost"] / k["clicks"], 2) if k["clicks"] > 0 else 0
        k["cvr"] = round(k["purchases"] / k["clicks"] * 100, 1) if k["clicks"] > 0 else 0
        camp = camp_map.get(k["campaignId"], {})
        k["campaignName"] = camp.get("name", "")
    return kw_agg


def build_keyword_performance_matrix(
    kw_rows: List[Dict], st_rows: List[Dict], campaigns: List[Dict],
    dataforseo: Dict[str, Dict], kw_rows_7d: Optional[List[Dict]] = None
) -> Dict:
    """Build detailed keyword-level performance analysis with 7d vs 30d trends.

    Returns dict with: top_keywords, bottom_keywords, adgroup_breakdown,
    match_type_breakdown, keyword_vs_google, keyword_trends, cannibalization
    """
    camp_map = {}
    for c in campaigns:
        camp_map[str(c["campaignId"])] = c

    # 1. Aggregate 30d keyword metrics (primary)
    kw_agg = _agg_keyword_rows(kw_rows, camp_map)
    all_kws = sorted(kw_agg.values(), key=lambda x: x["cost"], reverse=True)

    # 1b. Aggregate 7d keyword metrics (for trend comparison)
    kw_trends = []
    if kw_rows_7d:
        kw_agg_7d = _agg_keyword_rows(kw_rows_7d, camp_map)
        # Compare 7d vs 30d for keywords with meaningful spend
        for kid, k30 in kw_agg.items():
            if k30["cost"] < 2:
                continue
            k7 = kw_agg_7d.get(kid, {"roas": 0, "acos": None, "cost": 0, "sales": 0, "cpc": 0})
            # 30d-exclusive period (days 8-30) for comparison
            cost_prev = k30["cost"] - k7.get("cost", 0)
            sales_prev = k30["sales"] - k7.get("sales", 0)
            roas_prev = round(sales_prev / cost_prev, 2) if cost_prev > 1 else 0
            roas_7d = k7.get("roas", 0)
            if roas_prev > 0 and roas_7d > 0:
                trend_pct = round((roas_7d - roas_prev) / roas_prev * 100, 1)
            elif roas_7d > 0 and roas_prev == 0:
                trend_pct = 100.0  # New performer
            elif roas_7d == 0 and roas_prev > 0:
                trend_pct = -100.0  # Stopped performing
            else:
                trend_pct = 0
            kw_trends.append({
                "keywordText": k30["keywordText"],
                "matchType": k30["matchType"],
                "roas_7d": roas_7d,
                "roas_prev": roas_prev,
                "acos_7d": k7.get("acos"),
                "acos_30d": k30["acos"],
                "trend_pct": trend_pct,
                "cost_7d": round(k7.get("cost", 0), 2),
                "cost_30d": round(k30["cost"], 2),
                "direction": "up" if trend_pct > 10 else ("down" if trend_pct < -10 else "stable"),
            })
        kw_trends.sort(key=lambda x: abs(x["trend_pct"]), reverse=True)

    # 2. Top/Bottom keywords
    with_sales = [k for k in all_kws if k["sales"] > 0]
    top_kws = sorted(with_sales, key=lambda x: x["roas"], reverse=True)[:10]
    bottom_kws = sorted([k for k in all_kws if k["cost"] > 1], key=lambda x: (x["acos"] or 9999), reverse=True)[:10]

    # 3. Ad group breakdown
    ag_map = {}
    for k in all_kws:
        agid = k["adGroupId"]
        if agid not in ag_map:
            ag_map[agid] = {"adGroupId": agid, "keywords": 0, "clicks": 0, "cost": 0.0,
                            "sales": 0.0, "impressions": 0, "purchases": 0, "campaignName": k["campaignName"]}
        ag = ag_map[agid]
        ag["keywords"] += 1
        ag["clicks"] += k["clicks"]
        ag["cost"] += k["cost"]
        ag["sales"] += k["sales"]
        ag["impressions"] += k["impressions"]
        ag["purchases"] += k["purchases"]
    for ag in ag_map.values():
        ag["roas"] = round(ag["sales"] / ag["cost"], 2) if ag["cost"] > 0 else 0
        ag["acos"] = round(ag["cost"] / ag["sales"] * 100, 1) if ag["sales"] > 0 else None
        ag["cpc"] = round(ag["cost"] / ag["clicks"], 2) if ag["clicks"] > 0 else 0

    # 4. Match type breakdown
    mt_map = {}
    for k in all_kws:
        mt = k.get("matchType", "UNKNOWN")
        if mt not in mt_map:
            mt_map[mt] = {"matchType": mt, "keywords": 0, "clicks": 0, "cost": 0.0,
                          "sales": 0.0, "impressions": 0}
        m = mt_map[mt]
        m["keywords"] += 1
        m["clicks"] += k["clicks"]
        m["cost"] += k["cost"]
        m["sales"] += k["sales"]
        m["impressions"] += k["impressions"]
    for m in mt_map.values():
        m["roas"] = round(m["sales"] / m["cost"], 2) if m["cost"] > 0 else 0
        m["acos"] = round(m["cost"] / m["sales"] * 100, 1) if m["sales"] > 0 else None

    # 5. Amazon CPC vs Google CPC comparison
    amz_vs_google = []
    for k in all_kws:
        kw_lower = k["keywordText"].lower()
        gdata = dataforseo.get(kw_lower)
        if gdata and k["cpc"] > 0:
            amz_vs_google.append({
                "keyword": k["keywordText"],
                "amazon_cpc": k["cpc"],
                "google_cpc": gdata["cpc"],
                "search_volume": gdata["search_volume"],
                "cpc_gap": round(gdata["cpc"] - k["cpc"], 2) if gdata["cpc"] > 0 else None,
                "roas": k["roas"],
            })

    # 6. Cannibalization detection
    # Same keyword text appearing in multiple campaigns or ad groups
    cannibalization = []
    kw_by_text = defaultdict(list)
    for k in all_kws:
        kw_by_text[k["keywordText"].lower()].append(k)
    # Also check search terms hitting multiple campaigns
    st_by_query = defaultdict(list)
    for st in st_rows:
        q = st.get("searchTerm", st.get("query", "")).lower().strip()
        cid = str(st.get("campaignId", ""))
        if q and cid:
            st_by_query[q].append({
                "campaignId": cid,
                "campaignName": camp_map.get(cid, {}).get("name", cid[:20]),
                "cost": float(st.get("cost", 0) or 0),
                "sales": float(st.get("sales14d", 0) or 0),
            })

    # Keywords in multiple campaigns/ad groups
    for kw_text, entries in kw_by_text.items():
        if len(entries) < 2:
            continue
        unique_camps = set(e["campaignId"] for e in entries)
        unique_ags = set(e["adGroupId"] for e in entries)
        if len(unique_camps) > 1 or len(unique_ags) > 1:
            total_cost = sum(e["cost"] for e in entries)
            camp_names = [e["campaignName"][:30] or e["campaignId"][:15] for e in entries]
            cannibalization.append({
                "keyword": kw_text,
                "type": "keyword_overlap",
                "campaigns": list(unique_camps),
                "campaign_names": camp_names,
                "total_cost": round(total_cost, 2),
                "entries": len(entries),
                "detail": f"'{kw_text}' in {len(unique_camps)} campaigns: {', '.join(camp_names)}",
            })

    # Search terms hitting multiple campaigns
    for query, hits in st_by_query.items():
        unique_camps = set(h["campaignId"] for h in hits)
        if len(unique_camps) > 1:
            total_cost = sum(h["cost"] for h in hits)
            if total_cost < 2:
                continue
            camp_names = list(set(h["campaignName"] for h in hits))
            cannibalization.append({
                "keyword": query,
                "type": "search_term_overlap",
                "campaigns": list(unique_camps),
                "campaign_names": camp_names,
                "total_cost": round(total_cost, 2),
                "entries": len(hits),
                "detail": f"Search term '{query}' matched in {len(unique_camps)} campaigns (${total_cost:.0f} total)",
            })

    cannibalization.sort(key=lambda x: x["total_cost"], reverse=True)

    return {
        "top_keywords": top_kws,
        "bottom_keywords": bottom_kws,
        "adgroup_breakdown": sorted(ag_map.values(), key=lambda x: x["cost"], reverse=True),
        "match_type_breakdown": sorted(mt_map.values(), key=lambda x: x["cost"], reverse=True),
        "keyword_vs_google": amz_vs_google,
        "keyword_trends": kw_trends[:20],  # Top 20 by trend magnitude
        "cannibalization": cannibalization[:15],  # Top 15 by cost
        "total_keywords": len(all_kws),
    }


def _build_keyword_matrix_html(matrix: Optional[Dict]) -> str:
    """Build HTML for detailed keyword performance matrix."""
    if not matrix or matrix.get("total_keywords", 0) == 0:
        return ""

    sections = []

    # --- Ad Group Breakdown ---
    ag_rows = ""
    for ag in matrix.get("adgroup_breakdown", []):
        rcolor = "#28a745" if ag["roas"] >= 3.0 else ("#ffc107" if ag["roas"] >= 2.0 else "#dc3545")
        ag_rows += f"""<tr>
            <td style="padding:5px 8px;border:1px solid #eee;font-size:11px;">{ag['campaignName'][:40]}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:center;">{ag['keywords']}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${ag['cost']:.0f}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${ag['sales']:.0f}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;color:{rcolor};font-weight:bold;">{ag['roas']}x</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">{ag['acos'] or '-'}%</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${ag['cpc']:.2f}</td>
        </tr>"""
    sections.append(f"""
    <h3 style="color:#333;margin-top:25px;">Ad Group Performance</h3>
    <table style="border-collapse:collapse;width:100%;font-size:12px;">
        <tr style="background:#37474f;color:white;">
            <th style="padding:6px;">Campaign / Ad Group</th><th style="padding:6px;">KWs</th>
            <th style="padding:6px;">Spend</th><th style="padding:6px;">Sales</th>
            <th style="padding:6px;">ROAS</th><th style="padding:6px;">ACOS</th><th style="padding:6px;">CPC</th>
        </tr>{ag_rows}
    </table>""")

    # --- Match Type Breakdown ---
    mt_rows = ""
    for m in matrix.get("match_type_breakdown", []):
        mt_rows += f"""<tr>
            <td style="padding:5px 8px;border:1px solid #eee;">{m['matchType']}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:center;">{m['keywords']}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${m['cost']:.0f}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${m['sales']:.0f}</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;font-weight:bold;">{m['roas']}x</td>
            <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">{m['acos'] or '-'}%</td>
        </tr>"""
    sections.append(f"""
    <h3 style="color:#333;margin-top:20px;">Match Type Performance</h3>
    <table style="border-collapse:collapse;width:80%;font-size:12px;">
        <tr style="background:#546e7a;color:white;">
            <th style="padding:6px;">Match Type</th><th style="padding:6px;">KWs</th>
            <th style="padding:6px;">Spend</th><th style="padding:6px;">Sales</th>
            <th style="padding:6px;">ROAS</th><th style="padding:6px;">ACOS</th>
        </tr>{mt_rows}
    </table>""")

    # --- Top 10 Keywords by ROAS ---
    top_rows = ""
    for k in matrix.get("top_keywords", []):
        top_rows += f"""<tr>
            <td style="padding:4px 8px;border:1px solid #eee;font-size:11px;">{k['keywordText']}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:center;font-size:11px;">{k['matchType']}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">${k['cost']:.0f}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">${k['sales']:.0f}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;color:#28a745;font-weight:bold;">{k['roas']}x</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{k['acos'] or '-'}%</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{k['cvr']}%</td>
        </tr>"""
    sections.append(f"""
    <h3 style="color:#28a745;margin-top:20px;">Top 10 Keywords (by ROAS)</h3>
    <table style="border-collapse:collapse;width:100%;font-size:12px;">
        <tr style="background:#2e7d32;color:white;">
            <th style="padding:6px;">Keyword</th><th style="padding:6px;">Match</th>
            <th style="padding:6px;">Spend</th><th style="padding:6px;">Sales</th>
            <th style="padding:6px;">ROAS</th><th style="padding:6px;">ACOS</th><th style="padding:6px;">CVR</th>
        </tr>{top_rows}
    </table>""")

    # --- Bottom 10 Keywords (worst ACOS) ---
    bot_rows = ""
    for k in matrix.get("bottom_keywords", []):
        bot_rows += f"""<tr>
            <td style="padding:4px 8px;border:1px solid #eee;font-size:11px;">{k['keywordText']}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">${k['cost']:.0f}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">${k['sales']:.0f}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;color:#dc3545;font-weight:bold;">{k['acos'] or 'N/S'}{'%' if k['acos'] else ''}</td>
            <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{k['clicks']} / {k['impressions']}</td>
        </tr>"""
    sections.append(f"""
    <h3 style="color:#dc3545;margin-top:20px;">Bottom 10 Keywords (worst ACOS)</h3>
    <table style="border-collapse:collapse;width:100%;font-size:12px;">
        <tr style="background:#c62828;color:white;">
            <th style="padding:6px;">Keyword</th><th style="padding:6px;">Spend</th>
            <th style="padding:6px;">Sales</th><th style="padding:6px;">ACOS</th><th style="padding:6px;">Clicks/Impr</th>
        </tr>{bot_rows}
    </table>""")

    # --- Keyword Trends (7d vs Previous Period) ---
    trends = matrix.get("keyword_trends", [])
    if trends:
        trend_rows = ""
        for t in trends[:15]:
            if t["direction"] == "up":
                arrow = "^"
                tcolor = "#28a745"
            elif t["direction"] == "down":
                arrow = "v"
                tcolor = "#dc3545"
            else:
                arrow = "-"
                tcolor = "#999"
            trend_rows += f"""<tr>
                <td style="padding:4px 8px;border:1px solid #eee;font-size:11px;">{t['keywordText']}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:center;font-size:10px;">{t['matchType']}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{t['roas_7d']}x</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{t['roas_prev']}x</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;color:{tcolor};font-weight:bold;">{arrow} {t['trend_pct']:+.0f}%</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{t['acos_7d'] or '-'}%</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">${t['cost_7d']:.0f}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#6a1b9a;margin-top:20px;">Keyword Trends (7d vs Previous Period)</h3>
        <p style="color:#666;font-size:11px;">Compares last 7 days ROAS against days 8-30 ROAS to detect momentum shifts.</p>
        <table style="border-collapse:collapse;width:100%;font-size:12px;">
            <tr style="background:#6a1b9a;color:white;">
                <th style="padding:6px;">Keyword</th><th style="padding:6px;">Match</th>
                <th style="padding:6px;">ROAS 7d</th><th style="padding:6px;">ROAS prev</th>
                <th style="padding:6px;">Trend</th><th style="padding:6px;">ACOS 7d</th><th style="padding:6px;">Spend 7d</th>
            </tr>{trend_rows}
        </table>""")

    # --- Cannibalization Detection ---
    cannibal = matrix.get("cannibalization", [])
    if cannibal:
        can_rows = ""
        for c in cannibal[:10]:
            type_label = "KW Overlap" if c["type"] == "keyword_overlap" else "ST Overlap"
            type_bg = "#ff6f00" if c["type"] == "keyword_overlap" else "#e65100"
            can_rows += f"""<tr>
                <td style="padding:4px 8px;border:1px solid #eee;font-size:11px;">{c['keyword'][:40]}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:center;">
                    <span style="background:{type_bg};color:white;padding:1px 6px;border-radius:3px;font-size:10px;">{type_label}</span>
                </td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:center;">{len(c['campaigns'])}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;font-weight:bold;">${c['total_cost']:.0f}</td>
                <td style="padding:4px 8px;border:1px solid #eee;font-size:10px;">{', '.join(n[:25] for n in c['campaign_names'][:3])}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#e65100;margin-top:20px;">Cannibalization Alerts</h3>
        <p style="color:#666;font-size:11px;">Keywords or search terms competing across multiple campaigns, inflating CPCs.</p>
        <table style="border-collapse:collapse;width:100%;font-size:12px;">
            <tr style="background:#e65100;color:white;">
                <th style="padding:6px;">Keyword / Search Term</th><th style="padding:6px;">Type</th>
                <th style="padding:6px;">Camps</th><th style="padding:6px;">Total Cost</th><th style="padding:6px;">Campaigns</th>
            </tr>{can_rows}
        </table>""")

    # --- Amazon CPC vs Google CPC ---
    cpc_data = matrix.get("keyword_vs_google", [])
    if cpc_data:
        cpc_rows = ""
        for c in cpc_data:
            gap = c.get("cpc_gap")
            gap_str = f"${gap:+.2f}" if gap is not None else "-"
            gap_color = "#28a745" if gap and gap > 0 else "#dc3545"
            cpc_rows += f"""<tr>
                <td style="padding:4px 8px;border:1px solid #eee;font-size:11px;">{c['keyword']}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">${c['amazon_cpc']:.2f}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">${c['google_cpc']:.2f}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;color:{gap_color};">{gap_str}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{c['search_volume']:,}</td>
                <td style="padding:4px 8px;border:1px solid #eee;text-align:right;">{c['roas']}x</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#1565c0;margin-top:20px;">Amazon CPC vs Google CPC (DataForSEO)</h3>
        <p style="color:#666;font-size:11px;">Positive gap = room to increase Amazon bid. Negative = Amazon overbidding vs Google market.</p>
        <table style="border-collapse:collapse;width:100%;font-size:12px;">
            <tr style="background:#1565c0;color:white;">
                <th style="padding:6px;">Keyword</th><th style="padding:6px;">AMZ CPC</th>
                <th style="padding:6px;">Google CPC</th><th style="padding:6px;">Gap</th>
                <th style="padding:6px;">Monthly Vol</th><th style="padding:6px;">AMZ ROAS</th>
            </tr>{cpc_rows}
        </table>""")

    return "\n".join(sections)


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


def _confidence_tier(action: str, priority: str) -> str:
    """Map action+priority to confidence score (1-10) with label.

    Score system:
    10-9: No-Brainer (must-do, losing money or obvious win)
     8-7: Strong (high confidence, clear ROI signal)
     6-5: Optimize (actionable, needs fine-tuning)
     4-3: Moderate (worth considering, lower urgency)
     2-1: Monitor (watch but don't change yet)
    """
    if action == "pause" and priority == "urgent":
        return "10 No-Brainer"
    if action == "reduce_bid" and priority == "urgent":
        return "9 No-Brainer"
    if action == "reduce_bid" and priority == "high":
        return "8 Strong"
    if action == "increase_budget" and priority == "high":
        return "8 Strong"
    if priority == "urgent":
        return "9 No-Brainer"
    if action == "increase_budget" and priority == "medium":
        return "7 Strong"
    if action == "optimize" and priority == "medium":
        return "6 Optimize"
    if action == "optimize":
        return "5 Optimize"
    if priority == "medium":
        return "4 Moderate"
    if priority == "low" and action != "monitor":
        return "3 Moderate"
    return "1 Monitor"


def analyze_campaigns(campaigns: List[Dict], report_rows: List[Dict]) -> tuple:
    """Apply ROAS Decision Framework with manual/auto split.

    Returns (action_proposals, all_campaign_summary, anomalies).
    - action_proposals: campaigns needing changes (non-monitor)
    - all_campaign_summary: every enabled campaign with metrics (for overview table)
    - anomalies: list of detected anomaly strings
    """
    # Use actual latest date from data (not today-1) -- data may lag 1-2 days
    all_dates = set()
    for r in report_rows:
        try:
            all_dates.add(datetime.strptime(r.get("date", "")[:10], "%Y-%m-%d").date())
        except (ValueError, TypeError):
            pass

    if all_dates:
        latest_date = max(all_dates)
    else:
        latest_date = date.today() - timedelta(days=1)

    yesterday = latest_date  # "yesterday" = most recent full day with data
    d7_start = latest_date - timedelta(days=6)  # 7 days ending at latest_date
    d30_start = latest_date - timedelta(days=29)  # 30 days ending at latest_date

    print(f"  Data range: latest={latest_date}, 7d={d7_start}~{latest_date}, 30d={d30_start}~{latest_date}")

    # Aggregate by campaign for yd, 7d, 30d
    def agg(rows, from_d, to_d):
        bucket = defaultdict(lambda: {"cost": 0.0, "sales": 0.0, "clicks": 0, "impressions": 0, "purchases": 0})
        for r in rows:
            try:
                rd = datetime.strptime(r.get("date", "")[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            if from_d <= rd <= to_d:
                cid = str(r.get("campaignId", ""))
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
    all_campaigns = []
    anomalies = []

    # Totals for summary
    totals = {"yd": {"cost": 0, "sales": 0, "clicks": 0, "impressions": 0},
              "7d": {"cost": 0, "sales": 0, "clicks": 0, "impressions": 0, "purchases": 0},
              "30d": {"cost": 0, "sales": 0, "clicks": 0, "impressions": 0}}

    for camp in campaigns:
        cid = str(camp["campaignId"])
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
        acos_yd = round(cost_yd / sales_yd * 100, 1) if sales_yd > 0 else None

        # Accumulate totals
        for key, m, period in [("yd", myd, "yd"), ("7d", m7, "7d"), ("30d", m30, "30d")]:
            totals[key]["cost"] += m["cost"]
            totals[key]["sales"] += m["sales"]
            totals[key]["clicks"] += m["clicks"]
            totals[key]["impressions"] += m["impressions"]
            if key == "7d":
                totals[key]["purchases"] += m["purchases"]

        # Skip campaigns with negligible spend for proposals (but still track)
        negligible = cost_7d < 1.0 and cost_30d < 5.0

        # Apply ROAS Decision Framework (adjusted by campaign type)
        action = "monitor"
        bid_change_pct = None
        budget_change_pct = None
        priority = "low"
        reason = ""

        if not negligible:
            effective_roas = roas_7d
            if camp_type == "AUTO" and roas_7d >= config["min_roas"]:
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
                anomalies.append(f"Zero-sales: {camp['name']} - ${cost_7d:.0f} wasted (7d)")

        # Pre-compute CTR for reason and anomaly checks
        ctr_7d = round(m7["clicks"] / m7["impressions"] * 100, 2) if m7["impressions"] > 0 else 0

        # ROAS-based reason
        if not reason:
            trend = ""
            if roas_30d > 0:
                pct_change = round((roas_7d - roas_30d) / roas_30d * 100, 1)
                trend = f"7d vs 30d: {'+' if pct_change >= 0 else ''}{pct_change}%"

            cpc_7d = round(cost_7d / m7["clicks"], 2) if m7["clicks"] > 0 else 0

            if action == "optimize":
                # Build rich optimization reasoning
                target_acos = config["target_acos"]
                acos_gap = round(acos_7d - target_acos, 1) if acos_7d else 0
                opt_tips = []
                if acos_7d and acos_gap > 0:
                    opt_tips.append(f"ACOS {acos_7d}% exceeds target {target_acos}% by {acos_gap}pp -> bid -10%")
                elif acos_7d and acos_gap <= -5:
                    opt_tips.append(f"ACOS {acos_7d}% is {abs(acos_gap):.0f}pp below target {target_acos}% -> room to increase bid for more volume")
                else:
                    opt_tips.append(f"ACOS {acos_7d}% near target {target_acos}% -> fine-tune keyword bids")

                if cpc_7d > 0 and m7["clicks"] > 20:
                    if ctr_7d < 0.4:
                        opt_tips.append(f"CTR {ctr_7d}% is low -> review listing images, titles, pricing")
                    elif ctr_7d > 0.8:
                        opt_tips.append(f"CTR {ctr_7d}% is strong -> consider increasing bid to capture more impressions")

                if m7["purchases"] > 0:
                    cvr = round(m7["purchases"] / m7["clicks"] * 100, 2) if m7["clicks"] > 0 else 0
                    if cvr < 5:
                        opt_tips.append(f"CVR {cvr}% is below 5% benchmark -> optimize product page, A+ content, reviews")
                    elif cvr > 15:
                        opt_tips.append(f"CVR {cvr}% is excellent -> scale with more budget")

                reason = (f"[{camp_type}] 7d ROAS {roas_7d}x (ACOS {acos_7d}%) | "
                          f"30d ROAS {roas_30d}x | {trend}\n"
                          f"Optimization: {' | '.join(opt_tips)}")
            else:
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
                anomalies.append(f"ROAS drop: {camp['name']} yd {roas_yd}x vs 7d avg {roas_7d}x (-{drop_pct:.0f}%)")

        # Anomaly: single campaign eating >40% of total 7d spend
        total_7d_cost = totals["7d"]["cost"]
        if total_7d_cost > 0 and cost_7d / total_7d_cost > 0.4:
            anomalies.append(f"Budget hog: {camp['name']} consuming {cost_7d/total_7d_cost*100:.0f}% of total spend")

        # Anomaly: CTR below 0.3%
        if m7["impressions"] > 500 and ctr_7d < 0.3:
            anomalies.append(f"Low CTR: {camp['name']} CTR {ctr_7d}% ({m7['impressions']} impr)")

        # Budget safety cap
        type_budget = allocation[camp_type]["budget"]
        type_camp_count = max(allocation[camp_type]["campaigns"], 1)
        per_camp_share = round(type_budget / type_camp_count, 2)
        max_budget = min(per_camp_share * 2, MAX_SINGLE_CAMPAIGN_BUDGET)

        new_budget = camp["dailyBudget"]
        if budget_change_pct and camp["dailyBudget"] > 0:
            new_budget = round(camp["dailyBudget"] * (1 + budget_change_pct / 100), 2)
            if new_budget > max_budget:
                new_budget = max_budget

        tier = _confidence_tier(action, priority)

        campaign_entry = {
            "campaignId": cid,
            "campaignName": camp["name"],
            "campaignType": camp_type,
            "targetingType": camp.get("targetingType", ""),
            "currentState": camp["state"],
            "currentDailyBudget": camp["dailyBudget"],
            "metrics": {
                "yesterday": {"spend": round(cost_yd, 2), "sales": round(sales_yd, 2), "roas": roas_yd, "acos": acos_yd},
                "7d": {"spend": round(cost_7d, 2), "sales": round(sales_7d, 2), "roas": roas_7d, "acos": acos_7d,
                       "clicks": m7["clicks"], "impressions": m7["impressions"], "purchases": m7["purchases"],
                       "ctr": ctr_7d, "cpc": round(cost_7d / m7["clicks"], 2) if m7["clicks"] > 0 else 0},
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
            "tier": tier,
            "reason": reason,
            "additional": additional_action,
            "approved": False,
        }

        all_campaigns.append(campaign_entry)

        if action != "monitor" and not negligible:
            proposals.append(campaign_entry)

    # Sort by priority
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    proposals.sort(key=lambda x: priority_order.get(x["priority"], 9))

    # Sort all_campaigns by 7d spend descending
    all_campaigns.sort(key=lambda x: x["metrics"]["7d"]["spend"], reverse=True)

    # Build summary
    summary = {}
    for period in ("yd", "7d", "30d"):
        t = totals[period]
        summary[period] = {
            "spend": round(t["cost"], 2),
            "sales": round(t["sales"], 2),
            "roas": round(t["sales"] / t["cost"], 2) if t["cost"] > 0 else 0,
            "acos": round(t["cost"] / t["sales"] * 100, 1) if t["sales"] > 0 else None,
            "clicks": t["clicks"],
            "impressions": t["impressions"],
            "ctr": round(t["clicks"] / t["impressions"] * 100, 2) if t["impressions"] > 0 else 0,
            "cpc": round(t["cost"] / t["clicks"], 2) if t["clicks"] > 0 else 0,
        }
        if period == "7d":
            summary[period]["purchases"] = t.get("purchases", 0)
            summary[period]["cpa"] = round(t["cost"] / t["purchases"], 2) if t.get("purchases", 0) > 0 else 0

    # ROAS trend anomaly
    if summary["30d"]["roas"] > 0 and summary["7d"]["roas"] > 0:
        trend_pct = (summary["7d"]["roas"] - summary["30d"]["roas"]) / summary["30d"]["roas"] * 100
        if trend_pct < -20:
            anomalies.insert(0, f"Overall ROAS declining: 7d {summary['7d']['roas']}x vs 30d {summary['30d']['roas']}x ({trend_pct:+.0f}%)")
        elif trend_pct > 30:
            anomalies.insert(0, f"Overall ROAS improving: 7d {summary['7d']['roas']}x vs 30d {summary['30d']['roas']}x ({trend_pct:+.0f}%)")

    # Underspend detection: actual 7d daily avg vs budget target
    cfg = _cfg()
    target_daily = cfg["total_daily_budget"]
    actual_daily_7d = summary["7d"]["spend"] / 7 if summary["7d"]["spend"] > 0 else 0
    if target_daily > 0 and actual_daily_7d > 0:
        utilization = actual_daily_7d / target_daily * 100
        if utilization < 60:
            anomalies.insert(0,
                f"UNDERSPEND: Actual ${actual_daily_7d:.0f}/day vs target ${target_daily:.0f}/day "
                f"({utilization:.0f}% utilization). Aggressive budget increase recommended.")
            # Boost all increase_budget proposals
            for p in proposals:
                if p["proposed_action"] == "increase_budget" and p.get("budget_change_pct"):
                    old_pct = p["budget_change_pct"]
                    p["budget_change_pct"] = min(old_pct + 30, 80)  # Extra +30% boost, cap at +80%
                    if p.get("new_daily_budget") and p["currentDailyBudget"] > 0:
                        p["new_daily_budget"] = round(p["currentDailyBudget"] * (1 + p["budget_change_pct"] / 100), 2)
                        if p["new_daily_budget"] > MAX_SINGLE_CAMPAIGN_BUDGET:
                            p["new_daily_budget"] = MAX_SINGLE_CAMPAIGN_BUDGET
                    p["reason"] += f"\n** UNDERSPEND BOOST: budget increase amplified ({old_pct:+d}% -> {p['budget_change_pct']:+d}%) to reach ${target_daily}/day target"
            # Also boost bid increases for campaigns with good ROAS
            for p in proposals:
                if p["proposed_action"] in ("increase_budget", "optimize") and p["metrics"]["7d"]["roas"] >= 2.0:
                    if not p.get("bid_change_pct") or p["bid_change_pct"] == 0:
                        p["bid_change_pct"] = 15
                        p["reason"] += f"\n** UNDERSPEND: bid +15% to increase impressions/clicks (ROAS {p['metrics']['7d']['roas']}x supports growth)"
        elif utilization < 80:
            anomalies.insert(0,
                f"Budget underutilized: ${actual_daily_7d:.0f}/day of ${target_daily:.0f}/day ({utilization:.0f}%). "
                f"Consider increasing bids for more ad impressions.")

    # Deduplicate anomalies
    anomalies = list(dict.fromkeys(anomalies))

    return proposals, {"summary": summary, "all_campaigns": all_campaigns, "anomalies": anomalies,
                        "latest_date": latest_date.isoformat(), "d7_start": d7_start.isoformat()}


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

def log_to_sheets(executed_changes: List[Dict], brand_key: str = "naeiae"):
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
            BRAND_CONFIGS[brand_key]["brand_display"],
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
                   keyword_proposals: Optional[List[Dict]] = None,
                   brand_key: str = "naeiae"):
    cfg = BRAND_CONFIGS[brand_key]
    today_str = date.today().strftime("%Y%m%d")
    filepath = TMP_DIR / f"ppc_proposal_{brand_key}_{today_str}.json"

    kw_props = keyword_proposals or []
    payload = {
        "generated_at": datetime.now().isoformat(),
        "brand_key": brand_key,
        "brand": cfg["brand_display"],
        "seller": cfg["seller_name"],
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


def load_latest_proposal(brand_key: str = None) -> Optional[Dict]:
    """Load latest proposal. If brand_key given, filter to that brand."""
    if brand_key:
        proposals = sorted(TMP_DIR.glob(f"ppc_proposal_{brand_key}_*.json"), reverse=True)
    else:
        proposals = sorted(TMP_DIR.glob("ppc_proposal_*.json"), reverse=True)
    if not proposals:
        return None
    return json.loads(proposals[0].read_text(encoding="utf-8"))


# ===========================================================================
# Pretty Print Proposal
# ===========================================================================

def print_proposal_summary(proposals: List[Dict], brand_key: str = "naeiae"):
    cfg = BRAND_CONFIGS[brand_key]
    print(f"\n{'='*70}")
    print(f"  {cfg['brand_display']} ({cfg['seller_name']}) PPC Change Proposals - {date.today()}")
    print(f"  Daily Budget Cap: ${cfg['total_daily_budget']} (Manual 60% / Auto 40%)")
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


# ===========================================================================
# Cross-Platform Analysis (Google Ads + Meta + Shopify context)
# ===========================================================================

def fetch_cross_platform_context(brand_key: str, days: int = 30) -> Dict:
    """Pull Google Ads, Meta Ads, Shopify, Amazon Sales data from DataKeeper
    to provide cross-platform context for Amazon PPC proposals."""
    try:
        from data_keeper_client import DataKeeper
        dk = DataKeeper()
    except Exception as e:
        print(f"  [WARN] DataKeeper not available for cross-platform: {e}")
        return {}

    brand_map = {
        "naeiae": "Naeiae",
        "grosmimi": "Grosmimi",
        "chaenmom": "CHA&MOM",
    }
    brand_name = brand_map.get(brand_key, brand_key)
    ctx = {"brand": brand_name, "periods": {}}

    for period_label, period_days in [("7d", 7), ("30d", days)]:
        period = {}

        # --- Google Ads ---
        try:
            gads = dk.get("google_ads_daily", days=period_days)
            if gads:
                g_spend = sum(float(r.get("spend") or r.get("cost") or 0) for r in gads)
                g_conv_val = sum(float(r.get("conversions_value") or r.get("conversion_value") or 0) for r in gads)
                g_clicks = sum(int(r.get("clicks") or 0) for r in gads)
                g_impressions = sum(int(r.get("impressions") or 0) for r in gads)
                period["google_ads"] = {
                    "spend": round(g_spend, 2),
                    "conversions_value": round(g_conv_val, 2),
                    "roas": round(g_conv_val / g_spend, 2) if g_spend > 0 else 0,
                    "clicks": g_clicks,
                    "impressions": g_impressions,
                    "cpc": round(g_spend / g_clicks, 2) if g_clicks > 0 else 0,
                    "ctr": round(g_clicks / g_impressions * 100, 2) if g_impressions > 0 else 0,
                }
        except Exception as e:
            print(f"  [WARN] Google Ads cross-platform data: {e}")

        # --- Meta Ads ---
        try:
            meta = dk.get("meta_ads_daily", days=period_days)
            if meta:
                m_spend = sum(float(r.get("spend") or 0) for r in meta)
                m_revenue = sum(float(r.get("purchase_value") or r.get("conversions_value") or r.get("revenue") or 0) for r in meta)
                m_purchases = sum(int(r.get("purchases") or r.get("conversions") or 0) for r in meta)
                period["meta_ads"] = {
                    "spend": round(m_spend, 2),
                    "revenue": round(m_revenue, 2),
                    "roas": round(m_revenue / m_spend, 2) if m_spend > 0 else 0,
                    "purchases": m_purchases,
                    "cpa": round(m_spend / m_purchases, 2) if m_purchases > 0 else 0,
                }
        except Exception as e:
            print(f"  [WARN] Meta Ads cross-platform data: {e}")

        # --- Amazon Sales (organic + ad) ---
        try:
            amz_sales = dk.get("amazon_sales_daily", days=period_days, brand=brand_name)
            if amz_sales:
                total_rev = sum(float(r.get("gross_sales") or r.get("net_sales") or r.get("ordered_product_sales") or 0) for r in amz_sales)
                total_units = sum(int(r.get("units_ordered") or r.get("units") or 0) for r in amz_sales)
                period["amazon_sales"] = {
                    "revenue": round(total_rev, 2),
                    "total_units": total_units,
                }
        except Exception as e:
            print(f"  [WARN] Amazon Sales cross-platform data: {e}")

        # --- Shopify DTC (D2C channel only, brand-filtered, PR/B2B excluded) ---
        try:
            shopify_all = dk.get("shopify_orders_daily", days=period_days, brand=brand_name)
            shopify = [r for r in shopify_all if r.get("channel") == "D2C"]
            if shopify:
                s_revenue = sum(float(r.get("gross_sales") or r.get("net_sales") or r.get("total_price") or 0) for r in shopify)
                s_net = sum(float(r.get("net_sales") or 0) for r in shopify)
                s_orders = sum(int(r.get("orders") or 1) for r in shopify)
                period["shopify"] = {
                    "revenue": round(s_revenue, 2),
                    "net_sales": round(s_net, 2),
                    "orders": s_orders,
                    "aov": round(s_revenue / s_orders, 2) if s_orders > 0 else 0,
                }
        except Exception as e:
            print(f"  [WARN] Shopify cross-platform data: {e}")

        # --- GA4 ---
        try:
            ga4 = dk.get("ga4_daily", days=period_days)
            if ga4:
                ga4_sessions = sum(int(r.get("sessions") or r.get("active_users") or 0) for r in ga4)
                ga4_conv = sum(float(r.get("conversions") or r.get("ecommerce_purchases") or 0) for r in ga4)
                ga4_rev = sum(float(r.get("total_revenue") or r.get("purchase_revenue") or 0) for r in ga4)
                period["ga4"] = {
                    "sessions": ga4_sessions,
                    "conversions": round(ga4_conv),
                    "revenue": round(ga4_rev, 2),
                    "conv_rate": round(ga4_conv / ga4_sessions * 100, 2) if ga4_sessions > 0 else 0,
                }
        except Exception as e:
            print(f"  [WARN] GA4 cross-platform data: {e}")

        # --- Klaviyo ---
        try:
            klaviyo = dk.get("klaviyo_daily", days=period_days)
            if klaviyo:
                kl_revenue = sum(float(r.get("revenue") or r.get("attributed_revenue") or 0) for r in klaviyo)
                kl_opens = sum(int(r.get("opens") or r.get("unique_opens") or 0) for r in klaviyo)
                kl_clicks = sum(int(r.get("clicks") or r.get("unique_clicks") or 0) for r in klaviyo)
                period["klaviyo"] = {
                    "revenue": round(kl_revenue, 2),
                    "opens": kl_opens,
                    "clicks": kl_clicks,
                }
        except Exception as e:
            print(f"  [WARN] Klaviyo cross-platform data: {e}")

        ctx["periods"][period_label] = period

    # --- Cross-platform insights ---
    insights = []
    p30 = ctx["periods"].get("30d", {})
    p7 = ctx["periods"].get("7d", {})

    # Insight: Amazon vs Google ROAS comparison
    amz_ads_7d = p7.get("amazon_ads", {})
    gads_7d = p7.get("google_ads", {})
    if gads_7d.get("roas") and amz_ads_7d:
        g_roas = gads_7d["roas"]
        if g_roas > 0:
            insights.append(f"Google Ads 7d ROAS: {g_roas}x (CPC ${gads_7d.get('cpc', '?')})")

    # Insight: Meta ROAS comparison
    meta_7d = p7.get("meta_ads", {})
    if meta_7d.get("roas"):
        insights.append(f"Meta Ads 7d ROAS: {meta_7d['roas']}x (CPA ${meta_7d.get('cpa', '?')})")

    # Insight: Organic vs Ad sales ratio
    amz_sales_30d = p30.get("amazon_sales", {})
    if amz_sales_30d.get("total_revenue"):
        insights.append(f"Amazon Total Revenue (30d): ${amz_sales_30d['total_revenue']:,.0f} ({amz_sales_30d.get('total_units', 0)} units)")

    # Insight: Google Ads spend vs Amazon Ads spend comparison
    gads_30d = p30.get("google_ads", {})
    if gads_30d.get("spend") and gads_30d["spend"] > 0:
        insights.append(f"Google Ads 30d: ${gads_30d['spend']:,.0f} spend -> ${gads_30d.get('conversions_value', 0):,.0f} rev ({gads_30d['roas']}x)")

    # Insight: Shopify DTC performance
    shopify_7d = p7.get("shopify", {})
    if shopify_7d.get("revenue"):
        insights.append(f"Shopify DTC 7d: ${shopify_7d['revenue']:,.0f} ({shopify_7d['orders']} orders, AOV ${shopify_7d['aov']})")

    ctx["insights"] = insights
    return ctx


def _build_cross_platform_html(xp_ctx: Dict) -> str:
    """Build HTML section for cross-platform analysis context."""
    if not xp_ctx or not xp_ctx.get("periods"):
        return ""

    insights = xp_ctx.get("insights", [])
    p7 = xp_ctx["periods"].get("7d", {})
    p30 = xp_ctx["periods"].get("30d", {})

    rows = ""
    channels = [
        ("Google Ads", "google_ads", "roas", "spend"),
        ("Meta Ads", "meta_ads", "roas", "spend"),
        ("Amazon Sales", "amazon_sales", None, "total_revenue"),
        ("Shopify DTC", "shopify", None, "revenue"),
    ]

    for label, key, roas_field, spend_field in channels:
        d7 = p7.get(key, {})
        d30 = p30.get(key, {})
        if not d7 and not d30:
            continue

        spend_7 = d7.get(spend_field, 0)
        spend_30 = d30.get(spend_field, 0)
        roas_7 = d7.get(roas_field, "-") if roas_field else "-"
        roas_30 = d30.get(roas_field, "-") if roas_field else "-"

        def _rc(v):
            if v == "-" or not v: return "#666"
            try:
                v = float(v)
                if v >= 3.0: return "#28a745"
                if v >= 2.0: return "#ffc107"
                return "#dc3545"
            except: return "#666"

        rows += f"""<tr>
            <td style="padding:6px 10px;border:1px solid #ddd;font-weight:bold;">{label}</td>
            <td style="padding:6px 10px;border:1px solid #ddd;">${spend_7:,.0f}</td>
            <td style="padding:6px 10px;border:1px solid #ddd;color:{_rc(roas_7)};font-weight:bold;">{roas_7}{'x' if roas_7 != '-' else ''}</td>
            <td style="padding:6px 10px;border:1px solid #ddd;">${spend_30:,.0f}</td>
            <td style="padding:6px 10px;border:1px solid #ddd;color:{_rc(roas_30)};font-weight:bold;">{roas_30}{'x' if roas_30 != '-' else ''}</td>
        </tr>"""

    if not rows and not insights:
        return ""

    insights_html = ""
    if insights:
        items = "".join(f'<li style="margin:4px 0;font-size:13px;">{i}</li>' for i in insights)
        insights_html = f'<ul style="margin:8px 0;padding-left:20px;">{items}</ul>'

    return f"""
    <div style="margin-top:25px;padding:15px;background:#f0f4ff;border-radius:8px;border-left:4px solid #4a90d9;">
        <h3 style="margin:0 0 10px;color:#2c5282;">Cross-Platform Context</h3>
        <p style="color:#666;font-size:12px;margin:0 0 10px;">Other channels performance (from DataKeeper) -- use to contextualize Amazon PPC decisions</p>
        <table style="border-collapse:collapse;width:100%;margin-bottom:10px;">
            <tr style="background:#e2e8f0;">
                <th style="padding:8px 10px;text-align:left;">Channel</th>
                <th style="padding:8px 10px;">7d Spend/Rev</th>
                <th style="padding:8px 10px;">7d ROAS</th>
                <th style="padding:8px 10px;">30d Spend/Rev</th>
                <th style="padding:8px 10px;">30d ROAS</th>
            </tr>
            {rows}
        </table>
        {insights_html}
    </div>"""


def build_proposal_html(proposals: List[Dict],
                        kw_proposals: Optional[List[Dict]] = None,
                        brand_key: str = "naeiae",
                        xp_context: Optional[Dict] = None,
                        analysis: Optional[Dict] = None,
                        kw_matrix: Optional[Dict] = None) -> str:
    """Build comprehensive HTML email with performance summary, all campaigns, proposals, keyword matrix, and cross-platform context."""
    cfg = BRAND_CONFIGS[brand_key]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def color(priority):
        return {"urgent": "#dc3545", "high": "#fd7e14", "medium": "#ffc107"}.get(priority, "#6c757d")

    def roas_color(roas):
        if roas >= 3.0: return "#28a745"
        if roas >= 2.0: return "#ffc107"
        return "#dc3545"

    def tier_badge(tier):
        # Extract score number from tier string (e.g., "8 Strong" -> 8)
        score = 1
        label = tier
        parts = tier.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            score = int(parts[0])
            label = parts[1]
        # Gradient: same hue family, darker = higher score
        gradient = {
            10: "#b71c1c",  # Deep red - must do NOW
            9:  "#c62828",  # Red
            8:  "#d84315",  # Deep orange
            7:  "#e65100",  # Orange
            6:  "#00838f",  # Teal dark
            5:  "#00acc1",  # Teal
            4:  "#f9a825",  # Amber
            3:  "#fbc02d",  # Yellow
            2:  "#90a4ae",  # Grey
            1:  "#b0bec5",  # Light grey
        }
        c = gradient.get(score, "#b0bec5")
        text_color = "white" if score >= 4 else "#333"
        return f'<span style="background:{c};color:{text_color};padding:2px 8px;border-radius:3px;font-size:10px;white-space:nowrap;"><b>{score}</b> {label}</span>'

    # ---- Section 1: Performance Summary ----
    summary_html = ""
    all_camps = []
    anomalies = []
    if analysis:
        summary = analysis.get("summary", {})
        all_camps = analysis.get("all_campaigns", [])
        anomalies = analysis.get("anomalies", [])

        yd = summary.get("yd", {})
        s7 = summary.get("7d", {})
        s30 = summary.get("30d", {})

        # Trend arrows
        roas_trend = ""
        if s30.get("roas") and s7.get("roas"):
            pct = (s7["roas"] - s30["roas"]) / s30["roas"] * 100
            arrow = "^" if pct > 0 else "v"
            tc = "#28a745" if pct > 0 else "#dc3545"
            roas_trend = f' <span style="color:{tc};font-size:12px;">({arrow}{abs(pct):.0f}% vs 30d)</span>'

        latest_dt = analysis.get("latest_date", "Yesterday")
        d7_start = analysis.get("d7_start", "")
        summary_html = f"""
    <div style="background:#f8f9fa;padding:15px 20px;border-radius:8px;margin:15px 0;border-left:4px solid #343a40;">
        <h3 style="margin:0 0 12px;color:#333;">Performance Summary</h3>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#e9ecef;">
                <th style="padding:8px 12px;text-align:left;"></th>
                <th style="padding:8px 12px;">Latest ({latest_dt})</th>
                <th style="padding:8px 12px;">7-Day ({d7_start}~{latest_dt})</th>
                <th style="padding:8px 12px;">30-Day Avg</th>
            </tr>
            <tr>
                <td style="padding:6px 12px;font-weight:bold;">Spend</td>
                <td style="padding:6px 12px;text-align:center;">${yd.get('spend', 0):,.0f}</td>
                <td style="padding:6px 12px;text-align:center;">${s7.get('spend', 0):,.0f}</td>
                <td style="padding:6px 12px;text-align:center;">${s30.get('spend', 0):,.0f}</td>
            </tr>
            <tr style="background:#f8f9fa;">
                <td style="padding:6px 12px;font-weight:bold;">Sales</td>
                <td style="padding:6px 12px;text-align:center;">${yd.get('sales', 0):,.0f}</td>
                <td style="padding:6px 12px;text-align:center;">${s7.get('sales', 0):,.0f}</td>
                <td style="padding:6px 12px;text-align:center;">${s30.get('sales', 0):,.0f}</td>
            </tr>
            <tr>
                <td style="padding:6px 12px;font-weight:bold;">ROAS</td>
                <td style="padding:6px 12px;text-align:center;color:{roas_color(yd.get('roas', 0))};font-weight:bold;">{yd.get('roas', 0)}x</td>
                <td style="padding:6px 12px;text-align:center;color:{roas_color(s7.get('roas', 0))};font-weight:bold;">{s7.get('roas', 0)}x{roas_trend}</td>
                <td style="padding:6px 12px;text-align:center;color:{roas_color(s30.get('roas', 0))};font-weight:bold;">{s30.get('roas', 0)}x</td>
            </tr>
            <tr style="background:#f8f9fa;">
                <td style="padding:6px 12px;font-weight:bold;">ACOS</td>
                <td style="padding:6px 12px;text-align:center;">{yd.get('acos') or '-'}%</td>
                <td style="padding:6px 12px;text-align:center;">{s7.get('acos') or '-'}%</td>
                <td style="padding:6px 12px;text-align:center;">{s30.get('acos') or '-'}%</td>
            </tr>
            <tr>
                <td style="padding:6px 12px;font-weight:bold;">CPC</td>
                <td style="padding:6px 12px;text-align:center;">${yd.get('cpc', 0):.2f}</td>
                <td style="padding:6px 12px;text-align:center;">${s7.get('cpc', 0):.2f}</td>
                <td style="padding:6px 12px;text-align:center;">${s30.get('cpc', 0):.2f}</td>
            </tr>
            <tr style="background:#f8f9fa;">
                <td style="padding:6px 12px;font-weight:bold;">CTR</td>
                <td style="padding:6px 12px;text-align:center;">{yd.get('ctr', 0)}%</td>
                <td style="padding:6px 12px;text-align:center;">{s7.get('ctr', 0)}%</td>
                <td style="padding:6px 12px;text-align:center;">{s30.get('ctr', 0)}%</td>
            </tr>
            <tr>
                <td style="padding:6px 12px;font-weight:bold;">Conversions (7d)</td>
                <td style="padding:6px 12px;text-align:center;">-</td>
                <td style="padding:6px 12px;text-align:center;">{s7.get('purchases', 0)} orders (CPA ${s7.get('cpa', 0):.2f})</td>
                <td style="padding:6px 12px;text-align:center;">-</td>
            </tr>
        </table>
    </div>"""

    # ---- Section 2: Anomalies ----
    anomaly_html = ""
    if anomalies:
        items = "".join(f'<li style="margin:4px 0;color:#856404;">{a}</li>' for a in anomalies[:10])
        anomaly_html = f"""
    <div style="background:#fff3cd;padding:12px 20px;border-radius:8px;margin:15px 0;border-left:4px solid #ffc107;">
        <h3 style="margin:0 0 8px;color:#856404;">Anomalies Detected ({len(anomalies)})</h3>
        <ul style="margin:0;padding-left:20px;">{items}</ul>
    </div>"""

    # ---- Section 3: Action Proposals ----
    proposals_html = ""
    if proposals:
        rows_html = ""
        # A, B, C, ... Z, AA, AB, ... labeling for selective execution
        def _proposal_label(idx):
            if idx < 26:
                return chr(65 + idx)  # A-Z
            return chr(65 + idx // 26 - 1) + chr(65 + idx % 26)  # AA, AB, ...

        for i, p in enumerate(proposals):
            label = _proposal_label(i)
            p["_label"] = label  # Store for JSON reference
            m7 = p["metrics"]["7d"]
            action_text = p["proposed_action"]
            if p.get("bid_change_pct"):
                action_text += f" (bid {p['bid_change_pct']:+d}%)"
            if p.get("new_daily_budget"):
                action_text += f" (${p['currentDailyBudget']}->${p['new_daily_budget']})"

            reason_text = p.get("reason", "").replace("\n", "<br>")
            rows_html += f"""
            <tr>
                <td style="padding:6px 8px;border:1px solid #ddd;font-weight:bold;font-size:14px;text-align:center;background:#f5f5f5;width:30px;">{label}</td>
                <td style="padding:6px 8px;border:1px solid #ddd;">{tier_badge(p.get('tier', 'Monitor'))}</td>
                <td style="padding:6px 8px;border:1px solid #ddd;font-size:12px;">[{p.get('campaignType','?')}] {p['campaignName']}</td>
                <td style="padding:6px 8px;border:1px solid #ddd;color:{roas_color(m7['roas'])};font-weight:bold;">{m7['roas']}x</td>
                <td style="padding:6px 8px;border:1px solid #ddd;">{m7.get('acos') or '-'}%</td>
                <td style="padding:6px 8px;border:1px solid #ddd;">${m7['spend']:.0f}</td>
                <td style="padding:6px 8px;border:1px solid #ddd;">${m7['sales']:.0f}</td>
                <td style="padding:6px 8px;border:1px solid #ddd;font-weight:bold;">{action_text}</td>
            </tr>
            <tr>
                <td colspan="8" style="padding:4px 8px 8px 30px;border:1px solid #eee;font-size:11px;color:#555;background:#fafafa;">{reason_text}</td>
            </tr>"""

        # Count tiers by label (tier format: "8 Strong")
        def _tier_label(t): return t.split(" ", 1)[1] if " " in t else t
        urgent = [p for p in proposals if _tier_label(p.get("tier", "")) == "No-Brainer"]
        strong = [p for p in proposals if _tier_label(p.get("tier", "")) == "Strong"]
        optimize = [p for p in proposals if _tier_label(p.get("tier", "")) == "Optimize"]
        moderate = [p for p in proposals if _tier_label(p.get("tier", "")) == "Moderate"]
        # Score distribution
        scores = [int(p.get("tier", "1").split(" ")[0]) for p in proposals if p.get("tier", "1 ")[0].isdigit()]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        max_score = max(scores) if scores else 0
        proposals_html = f"""
    <h3 style="color:#333;margin-top:25px;">Action Proposals ({len(proposals)}) -- Avg Score: {avg_score}/10, Max: {max_score}</h3>
    <div style="display:flex;gap:15px;margin:10px 0;flex-wrap:wrap;">
        <div style="background:#ffcdd2;padding:8px 15px;border-radius:6px;font-size:13px;"><strong>{len(urgent)}</strong> No-Brainer (9-10)</div>
        <div style="background:#ffe0b2;padding:8px 15px;border-radius:6px;font-size:13px;"><strong>{len(strong)}</strong> Strong (7-8)</div>
        <div style="background:#b2ebf2;padding:8px 15px;border-radius:6px;font-size:13px;"><strong>{len(optimize)}</strong> Optimize (5-6)</div>
        <div style="background:#fff9c4;padding:8px 15px;border-radius:6px;font-size:13px;"><strong>{len(moderate)}</strong> Moderate (3-4)</div>
    </div>
    <p style="color:#666;font-size:12px;margin:5px 0;">Reply with letter codes to execute selectively (e.g., "Execute A, C, E" or "Execute all").</p>
    <table style="border-collapse:collapse;width:100%;">
        <tr style="background:#343a40;color:white;">
            <th style="padding:8px;border:1px solid #ddd;">ID</th>
            <th style="padding:8px;border:1px solid #ddd;">Tier</th>
            <th style="padding:8px;border:1px solid #ddd;">Campaign</th>
            <th style="padding:8px;border:1px solid #ddd;">7d ROAS</th>
            <th style="padding:8px;border:1px solid #ddd;">7d ACOS</th>
            <th style="padding:8px;border:1px solid #ddd;">7d Spend</th>
            <th style="padding:8px;border:1px solid #ddd;">7d Sales</th>
            <th style="padding:8px;border:1px solid #ddd;">Proposed Action</th>
        </tr>
        {rows_html}
    </table>"""
    else:
        proposals_html = """
    <div style="background:#d4edda;padding:12px 20px;border-radius:8px;margin:15px 0;border-left:4px solid #28a745;">
        <strong>All campaigns within healthy ROAS range.</strong> No urgent action items. See campaign breakdown below for optimization opportunities.
    </div>"""

    # ---- Section 4: All Campaigns Overview ----
    all_camps_html = ""
    if all_camps:
        camp_rows = ""
        for c in all_camps[:30]:  # Top 30 by spend
            m7 = c["metrics"]["7d"]
            myd = c["metrics"]["yesterday"]
            m30 = c["metrics"]["30d"]
            trend_pct = ""
            if m30["roas"] > 0:
                pct = (m7["roas"] - m30["roas"]) / m30["roas"] * 100
                tc = "#28a745" if pct > 0 else "#dc3545"
                trend_pct = f'<span style="color:{tc};font-size:11px;">({pct:+.0f}%)</span>'

            camp_rows += f"""
            <tr>
                <td style="padding:5px 8px;border:1px solid #eee;font-size:12px;">{tier_badge(c.get('tier', 'Monitor'))}</td>
                <td style="padding:5px 8px;border:1px solid #eee;font-size:11px;">[{c.get('campaignType','?')}] {c['campaignName'][:45]}</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${myd.get('spend', 0):.0f}</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;color:{roas_color(myd.get('roas', 0))};">{myd.get('roas', 0)}x</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${m7['spend']:.0f}</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;color:{roas_color(m7['roas'])};font-weight:bold;">{m7['roas']}x</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">{m7.get('acos') or '-'}%</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">${m7['cpc']:.2f}</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;">{m7.get('ctr', 0)}%</td>
                <td style="padding:5px 8px;border:1px solid #eee;text-align:right;color:{roas_color(m30['roas'])};">{m30['roas']}x {trend_pct}</td>
            </tr>"""

        all_camps_html = f"""
    <h3 style="color:#333;margin-top:25px;">All Campaigns ({len(all_camps)} active)</h3>
    <p style="color:#666;font-size:12px;margin:0 0 8px;">Sorted by 7d spend. Top 30 shown.</p>
    <table style="border-collapse:collapse;width:100%;font-size:12px;">
        <tr style="background:#495057;color:white;">
            <th style="padding:6px;">Tier</th>
            <th style="padding:6px;">Campaign</th>
            <th style="padding:6px;">Yd $</th>
            <th style="padding:6px;">Yd ROAS</th>
            <th style="padding:6px;">7d $</th>
            <th style="padding:6px;">7d ROAS</th>
            <th style="padding:6px;">7d ACOS</th>
            <th style="padding:6px;">CPC</th>
            <th style="padding:6px;">CTR</th>
            <th style="padding:6px;">30d ROAS</th>
        </tr>
        {camp_rows}
    </table>"""

    # ============================================================
    # Build COMPREHENSIVE data source appendix
    # Shows ALL DataKeeper channels with freshness + usage detail
    # ============================================================
    data_sources = []  # Top banner (short)
    data_appendix_rows = []  # Detailed appendix (5 columns)
    analysis_notes = []  # How each source influenced proposals

    n_all_camps = len(analysis.get("all_campaigns", [])) if analysis else 0

    # --- 1. Amazon Ads (primary source) ---
    if analysis:
        latest = analysis.get("latest_date", "?")
        d7_start = analysis.get("d7_start", "?")
        data_sources.append(f"Amazon Ads: {d7_start} ~ {latest}")
        s7 = analysis.get("summary", {}).get("7d", {})
        s30 = analysis.get("summary", {}).get("30d", {})
        data_appendix_rows.append((
            "Amazon Ads Campaign Metrics",
            "DataKeeper gk_amazon_ads_daily",
            f"{d7_start} ~ {latest}",
            f"{n_all_camps} active campaigns. 7d: ${s7.get('spend',0):,.0f} spend, {s7.get('clicks',0):,} clicks, "
            f"{s7.get('impressions',0):,} impr, {s7.get('purchases',0)} purchases. "
            f"30d: ${s30.get('spend',0):,.0f} spend, ${s30.get('sales',0):,.0f} sales.",
            "ROAS Decision Framework (1-10 score), budget allocation, trend anomaly detection, "
            "campaign-level bid/budget proposals, yesterday vs 7d vs 30d comparison"
        ))
        analysis_notes.append(
            f"Campaign ROAS framework applied to {n_all_camps} campaigns using {d7_start}~{latest} data. "
            f"7d ROAS {s7.get('roas',0)}x drove tier scoring. "
            f"30d ROAS used for trend comparison ({'+' if s7.get('roas',0) > s30.get('roas',0) else '-'}trend)."
        )

    # --- 2. Amazon Keyword Reports (API) ---
    if kw_matrix and kw_matrix.get("total_keywords", 0) > 0:
        n_kw = kw_matrix["total_keywords"]
        n_trends = len(kw_matrix.get("keyword_trends", []))
        n_cannibal = len(kw_matrix.get("cannibalization", []))
        mt_list = ', '.join(m['matchType'] for m in kw_matrix.get('match_type_breakdown', []))
        data_sources.append(f"Keywords: {n_kw}")
        data_appendix_rows.append((
            "Amazon Keyword Report (7d)",
            "Amazon Ads Reporting API v3",
            "Last 7 days (SUMMARY)",
            f"{n_kw} keywords. Used for recent performance snapshot.",
            "7d vs previous period ROAS trend per keyword, recent bid efficiency check"
        ))
        data_appendix_rows.append((
            "Amazon Keyword Report (30d)",
            "Amazon Ads Reporting API v3",
            "Last 30 days (SUMMARY)",
            f"{n_kw} keywords. Match types: {mt_list}. Trend: {n_trends} keywords compared.",
            "Top/bottom 10 ranking, match type comparison, ad group breakdown, "
            f"keyword bid adjustments, cannibalization detection ({n_cannibal} alerts)"
        ))
        data_appendix_rows.append((
            "Amazon Search Term Report (30d)",
            "Amazon Ads Reporting API v3",
            "Last 30 days (SUMMARY)",
            "Customer search queries matched to campaigns.",
            "New keyword harvesting (exact match), negative keyword candidates, "
            "search term cannibalization across campaigns"
        ))
        analysis_notes.append(
            f"Keyword analysis: {n_kw} keywords analyzed across {mt_list}. "
            f"7d vs previous ROAS compared for {n_trends} keywords to detect momentum shifts. "
            f"{n_cannibal} cannibalization alerts (same keyword/search term in multiple campaigns)."
        )

    # --- 3. DataForSEO / Google Keyword Planner ---
    if kw_matrix and kw_matrix.get("keyword_vs_google"):
        n_google = len(kw_matrix["keyword_vs_google"])
        data_sources.append(f"DataForSEO: {n_google} kw")
        data_appendix_rows.append((
            "DataForSEO / Google Keyword Planner",
            "DataKeeper gk_dataforseo_keywords",
            "Last 30 days",
            f"{n_google} keywords with Google search volume, CPC, competition index. "
            f"Cross-referenced with Amazon keyword CPC for market benchmarking.",
            "Google CPC vs Amazon CPC gap analysis. Overbidding detection "
            "(AMZ CPC > Google CPC x1.5 -> bid reduction). Underbidding detection "
            "(AMZ CPC < Google CPC x0.5 + ROAS >2 -> bid increase). "
            "Search volume used for keyword priority ranking."
        ))
        analysis_notes.append(
            f"DataForSEO: {n_google} Amazon keywords matched to Google CPC. "
            f"Overbidding/underbidding adjustments applied to bid proposals."
        )
    else:
        data_appendix_rows.append((
            "DataForSEO / Google Keyword Planner",
            "DataKeeper gk_dataforseo_keywords",
            "N/A",
            "No keyword matches found for this brand.",
            "Would provide Google CPC benchmark for bid optimization if keywords matched."
        ))

    # --- 4. Cross-platform DataKeeper channels (ALL channels, active or not) ---
    all_dk_channels = [
        ("google_ads", "Google Ads", "gk_google_ads_daily",
         "Cross-platform ROAS comparison. If Google Ads ROAS > Amazon ROAS, "
         "signals potential budget reallocation. Campaign type and keyword overlap analysis."),
        ("meta_ads", "Meta Ads (Facebook/Instagram)", "gk_meta_ads_daily",
         "Cross-platform CPA/ROAS comparison. Meta's audience signals inform "
         "Amazon keyword strategy (high-converting Meta audiences -> Amazon keyword themes)."),
        ("amazon_sales", "Amazon Sales (SP-API)", "gk_amazon_sales_daily",
         "Organic vs ad-attributed sales gap. If organic sales are high, "
         "ad spend efficiency is validated. Brand vs non-brand sales split."),
        ("shopify_dtc", "Shopify DTC Orders", "gk_shopify_orders_daily",
         "DTC pricing context. Discount rates vs Amazon pricing. "
         "Influencer code usage patterns inform keyword targeting strategy."),
        ("ga4", "Google Analytics 4", "gk_ga4_daily",
         "Website traffic sources, conversion paths. Organic search keywords "
         "inform Amazon keyword expansion. Landing page performance context."),
        ("klaviyo", "Klaviyo Email/SMS", "gk_klaviyo_daily",
         "Email campaign performance, subscriber engagement. "
         "High-converting email products suggest Amazon ad focus areas."),
    ]

    # Map appendix keys to xp_context period keys (which may differ)
    _xp_key_map = {"shopify_dtc": "shopify"}  # appendix key -> xp_context key

    for ch_key, ch_label, ch_table, ch_usage in all_dk_channels:
        xp_key = _xp_key_map.get(ch_key, ch_key)
        p7 = xp_context.get("periods", {}).get("7d", {}) if xp_context else {}
        ch_data = p7.get(xp_key, {})
        spend_7d = ch_data.get("spend", 0)
        rev_7d = ch_data.get("revenue", 0)
        roas_7d = ch_data.get("roas", 0)
        sessions_7d = ch_data.get("sessions", 0)
        has_data = spend_7d > 0 or rev_7d > 0 or sessions_7d > 0

        if has_data:
            if spend_7d:
                data_sources.append(f"{ch_label.split('(')[0].strip()}: ${spend_7d:,.0f}/7d")
                summary_text = f"7d: ${spend_7d:,.0f} spend"
            elif rev_7d:
                data_sources.append(f"{ch_label.split('(')[0].strip()}: ${rev_7d:,.0f}/7d")
                summary_text = f"7d: ${rev_7d:,.0f} revenue"
            elif sessions_7d:
                data_sources.append(f"{ch_label.split('(')[0].strip()}: {sessions_7d:,} sessions/7d")
                summary_text = f"7d: {sessions_7d:,} sessions"
                conv_rate = ch_data.get("conv_rate", 0)
                if conv_rate:
                    summary_text += f", {conv_rate}% conv rate"
            else:
                summary_text = "7d: data present"
                data_sources.append(f"{ch_label.split('(')[0].strip()}: active")
            if roas_7d:
                summary_text += f", ROAS {roas_7d}x"
            status_icon = "ACTIVE"
            status_color = "#28a745"
        else:
            summary_text = "No recent data or channel not applicable for this brand."
            status_icon = "NO DATA"
            status_color = "#999"

        data_appendix_rows.append((
            f'<span style="color:{status_color};font-size:9px;">[{status_icon}]</span> {ch_label}',
            f"DataKeeper {ch_table}",
            "Last 7-30 days" if has_data else "--",
            summary_text,
            ch_usage if has_data else f"<i style='color:#999;'>{ch_usage}</i>"
        ))

        if has_data:
            amz_roas = s7.get('roas', 0) if analysis else 0
            if ch_key in ("google_ads", "meta_ads") and spend_7d > 0:
                roas_label = f"{roas_7d}x" if roas_7d else "N/A"
                comparison = 'Outperforming' if roas_7d and roas_7d > amz_roas else 'Underperforming'
                analysis_notes.append(
                    f"{ch_label}: 7d ${spend_7d:,.0f} spend, ROAS {roas_label}. "
                    f"{comparison} vs Amazon Ads ({amz_roas}x). "
                    f"{'Budget reallocation signal.' if roas_7d and roas_7d > amz_roas * 1.5 else ''}"
                )
            elif ch_key == "amazon_sales" and rev_7d > 0:
                analysis_notes.append(
                    f"{ch_label}: 7d ${rev_7d:,.0f} total revenue (organic+ad). "
                    f"Used to validate ad spend efficiency."
                )
            elif ch_key == "ga4" and sessions_7d > 0:
                analysis_notes.append(
                    f"{ch_label}: 7d {sessions_7d:,} sessions, {ch_data.get('conv_rate',0)}% conv. "
                    f"Organic search keywords inform Amazon keyword expansion."
                )
            elif ch_key == "klaviyo" and (ch_data.get("opens", 0) > 0 or rev_7d > 0):
                analysis_notes.append(
                    f"{ch_label}: 7d ${rev_7d:,.0f} attributed revenue, {ch_data.get('opens',0):,} opens. "
                    f"High-converting email products suggest ad focus areas."
                )

    sources_str = " | ".join(data_sources) if data_sources else "No data sources"

    # Build tier legend HTML
    tier_legend = """
    <div style="margin-top:30px;padding:15px;background:#f5f5f5;border-radius:8px;border:1px solid #e0e0e0;">
        <h3 style="color:#333;margin:0 0 10px;">Confidence Score Guide (1-10)</h3>
        <table style="border-collapse:collapse;width:100%;font-size:12px;">
            <tr>
                <td style="padding:4px 8px;"><span style="background:#b71c1c;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>10</b> No-Brainer</span></td>
                <td style="padding:4px 8px;color:#666;">Must do. Losing money or obvious massive win. Execute immediately.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#c62828;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>9</b> No-Brainer</span></td>
                <td style="padding:4px 8px;color:#666;">Strong urgency. Clear waste or high-confidence bid reduction needed.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#d84315;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>8</b> Strong</span></td>
                <td style="padding:4px 8px;color:#666;">High confidence. Clear ROI signal supports this change.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#e65100;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>7</b> Strong</span></td>
                <td style="padding:4px 8px;color:#666;">Good data backing. Budget increase or bid adjustment recommended.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#00838f;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>6</b> Optimize</span></td>
                <td style="padding:4px 8px;color:#666;">Actionable optimization. Fine-tune bids, test new keywords.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#00acc1;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>5</b> Optimize</span></td>
                <td style="padding:4px 8px;color:#666;">Worth trying. Moderate signal, monitor after applying.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#f9a825;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>4</b> Moderate</span></td>
                <td style="padding:4px 8px;color:#666;">Consider it. Lower urgency but could improve efficiency.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#fbc02d;color:white;padding:2px 8px;border-radius:3px;font-size:10px;"><b>3</b> Moderate</span></td>
                <td style="padding:4px 8px;color:#666;">Low priority. Apply if bandwidth allows.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#90a4ae;color:#333;padding:2px 8px;border-radius:3px;font-size:10px;"><b>2</b> Monitor</span></td>
                <td style="padding:4px 8px;color:#666;">Watch. Insufficient data or borderline performance.</td>
            </tr>
            <tr>
                <td style="padding:4px 8px;"><span style="background:#b0bec5;color:#333;padding:2px 8px;border-radius:3px;font-size:10px;"><b>1</b> Monitor</span></td>
                <td style="padding:4px 8px;color:#666;">No action. Performance within acceptable range.</td>
            </tr>
        </table>
    </div>"""

    # Build data appendix HTML (5-column: source, storage, period, data summary, usage in this report)
    appendix_rows_html = ""
    for row in data_appendix_rows:
        src_name, storage, period, data_summary, usage = row
        appendix_rows_html += f"""<tr>
            <td style="padding:5px 8px;border:1px solid #e0e0e0;font-size:11px;font-weight:bold;">{src_name}</td>
            <td style="padding:5px 8px;border:1px solid #e0e0e0;font-size:10px;color:#546e7a;font-family:monospace;">{storage}</td>
            <td style="padding:5px 8px;border:1px solid #e0e0e0;font-size:11px;white-space:nowrap;">{period}</td>
            <td style="padding:5px 8px;border:1px solid #e0e0e0;font-size:10px;color:#666;">{data_summary}</td>
            <td style="padding:5px 8px;border:1px solid #e0e0e0;font-size:10px;color:#1565c0;">{usage}</td>
        </tr>"""
    data_appendix = f"""
    <div style="margin-top:25px;padding:15px;background:#fafafa;border-radius:8px;border:1px solid #e0e0e0;">
        <h3 style="color:#546e7a;margin:0 0 10px;">Appendix: Data Sources & Freshness</h3>
        <table style="border-collapse:collapse;width:100%;font-size:12px;">
            <tr style="background:#78909c;color:white;">
                <th style="padding:6px;">Data Source</th>
                <th style="padding:6px;">Storage / API</th>
                <th style="padding:6px;">Period</th>
                <th style="padding:6px;">Data Summary</th>
                <th style="padding:6px;">Used For</th>
            </tr>
            {appendix_rows_html}
        </table>
        <p style="color:#999;font-size:10px;margin-top:8px;">
            DataKeeper = orbitools.orbiters.co.kr PostgreSQL (gk_* tables). Refreshes 2x daily (PST 00:00, 12:00).<br>
            Amazon Ads API has a 1-day reporting lag (D+1). Data for today becomes available tomorrow KST 17:00.<br>
            Keyword reports fetched directly from Amazon Ads Reporting API v3 (async submit -> poll -> download GZIP).
        </p>
    </div>""" if data_appendix_rows else ""

    # Build analysis notes HTML -- detailed explanation of how each data source influenced proposals
    analysis_notes_html = ""
    if analysis_notes:
        notes_items = ""
        for i, note in enumerate(analysis_notes, 1):
            notes_items += f'<li style="padding:4px 0;font-size:11px;color:#37474f;line-height:1.5;">{note}</li>\n'
        analysis_notes_html = f"""
    <div style="margin-top:20px;padding:15px;background:#fff8e1;border-radius:8px;border-left:4px solid #ff8f00;">
        <h3 style="color:#e65100;margin:0 0 10px;font-size:14px;">Analysis Notes: How Data Sources Influenced Proposals</h3>
        <p style="color:#999;font-size:10px;margin:0 0 8px;">Each note below explains what data was analyzed and how it shaped specific recommendations in this report.</p>
        <ol style="margin:0;padding-left:20px;">
            {notes_items}
        </ol>
    </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:1200px;margin:0 auto;padding:20px;">
    <div style="background:#263238;color:white;padding:10px 18px;border-radius:6px;margin-bottom:15px;font-size:12px;">
        <strong>Data Sources:</strong> {sources_str}
    </div>
    <h2 style="color:#333;">{cfg['brand_display']} ({cfg['seller_name']}) PPC Daily Proposal</h2>
    <p style="color:#666;">Generated: {now} | Daily Budget: ${cfg['total_daily_budget']:,.0f} | ACOS targets: Manual {cfg['targeting']['MANUAL']['target_acos']}% / Auto {cfg['targeting']['AUTO']['target_acos']}%</p>

    {summary_html}

    {anomaly_html}

    {proposals_html}

    {_build_keyword_html(kw_proposals, label_start=len(proposals) if proposals else 0)}

    {_build_keyword_matrix_html(kw_matrix) if kw_matrix else ''}

    {all_camps_html}

    {_build_cross_platform_html(xp_context) if xp_context else ''}

    <div style="margin-top:25px;padding:15px;background:#e3f2fd;border-radius:8px;border-left:4px solid #2196f3;">
        <strong>To execute proposals:</strong> Reply "execute" to this email, or edit <code>.tmp/ppc_proposal_*.json</code> and run <code>--execute</code>.
    </div>

    {tier_legend}

    {data_appendix}

    {analysis_notes_html}

    <p style="color:#999;margin-top:20px;font-size:11px;">
        Amazon PPC Executor ({cfg['brand_display']}) | Scheduled daily KST 08:00 | Auto-check for "execute" reply every 2h
    </p>
</body>
</html>"""
    return html


def _build_keyword_html(kw_proposals: Optional[List[Dict]], label_start: int = 0) -> str:
    """Build HTML section for keyword-level proposals with A/B/C labels continuing from campaign proposals."""
    if not kw_proposals:
        return ""

    def _label(idx):
        i = label_start + idx
        if i < 26:
            return chr(65 + i)
        return chr(65 + i // 26 - 1) + chr(65 + i % 26)

    harvest = [p for p in kw_proposals if p.get("type") == "harvest"]
    negate = [p for p in kw_proposals if p.get("type", "").startswith("negate")]
    bid_adj = [p for p in kw_proposals if p.get("type") == "keyword_bid"]

    sections = []
    lbl_idx = 0  # running counter across all keyword types

    if harvest:
        rows = ""
        for h in harvest[:20]:
            lbl = _label(lbl_idx)
            h["_label"] = lbl
            lbl_idx += 1
            rows += f"""<tr>
                <td style="padding:6px;border:1px solid #ddd;font-weight:bold;font-size:14px;text-align:center;background:#f5f5f5;width:30px;">{lbl}</td>
                <td style="padding:6px;border:1px solid #ddd;">{h['searchTerm']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{h['acos']}%</td>
                <td style="padding:6px;border:1px solid #ddd;">{h['purchases']}</td>
                <td style="padding:6px;border:1px solid #ddd;">${h['cost']}</td>
                <td style="padding:6px;border:1px solid #ddd;">${h['proposed_bid']}</td>
                <td style="padding:6px;border:1px solid #ddd;font-size:11px;">{h['sourceCampaignName']}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#28a745;margin-top:25px;">Keyword Harvesting ({len(harvest)} candidates)</h3>
        <p style="color:#666;font-size:13px;">Profitable search terms to add as exact match keywords in Manual campaign. <b>Execute by letter code (e.g., "Execute {_label(0)}, {_label(min(2,len(harvest)-1))}").</b></p>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#28a745;color:white;">
                <th style="padding:8px;">ID</th>
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
            lbl = _label(lbl_idx)
            n["_label"] = lbl
            lbl_idx += 1
            rows += f"""<tr>
                <td style="padding:6px;border:1px solid #ddd;font-weight:bold;font-size:14px;text-align:center;background:#f5f5f5;width:30px;">{lbl}</td>
                <td style="padding:6px;border:1px solid #ddd;">{n['searchTerm']}</td>
                <td style="padding:6px;border:1px solid #ddd;">${n['cost']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{n.get('sales', 0)}</td>
                <td style="padding:6px;border:1px solid #ddd;">{n['clicks']}</td>
                <td style="padding:6px;border:1px solid #ddd;font-size:11px;">{n['reason']}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#dc3545;margin-top:25px;">Negative Keywords ({len(negate)} candidates)</h3>
        <p style="color:#666;font-size:13px;">Unprofitable search terms to block in Auto campaign. <b>Execute by letter code.</b></p>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#dc3545;color:white;">
                <th style="padding:8px;">ID</th>
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
            lbl = _label(lbl_idx)
            b["_label"] = lbl
            lbl_idx += 1
            color = "#28a745" if "increase" in b.get("action", "") else "#dc3545"
            rows += f"""<tr>
                <td style="padding:6px;border:1px solid #ddd;font-weight:bold;font-size:14px;text-align:center;background:#f5f5f5;width:30px;">{lbl}</td>
                <td style="padding:6px;border:1px solid #ddd;">{b['keywordText']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{b.get('matchType', '')}</td>
                <td style="padding:6px;border:1px solid #ddd;">${b['current_bid']}</td>
                <td style="padding:6px;border:1px solid #ddd;color:{color};font-weight:bold;">${b['new_bid']}</td>
                <td style="padding:6px;border:1px solid #ddd;">{b.get('acos_pct') or '-'}%</td>
                <td style="padding:6px;border:1px solid #ddd;font-size:11px;">{b['reason']}</td>
            </tr>"""
        sections.append(f"""
        <h3 style="color:#fd7e14;margin-top:25px;">Keyword Bid Adjustments ({len(bid_adj)})</h3>
        <p style="color:#666;font-size:13px;"><b>Execute by letter code.</b></p>
        <table style="border-collapse:collapse;width:100%;">
            <tr style="background:#fd7e14;color:white;">
                <th style="padding:8px;">ID</th>
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
                        cc: str = DEFAULT_CC,
                        brand_key: str = "naeiae",
                        xp_context: Optional[Dict] = None,
                        analysis: Optional[Dict] = None,
                        kw_matrix: Optional[Dict] = None) -> Optional[str]:
    """Send proposal HTML email via send_gmail.py. Returns Gmail message ID or None."""
    cfg = BRAND_CONFIGS[brand_key]
    html = build_proposal_html(proposals, kw_proposals, brand_key=brand_key,
                               xp_context=xp_context, analysis=analysis, kw_matrix=kw_matrix)
    html_path = TMP_DIR / f"ppc_proposal_{brand_key}_{date.today().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.html"
    html_path.write_text(html, encoding="utf-8")

    kw_count = len(kw_proposals) if kw_proposals else 0
    anomaly_count = len(analysis.get("anomalies", [])) if analysis else 0
    s7 = analysis.get("summary", {}).get("7d", {}) if analysis else {}
    roas_7d_str = f" | ROAS {s7.get('roas', '?')}x" if s7 else ""

    action_count = len(proposals)
    data_date = analysis.get("latest_date", datetime.now().strftime("%Y-%m-%d")) if analysis else datetime.now().strftime("%Y-%m-%d")
    subject = (
        f"[Amazon PPC] {cfg['brand_display']} Daily{roas_7d_str} | "
        f"{action_count} actions, {kw_count} kw, {anomaly_count} anomalies"
        f" | data:{data_date}"
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
            _save_proposal_email_id(msg_id, subject, brand_key=brand_key)
            return msg_id
    else:
        print(f"[ERROR] Email failed: {result.stderr}")
        print(f"[INFO] HTML saved at: {html_path}")
    return None


def _save_proposal_email_id(message_id: str, subject: str, brand_key: str = "naeiae"):
    """Save the proposal email message ID to the latest proposal JSON."""
    proposal_path = sorted(TMP_DIR.glob(f"ppc_proposal_{brand_key}_*.json"), reverse=True)
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
                         cc: str = DEFAULT_CC, brand_key: str = "naeiae"):
    """Send execution confirmation email."""
    cfg = BRAND_CONFIGS[brand_key]
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
    <h2 style="color:{summary_color};">{cfg['brand_display']} PPC Changes Executed</h2>
    <p>{now} | {len(executed)} changes applied ({summary_text})</p>
    {camp_html}
    {kw_html}
    <p style="color:#999;font-size:12px;margin-top:24px;">Logged to Google Sheets PPC Change Log</p>
</body></html>"""

    html_path = TMP_DIR / f"ppc_executed_{date.today().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M')}.html"
    html_path.write_text(html, encoding="utf-8")

    subject = f"[Amazon PPC] {cfg['brand_display']} EXECUTED - {len(executed)} changes applied | {now}"
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
    """Run analysis every 6 hours, email proposals each time (all brands)."""
    brands = _resolve_brands(args)
    brand_names = ", ".join(BRAND_CONFIGS[b]["brand_display"] for b in brands)
    print(f"[Cycle] Starting 6-hour analysis cycle for {brand_names}")
    print(f"  Interval: {CYCLE_INTERVAL_HOURS}h | Emails to: {args.to}")

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
    """Poll Gmail for 'execute' reply to latest proposal emails, then auto-execute (per brand)."""
    brands = _resolve_brands(args)
    for bk in brands:
        _apply_brand_config(bk)
        _check_execute_for_brand(args, bk)


def _check_execute_for_brand(args, brand_key: str):
    """Check email and execute for a single brand."""
    cfg = BRAND_CONFIGS[brand_key]
    data = load_latest_proposal(brand_key=brand_key)
    if not data:
        print(f"[check-execute] No proposal found for {cfg['brand_display']}.")
        return

    # Already executed?
    if data.get("executed"):
        print(f"[check-execute] {cfg['brand_display']}: Latest proposal already executed. Skipping.")
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
                continue  # Reply is older than proposal -- ignore
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
    latest_path = sorted(TMP_DIR.glob(f"ppc_proposal_{brand_key}_*.json"), reverse=True)[0]
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

        log_to_sheets(executed, brand_key=brand_key)
        send_execution_email(executed, args.to, cc=args.cc, brand_key=brand_key)
        print(f"\n[check-execute] {cfg['brand_display']}: {len(executed)} changes auto-executed via email reply!")
    else:
        print(f"[check-execute] {cfg['brand_display']}: No approved items to execute.")


# ===========================================================================
# Main
# ===========================================================================

def run_propose_single(args, brand_key: str):
    """Core propose logic for a single brand."""
    _apply_brand_config(brand_key)
    cfg = BRAND_CONFIGS[brand_key]
    brand_display = cfg["brand_display"]

    print(f"\n{'#'*70}")
    print(f"  {brand_display} ({cfg['seller_name']}) - Proposal Analysis")
    print(f"  Budget: ${cfg['total_daily_budget']:,.0f}/day | ACOS targets: Manual {cfg['targeting']['MANUAL']['target_acos']}% / Auto {cfg['targeting']['AUTO']['target_acos']}%")
    print(f"{'#'*70}")

    print(f"\n[1/7] Finding {cfg['seller_name']} profile...")
    profile = get_brand_profile(brand_key)
    if not profile:
        print(f"[ERROR] {cfg['seller_name']} profile not found! Skipping.")
        return
    profile_id = profile["profile_id"]
    print(f"  Found: profile_id={profile_id}")

    print(f"\n[2/7] Collecting {args.days}d campaign data...")
    campaigns = fetch_campaigns(profile_id)
    print(f"  {len(campaigns)} campaigns found")

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=args.days - 1)

    # Primary: DataKeeper (cached, reliable). Fallback: direct API.
    dk_days = max(args.days, 35)  # Always need 30+ days for the 30d analysis window
    report_rows = fetch_report_from_datakeeper(brand_key, days=dk_days)
    if not report_rows:
        print("  [INFO] DataKeeper unavailable, falling back to direct API...")
        report_rows = fetch_sp_report(profile_id, start_date, end_date)
    print(f"  {len(report_rows)} daily metric rows collected")

    print(f"\n[3/7] Analyzing campaigns (ROAS framework)...")
    proposals, analysis = analyze_campaigns(campaigns, report_rows)
    all_camps = analysis["all_campaigns"]
    anomalies = analysis["anomalies"]
    summary = analysis["summary"]

    print(f"  {len(all_camps)} active campaigns analyzed")
    print(f"  {len(proposals)} action proposals, {len(anomalies)} anomalies detected")
    s7 = summary.get("7d", {})
    print(f"  7d Total: ${s7.get('spend', 0):,.0f} spend / ${s7.get('sales', 0):,.0f} sales / {s7.get('roas', 0)}x ROAS")

    # --- Search Term & Keyword Analysis ---
    kw_proposals = []
    kw_matrix = None
    st_rows = []
    kw_rows = []

    if not args.skip_keywords:
        # Use latest_date from analysis instead of end_date for proper alignment
        latest = analysis["summary"].get("latest_date", end_date)
        if isinstance(latest, str):
            latest = datetime.strptime(latest[:10], "%Y-%m-%d").date()
        st_start_7d = latest - timedelta(days=6)   # 7-day window
        st_start_30d = latest - timedelta(days=29)  # 30-day window
        print(f"\n[4/8] Fetching keyword reports (7d: {st_start_7d}~{latest}, 30d: {st_start_30d}~{latest})...")
        try:
            st_rows = fetch_search_term_report(profile_id, st_start_30d, latest)
            print(f"  {len(st_rows)} search term rows (30d)")

            # Fetch 7d and 30d keyword reports separately for trend analysis
            kw_rows_7d = fetch_keyword_report(profile_id, st_start_7d, latest)
            print(f"  {len(kw_rows_7d)} keyword rows (7d)")
            kw_rows_30d = fetch_keyword_report(profile_id, st_start_30d, latest)
            print(f"  {len(kw_rows_30d)} keyword rows (30d)")
            kw_rows = kw_rows_30d  # Use 30d for main analysis

            # Fetch DataForSEO FIRST so it can feed into both bid analysis and matrix
            print(f"\n[5/8] Fetching DataForSEO + analyzing search terms & keywords...")
            dataforseo = fetch_dataforseo_keywords(brand_key)

            st_analysis = analyze_search_terms(st_rows, campaigns, kw_rows)
            kw_bid_proposals = analyze_keyword_bids(kw_rows, campaigns, dataforseo=dataforseo)

            kw_proposals = st_analysis["harvest"] + st_analysis["negate"] + kw_bid_proposals
            print(f"  {len(st_analysis['harvest'])} harvest candidates")
            print(f"  {len(st_analysis['negate'])} negative candidates")
            print(f"  {len(kw_bid_proposals)} keyword bid adjustments")

            # Keyword performance matrix with 7d vs 30d trend
            print(f"\n[6/8] Building keyword performance matrix...")
            kw_matrix = build_keyword_performance_matrix(
                kw_rows_30d, st_rows, campaigns, dataforseo, kw_rows_7d=kw_rows_7d)
            print(f"  {kw_matrix['total_keywords']} keywords analyzed")
            print(f"  {len(kw_matrix.get('keyword_vs_google', []))} keywords matched to Google CPC")
            print(f"  {len(kw_matrix.get('cannibalization', []))} cannibalization alerts")
        except Exception as e:
            print(f"  [WARN] Search term/keyword analysis failed: {e}")
            import traceback; traceback.print_exc()
            print(f"  Continuing with campaign-level proposals only.")
    else:
        print(f"\n[4/8] Skipping keyword analysis (--skip-keywords)")
        print(f"[5/8] Skipped")
        print(f"[6/8] Skipped")

    # --- Cross-Platform Context (Google Ads, Meta, Shopify, Amazon Sales) ---
    print(f"\n[7/8] Fetching cross-platform context (Google Ads, Meta, Shopify)...")
    xp_context = {}
    try:
        xp_context = fetch_cross_platform_context(brand_key, days=args.days)
        if xp_context.get("insights"):
            for ins in xp_context["insights"]:
                print(f"  >> {ins}")
        else:
            print(f"  No cross-platform insights available")
    except Exception as e:
        print(f"  [WARN] Cross-platform analysis failed: {e}")

    # Always save and send -- even with 0 action proposals, the analysis is valuable
    filepath = save_proposal(proposals, profile_id, kw_proposals, brand_key=brand_key)
    if proposals:
        print_proposal_summary(proposals, brand_key=brand_key)
    if kw_proposals:
        print_keyword_summary(kw_proposals)

    print(f"\n[8/8] Sending {brand_display} proposal email...")
    send_proposal_email(proposals, args.to, kw_proposals, cc=args.cc, brand_key=brand_key,
                        xp_context=xp_context, analysis=analysis, kw_matrix=kw_matrix)


def run_propose(args):
    """Run propose for all requested brands (default: all 3)."""
    brands_to_run = _resolve_brands(args)
    print(f"\n[Multi-Brand Propose] Running for: {', '.join(BRAND_CONFIGS[b]['brand_display'] for b in brands_to_run)}")
    for brand_key in brands_to_run:
        try:
            run_propose_single(args, brand_key)
        except Exception as e:
            print(f"\n[ERROR] {BRAND_CONFIGS[brand_key]['brand_display']} propose failed: {e}")
            import traceback
            traceback.print_exc()


def _resolve_brands(args) -> List[str]:
    """Resolve which brands to run based on --brand arg."""
    if hasattr(args, 'brand') and args.brand:
        brand = args.brand.lower().strip()
        # Allow aliases
        aliases = {
            "naeiae": "naeiae", "fleeters": "naeiae",
            "grosmimi": "grosmimi", "gros": "grosmimi",
            "chaenmom": "chaenmom", "orbitool": "chaenmom", "cha&mom": "chaenmom", "chamom": "chaenmom",
        }
        key = aliases.get(brand, brand)
        if key not in BRAND_CONFIGS:
            print(f"[ERROR] Unknown brand '{args.brand}'. Available: {', '.join(ALL_BRAND_KEYS)}")
            sys.exit(1)
        return [key]
    return ALL_BRAND_KEYS


def main():
    parser = argparse.ArgumentParser(description="Amazon PPC Executor (Multi-Brand: Naeiae, Grosmimi, CHA&MOM)")
    parser.add_argument("--propose", action="store_true", help="Analyze & email change proposals")
    parser.add_argument("--execute", action="store_true", help="Execute approved changes from latest proposal")
    parser.add_argument("--check-execute", action="store_true", help="Poll Gmail for 'execute' reply and auto-execute")
    parser.add_argument("--status", action="store_true", help="Show latest proposal status")
    parser.add_argument("--cycle", action="store_true", help="Run 6-hour analysis cycle")
    parser.add_argument("--brand", type=str, default=None,
                        help="Target brand: naeiae/grosmimi/chaenmom (default: all)")
    parser.add_argument("--days", type=int, default=14, help="Days of data to analyze (default: 14, max 60)")
    parser.add_argument("--to", type=str, default=DEFAULT_TO, help="Email recipient")
    parser.add_argument("--cc", type=str, default=DEFAULT_CC, help="CC email recipient")
    parser.add_argument("--skip-keywords", action="store_true",
                        help="Skip search term & keyword analysis (faster, campaign-level only)")
    args = parser.parse_args()

    if args.status:
        brands = _resolve_brands(args)
        for bk in brands:
            data = load_latest_proposal(brand_key=bk)
            if not data:
                print(f"[INFO] No proposals found for {BRAND_CONFIGS[bk]['brand_display']}")
                continue
            proposals = data["proposals"]
            approved_count = sum(1 for p in proposals if p.get("approved"))
            print(f"\n{'='*50}")
            print(f"Latest proposal: {data['generated_at']}")
            print(f"Brand: {data['brand']} ({data['seller']})")
            print(f"Total: {len(proposals)} proposals, {approved_count} approved")
            for p in proposals:
                status = "[APPROVED]" if p.get("approved") else "[pending]"
                print(f"  {status} {p['proposed_action']:>16} | [{p.get('campaignType','?')}] {p['campaignName']} | 7d ROAS {p['metrics']['7d']['roas']}x")
        return

    if args.execute:
        brands = _resolve_brands(args)
        for bk in brands:
            _apply_brand_config(bk)
            data = load_latest_proposal(brand_key=bk)
            if not data:
                print(f"[ERROR] No proposal found for {BRAND_CONFIGS[bk]['brand_display']}. Run --propose first.")
                continue
            executed = execute_approved(data)
            if executed:
                latest_path = sorted(TMP_DIR.glob(f"ppc_proposal_{bk}_*.json"), reverse=True)
                if latest_path:
                    data["executed"] = True
                    data["executed_at"] = datetime.now().isoformat()
                    latest_path[0].write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                log_to_sheets(executed, brand_key=bk)
                send_execution_email(executed, args.to, cc=args.cc, brand_key=bk)
                print(f"\n[DONE] {BRAND_CONFIGS[bk]['brand_display']}: {len(executed)} changes executed, logged, and emailed.")
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
