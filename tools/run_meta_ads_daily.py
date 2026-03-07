"""
run_meta_ads_daily.py - Meta Ads 일간 분석 에이전트

신규 광고 퍼포먼스 + 우수 광고 D+N 동 시점 비교 + Traffic/CVR 분리 + 브랜드별

Usage:
    python tools/run_meta_ads_daily.py
    python tools/run_meta_ads_daily.py --dry-run
    python tools/run_meta_ads_daily.py --days 60 --to wj.choi@orbiters.co.kr
    python tools/run_meta_ads_daily.py --new-window 7  # "신규" 기준 일수
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent

ACCESS_TOKEN    = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID   = os.getenv("META_AD_ACCOUNT_ID")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")
API_VERSION     = "v18.0"
BASE_URL        = f"https://graph.facebook.com/{API_VERSION}"


# ===========================================================================
# Brand + Campaign Type Classification
# ===========================================================================

BRAND_RULES = [
    # GM = Grosmimi campaign code (e.g. "Shopify | CVR | GM | Stainless")
    ("Grosmimi",    ["grosmimi", "grosm", "grossmimi", "ppsu", "stainless steel", "sls cup",
                     "stainless straw", "| gm |", " gm |", "| gm_", "_gm_", "gm_tumbler",
                     "dentalmom", "dental mom", "dental_mom", "livfuselli"]),
    # Love&Care = CHA&MOM line; CM = CHA&MOM campaign code
    ("CHA&MOM",     ["cha&mom", "cha_mom", "chamom", "| cm |", " cm |", "| cm_", "_cm_",
                     "skincare", "lotion", "hair wash", "love&care", "love_care", "love care"]),
    ("Alpremio",    ["alpremio"]),
    ("Easy Shower", ["easy shower", "easy_shower", "easyshower", "shower stand"]),
    ("Hattung",     ["hattung"]),
    ("Beemymagic",  ["beemymagic", "beemy"]),
    ("Comme Moi",   ["commemoi", "comme moi", "commemo"]),
    ("BabyRabbit",  ["babyrabbit", "baby rabbit"]),
    ("Naeiae",      ["naeiae", "rice snack", "pop rice"]),
    ("RIDE & GO",   ["ride & go", "ridego", "ride_go"]),
    ("BambooeBebe", ["bamboobebe"]),
    # Promo = cross-brand or seasonal promo campaigns (no single brand owner)
    ("Promo",       ["newyear", "new year", "new_year", "asc campaign (legacy)",
                     "promo campaign", "promo_campaign"]),
]

def classify_brand(name: str) -> str:
    n = name.lower()
    for brand, kws in BRAND_RULES:
        if any(k in n for k in kws):
            return brand
    return "Non-classified"

# URL-based brand classification (landing page domain/path matching)
BRAND_URL_RULES = [
    ("Grosmimi",    ["grosmimi"]),
    ("CHA&MOM",     ["cha-mom", "chamom", "cha_mom"]),
    ("Alpremio",    ["alpremio"]),
    ("Easy Shower", ["easy-shower", "easyshower"]),
    ("Hattung",     ["hattung"]),
    ("Beemymagic",  ["beemymagic"]),
    ("Comme Moi",   ["commemoi", "comme-moi"]),
    ("BabyRabbit",  ["babyrabbit", "baby-rabbit"]),
    ("Naeiae",      ["naeiae"]),
    ("RIDE & GO",   ["ridego", "ride-go"]),
    ("BambooeBebe", ["bamboobebe"]),
]

def classify_brand_from_url(url: str) -> str:
    u = url.lower()
    # Direct domain/path match
    for brand, kws in BRAND_URL_RULES:
        if any(k in u for k in kws):
            return brand
    # Amazon URL: extract brand from search query or store path
    if "amazon." in u:
        # /s?k=brand+product → parse search keyword
        if "?" in url:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            kw = " ".join(parsed.get("k", []))
            if kw:
                b = classify_brand(kw)
                if b != "Non-classified":
                    return b
        # /stores/BrandName/ → extract store name
        import re
        m = re.search(r"/stores/([^/?]+)", url, re.IGNORECASE)
        if m:
            b = classify_brand(m.group(1).replace("-", " ").replace("_", " "))
            if b != "Non-classified":
                return b
        # /dp/ASIN + title keywords in URL path
        b = classify_brand(url)
        if b != "Non-classified":
            return b
    return "Non-classified"

TRAFFIC_OBJECTIVES = {
    "LINK_CLICKS", "REACH", "BRAND_AWARENESS", "VIDEO_VIEWS",
    "POST_ENGAGEMENT", "PAGE_LIKES", "EVENT_RESPONSES",
    "OUTCOME_TRAFFIC", "OUTCOME_AWARENESS", "OUTCOME_ENGAGEMENT",
}
CVR_OBJECTIVES = {
    "CONVERSIONS", "PRODUCT_CATALOG_SALES", "STORE_TRAFFIC",
    "OUTCOME_SALES", "OUTCOME_LEADS", "APP_INSTALLS",
}

def classify_campaign_type(objective: str) -> str:
    obj = (objective or "").upper()
    if obj in TRAFFIC_OBJECTIVES:
        return "traffic"
    if obj in CVR_OBJECTIVES:
        return "cvr"
    return "other"


# ===========================================================================
# Meta Graph API helpers
# ===========================================================================

def _api_get(path: str, params: dict, timeout: int = 120, retries: int = 3) -> dict:
    params["access_token"] = ACCESS_TOKEN
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            err_msg = body.get('error', {}).get('message', str(e))
            code = e.code
            if code >= 500 and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"\n    [WARN] Meta API {code}, retry {attempt+1}/{retries} in {wait}s...", flush=True)
                import time; time.sleep(wait)
                continue
            raise Exception(f"Meta API: {err_msg}")
        except Exception as e:
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"\n    [WARN] {e}, retry {attempt+1}/{retries} in {wait}s...", flush=True)
                import time; time.sleep(wait)
                continue
            raise

def _fetch_all(path: str, params: dict) -> list:
    results = []
    while True:
        data = _api_get(path, params)
        results.extend(data.get("data", []))
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            break
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(nxt).query)
        after = qs.get("after", [None])[0]
        if not after:
            break
        params = {**params, "after": after}
    return results

def fetch_campaign_objectives() -> Dict[str, str]:
    """Returns {campaign_id: campaign_type}"""
    print("  Fetching campaign objectives...")
    items = _fetch_all(f"/{AD_ACCOUNT_ID}/campaigns", {
        "fields": "id,objective",
        "limit": 500,
    })
    result = {c["id"]: classify_campaign_type(c.get("objective", "")) for c in items}
    print(f"  -> {len(result)} campaigns")
    return result

def fetch_ad_landing_pages() -> Dict[str, str]:
    """Returns {ad_id: landing_page_url} for brand classification fallback."""
    print("  Fetching ad landing pages...")
    try:
        items = _fetch_all(f"/{AD_ACCOUNT_ID}/ads", {
            "fields": "id,creative{object_url,object_story_spec{link_data{link},video_data{call_to_action{value{link}}}}}",
            "limit": 100,
        })
        result = {}
        for item in items:
            cr  = item.get("creative", {})
            url = cr.get("object_url", "")
            if not url:
                oss = cr.get("object_story_spec", {})
                url = (oss.get("link_data", {}).get("link", "") or
                       oss.get("video_data", {}).get("call_to_action", {})
                           .get("value", {}).get("link", ""))
            if url:
                result[item["id"]] = url
        print(f"  -> {len(result)} ads with landing URLs")
        return result
    except Exception as e:
        print(f"  ! Landing page fetch failed: {e} (skipping)")
        return {}

def fetch_ad_daily_insights(since: str, until: str) -> list:
    """Ad-level daily rows — fetched in 30-day chunks to avoid timeout."""
    fields = ",".join([
        "ad_id", "ad_name", "adset_id", "adset_name",
        "campaign_id", "campaign_name",
        "spend", "impressions", "clicks", "reach", "frequency",
        "actions", "action_values",
    ])

    all_raw = []
    cur = datetime.strptime(since, "%Y-%m-%d").date()
    end = datetime.strptime(until, "%Y-%m-%d").date()

    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=14))
        since_s = cur.strftime("%Y-%m-%d")
        until_s = chunk_end.strftime("%Y-%m-%d")
        print(f"  Fetching ad insights {since_s} ~ {until_s}...", end=" ", flush=True)
        chunk = _fetch_all(f"/{AD_ACCOUNT_ID}/insights", {
            "fields": fields,
            "level": "ad",
            "time_range": json.dumps({"since": since_s, "until": until_s}),
            "time_increment": 1,
            "limit": 500,
        })
        print(f"{len(chunk)} rows")
        all_raw.extend(chunk)
        cur = chunk_end + timedelta(days=1)

    print(f"  -> Total {len(all_raw)} raw daily rows")
    return all_raw

def _extract_purchases(actions, action_values) -> Tuple[int, float]:
    purchases, value = 0, 0.0
    purchase_types = ("purchase", "offsite_conversion.fb_pixel_purchase")
    for a in (actions or []):
        if a.get("action_type") in purchase_types:
            purchases += int(float(a.get("value", 0)))
    for av in (action_values or []):
        if av.get("action_type") in purchase_types:
            value += float(av.get("value", 0))
    return purchases, value

def process_insights(raw: list) -> list:
    rows = []
    for r in raw:
        p, pv = _extract_purchases(r.get("actions"), r.get("action_values"))
        rows.append({
            "date":          r.get("date_start", ""),
            "ad_id":         r.get("ad_id", ""),
            "ad_name":       r.get("ad_name", ""),
            "adset_name":    r.get("adset_name", ""),
            "campaign_id":   r.get("campaign_id", ""),
            "campaign_name": r.get("campaign_name", ""),
            "spend":         float(r.get("spend", 0) or 0),
            "impressions":   int(r.get("impressions", 0) or 0),
            "clicks":        int(r.get("clicks", 0) or 0),
            "reach":         int(r.get("reach", 0) or 0),
            "frequency":     float(r.get("frequency", 0) or 0),
            "purchases":     p,
            "purchases_value": pv,
        })
    return rows


# ===========================================================================
# D+N Analysis Engine
# ===========================================================================

def build_ad_histories(rows: list, campaign_types: Dict[str, str],
                       landing_pages: Dict[str, str] = None) -> Dict[str, dict]:
    """Group rows by ad_id. Attach brand + campaign_type. Compute first_spend_date."""
    by_ad: Dict[str, list] = defaultdict(list)
    meta: Dict[str, dict] = {}

    for r in rows:
        ad_id = r["ad_id"]
        by_ad[ad_id].append(r)
        if ad_id not in meta:
            meta[ad_id] = {
                "ad_name":       r["ad_name"],
                "adset_name":    r["adset_name"],
                "campaign_id":   r["campaign_id"],
                "campaign_name": r["campaign_name"],
            }

    histories = {}
    for ad_id, daily in by_ad.items():
        daily_sorted = sorted(daily, key=lambda x: x["date"])
        spend_days = [d for d in daily_sorted if d["spend"] > 0]
        if not spend_days:
            continue

        first_spend = datetime.strptime(spend_days[0]["date"], "%Y-%m-%d").date()
        camp_id = meta[ad_id]["campaign_id"]
        ad_name = meta[ad_id]["ad_name"]
        camp_name = meta[ad_id]["campaign_name"]

        adset_name = meta[ad_id]["adset_name"]
        brand = classify_brand(ad_name)
        if brand == "Non-classified":
            brand = classify_brand(camp_name)
        if brand == "Non-classified":
            brand = classify_brand(adset_name)
        landing_url = landing_pages.get(ad_id, "") if landing_pages else ""
        if landing_url and brand == "Non-classified":
            brand = classify_brand_from_url(landing_url)

        camp_type = campaign_types.get(camp_id, "other")
        camp_lower  = camp_name.lower()
        ad_lower    = ad_name.lower()

        # Override 1: campaign name contains "CVR" → force cvr type
        # (user naming convention trumps Meta objective)
        if "cvr" in camp_lower and camp_type != "cvr":
            camp_type = "cvr"

        # Override 2: Amazon-landing campaigns → traffic (no Meta pixel conversion)
        # BUT skip if campaign is explicitly named CVR (Shopify pixel present)
        AMAZON_SIGNALS = ("wl_", "| wl |", " wl | ", "whitelist", "amazon", "amz", "asin")
        AMAZON_BRANDS  = ("naeiae", "rice snack", "pop rice")
        url_is_amazon = "amazon." in landing_url.lower() if landing_url else False
        if camp_type != "traffic" and "cvr" not in camp_lower and (
            any(s in camp_lower or s in ad_lower for s in AMAZON_SIGNALS) or
            any(s in camp_lower or s in ad_lower for s in AMAZON_BRANDS) or
            url_is_amazon
        ):
            camp_type = "traffic"

        histories[ad_id] = {
            **meta[ad_id],
            "brand":             brand,
            "campaign_type":     camp_type,
            "daily":             daily_sorted,
            "first_spend_date":  first_spend,
        }
    return histories

def _cumulative(daily: list, first_spend: date, up_to_day_n: int) -> dict:
    """Sum metrics from D+0 to D+up_to_day_n (inclusive)."""
    sp = impr = cl = pu = 0
    pv = 0.0
    for r in daily:
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        dn = (d - first_spend).days
        if 0 <= dn <= up_to_day_n:
            sp   += r["spend"]
            impr += r["impressions"]
            cl   += r["clicks"]
            pu   += r["purchases"]
            pv   += r["purchases_value"]
    return {
        "spend":           round(sp, 2),
        "impressions":     impr,
        "clicks":          cl,
        "purchases":       pu,
        "purchases_value": round(pv, 2),
        "roas": round(pv / sp, 3)          if sp > 0 else 0,
        "ctr":  round(cl / impr * 100, 3)  if impr > 0 else 0,
        "cpc":  round(sp / cl, 3)          if cl > 0 else 0,
        "cpm":  round(sp / impr * 1000, 3) if impr > 0 else 0,
        "cpa":  round(sp / pu, 3)          if pu > 0 else 0,
        "cvr":  round(pu / cl * 100, 3)    if cl > 0 else 0,
    }

def _day_n(h: dict, today: date) -> int:
    return (today - h["first_spend_date"]).days

def build_day_n_benchmark(top_performers: dict, target_dn: int, camp_type: str) -> Optional[dict]:
    """
    Average metrics of same-type top performers at their D+target_dn.
    Only uses top performers that ran at least target_dn days.
    """
    type_tops = {k: v for k, v in top_performers.items()
                 if v["campaign_type"] == camp_type}
    samples = []
    for ad_id, h in type_tops.items():
        if h["day_n"] < target_dn:
            continue
        m = _cumulative(h["daily"], h["first_spend_date"], target_dn)
        if m["spend"] > 0:
            samples.append(m)
    if not samples:
        return None
    n = len(samples)
    return {
        "n_ads":     n,
        "avg_roas":  round(sum(s["roas"] for s in samples) / n, 3),
        "avg_ctr":   round(sum(s["ctr"]  for s in samples) / n, 3),
        "avg_cpc":   round(sum(s["cpc"]  for s in samples) / n, 3),
        "avg_cpm":   round(sum(s["cpm"]  for s in samples) / n, 3),
        "avg_cpa":   round(sum(s["cpa"]  for s in samples) / n, 3),
        "avg_cvr":   round(sum(s["cvr"]  for s in samples) / n, 3),
        "avg_spend": round(sum(s["spend"] for s in samples) / n, 2),
    }

def _vs_benchmark(metrics: dict, bench: dict, camp_type: str) -> dict:
    """Compute % diff vs benchmark. Positive = better for ROAS/CTR/CVR, worse for CPM/CPC/CPA."""
    def pct(a, b_key):
        b = bench.get(b_key, 0)
        return round((a - b) / b * 100, 1) if b > 0 else None

    result = {}
    if camp_type == "cvr":
        result["roas_vs_bench"] = pct(metrics["roas"], "avg_roas")
        result["cpa_vs_bench"]  = pct(metrics["cpa"],  "avg_cpa")   # lower is better → negate sign in HTML
        result["cvr_vs_bench"]  = pct(metrics["cvr"],  "avg_cvr")
    result["ctr_vs_bench"]  = pct(metrics["ctr"],  "avg_ctr")
    result["cpm_vs_bench"]  = pct(metrics["cpm"],  "avg_cpm")   # lower is better
    result["cpc_vs_bench"]  = pct(metrics["cpc"],  "avg_cpc")   # lower is better
    return result


# ===========================================================================
def _period_metrics_raw(daily: list, start: date, end: date) -> dict:
    """Aggregate daily rows for an ad within [start, end]. Standalone version."""
    sp = impr = cl = pu = 0; pv = 0.0
    for r in daily:
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        if start <= d <= end:
            sp   += r["spend"]; impr += r["impressions"]
            cl   += r["clicks"]; pu  += r["purchases"]
            pv   += r["purchases_value"]
    return {
        "spend": round(sp, 2),
        "roas":  round(pv / sp, 3)          if sp > 0 else 0,
        "ctr":   round(cl / impr * 100, 3)  if impr > 0 else 0,
        "cpc":   round(sp / cl, 3)          if cl > 0 else 0,
        "cpm":   round(sp / impr * 1000, 3) if impr > 0 else 0,
        "cpa":   round(sp / pu, 3)          if pu > 0 else 0,
    }

# ===========================================================================
# Build full analysis payload
# ===========================================================================

def build_payload(
    rows: list,
    campaign_types: Dict[str, str],
    today: date,
    new_window: int = 7,
    landing_pages: Dict[str, str] = None,
) -> dict:
    print("\n[Step 2] Building analysis payload...")
    histories = build_ad_histories(rows, campaign_types, landing_pages)
    print(f"  Active ads with spend: {len(histories)}")

    since_30 = today - timedelta(days=30)
    cutoff_new = today - timedelta(days=new_window)

    # --- Classify new vs established ---
    new_ads = {k: v for k, v in histories.items()
               if v["first_spend_date"] >= cutoff_new}

    top_performers = {}
    since_7_eval = today - timedelta(days=7)
    yesterday_eval = today - timedelta(days=1)
    for ad_id, h in histories.items():
        dn = _day_n(h, today)
        if dn < 14:
            continue
        m_life = _cumulative(h["daily"], h["first_spend_date"], dn)
        if m_life["spend"] < 50:
            continue
        # Evaluate on RECENT 7-day performance
        m7 = _period_metrics_raw(h["daily"], since_7_eval, yesterday_eval)
        if m7["spend"] < 10:
            continue
        # Good ROAS (CVR) OR good CTR (Traffic) — 7-day basis
        if m7["roas"] >= 3.0 or (h["campaign_type"] == "traffic" and m7["ctr"] >= 1.5):
            top_performers[ad_id] = {**h, "day_n": dn, "lifetime_metrics": m_life, "metrics_7d_eval": m7}

    print(f"  New ads (last {new_window}d): {len(new_ads)}")
    print(f"  Top performers (established): {len(top_performers)}")

    # --- New Ads Section ---
    new_ads_data = []
    for ad_id, h in sorted(new_ads.items(),
                            key=lambda x: x[1]["first_spend_date"], reverse=True):
        dn = _day_n(h, today)
        cum = _cumulative(h["daily"], h["first_spend_date"], dn)
        if cum["spend"] == 0:
            continue

        bench = build_day_n_benchmark(top_performers, dn, h["campaign_type"])
        vs    = _vs_benchmark(cum, bench, h["campaign_type"]) if bench else None

        new_ads_data.append({
            "ad_name":        h["ad_name"][:70],
            "adset_name":     h["adset_name"][:70],
            "campaign_name":  h["campaign_name"][:70],
            "brand":          h["brand"],
            "campaign_type":  h["campaign_type"],
            "first_spend":    h["first_spend_date"].strftime("%Y-%m-%d"),
            "day_n":          dn,
            "metrics":        cum,
            "benchmark":      bench,
            "vs_benchmark":   vs,
        })

    # Sort: CVR first, then Traffic; within each group by ROAS or CTR
    new_ads_data.sort(key=lambda x: (
        0 if x["campaign_type"] == "cvr" else 1,
        -(x["metrics"]["roas"] if x["campaign_type"] == "cvr" else x["metrics"]["ctr"])
    ))

    # --- Brand + Type Breakdown (30d, 7d, prior 7d) ---
    yesterday     = today - timedelta(days=1)
    since_7       = today - timedelta(days=7)

    def _period_metrics(daily: list, start: date, end: date) -> dict:
        """Aggregate daily rows for an ad within [start, end]."""
        sp = impr = cl = pu = 0; pv = 0.0
        for r in daily:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if start <= d <= end:
                sp   += r["spend"]; impr += r["impressions"]
                cl   += r["clicks"]; pu  += r["purchases"]
                pv   += r["purchases_value"]
        return {
            "spend": round(sp, 2),
            "roas":  round(pv / sp, 3)          if sp > 0 else 0,
            "ctr":   round(cl / impr * 100, 3)  if impr > 0 else 0,
            "cpc":   round(sp / cl, 3)          if cl > 0 else 0,
            "cpm":   round(sp / impr * 1000, 3) if impr > 0 else 0,
            "cpa":   round(sp / pu, 3)          if pu > 0 else 0,
        }

    prior_7_start = today - timedelta(days=14)
    prior_7_end   = today - timedelta(days=8)

    # --- Top Performers Summary — sorted by 7-day ROAS/CTR ---
    top_list = sorted(
        top_performers.items(),
        key=lambda kv: (
            0 if kv[1]["campaign_type"] == "cvr" else 1,
            -(kv[1]["metrics_7d_eval"]["roas"] if kv[1]["campaign_type"] == "cvr"
              else kv[1]["metrics_7d_eval"]["ctr"])
        )
    )[:20]
    top_summary = [{
        "ad_id":         ad_id,
        "campaign_id":   h["campaign_id"],
        "ad_name":       h["ad_name"][:70],
        "campaign_name": h["campaign_name"][:70],
        "brand":         h["brand"],
        "campaign_type": h["campaign_type"],
        "first_spend":   h["first_spend_date"].strftime("%Y-%m-%d"),
        "day_n":         h["day_n"],
        "roas":          h["metrics_7d_eval"]["roas"],
        "ctr":           h["metrics_7d_eval"]["ctr"],
        "cpm":           h["metrics_7d_eval"]["cpm"],
        "cpa":           h["metrics_7d_eval"]["cpa"],
        "spend":         h["lifetime_metrics"]["spend"],
        "metrics_1d":    _period_metrics(h["daily"], yesterday,     yesterday),
        "metrics_7d":    _period_metrics(h["daily"], since_7,       yesterday),
        "metrics_p7d":   _period_metrics(h["daily"], prior_7_start, prior_7_end),
        "metrics_30d":   _period_metrics(h["daily"], since_30,      yesterday),
    } for ad_id, h in top_list]

    # --- Worst Performers (D+14+, significant spend, bad 7-day metric) ---
    worst_performers = {}
    for ad_id, h in histories.items():
        dn = _day_n(h, today)
        if dn < 14:
            continue
        m_life = _cumulative(h["daily"], h["first_spend_date"], dn)
        if m_life["spend"] < 100:
            continue
        # Evaluate on RECENT 7-day performance
        m7 = _period_metrics_raw(h["daily"], since_7_eval, yesterday_eval)
        if m7["spend"] < 10:
            continue
        if h["campaign_type"] in ("cvr", "other") and m7["roas"] < 2.0:
            worst_performers[ad_id] = {**h, "day_n": dn, "lifetime_metrics": m_life, "metrics_7d_eval": m7}
        elif h["campaign_type"] == "traffic" and m7["ctr"] < 1.0:
            worst_performers[ad_id] = {**h, "day_n": dn, "lifetime_metrics": m_life, "metrics_7d_eval": m7}

    worst_list = sorted(
        worst_performers.items(),
        key=lambda kv: (
            0 if kv[1]["campaign_type"] == "cvr" else 1,
            (kv[1]["metrics_7d_eval"]["roas"] if kv[1]["campaign_type"] == "cvr"
             else kv[1]["metrics_7d_eval"]["ctr"])  # ascending: worst first
        )
    )[:20]
    worst_summary = [{
        "ad_id":         ad_id,
        "campaign_id":   h["campaign_id"],
        "ad_name":       h["ad_name"][:70],
        "campaign_name": h["campaign_name"][:70],
        "brand":         h["brand"],
        "campaign_type": h["campaign_type"],
        "first_spend":   h["first_spend_date"].strftime("%Y-%m-%d"),
        "day_n":         h["day_n"],
        "roas":          h["metrics_7d_eval"]["roas"],
        "ctr":           h["metrics_7d_eval"]["ctr"],
        "spend":         h["lifetime_metrics"]["spend"],
        "metrics_1d":    _period_metrics(h["daily"], yesterday,     yesterday),
        "metrics_7d":    _period_metrics(h["daily"], since_7,       yesterday),
        "metrics_p7d":   _period_metrics(h["daily"], prior_7_start, prior_7_end),
        "metrics_30d":   _period_metrics(h["daily"], since_30,      yesterday),
    } for ad_id, h in worst_list]
    print(f"  Worst performers (D+14, bad metric): {len(worst_performers)}")

    def _bucket_rows(start: date, end: date):
        brand_b: Dict[str, dict] = defaultdict(
            lambda: {"spend": 0.0, "impr": 0, "clicks": 0, "pu": 0, "pv": 0.0}
        )
        type_b: Dict[str, dict] = defaultdict(
            lambda: {"spend": 0.0, "impr": 0, "clicks": 0, "pu": 0, "pv": 0.0, "ad_count": set()}
        )
        for r in rows:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if d < start or d > end:
                continue
            brand = histories.get(r["ad_id"], {}).get("brand") or classify_brand(r["ad_name"])
            b = brand_b[brand]
            b["spend"] += r["spend"]; b["impr"] += r["impressions"]
            b["clicks"] += r["clicks"]; b["pu"] += r["purchases"]
            b["pv"] += r["purchases_value"]

            ctype = histories.get(r["ad_id"], {}).get("campaign_type", "other")
            t = type_b[ctype]
            t["spend"] += r["spend"]; t["impr"] += r["impressions"]
            t["clicks"] += r["clicks"]; t["pu"] += r["purchases"]
            t["pv"] += r["purchases_value"]; t["ad_count"].add(r["ad_id"])
        return brand_b, type_b

    def _to_brand_list(bucket: dict) -> list:
        out = []
        for brand, v in sorted(bucket.items(), key=lambda x: -x[1]["spend"]):
            sp = v["spend"]; im = v["impr"]; cl = v["clicks"]; pv = v["pv"]; pu = v["pu"]
            out.append({
                "brand":     brand,
                "spend":     round(sp, 2),
                "revenue":   round(pv, 2),
                "roas":      round(pv / sp, 3) if sp > 0 else 0,
                "ctr":       round(cl / im * 100, 3) if im > 0 else 0,
                "cpm":       round(sp / im * 1000, 3) if im > 0 else 0,
                "cpa":       round(sp / pu, 3) if pu > 0 else 0,
                "purchases": pu,
            })
        return out

    def _to_type_summary(bucket: dict) -> dict:
        out = {}
        for ctype, v in bucket.items():
            sp = v["spend"]; im = v["impr"]; cl = v["clicks"]; pv = v["pv"]; pu = v["pu"]
            out[ctype] = {
                "spend":    round(sp, 2),
                "revenue":  round(pv, 2),
                "roas":     round(pv / sp, 3) if sp > 0 else 0,
                "ctr":      round(cl / im * 100, 3) if im > 0 else 0,
                "cpm":      round(sp / im * 1000, 3) if im > 0 else 0,
                "cpc":      round(sp / cl, 3) if cl > 0 else 0,
                "cpa":      round(sp / pu, 3) if pu > 0 else 0,
                "ad_count": len(v["ad_count"]),
            }
        return out

    def _bucket_by_brand_type(start: date, end: date) -> dict:
        """Per-brand, per-campaign-type aggregation for a time window."""
        b: Dict[str, Dict[str, dict]] = defaultdict(lambda: defaultdict(
            lambda: {"spend": 0.0, "impr": 0, "clicks": 0, "pu": 0, "pv": 0.0, "ids": set()}
        ))
        for r in rows:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if d < start or d > end:
                continue
            brand = histories.get(r["ad_id"], {}).get("brand") or classify_brand(r["ad_name"])
            ctype = histories.get(r["ad_id"], {}).get("campaign_type", "other")
            v = b[brand][ctype]
            v["spend"] += r["spend"]; v["impr"] += r["impressions"]
            v["clicks"] += r["clicks"]; v["pu"] += r["purchases"]
            v["pv"] += r["purchases_value"]; v["ids"].add(r["ad_id"])
        result = {}
        for brand, by_type in b.items():
            result[brand] = {}
            for ct, v in by_type.items():
                sp = v["spend"]; im = v["impr"]; cl = v["clicks"]
                pv = v["pv"];    pu = v["pu"]
                result[brand][ct] = {
                    "spend": round(sp, 2),
                    "roas":  round(pv / sp, 2)         if sp > 0 else 0,
                    "ctr":   round(cl / im * 100, 2)   if im > 0 else 0,
                    "cpc":   round(sp / cl, 2)          if cl > 0 else 0,
                    "cpa":   round(sp / pu, 2)          if pu > 0 else 0,
                    "ads":   len(v["ids"]),
                }
        return result

    bbt_1d  = _bucket_by_brand_type(yesterday,     yesterday)
    bbt_7d  = _bucket_by_brand_type(since_7,        yesterday)
    bbt_p7d = _bucket_by_brand_type(prior_7_start,  prior_7_end)
    bbt_30d = _bucket_by_brand_type(since_30,       yesterday)

    all_detail_brands = sorted(
        set(list(bbt_1d.keys()) + list(bbt_7d.keys()) + list(bbt_30d.keys())),
        key=lambda x: -(
            bbt_30d.get(x, {}).get("cvr", {}).get("spend", 0) +
            bbt_30d.get(x, {}).get("traffic", {}).get("spend", 0)
        )
    )
    brand_detail_table = [
        {
            "brand": brand,
            "1d":    bbt_1d.get(brand, {}),
            "7d":    bbt_7d.get(brand, {}),
            "p7d":   bbt_p7d.get(brand, {}),
            "30d":   bbt_30d.get(brand, {}),
        }
        for brand in all_detail_brands
    ]

    brand_b1d, type_b1d = _bucket_rows(yesterday,       yesterday)
    brand_b30, type_b30 = _bucket_rows(since_30,        yesterday)
    brand_b7,  type_b7  = _bucket_rows(since_7,         yesterday)
    brand_bp7, type_bp7 = _bucket_rows(prior_7_start,   prior_7_end)

    brand_breakdown_1d = _to_brand_list(brand_b1d)
    brand_breakdown_30 = _to_brand_list(brand_b30)
    brand_breakdown_7  = _to_brand_list(brand_b7)
    brand_breakdown_p7 = _to_brand_list(brand_bp7)
    type_summary_1d    = _to_type_summary(type_b1d)
    type_summary_30    = _to_type_summary(type_b30)
    type_summary_7     = _to_type_summary(type_b7)
    type_summary_p7    = _to_type_summary(type_bp7)

    # Build brand comparison (최근 7일 / 이전 7일 / 최근 30일)
    b1d_map = {b["brand"]: b for b in brand_breakdown_1d}
    b30_map = {b["brand"]: b for b in brand_breakdown_30}
    b7_map  = {b["brand"]: b for b in brand_breakdown_7}
    bp7_map = {b["brand"]: b for b in brand_breakdown_p7}
    brand_comparison = []
    all_brands = sorted(set(list(b30_map.keys()) + list(b7_map.keys())),
                        key=lambda x: -(b30_map.get(x, {}).get("spend", 0)))
    for brand in all_brands:
        b1d = b1d_map.get(brand, {})
        b30 = b30_map.get(brand, {})
        b7  = b7_map.get(brand, {})
        bp7 = bp7_map.get(brand, {})
        roas_7  = b7.get("roas", 0)
        roas_p7 = bp7.get("roas", 0)
        roas_30 = b30.get("roas", 0)
        # WoW = this 7d vs prior 7d
        roas_wow = round((roas_7 - roas_p7) / roas_p7 * 100, 1) if roas_p7 > 0 else None
        ctr_wow  = round((b7.get("ctr",0) - bp7.get("ctr",0)) / bp7.get("ctr",1) * 100, 1) \
                   if bp7.get("ctr", 0) > 0 else None
        brand_comparison.append({
            "brand":       brand,
            "spend_1d":    b1d.get("spend", 0),
            "spend_30d":   b30.get("spend", 0),
            "spend_7d":    b7.get("spend", 0),
            "spend_p7d":   bp7.get("spend", 0),
            "roas_1d":     b1d.get("roas", 0),
            "roas_30d":    roas_30,
            "roas_7d":     roas_7,
            "roas_p7d":    roas_p7,
            "roas_wow":    roas_wow,
            "ctr_1d":      b1d.get("ctr", 0),
            "ctr_30d":     b30.get("ctr", 0),
            "ctr_7d":      b7.get("ctr", 0),
            "ctr_p7d":     bp7.get("ctr", 0),
            "ctr_wow":     ctr_wow,
            "cpm_1d":      b1d.get("cpm", 0),
            "cpm_30d":     b30.get("cpm", 0),
            "cpm_7d":      b7.get("cpm", 0),
            "cpm_p7d":     bp7.get("cpm", 0),
        })

    # --- Yesterday PST Full-Day Spend ---
    pst = timezone(timedelta(hours=-8))
    yesterday_pst     = (datetime.now(pst) - timedelta(days=1)).date()
    yesterday_pst_str = yesterday_pst.strftime("%Y-%m-%d")

    yday_total: float = 0.0
    yday_by_type: Dict[str, float]  = defaultdict(float)
    yday_by_brand: Dict[str, float] = defaultdict(float)

    for r in rows:
        if r["date"] != yesterday_pst_str:
            continue
        yday_total += r["spend"]
        ct = histories.get(r["ad_id"], {}).get("campaign_type", "other")
        yday_by_type[ct] += r["spend"]
        br = histories.get(r["ad_id"], {}).get("brand") or classify_brand(r["ad_name"])
        yday_by_brand[br] += r["spend"]

    yesterday_spend = {
        "date":     yesterday_pst_str,
        "total":    round(yday_total, 2),
        "by_type":  {k: round(v, 2) for k, v in sorted(yday_by_type.items())},
        "by_brand": sorted(
            [{"brand": k, "spend": round(v, 2)} for k, v in yday_by_brand.items()],
            key=lambda x: -x["spend"]
        )[:12],
    }

    return {
        "analysis_date":         today.strftime("%Y-%m-%d"),
        "new_window_days":       new_window,
        "new_ads":               new_ads_data,
        "top_performers":        top_summary,
        "worst_performers":      worst_summary,
        "brand_breakdown_1d":    brand_breakdown_1d,
        "brand_breakdown_30d":   brand_breakdown_30,
        "brand_breakdown_7d":    brand_breakdown_7,
        "brand_breakdown_p7d":   brand_breakdown_p7,
        "brand_comparison":      brand_comparison,
        "campaign_type_1d":      type_summary_1d,
        "campaign_type_30d":     type_summary_30,
        "campaign_type_7d":      type_summary_7,
        "campaign_type_p7d":     type_summary_p7,
        "brand_detail_table":    brand_detail_table,
        "yesterday_spend":       yesterday_spend,
        "stats": {
            "total_ads":           len(histories),
            "new_ads_count":       len(new_ads_data),
            "top_performers_cnt":  len(top_performers),
            "worst_performers_cnt": len(worst_performers),
        },
    }


# ===========================================================================
# Claude Analysis
# ===========================================================================

SYSTEM_PROMPT = """당신은 Meta (Facebook/Instagram) 광고 전문 에이전시의 시니어 퍼포먼스 마케터입니다 (10년+ 경력).
이커머스 DTC 브랜드 (Baby/Kids) 광고 운영, 크리에이티브 전략, 오디언스 최적화에 특화되어 있습니다.
관리 브랜드: Grosmimi(유아식기), CHA&MOM(스킨케어), Naeiae(스낵), Alpremio 외 다수.

=== 분석 프레임워크 ===

1단계: 전체 계정 건전성 (Health Score)
- 전체 ROAS (7d vs 30d 트렌드)
- 전체 CPM 수준 (이커머스 벤치마크: $12.50, Baby Products: $8-15)
- 전체 CTR (벤치마크: Traffic 1.71%, CVR 캠페인 1.0%+)
- Frequency 경고: 7일 평균 >= 3.0이면 오디언스 번아웃 시작, >= 5.0이면 심각

2단계: Breakdown Effect 원칙 (가장 중요 — 반드시 준수)
- 세그먼트별 CPA/CPM이 높다고 무조건 나쁜 것이 아님
- Meta의 최적화 알고리즘이 저비용 기회를 먼저 소진한 후 한계 비용이 올라가는 구조
- 세그먼트 제거 시 전체 CPA가 오히려 상승할 수 있음
- 따라서 "이 세그먼트 CPA가 높으니 끄세요"는 틀린 조언
- 올바른 분석: 세그먼트별 한계 비용(marginal cost) vs 전체 효율 기여도 평가
- 세그먼트 제거 권고 시 반드시 "테스트 가설"로 프레이밍

3단계: 크리에이티브 피로도 진단 (Creative Fatigue)
- CTR이 14일간 20%+ 하락: 크리에이티브 피로 확정
- Frequency > 4회: 같은 사람에게 반복 노출 → 반응 감소
- TOF(상위퍼널) 크리에이티브 수명: 보통 3-4주
- 크리에이티브 다양성: 최소 3개 포맷 (이미지/비디오/카루셀) 동시 운영 권장
- 진단 후 액션: 새 크리에이티브 투입 타이밍 + 기존 크리에이티브 OFF 시점

4단계: D+N 벤치마크 비교
- 신규 광고의 D+N 시점 성과를 우수 광고들의 같은 시점과 비교
- CTR/ROAS/CVR이 벤치마크 대비 양수(+): "유망"
- CPM/CPC/CPA가 벤치마크 대비 음수(-): 비용 효율적
- benchmark null이면 절대값으로만 판단 (비교 우수 광고 부족)

5단계: Traffic vs CVR 예산 배분 전략
- Traffic 캠페인 성공 기준: CTR >= 1.5%, CPM $12 이하
- CVR 캠페인 성공 기준: ROAS >= 3.0, CPA $25 이하 (Baby Products)
- 최적 배분: 보통 Traffic 20-30% / CVR 70-80% (매출 중심이면 CVR 비중 높게)
- WoW(주간) 비교: 7일 vs 전주(p7d)로 단기 트렌드 확인

6단계: 브랜드 포트폴리오 전략
- 브랜드간 ROAS 격차 확인 → 고성과 브랜드에 예산 이동
- 각 브랜드의 라이프사이클 고려 (신규 진입 vs 성장기 vs 성숙기)
- 브랜드별 크리에이티브 피로도 개별 진단

7단계: 모든 액션의 구체성
- 예산 액션: "현재 $XX/일 → $XX/일로 XX% 증액 (강추)" 또는 "XX% 감액 (권장)"
- 중단 액션: "즉시 OFF (강추)" 또는 "재검토 후 판단 (약추)"
- 추천 강도: "강추" (즉각 실행 필요) | "권장" (이번 주 내) | "약추" (모니터링 후 결정)
- 크리에이티브 액션: "새 크리에이티브 3종 투입 필요 (강추)" 등

=== 이커머스 벤치마크 (2026 기준) ===
- Meta 전체 ROAS 중앙값: 2.19x | Advantage+ Sales: 4.52x | 리타겟팅: 3.61x
- E-commerce CPM: $12.50 | Baby Products: $8-15
- Traffic CTR 벤치마크: 1.71% | CPC: $0.70
- CPA (e-commerce): $23.74 | YoY +12.35%
- Creative fatigue 임계: Frequency >3(경고), >5(심각), CTR 14일 -20%(확정)

=== 텍스트 포맷 규칙 (executive_summary, insight, action, reason, recommendation 등 모든 텍스트 필드에 적용) ===
- 줄바꿈(\\n)을 적극 활용하여 가독성 확보
- 핵심 수치는 **볼드**로 강조 (예: **ROAS 4.2x**, **CTR 2.1%**, **$500/일 증액**)
- 불렛포인트(- )로 항목 구분. 하위 항목은 들여쓰기 후 - 사용
- 번호 매기기(1. 2. 3.)로 순서/단계 표현
- 한 문단에 모든 내용 넣지 말고, 의미 단위로 줄바꿈
- 예시:
  "executive_summary": "**전체 ROAS 2.8x** (벤치마크 2.19x 대비 양호)\\n- Grosmimi CVR 캠페인: **ROAS 4.5x** 최고 효율, 스케일업 대상\\n- CHA&MOM Traffic: CTR **0.9%** → 크리에이티브 교체 시급 (피로도 HIGH)"

=== 출력: 아래 JSON 구조 엄격히 준수 (코드블록 없이 순수 JSON) ===
{
  "executive_summary": "3줄 핵심 요약: (1) 전체 건전성 (2) 가장 큰 리스크 (3) 가장 큰 기회",
  "overall_assessment": "good | warning | danger",
  "health_score": {
    "score": 75,
    "roas_vs_benchmark": "현재 ROAS vs 벤치마크(2.19x) 비교",
    "cpm_diagnosis": "현재 CPM 수준 및 벤치마크($12.50) 대비 진단",
    "fatigue_risk": "none | low | medium | high",
    "trend_direction": "improving | stable | declining"
  },
  "new_ads_diagnosis": [
    {
      "ad_name": "광고명",
      "brand": "브랜드",
      "campaign_type": "traffic | cvr",
      "verdict": "유망 | 보통 | 조기개입필요",
      "reason": "D+N 벤치마크 대비 구체적 근거 (수치 포함)",
      "action": "구체적 액션 + 추천 강도",
      "scale_potential": "high | medium | low"
    }
  ],
  "creative_fatigue_alert": {
    "at_risk_ads": ["CTR 하락 또는 Frequency 높은 광고명 목록"],
    "recommendation": "크리에이티브 교체/추가 권고 (구체적 포맷 + 수량)",
    "healthy_ads_count": 0,
    "fatigued_ads_count": 0
  },
  "top_performers_insight": "우수 광고들의 공통점 (크리에이티브 유형, 타겟, 메시지) + 스케일 가능 여부 (증액 % 포함)",
  "brand_insights": [
    {
      "brand": "브랜드명",
      "status": "good | warning | danger",
      "insight": "1-2줄 인사이트 (ROAS, CTR, CPM 핵심 수치 포함)",
      "action": "구체적 액션 + 추천 강도",
      "budget_recommendation": "현재 일예산 추정 → 권장 일예산 (증감%)"
    }
  ],
  "traffic_vs_cvr_analysis": {
    "current_split": "Traffic XX% / CVR XX% (금액 기준)",
    "optimal_split": "권장 배분 비율",
    "recommendation": "배분 변경 권고 + 근거"
  },
  "weekly_actions": [
    {"priority": 1, "action": "구체적 액션 + 추천 강도", "target": "대상 광고/캠페인명", "expected_result": "기대 효과 (수치 포함)", "urgency": "강추|권장|약추"},
    {"priority": 2, "action": "구체적 액션 + 추천 강도", "target": "대상 광고/캠페인명", "expected_result": "기대 효과 (수치 포함)", "urgency": "강추|권장|약추"},
    {"priority": 3, "action": "구체적 액션 + 추천 강도", "target": "대상 광고/캠페인명", "expected_result": "기대 효과 (수치 포함)", "urgency": "강추|권장|약추"}
  ]
}"""

def _slim_payload(payload: dict) -> dict:
    """Claude에게 보낼 페이로드 축소 (토큰 절약)."""
    def slim_metrics(m: dict) -> dict:
        return {k: m[k] for k in ("spend", "roas", "ctr", "cpm", "cpa", "cvr", "purchases") if k in m}

    slim_new_ads = []
    for a in payload.get("new_ads", []):
        slim_new_ads.append({
            "ad_name":       a["ad_name"][:50],
            "brand":         a["brand"],
            "campaign_type": a["campaign_type"],
            "day_n":         a["day_n"],
            "metrics":       slim_metrics(a["metrics"]),
            "benchmark":     a.get("benchmark"),
            "vs_benchmark":  a.get("vs_benchmark"),
        })

    slim_top = [{
        "ad_name":       t["ad_name"][:50],
        "brand":         t["brand"],
        "campaign_type": t["campaign_type"],
        "day_n":         t["day_n"],
        "roas":          t["roas"],
        "ctr":           t["ctr"],
        "cpm":           t["cpm"],
        "spend":         t["spend"],
    } for t in payload.get("top_performers", [])[:10]]

    slim_brands = [{k: b[k] for k in ("brand", "spend", "revenue", "roas", "ctr", "cpm", "purchases")}
                   for b in payload.get("brand_breakdown_30d", [])]

    slim_comparison = [{
        "brand": b["brand"],
        "spend_7d": b["spend_7d"], "spend_p7d": b["spend_p7d"], "spend_30d": b["spend_30d"],
        "roas_7d": b["roas_7d"], "roas_p7d": b["roas_p7d"], "roas_30d": b["roas_30d"], "roas_wow": b["roas_wow"],
        "ctr_7d": b["ctr_7d"],   "ctr_p7d": b["ctr_p7d"],  "ctr_30d": b["ctr_30d"],   "ctr_wow": b["ctr_wow"],
    } for b in payload.get("brand_comparison", [])]

    return {
        "analysis_date":        payload["analysis_date"],
        "new_window_days":      payload["new_window_days"],
        "stats":                payload["stats"],
        "new_ads":              slim_new_ads,
        "top_performers_top10": slim_top,
        "brand_comparison":     slim_comparison,
        "campaign_type_7d":     payload.get("campaign_type_7d", {}),
        "campaign_type_p7d":    payload.get("campaign_type_p7d", {}),
        "campaign_type_30d":    payload.get("campaign_type_30d", {}),
    }


def analyze_with_claude(payload: dict) -> dict:
    if not ANTHROPIC_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    slim = _slim_payload(payload)

    user_msg = f"""오늘({slim['analysis_date']}) 기준 Meta Ads 광고 성과 데이터입니다.
전문 에이전시 퍼포먼스 마케터로서 깊이 있는 분석을 JSON으로 제공하세요.

=== 분석 데이터 ===
{json.dumps(slim, ensure_ascii=False, indent=2)}

=== 분석 체크리스트 (반드시 수행) ===
1. D+N 벤치마크 비교: new_ads의 vs_benchmark 양수(+)=좋음(CTR/ROAS/CVR), CPM/CPC/CPA는 반대
2. Breakdown Effect 준수: 세그먼트 CPA 높다고 즉시 제거 권고 금지. 한계비용 관점으로 분석
3. Creative Fatigue 진단: top_performers 중 day_n > 21이면 피로도 경고 체크
4. Frequency 확인: brand_comparison의 데이터에서 frequency 높은 브랜드 찾기
5. Traffic vs CVR 배분: campaign_type_7d/30d 비교 → 최적 배분 비율 권고
6. health_score: 0-100 점수 (ROAS 35점 + CPM효율 20점 + 크리에이티브건전성 25점 + 트렌드 20점)
7. 모든 액션에 추천강도(강추/권장/약추) 필수 포함
8. benchmark null이면 절대값으로만 판단
9. campaign_type "traffic"이면 ROAS 대신 CTR/CPM으로 평가
- JSON만 출력 (코드블록 없이)"""

    for attempt in range(3):
        max_tok = 8192 if attempt == 0 else 16384
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": max_tok,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_msg}],
                },
                timeout=300,
            )
        except requests.exceptions.ReadTimeout:
            print(f"  [WARN] Claude API timeout (300s), retry {attempt+1}/3")
            if attempt < 2:
                continue
            raise
        resp.raise_for_status()
        body = resp.json()
        text = body["content"][0]["text"].strip()
        stop = body.get("stop_reason", "")
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip().rstrip("`").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt < 2:
                print(f"  [WARN] Claude JSON parse fail (stop={stop}, tokens={max_tok}), retry {attempt+1}/3")
                continue
            raise RuntimeError(f"Claude JSON parse failed after 3 attempts (stop={stop})")


# ===========================================================================
# HTML Email Builder
# ===========================================================================

def _md_to_html(text: str) -> str:
    """Convert markdown-like text from Claude analysis to styled HTML."""
    import re
    if not text:
        return ""
    lines = text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<div style='height:6px'></div>")
            continue

        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        stripped = re.sub(r'__(.+?)__', r'<strong>\1</strong>', stripped)
        stripped = re.sub(r'`(.+?)`', r'<code style="background:#f5f5f5;padding:1px 5px;border-radius:3px;font-size:12px">\1</code>', stripped)

        bullet_match = re.match(r'^[-*]\s+(.+)', stripped)
        sub_bullet_match = re.match(r'^[-*]\s+(.+)', line) if line.startswith("  ") or line.startswith("\t") else None

        if sub_bullet_match:
            if not in_list:
                html_parts.append("<ul style='margin:4px 0 4px 16px;padding-left:12px;list-style:disc'>")
                in_list = True
            html_parts.append(f"<li style='margin:3px 0;color:#555;font-size:13px'>{sub_bullet_match.group(1)}</li>")
        elif bullet_match:
            if not in_list:
                html_parts.append("<ul style='margin:4px 0;padding-left:16px;list-style:none'>")
                in_list = True
            content = bullet_match.group(1)
            html_parts.append(f"<li style='margin:5px 0;color:#333;font-size:13px;position:relative;padding-left:12px'>"
                              f"<span style='position:absolute;left:-4px;color:#1877F2'>&#8226;</span>{content}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            num_match = re.match(r'^(\d+)[.)]\s+(.+)', stripped)
            if num_match:
                num, content = num_match.groups()
                html_parts.append(
                    f"<div style='display:flex;align-items:flex-start;margin:5px 0'>"
                    f"<span style='background:#1877F2;color:white;border-radius:50%;min-width:20px;height:20px;"
                    f"display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;"
                    f"margin-right:8px;flex-shrink:0'>{num}</span>"
                    f"<span style='color:#333;font-size:13px;line-height:1.5'>{content}</span></div>")
            else:
                html_parts.append(f"<p style='margin:4px 0;color:#333;font-size:13px;line-height:1.6'>{stripped}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _c(val, good_if_high=True, good_thresh=None, warn_thresh=None):
    """Color a numeric value."""
    if val is None:
        return '<span style="color:#999">-</span>'
    if good_thresh is not None:
        color = "#1a5c3a" if (val >= good_thresh if good_if_high else val <= good_thresh) else \
                "#8b1a1a" if (val < warn_thresh if good_if_high else val > warn_thresh) else "#8d6e00"
    else:
        color = "#333"
    return f'<span style="color:{color};font-weight:bold">{val}</span>'

def _roas_cell(v):
    return _c(round(v, 2) if v else v, good_thresh=3.0, warn_thresh=2.0)

def _ctr_cell(v):
    if not v:
        return "-"
    colored = _c(v, good_thresh=1.50, warn_thresh=0.80, good_if_high=True)
    return colored.replace(f">{v}<", f">{v:.2f}%<")

def _diff_badge(pct, good_if_positive=True):
    """Show % diff vs benchmark with color."""
    if pct is None:
        return '<span style="color:#aaa">n/a</span>'
    good = (pct > 0) == good_if_positive
    color = "#1a5c3a" if good else "#8b1a1a"
    arrow = "▲" if pct > 0 else "▼"
    return f'<span style="color:{color};font-weight:bold">{arrow}{abs(pct):.1f}%</span>'

def _verdict_badge(verdict):
    colors = {"유망": "#1a5c3a", "보통": "#8d6e00", "조기개입필요": "#8b1a1a"}
    color = colors.get(verdict, "#555")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:12px">{verdict}</span>'

def _status_dot(status):
    colors = {"good": "#1a5c3a", "warning": "#8d6e00", "danger": "#8b1a1a"}
    return f'<span style="color:{colors.get(status,"#555")};font-size:18px">&#9679;</span>'


def _build_yesterday_block(ys: dict, brand_detail: list = None) -> str:
    """어제 PST 기준 전체 지출 + 브랜드×기간×타입 상세 테이블."""
    if not ys or ys.get("total", 0) == 0:
        return ""

    total   = ys["total"]
    by_type = ys.get("by_type", {})
    type_colors = {"traffic": "#1565c0", "cvr": "#1a5c3a", "other": "#555"}
    type_labels = {"traffic": "Traffic", "cvr": "CVR", "other": "기타"}

    # Header pills
    type_pills = ""
    for ct, sp in sorted(by_type.items(), key=lambda x: -x[1]):
        col = type_colors.get(ct, "#555")
        lbl = type_labels.get(ct, ct)
        pct = round(sp / total * 100) if total > 0 else 0
        type_pills += (
            f'<span style="background:{col};color:white;padding:4px 12px;'
            f'border-radius:20px;font-size:12px;margin-right:6px;white-space:nowrap">'
            f'{lbl} ${sp:,.0f} ({pct}%)</span>'
        )

    def _m(d, key, fmt="sp"):
        v = d.get(key, 0) if d else 0
        if fmt == "sp":   return f'${v:,.0f}' if v else '-'
        if fmt == "roas": return f'{v:.2f}x' if v else '-'
        if fmt == "ctr":  return f'{v:.2f}%' if v else '-'
        if fmt == "cpc":  return f'${v:.2f}' if v else '-'
        return str(v) if v else '-'

    def _cell(d, ctype):
        """Build a mini-cell: spend + key metric."""
        if not d or d.get("spend", 0) == 0:
            return '<td style="padding:4px 6px;font-size:11px;color:#ddd;text-align:right">-</td>'
        sp = d.get("spend", 0)
        ads = d.get("ads", 0)
        if ctype == "cvr":
            roas = d.get("roas", 0)
            cpa = d.get("cpa", 0)
            color = "#1a5c3a" if roas >= 3.0 else "#8b1a1a" if roas < 2.0 else "#8d6e00"
            metric = f'<span style="color:{color};font-weight:bold">{roas:.2f}x</span>'
            cac_str = f' <span style="color:#666">CAC${cpa:,.0f}</span>' if cpa > 0 else ""
        else:
            ctr = d.get("ctr", 0)
            color = "#1565c0" if ctr >= 1.5 else "#8b1a1a" if ctr < 0.8 else "#8d6e00"
            metric = f'<span style="color:{color};font-weight:bold">{ctr:.2f}%</span>'
            cac_str = ""
        return (f'<td style="padding:4px 6px;font-size:11px;text-align:right;vertical-align:top">'
                f'<div style="font-weight:bold">${sp:,.0f}</div>'
                f'<div style="font-size:10px;color:#888">{metric}{cac_str} {ads}개</div>'
                f'</td>')

    if not brand_detail:
        # Fallback: simple brand list
        rows_html = ""
        for b in ys.get("by_brand", []):
            pct = round(b["spend"] / total * 100) if total > 0 else 0
            rows_html += (f'<tr><td style="padding:5px 10px;font-size:12px">{b["brand"]}</td>'
                          f'<td style="padding:5px 10px;text-align:right;font-weight:bold">${b["spend"]:,.0f}</td>'
                          f'<td style="padding:5px 10px;text-align:right;color:#aaa">{pct}%</td></tr>')
        detail_html = f'<table style="width:100%;border-collapse:collapse">{rows_html}</table>'
    else:
        # Full brand×period×type table — split CVR / Traffic
        th_style = "padding:5px 6px;font-size:10px;text-align:right;white-space:nowrap;color:white"
        periods = [("어제", "1d"), ("최근7일", "7d"), ("이전7일", "p7d"), ("30일", "30d")]

        def _brand_section(ctype, color, label):
            metric_name = "ROAS" if ctype == "cvr" else "CTR"
            rows = ""
            for entry in brand_detail:
                bname = entry["brand"]
                cells = ""
                has_data = False
                for _, pk in periods:
                    d = entry.get(pk, {}).get(ctype)
                    if d and d.get("spend", 0) > 0:
                        has_data = True
                    cells += _cell(d, ctype)
                if not has_data:
                    continue
                rows += (f'<tr style="border-bottom:1px solid #f0f0f0">'
                         f'<td style="padding:4px 8px;font-size:11px;font-weight:600;min-width:90px">{bname}</td>'
                         f'{cells}</tr>')
            if not rows:
                return ""
            # Row 1: period names on solid color bg
            period_ths = "".join(
                f'<th style="padding:5px 8px;font-size:10px;text-align:right;white-space:nowrap;'
                f'color:white;font-weight:bold">{p}</th>'
                for p, _ in periods
            )
            # Row 2: metric label on light bg
            metric_ths = "".join(
                f'<th style="padding:2px 8px;font-size:9px;text-align:right;color:#888;'
                f'font-weight:normal;white-space:nowrap">지출 / {metric_name}</th>'
                for _ in periods
            )
            return f"""
            <div style="margin-bottom:10px">
              <div style="background:{color};color:white;padding:5px 10px;border-radius:5px 5px 0 0;
                          font-size:11px;font-weight:bold">{label}</div>
              <table style="width:100%;border-collapse:collapse;background:white;border:1px solid #e0e0e0">
                <thead>
                  <tr style="background:{color}">
                    <th style="padding:5px 8px;font-size:10px;text-align:left;color:white">브랜드</th>
                    {period_ths}
                  </tr>
                  <tr style="background:#f5f5f5">
                    <th style="padding:2px 8px;font-size:9px;color:#aaa;text-align:left;font-weight:normal"></th>
                    {metric_ths}
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>"""

        cvr_section     = _brand_section("cvr",     "#1a5c3a", "CVR 캠페인 (전환 목적)")
        traffic_section = _brand_section("traffic",  "#1565c0", "Traffic 캠페인 (인지/클릭 목적)")
        detail_html = cvr_section + traffic_section

    return f"""
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:10px;padding:16px 20px;margin-bottom:24px">
      <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:10px">
        <div>
          <div style="font-size:11px;color:#8d6e00;font-weight:600;letter-spacing:.5px;text-transform:uppercase">어제 실지출 (PST {ys["date"]})</div>
          <div style="font-size:28px;font-weight:bold;color:#222;line-height:1.2">${total:,.0f}</div>
        </div>
        <div style="margin-left:auto;font-size:11px;color:#aaa">Full Day PST</div>
      </div>
      <div style="margin-bottom:12px;display:flex;flex-wrap:wrap;gap:4px">{type_pills}</div>
      <p style="font-size:10px;color:#aaa;margin:0 0 8px">각 셀: 지출 / 핵심지표(ROAS or CTR) + 광고수</p>
      {detail_html}
    </div>"""


def build_html(payload: dict, analysis: dict) -> str:
    today = payload["analysis_date"]
    oa = analysis.get("overall_assessment", "warning")
    oa_label = {"good": "양호", "warning": "주의", "danger": "위험"}.get(oa, "주의")
    oa_color = {"good": "#1a5c3a", "warning": "#8d6e00", "danger": "#8b1a1a"}.get(oa, "#8d6e00")

    # ── Section 1: 신규 광고 (Traffic / CVR 분리) ──────────────────
    def new_ad_rows(ads, ctype):
        rows = [a for a in ads if a["campaign_type"] == ctype]
        if not rows:
            return f'<tr><td colspan="9" style="padding:12px;color:#999;text-align:center">이번 주 {ctype.upper()} 신규 광고 없음</td></tr>'
        html = ""
        for a in rows:
            m = a["metrics"]
            vs = a.get("vs_benchmark") or {}
            b  = a.get("benchmark") or {}

            diagnosis = next((d for d in analysis.get("new_ads_diagnosis", [])
                              if a["ad_name"][:20] in d.get("ad_name", "")), {})
            verdict = diagnosis.get("verdict", "")

            # Primary metrics differ by type
            if ctype == "cvr":
                primary = f'ROAS: {_roas_cell(m["roas"])} | CPA: ${m["cpa"]:.2f}'
                bench_primary = (f'벤치 ROAS: {b.get("avg_roas","?")}x ({_diff_badge(vs.get("roas_vs_bench"), True)})'
                                 if b else "벤치 없음")
            else:
                ctr_str = f'{m["ctr"]:.2f}%'
                primary = f'CTR: {ctr_str} | CPC: ${m["cpc"]:.2f}'
                bench_primary = (f'벤치 CTR: {b.get("avg_ctr","?")}% ({_diff_badge(vs.get("ctr_vs_bench"), True)})'
                                 if b else "벤치 없음")

            html += f"""
            <tr style="border-bottom:1px solid #eee">
              <td style="padding:10px 12px">
                <div style="font-weight:600;color:#222;font-size:13px">{a["ad_name"]}</div>
                <div style="color:#888;font-size:11px;margin-top:2px">{a["adset_name"]}</div>
              </td>
              <td style="padding:10px 12px;white-space:nowrap">
                <span style="background:#e3f2fd;color:#1565c0;padding:2px 6px;border-radius:4px;font-size:12px">{a["brand"]}</span>
              </td>
              <td style="padding:10px 12px;text-align:center;font-size:11px;color:#666">{a["first_spend"]}</td>
              <td style="padding:10px 12px;text-align:center;font-weight:bold">D+{a["day_n"]}</td>
              <td style="padding:10px 12px;font-size:13px">{primary}</td>
              <td style="padding:10px 12px;font-size:12px;color:#666">${m["spend"]:.2f} spend</td>
              <td style="padding:10px 12px;font-size:12px">{bench_primary}</td>
              <td style="padding:10px 12px;font-size:12px;color:#555">
                CPM vs 벤치: {_diff_badge(vs.get("cpm_vs_bench"), False)}<br>
                CPC vs 벤치: {_diff_badge(vs.get("cpc_vs_bench"), False)}
              </td>
              <td style="padding:10px 12px">{_verdict_badge(verdict) if verdict else ""}</td>
            </tr>
            <tr style="background:#fafafa;border-bottom:1px solid #e0e0e0">
              <td colspan="9" style="padding:6px 12px 10px 24px;font-size:12px">
                <div style="color:#555">{_md_to_html(diagnosis.get("reason", ""))}</div>
                {"" if not diagnosis.get("action") else f'<div style="margin-top:4px;padding:6px 10px;background:#e8f5e9;border-radius:4px"><strong style="color:#1a5c3a;font-size:11px">ACTION:</strong> {_md_to_html(diagnosis.get("action", ""))}</div>'}
              </td>
            </tr>"""
        return html

    traffic_rows = new_ad_rows(payload["new_ads"], "traffic")
    cvr_rows     = new_ad_rows(payload["new_ads"], "cvr")

    # ── Section 2 & helper: performer tables (top / worst) ──────────
    acct_num = (AD_ACCOUNT_ID or "").replace("act_", "")

    def _ad_link(campaign_id):
        # manage/ads + selected_campaign_ids → 해당 캠페인 광고만 필터링해서 표시
        url = f"https://www.facebook.com/adsmanager/manage/ads?act={acct_num}&selected_campaign_ids={campaign_id}"
        return (f'<a href="{url}" target="_blank" '
                f'style="color:#1877F2;text-decoration:none;font-size:10px;white-space:nowrap">'
                f'&#128279; 광고 바로가기</a>')

    def _performer_section(items_src, ctype, color, label, sort_worst=False):
        items = [t for t in items_src if t["campaign_type"] == ctype]
        # Sort by yesterday spend descending (top) or ascending (worst)
        items.sort(key=lambda t: t.get("metrics_1d", {}).get("spend", 0),
                   reverse=not sort_worst)
        metric_label = "ROAS / CAC" if ctype == "cvr" else "CTR"

        def _sp(m):
            return f'${m.get("spend",0):,.0f}' if m.get("spend", 0) > 0 else "-"

        def _mk(m, worst=sort_worst):
            if not m.get("spend", 0):
                return ""
            if ctype == "cvr":
                roas = m.get("roas", 0)
                cpa = m.get("cpa", 0)
                rc = "#1a3a5c" if roas >= 3.0 else "#8b1a1a" if roas < 2.0 else "#8d6e00"
                cpa_str = f'<span style="font-size:9px;color:#666">CAC ${cpa:,.0f}</span>' if cpa > 0 else ""
                return f'<div style="font-size:10px;color:{rc};font-weight:bold">{roas:.2f}x</div>{cpa_str}'
            else:
                ctr = m.get("ctr", 0)
                c = "#1a3a5c" if ctr >= 1.5 else "#8b1a1a" if ctr < 0.8 else "#8d6e00"
                return f'<div style="font-size:10px;color:{c};font-weight:bold">{ctr:.2f}%</div>'

        if not items:
            body = f'<tr><td colspan="9" style="padding:12px;color:#999;text-align:center">{label} 없음</td></tr>'
        else:
            body = ""
            for i, t in enumerate(items, 1):
                bg = "#f9f9f9" if i % 2 == 0 else "white"
                m1d  = t.get("metrics_1d",  {})
                m7   = t.get("metrics_7d",  {})
                mp7  = t.get("metrics_p7d", {})
                m30  = t.get("metrics_30d", {})
                if ctype == "cvr":
                    lifetime_cpa = t.get("cpa", 0)
                    lifetime_str = f'{t["roas"]:.2f}x'
                    if lifetime_cpa > 0:
                        lifetime_str += f'<br><span style="font-size:9px;color:#666">CAC ${lifetime_cpa:,.0f}</span>'
                else:
                    lifetime_str = f'{t["ctr"]:.2f}%'
                camp_id_val = t.get("campaign_id", "")
                camp_link = _ad_link(camp_id_val) if camp_id_val else ""
                body += f"""
        <tr style="background:{bg}">
          <td style="padding:7px 10px;font-size:12px">
            {t["ad_name"]}
            <div style="margin-top:2px">{camp_link}</div>
          </td>
          <td style="padding:7px 8px"><span style="background:#e3f2fd;color:#1565c0;padding:2px 5px;border-radius:4px;font-size:11px">{t["brand"]}</span></td>
          <td style="padding:7px 8px;text-align:center;font-size:10px;color:#666">{t.get("first_spend","")}</td>
          <td style="padding:7px 8px;text-align:center;font-size:11px">D+{t["day_n"]}</td>
          <td style="padding:7px 8px;text-align:right;color:#8d6e00;font-weight:bold">{_sp(m1d)}{_mk(m1d)}</td>
          <td style="padding:7px 8px;text-align:right;font-weight:bold">{_sp(m7)}{_mk(m7)}</td>
          <td style="padding:7px 8px;text-align:right;color:#888">{_sp(mp7)}{_mk(mp7)}</td>
          <td style="padding:7px 8px;text-align:right;color:#aaa">{_sp(m30)}{_mk(m30)}</td>
          <td style="padding:7px 8px;text-align:right;font-size:11px;color:#999">{lifetime_str}<br><span style="color:#aaa">누적</span></td>
        </tr>"""

        return f"""
        <div style="margin-bottom:16px;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden">
          <div style="background:{color};color:white;padding:8px 16px;font-weight:bold;font-size:13px">{label}</div>
          <div style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse;font-size:12px;min-width:680px">
            <thead>
              <tr style="background:#f5f5f5">
                <th style="padding:7px 10px;text-align:left">광고명</th>
                <th style="padding:7px 8px">브랜드</th>
                <th style="padding:7px 8px;text-align:center">첫집행일</th>
                <th style="padding:7px 8px;text-align:center">D+N</th>
                <th style="padding:7px 8px;text-align:right;color:#8d6e00">어제(1일)</th>
                <th style="padding:7px 8px;text-align:right;color:{color}">최근 7일</th>
                <th style="padding:7px 8px;text-align:right;color:#888">이전 7일</th>
                <th style="padding:7px 8px;text-align:right;color:#aaa">최근 30일</th>
                <th style="padding:7px 8px;text-align:right;color:#999">누적</th>
              </tr>
              <tr style="background:#fafafa;font-size:10px;color:#aaa">
                <th colspan="4"></th>
                <th style="padding:2px 8px;text-align:right">지출 / {metric_label}</th>
                <th style="padding:2px 8px;text-align:right">지출 / {metric_label}</th>
                <th style="padding:2px 8px;text-align:right">지출 / {metric_label}</th>
                <th style="padding:2px 8px;text-align:right">지출 / {metric_label}</th>
                <th style="padding:2px 8px;text-align:right">{metric_label}</th>
              </tr>
            </thead>
            <tbody>{body}</tbody>
          </table>
          </div>
        </div>"""

    top_cvr_section     = _performer_section(payload["top_performers"],   "cvr",     "#1a5c3a", "CVR 우수 광고 (전환 목적, ROAS 3.0+) — 어제 지출 높은순")
    top_traffic_section = _performer_section(payload["top_performers"],   "traffic",  "#2c5f8a", "Traffic 우수 광고 (인지/클릭 목적, CTR 1.5%+) — 어제 지출 높은순")
    worst_cvr_section     = _performer_section(payload.get("worst_performers", []), "cvr",    "#8b1a1a", "CVR 워스트 광고 (ROAS 2.0 미만) — 최악순", sort_worst=True)
    worst_traffic_section = _performer_section(payload.get("worst_performers", []), "traffic", "#7a4400", "Traffic 워스트 광고 (CTR 1.0% 미만) — 최악순", sort_worst=True)

    # ── Section 3: Brand Comparison (최근 7일 / 이전 7일 / 최근 30일) ───────────────────
    # Build brand rows with CVR/Traffic sub-rows
    brand_rows = ""
    brand_detail = payload.get("brand_detail_table", [])
    brand_detail_map = {bd["brand"]: bd for bd in brand_detail}

    for b in payload.get("brand_comparison", []):
        brand_insight = next((bi for bi in analysis.get("brand_insights", [])
                              if bi.get("brand") == b["brand"]), {})
        status = brand_insight.get("status", "")
        dot = _status_dot(status) if status else ""
        roas_wow = b.get("roas_wow")

        # Main brand row (totals)
        brand_rows += f"""
        <tr style="border-bottom:1px solid #ddd;background:#f8f9fb">
          <td style="padding:10px 12px" rowspan="1">{dot} <strong style="font-size:14px">{b["brand"]}</strong></td>
          <td style="padding:8px 8px;text-align:right;color:#555;font-size:11px">전체</td>
          <td style="padding:8px 8px;text-align:right;color:#8d6e00;font-weight:bold">${b.get("spend_1d",0):,.0f}</td>
          <td style="padding:8px 8px;text-align:right;font-weight:bold">${b["spend_7d"]:,.0f}</td>
          <td style="padding:8px 8px;text-align:right;color:#888">${b["spend_p7d"]:,.0f}</td>
          <td style="padding:8px 8px;text-align:right;color:#aaa">${b["spend_30d"]:,.0f}</td>
          <td style="padding:8px 8px;text-align:center">{_roas_cell(b["roas_7d"])}</td>
          <td style="padding:8px 8px;text-align:center;color:#aaa">{b["roas_30d"]:.2f}x</td>
          <td style="padding:8px 8px;text-align:center">{_diff_badge(roas_wow, True) if roas_wow is not None else "-"}</td>
          <td style="padding:8px 8px;text-align:center">{b["ctr_7d"]:.2f}%</td>
          <td style="padding:8px 8px;text-align:center;color:#aaa">{b["ctr_30d"]:.2f}%</td>
        </tr>"""

        # CVR/Traffic sub-rows from brand_detail_table
        bd = brand_detail_map.get(b["brand"], {})
        for ctype, ct_label, ct_color in [("cvr", "CVR", "#1a5c3a"), ("traffic", "Traffic", "#2c5f8a")]:
            d7 = (bd.get("7d") or {}).get(ctype, {})
            d30 = (bd.get("30d") or {}).get(ctype, {})
            dp7 = (bd.get("p7d") or {}).get(ctype, {})
            d1d = (bd.get("1d") or {}).get(ctype, {})
            if not d7 and not d30:
                continue
            sp7 = d7.get("spend", 0) if d7 else 0
            sp30 = d30.get("spend", 0) if d30 else 0
            if sp7 == 0 and sp30 == 0:
                continue
            r7 = d7.get("roas", 0) if d7 else 0
            r30 = d30.get("roas", 0) if d30 else 0
            ctr7 = d7.get("ctr", 0) if d7 else 0
            ctr30 = d30.get("ctr", 0) if d30 else 0
            cpa7 = d7.get("cpa", 0) if d7 else 0
            sp1d = d1d.get("spend", 0) if d1d else 0
            spp7 = dp7.get("spend", 0) if dp7 else 0

            # CAC display for CVR type
            cac_str = f'<span style="font-size:10px;color:#666">CAC ${cpa7:,.0f}</span>' if ctype == "cvr" and cpa7 > 0 else ""

            brand_rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:4px 12px"></td>
          <td style="padding:4px 8px;text-align:right">
            <span style="background:{ct_color};color:white;padding:1px 6px;border-radius:8px;font-size:10px">{ct_label}</span>
          </td>
          <td style="padding:4px 8px;text-align:right;color:#8d6e00;font-size:11px">${sp1d:,.0f}</td>
          <td style="padding:4px 8px;text-align:right;font-size:11px;font-weight:bold">${sp7:,.0f}</td>
          <td style="padding:4px 8px;text-align:right;color:#888;font-size:11px">${spp7:,.0f}</td>
          <td style="padding:4px 8px;text-align:right;color:#aaa;font-size:11px">${sp30:,.0f}</td>
          <td style="padding:4px 8px;text-align:center;font-size:11px">{_roas_cell(r7) if ctype == "cvr" else "-"} {cac_str}</td>
          <td style="padding:4px 8px;text-align:center;color:#aaa;font-size:11px">{f"{r30:.2f}x" if ctype == "cvr" and r30 else "-"}</td>
          <td style="padding:4px 8px;text-align:center;font-size:11px">-</td>
          <td style="padding:4px 8px;text-align:center;font-size:11px">{f"{ctr7:.2f}%" if ctr7 else "-"}</td>
          <td style="padding:4px 8px;text-align:center;color:#aaa;font-size:11px">{f"{ctr30:.2f}%" if ctr30 else "-"}</td>
        </tr>"""

        # Insight row
        if brand_insight.get("insight") or brand_insight.get("action"):
            brand_rows += f"""
        <tr style="background:#f5f8fb;border-bottom:2px solid #ddd">
          <td colspan="11" style="padding:6px 12px 10px 32px;font-size:12px">
            <div>{_md_to_html(brand_insight.get("insight", ""))}</div>
            {"" if not brand_insight.get("action") else f'<div style="margin-top:4px;color:#2c5f8a;font-weight:500">{_md_to_html(brand_insight["action"])}</div>'}
          </td>
        </tr>"""

    # ── Section 4: Campaign Type Summary (3 periods: 최근 7일 / 이전 7일 / 최근 30일) ──────────────
    type_html = ""
    t1d = payload.get("campaign_type_1d", {})
    t30 = payload.get("campaign_type_30d", {})
    t7  = payload.get("campaign_type_7d", {})
    tp7 = payload.get("campaign_type_p7d", {})

    def _pct_wow(new_val, old_val, good_if_high=True):
        if not old_val:
            return '<span style="color:#aaa">-</span>'
        pct = round((new_val - old_val) / old_val * 100, 1)
        return _diff_badge(pct, good_if_high)

    for ctype in [k for k in ["traffic", "cvr", "other"]
                  if k in set(list(t30.keys()) + list(t7.keys()) + list(tp7.keys()))]:
        v1d  = t1d.get(ctype, {})
        v7   = t7.get(ctype, {})
        vp7  = tp7.get(ctype, {})
        v30  = t30.get(ctype, {})
        label     = {"traffic": "Traffic 캠페인 (인지/클릭 목적)", "cvr": "CVR 캠페인 (전환/판매 목적)", "other": "기타"}.get(ctype, ctype)
        hdr_color = "#1565c0" if ctype == "traffic" else "#1a5c3a" if ctype == "cvr" else "#555"
        is_traffic = (ctype == "traffic")

        roas_1d = v1d.get("roas", 0); roas_7 = v7.get("roas", 0)
        roas_p7 = vp7.get("roas", 0); roas_30 = v30.get("roas", 0)

        type_html += f"""
        <div style="margin-bottom:20px;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden">
          <div style="background:{hdr_color};color:white;padding:10px 16px;font-weight:bold;font-size:13px">{label}</div>
          <table style="width:100%;font-size:12px;border-collapse:collapse">
            <thead>
              <tr style="background:#f5f5f5">
                <th style="padding:8px 12px;text-align:left;color:#666;border-bottom:1px solid #e0e0e0">지표</th>
                <th style="padding:8px 10px;text-align:right;color:#8d6e00;font-weight:700;border-bottom:1px solid #e0e0e0">어제</th>
                <th style="padding:8px 10px;text-align:right;color:{hdr_color};font-weight:700;border-bottom:1px solid #e0e0e0">최근 7일</th>
                <th style="padding:8px 10px;text-align:right;color:#888;border-bottom:1px solid #e0e0e0">이전 7일</th>
                <th style="padding:8px 10px;text-align:right;color:#aaa;border-bottom:1px solid #e0e0e0">최근 30일</th>
                <th style="padding:8px 10px;text-align:right;color:#555;border-bottom:1px solid #e0e0e0">WoW</th>
              </tr>
            </thead>
            <tbody>
              <tr style="border-top:1px solid #f0f0f0">
                <td style="padding:7px 12px;color:#888">광고 수</td>
                <td style="padding:7px 10px;text-align:right;color:#8d6e00">{v1d.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">{v7.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">{vp7.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">{v30.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">-</td>
              </tr>
              <tr style="background:#fafafa;border-top:1px solid #f0f0f0">
                <td style="padding:7px 12px;color:#888">지출</td>
                <td style="padding:7px 10px;text-align:right;color:#8d6e00">${v1d.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">${v7.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">${vp7.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">${v30.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right">-</td>
              </tr>
              <tr style="border-top:1px solid #f0f0f0;{'background:#fffde7' if is_traffic else ''}">
                <td style="padding:7px 12px;color:#888">{'CTR ★' if is_traffic else 'CTR'}</td>
                <td style="padding:7px 10px;text-align:right;color:#8d6e00">{v1d.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">{v7.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right;color:#888">{vp7.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">{v30.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right">{_pct_wow(v7.get('ctr',0), vp7.get('ctr',0), True)}</td>
              </tr>
              <tr style="border-top:1px solid #f0f0f0;{'background:#fffde7' if is_traffic else 'background:#fafafa'}">
                <td style="padding:7px 12px;color:#888">{'CPC ★' if is_traffic else 'CPC'}</td>
                <td style="padding:7px 10px;text-align:right;color:#8d6e00">${v1d.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">${v7.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">${vp7.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">${v30.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right">{_pct_wow(v7.get('cpc',0), vp7.get('cpc',0), False)}</td>
              </tr>
              <tr style="border-top:1px solid #f0f0f0;{'background:#fffde7' if not is_traffic else ''}">
                <td style="padding:7px 12px;color:#888">{'ROAS ★' if not is_traffic else 'ROAS'}</td>
                <td style="padding:7px 10px;text-align:right;color:#8d6e00">{'N/A' if is_traffic else f'{roas_1d:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">{'N/A' if is_traffic else f'{roas_7:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">{'N/A' if is_traffic else f'{roas_p7:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">{'N/A' if is_traffic else f'{roas_30:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right">{'-' if is_traffic else _pct_wow(roas_7, roas_p7, True)}</td>
              </tr>
              <tr style="background:#fafafa;border-top:1px solid #f0f0f0">
                <td style="padding:7px 12px;color:#888">CPM</td>
                <td style="padding:7px 10px;text-align:right;color:#8d6e00">${v1d.get('cpm',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">${v7.get('cpm',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">${vp7.get('cpm',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">${v30.get('cpm',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right">{_pct_wow(v7.get('cpm',0), vp7.get('cpm',0), False)}</td>
              </tr>
            </tbody>
          </table>
        </div>"""

    # ── Section 5: Brand Insights (Claude) ───────────────────────
    brand_insight_cards = ""
    for bi in analysis.get("brand_insights", []):
        sc = {"good": "#1a5c3a", "warning": "#8d6e00", "danger": "#8b1a1a"}.get(bi.get("status",""), "#555")
        budget_rec = bi.get("budget_recommendation", "")
        budget_html = f'<div style="margin-top:6px;padding:4px 10px;background:#e8f5e9;border-radius:4px;font-size:12px;color:#1a5c3a">{budget_rec}</div>' if budget_rec else ""
        brand_insight_cards += f"""
        <div style="border-left:4px solid {sc};padding:10px 16px;margin:8px 0;background:#fafafa;border-radius:0 6px 6px 0">
          <strong style="color:{sc};font-size:15px">{bi["brand"]}</strong>
          <div style="margin:6px 0">{_md_to_html(bi.get("insight", ""))}</div>
          <div style="margin:6px 0;padding:8px 12px;background:#f0f4f8;border-radius:6px">
            <span style="color:#1565c0;font-weight:bold;font-size:12px">ACTION:</span>
            <div style="margin-top:4px">{_md_to_html(bi.get("action", ""))}</div>
          </div>
          {budget_html}
        </div>"""

    # ── Section 6: Weekly Actions ─────────────────────────────────
    URGENCY_META = {"강추": "#8b1a1a", "권장": "#8d6e00", "약추": "#1565c0"}
    action_html = ""
    for wa in analysis.get("weekly_actions", []):
        urg = wa.get("urgency", "권장")
        urg_color = URGENCY_META.get(urg, "#555")
        action_html += f"""
        <div style="display:flex;align-items:flex-start;margin:14px 0">
          <div style="background:#1877F2;color:white;border-radius:50%;width:28px;height:28px;
                      min-width:28px;display:flex;align-items:center;justify-content:center;
                      font-weight:bold;margin-right:14px;font-size:14px">{wa["priority"]}</div>
          <div>
            <span style="background:{urg_color};color:white;padding:1px 8px;border-radius:10px;font-size:11px;margin-right:6px">{urg}</span>
            <strong style="color:#222;font-size:14px">{wa["action"]}</strong>
            <p style="margin:3px 0;color:#666;font-size:12px">대상: {wa.get("target","-")}</p>
            <p style="margin:3px 0;color:#1a5c3a;font-size:12px">&#8594; {wa.get("expected_result","")}</p>
          </div>
        </div>"""

    stats = payload["stats"]
    tvc_raw = analysis.get("traffic_vs_cvr_analysis", "")
    if isinstance(tvc_raw, dict):
        tvc = f"{tvc_raw.get('current_split', '')} | 권장: {tvc_raw.get('optimal_split', '')} — {tvc_raw.get('recommendation', '')}"
    else:
        tvc = tvc_raw

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meta Ads 일간 리포트</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:750px;margin:0 auto;background:white">

  <!-- Header -->
  <div style="background:#1877F2;padding:24px 30px;color:white">
    <div style="font-size:12px;color:rgba(255,255,255,0.7);margin-bottom:6px">Meta Ads 일간 리포트</div>
    <div style="font-size:22px;font-weight:bold">{today}</div>
    <div style="margin-top:10px">
      <span style="background:{oa_color};padding:4px 14px;border-radius:20px;font-size:13px;font-weight:bold">
        전체 상태: {oa_label}
      </span>
      <span style="margin-left:12px;font-size:13px;color:rgba(255,255,255,0.8)">
        신규 광고 {stats["new_ads_count"]}개 | 우수 광고 {stats["top_performers_cnt"]}개 | 전체 활성 {stats["total_ads"]}개
      </span>
    </div>
    <div style="margin-top:14px;font-size:14px;color:rgba(255,255,255,0.9);line-height:1.7;background:rgba(0,0,0,0.15);padding:12px 16px;border-radius:8px">
      {_md_to_html(analysis.get("executive_summary","")).replace('color:#333', 'color:rgba(255,255,255,0.9)').replace('color:#555', 'color:rgba(255,255,255,0.7)').replace('color:#1877F2', 'color:rgba(255,255,255,0.8)')}
    </div>
  </div>

  <div style="padding:24px 30px">

    {"" if not analysis.get("health_score") else f'''
    <div style="background:linear-gradient(135deg,#1877F2,#42A5F5);border-radius:10px;padding:20px 24px;margin-bottom:20px;color:white">
      <div style="display:flex;align-items:center;gap:16px">
        <div style="font-size:42px;font-weight:bold;min-width:60px">{analysis["health_score"].get("score", "-")}</div>
        <div style="font-size:11px;color:rgba(255,255,255,0.7);border-left:1px solid rgba(255,255,255,0.3);padding-left:16px">
          <div>HEALTH SCORE /100</div>
          <div style="color:rgba(255,255,255,0.9);margin-top:4px">{analysis["health_score"].get("roas_vs_benchmark", "")}</div>
          <div style="color:rgba(255,255,255,0.9);margin-top:2px">{analysis["health_score"].get("cpm_diagnosis", "")}</div>
          <div style="margin-top:4px;display:flex;gap:8px">
            <span style="background:{"#1a5c3a" if analysis["health_score"].get("trend_direction") == "improving" else "#8b1a1a" if analysis["health_score"].get("trend_direction") == "declining" else "#8d6e00"};padding:2px 8px;border-radius:10px;font-size:11px">
              {"+ 개선중" if analysis["health_score"].get("trend_direction") == "improving" else "- 악화중" if analysis["health_score"].get("trend_direction") == "declining" else "= 유지"}
            </span>
            <span style="background:{"#1a5c3a" if analysis["health_score"].get("fatigue_risk") == "none" else "#8b1a1a" if analysis["health_score"].get("fatigue_risk") == "high" else "#8d6e00" if analysis["health_score"].get("fatigue_risk") == "medium" else "#888"};padding:2px 8px;border-radius:10px;font-size:11px">
              피로도: {analysis["health_score"].get("fatigue_risk", "N/A")}
            </span>
          </div>
        </div>
      </div>
    </div>'''}

    {"" if not analysis.get("creative_fatigue_alert") or not analysis["creative_fatigue_alert"].get("at_risk_ads") else f"""
    <div style="background:#fff3e0;border:1px solid #ffe0b2;border-radius:8px;padding:14px 18px;margin-bottom:20px">
      <div style="font-weight:bold;color:#8d6e00;font-size:14px;margin-bottom:6px">
        Creative Fatigue Alert
        <span style="background:#8d6e00;color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px">
          {analysis["creative_fatigue_alert"].get("fatigued_ads_count", 0)}개 피로
        </span>
      </div>
      <div style="font-size:12px;color:#555;margin-bottom:4px">
        피로 의심 광고: {", ".join(analysis["creative_fatigue_alert"].get("at_risk_ads", [])[:5])}
      </div>
      <div style="font-size:12px;color:#1565c0;font-weight:500">
        {analysis["creative_fatigue_alert"].get("recommendation", "")}
      </div>
    </div>"""}

    <!-- Yesterday PST Spend -->
    {_build_yesterday_block(payload.get("yesterday_spend", {}), payload.get("brand_detail_table", []))}

    <!-- Campaign Type Overview -->
    <h2 style="color:#1877F2;border-bottom:2px solid #1877F2;padding-bottom:8px">캠페인 유형별 성과 <span style="font-size:14px;color:#888;font-weight:normal">— 어제 / 최근 7일 / 이전 7일 / 최근 30일</span></h2>
    <p style="font-size:12px;color:#888;margin:0 0 12px">★ = 해당 캠페인 유형의 핵심 지표 | WoW = 최근 7일 vs 이전 7일 | <span style="color:#8d6e00">주황 = 어제 (PST)</span></p>
    <div style="margin-bottom:8px">{type_html}</div>
    <div style="background:#e8f4fd;border-left:4px solid #1877F2;padding:12px 16px;border-radius:0 6px 6px 0;margin-top:12px">
      <strong style="color:#1877F2;font-size:13px">Traffic vs CVR 배분 분석</strong>
      <div style="margin-top:6px">{_md_to_html(tvc)}</div>
    </div>

    <!-- New Ads: CVR -->
    <h2 style="color:#1a5c3a;border-bottom:2px solid #1a5c3a;padding-bottom:8px;margin-top:32px">
      &#128195; 이번 주 신규 광고 — CVR 캠페인 (전환 목적)
    </h2>
    <p style="font-size:12px;color:#888;margin:0 0 10px">
      * D+N = 첫 광고비 지출 후 경과일 | 벤치마크 = 우수 광고(ROAS 3.0+)의 동 시점 누적 평균
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#e8f5e9">
          <th style="padding:10px 12px;text-align:left">광고명</th>
          <th style="padding:10px 12px">브랜드</th>
          <th style="padding:10px 12px">첫 집행일</th>
          <th style="padding:10px 12px">D+N</th>
          <th style="padding:10px 12px">핵심 지표</th>
          <th style="padding:10px 12px">지출</th>
          <th style="padding:10px 12px">벤치마크 비교</th>
          <th style="padding:10px 12px">CPM/CPC</th>
          <th style="padding:10px 12px">진단</th>
        </tr>
      </thead>
      <tbody>{cvr_rows}</tbody>
    </table>

    <!-- New Ads: Traffic -->
    <h2 style="color:#1565c0;border-bottom:2px solid #1565c0;padding-bottom:8px;margin-top:32px">
      &#128200; 이번 주 신규 광고 — Traffic 캠페인 (인지/클릭 목적)
    </h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#e3f2fd">
          <th style="padding:10px 12px;text-align:left">광고명</th>
          <th style="padding:10px 12px">브랜드</th>
          <th style="padding:10px 12px">첫 집행일</th>
          <th style="padding:10px 12px">D+N</th>
          <th style="padding:10px 12px">핵심 지표</th>
          <th style="padding:10px 12px">지출</th>
          <th style="padding:10px 12px">벤치마크 비교</th>
          <th style="padding:10px 12px">CPM/CPC</th>
          <th style="padding:10px 12px">진단</th>
        </tr>
      </thead>
      <tbody>{traffic_rows}</tbody>
    </table>

    <!-- Top Performers -->
    <h2 style="color:#333;border-bottom:2px solid #333;padding-bottom:8px;margin-top:32px">
      &#127942; 우수 광고 (D+14이상, ROAS 3.0+ 또는 CTR 1.5+%)
    </h2>
    <p style="font-size:12px;color:#888;margin:0 0 10px">
      신규 광고 D+N 벤치마크의 기준. <span style="color:#8d6e00">주황=어제</span> | <strong>굵음=최근7일</strong> | 회색=이전7일 | 연회색=30일
    </p>
    <div style="background:#f8f9fa;padding:12px 16px;border-radius:6px;margin-bottom:16px">
      {_md_to_html(analysis.get("top_performers_insight",""))}
    </div>
    {top_cvr_section}
    {top_traffic_section}

    <!-- Worst Performers -->
    <h2 style="color:#8b1a1a;border-bottom:2px solid #8b1a1a;padding-bottom:8px;margin-top:32px">
      &#9888; 워스트 광고 (D+14이상, CVR ROAS 2.0 미만 / Traffic CTR 1.0% 미만, 지출 $100+)
    </h2>
    <p style="font-size:12px;color:#888;margin:0 0 10px">
      검토 또는 OFF 대상. 어제 지출 기준 정렬.
    </p>
    {worst_cvr_section}
    {worst_traffic_section}

    <!-- Brand Comparison 3 periods -->
    <h2 style="color:#333;border-bottom:2px solid #333;padding-bottom:8px;margin-top:32px">
      브랜드별 성과 비교 <span style="font-size:14px;color:#888;font-weight:normal">— 어제 / 최근 7일 / 이전 7일 / 최근 30일</span>
    </h2>
    <p style="font-size:12px;color:#888;margin:0 0 10px">
      * <span style="color:#8d6e00">어제</span> | <strong>굵은 숫자</strong> = 최근 7일 | 회색 = 이전 7일 | 연회색 = 30일 | WoW = 최근 7일 vs 이전 7일 | CVR 행에 CAC 표시
    </p>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:12px;min-width:700px">
      <thead>
        <tr style="background:#f0f0f0">
          <th style="padding:8px 10px;text-align:left" rowspan="2">브랜드</th>
          <th style="padding:6px 8px;text-align:center" rowspan="2">타입</th>
          <th style="padding:6px 8px;text-align:center;border-bottom:1px solid #ddd" colspan="4">지출</th>
          <th style="padding:6px 8px;text-align:center;border-bottom:1px solid #ddd" colspan="3">ROAS</th>
          <th style="padding:6px 8px;text-align:center;border-bottom:1px solid #ddd" colspan="2">CTR</th>
        </tr>
        <tr style="background:#f5f5f5;font-size:11px;color:#666">
          <th style="padding:4px 8px;text-align:right;color:#8d6e00">어제</th>
          <th style="padding:4px 8px;text-align:right">7일</th>
          <th style="padding:4px 8px;text-align:right">이전7일</th>
          <th style="padding:4px 8px;text-align:right">30일</th>
          <th style="padding:4px 8px;text-align:center">7일</th>
          <th style="padding:4px 8px;text-align:center">30일</th>
          <th style="padding:4px 8px;text-align:center">WoW</th>
          <th style="padding:4px 8px;text-align:center">7일</th>
          <th style="padding:4px 8px;text-align:center">30일</th>
        </tr>
      </thead>
      <tbody>{brand_rows}</tbody>
    </table>
    </div>

    <!-- Brand Insights (Claude) -->
    <h2 style="color:#333;border-bottom:2px solid #333;padding-bottom:8px;margin-top:32px">
      브랜드별 전문가 진단
    </h2>
    {brand_insight_cards}

    <!-- Weekly Actions -->
    <h2 style="color:#1877F2;border-bottom:2px solid #1877F2;padding-bottom:8px;margin-top:32px">
      이번 주 반드시 해야 할 액션 3가지
    </h2>
    <div style="background:#f0f2f5;border-radius:10px;padding:20px 24px">
      {action_html}
    </div>

  </div>

  <!-- Footer -->
  <div style="background:#e8eaf0;padding:16px 30px;font-size:11px;color:#888;text-align:center">
    분석 기준일: {today} | 데이터: Meta Graph API (Ad-level daily insights)<br>
    D+N 벤치마크 기준: ROAS 3.0+ 또는 CTR 1.5%+ 우수 광고 {stats["top_performers_cnt"]}개 평균<br>
    분석: Claude Sonnet 4.6 (Meta Ads Expert Agent) | Orbiters
  </div>

</div>
</body>
</html>"""


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Meta Ads 일간 분석 에이전트")
    parser.add_argument("--days",       type=int, default=60,
                        help="수집 기간 일수 (기본 60: 최근 30일 + 우수광고 이력)")
    parser.add_argument("--new-window", type=int, default=7,
                        help="신규 광고 기준 일수 (기본 7일)")
    parser.add_argument("--to",         default=os.getenv("META_REPORT_RECIPIENT", "wj.choi@orbiters.co.kr"),
                        help="수신 이메일")
    parser.add_argument("--dry-run",    action="store_true",
                        help="이메일 발송 없이 HTML 저장만")
    args = parser.parse_args()

    if not ACCESS_TOKEN or not AD_ACCOUNT_ID:
        print("[ERROR] META_ACCESS_TOKEN / META_AD_ACCOUNT_ID 없음")
        sys.exit(1)

    today = date.today()
    until = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    since = (today - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"\n[Meta Agent] 분석일: {today} | 데이터: {since} ~ {until}")
    print(f"[Meta Agent] 신규 광고 기준: 최근 {args.new_window}일\n")

    # Step 1: Fetch
    print("[Step 1] Meta Ads 데이터 수집...")
    campaign_types = fetch_campaign_objectives()
    landing_pages  = fetch_ad_landing_pages()
    raw   = fetch_ad_daily_insights(since, until)
    rows  = process_insights(raw)
    print(f"  처리된 일별 행: {len(rows)}")

    if not rows:
        print("[ERROR] 수집된 데이터 없음")
        sys.exit(1)

    # Step 2: Payload
    payload = build_payload(rows, campaign_types, today, args.new_window, landing_pages)
    print(f"\n[Step 2] 완료")
    print(f"  신규 광고: {payload['stats']['new_ads_count']}개")
    print(f"  우수 광고: {payload['stats']['top_performers_cnt']}개")

    # Step 3: Claude
    print("\n[Step 3] Claude 분석 중...")
    analysis = analyze_with_claude(payload)
    print(f"  전체 평가: {analysis.get('overall_assessment','?')}")
    print(f"  신규 광고 진단: {len(analysis.get('new_ads_diagnosis',[]))}개")
    print(f"  액션: {len(analysis.get('weekly_actions',[]))}개")

    # Step 4: HTML
    print("\n[Step 4] HTML 생성...")
    html = build_html(payload, analysis)

    out_dir = ROOT / ".tmp"
    out_dir.mkdir(exist_ok=True)
    date_str  = today.strftime("%Y%m%d")
    html_path = out_dir / f"meta_ads_report_{date_str}.html"
    json_path = out_dir / f"meta_ads_payload_{date_str}.json"

    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json.dumps({"payload": payload, "analysis": analysis},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  저장: {html_path}")

    # Step 5: Email
    type_30 = payload.get("campaign_type_30d", {})
    cvr_roas = type_30.get("cvr", {}).get("roas", 0)
    traffic_ctr = type_30.get("traffic", {}).get("ctr", 0)
    subject = (
        f"[Meta Ads] {today.strftime('%Y-%m-%d')} | "
        f"신규 {payload['stats']['new_ads_count']}개 | "
        f"CVR ROAS {cvr_roas:.2f}x | Traffic CTR {traffic_ctr:.2f}%"
    )

    if args.dry_run:
        print(f"\n[Dry Run] 이메일 발송 건너뜀")
        print(f"  제목: {subject}")
        print(f"  HTML: {html_path}")
    else:
        print(f"\n[Step 5] 이메일 발송 -> {args.to}")
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "send_gmail.py"),
             "--to", args.to,
             "--subject", subject,
             "--body-file", str(html_path)],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode == 0:
            print(result.stdout)
            print(f"[완료] {args.to} 발송 성공!")
        else:
            print(f"[ERROR] 발송 실패:\n{result.stderr}")
            sys.exit(1)

    print(f"\n[완료] 페이로드: {json_path}")


if __name__ == "__main__":
    main()
