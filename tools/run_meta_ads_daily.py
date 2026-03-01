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

def _api_get(path: str, params: dict, timeout: int = 120) -> dict:
    params["access_token"] = ACCESS_TOKEN
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        raise Exception(f"Meta API: {body.get('error', {}).get('message', str(e))}")

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
        "spend", "impressions", "clicks", "reach",
        "actions", "action_values",
    ])

    all_raw = []
    cur = datetime.strptime(since, "%Y-%m-%d").date()
    end = datetime.strptime(until, "%Y-%m-%d").date()

    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=29))
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
        # Override: Amazon-landing campaigns → traffic (no Meta pixel conversion)
        camp_lower  = camp_name.lower()
        ad_lower    = ad_name.lower()
        AMAZON_SIGNALS = ("wl_", "| wl |", " wl | ", "whitelist", "amazon", "amz", "asin")
        # Naeiae exclusively lands on Amazon
        AMAZON_BRANDS  = ("naeiae", "rice snack", "pop rice")
        # URL-based Amazon detection
        url_is_amazon = "amazon." in landing_url.lower() if landing_url else False
        if camp_type != "traffic" and (
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
    for ad_id, h in histories.items():
        dn = _day_n(h, today)
        if dn < 14:
            continue
        m = _cumulative(h["daily"], h["first_spend_date"], dn)
        if m["spend"] < 50:
            continue
        # Good ROAS (CVR) OR good CTR (Traffic)
        if m["roas"] >= 3.0 or (h["campaign_type"] == "traffic" and m["ctr"] >= 1.5):
            top_performers[ad_id] = {**h, "day_n": dn, "lifetime_metrics": m}

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

    # --- Top Performers Summary — sorted by yesterday spend desc within each type ---
    top_list = sorted(
        top_performers.items(),
        key=lambda kv: (
            0 if kv[1]["campaign_type"] == "cvr" else 1,
            -(kv[1]["lifetime_metrics"]["roas"] if kv[1]["campaign_type"] == "cvr"
              else kv[1]["lifetime_metrics"]["ctr"])
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
        "roas":          h["lifetime_metrics"]["roas"],
        "ctr":           h["lifetime_metrics"]["ctr"],
        "cpm":           h["lifetime_metrics"]["cpm"],
        "cpa":           h["lifetime_metrics"]["cpa"],
        "spend":         h["lifetime_metrics"]["spend"],
        "metrics_1d":    _period_metrics(h["daily"], yesterday,     yesterday),
        "metrics_7d":    _period_metrics(h["daily"], since_7,       yesterday),
        "metrics_p7d":   _period_metrics(h["daily"], prior_7_start, prior_7_end),
        "metrics_30d":   _period_metrics(h["daily"], since_30,      yesterday),
    } for ad_id, h in top_list]

    # --- Worst Performers (D+14+, significant spend, bad metric) ---
    worst_performers = {}
    for ad_id, h in histories.items():
        dn = _day_n(h, today)
        if dn < 14:
            continue
        m = _cumulative(h["daily"], h["first_spend_date"], dn)
        if m["spend"] < 100:
            continue
        if h["campaign_type"] == "cvr" and m["roas"] < 2.0:
            worst_performers[ad_id] = {**h, "day_n": dn, "lifetime_metrics": m}
        elif h["campaign_type"] == "traffic" and m["ctr"] < 1.0:
            worst_performers[ad_id] = {**h, "day_n": dn, "lifetime_metrics": m}

    worst_list = sorted(
        worst_performers.items(),
        key=lambda kv: (
            0 if kv[1]["campaign_type"] == "cvr" else 1,
            (kv[1]["lifetime_metrics"]["roas"] if kv[1]["campaign_type"] == "cvr"
             else kv[1]["lifetime_metrics"]["ctr"])  # ascending: worst first
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
        "roas":          h["lifetime_metrics"]["roas"],
        "ctr":           h["lifetime_metrics"]["ctr"],
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

SYSTEM_PROMPT = """당신은 Meta (Facebook/Instagram) 광고 퍼포먼스 전문 분석가입니다.
이커머스 DTC 브랜드 광고 운영 10년 경력을 보유하고 있으며,
신규 광고 잠재력 진단, 크리에이티브 성과 예측, 오디언스 최적화에 특화되어 있습니다.

분석 원칙:
1. 숫자 나열 금지 — 반드시 의미와 액션을 함께 제시한다
2. Traffic 캠페인 성공 기준: CTR >= 1.5%, CPM 전주 대비 -20% 이내
3. CVR 캠페인 성공 기준: ROAS >= 3.0, CPA 벤치마크 대비 -20% 이내
4. D+N 비교: 신규 광고가 우수 광고들의 같은 시점보다 좋으면 "유망", 나쁘면 "조기 개입 필요"
5. 브랜드별로 반드시 구분하여 분석한다
6. Frequency >= 3.0 이면 오디언스 번아웃 경고
7. 결론은 항상 "이번 주 액션 3가지 (우선순위 순)"로 마무리
8. 모든 액션은 구체적 수치와 추천 강도를 포함한다:
   - 예산 액션: "현재 $XX/일 → $XX/일로 XX% 증액 (강추)" 또는 "XX% 감액 (권장)"
   - 중단 액션: "즉시 OFF (강추)" 또는 "재검토 후 판단 (약추)"
   - 추천 강도: "강추" (즉각 실행 필요) | "권장" (이번 주 내) | "약추" (모니터링 후 결정)

출력: 아래 JSON 구조 엄격히 준수 (코드블록 없이 순수 JSON)
{
  "executive_summary": "3줄 이내 핵심 요약",
  "overall_assessment": "good | warning | danger",
  "new_ads_diagnosis": [
    {
      "ad_name": "광고명",
      "brand": "브랜드",
      "campaign_type": "traffic | cvr",
      "verdict": "유망 | 보통 | 조기개입필요",
      "reason": "D+N 벤치마크 대비 구체적 근거 (수치 포함)",
      "action": "구체적 액션 (예: 일예산 $50→$100 증액 강추 / 즉시 OFF 강추 / 3일 더 관찰 후 판단)"
    }
  ],
  "top_performers_insight": "우수 광고들의 공통점 및 스케일 가능 여부 (스케일업 가능하면 추천 증액 % 포함)",
  "brand_insights": [
    {
      "brand": "브랜드명",
      "status": "good | warning | danger",
      "insight": "1-2줄 인사이트 (핵심 수치 포함)",
      "action": "구체적 액션 + 추천 강도 (예: 전체 예산 20% 증액 강추 / 하위 2개 광고 OFF 권장)"
    }
  ],
  "traffic_vs_cvr_analysis": "Traffic/CVR 캠페인 비교 분석 및 현재 예산 배분 → 최적 배분 제언 (% 또는 금액)",
  "weekly_actions": [
    {"priority": 1, "action": "구체적 액션 + 추천 강도", "target": "대상 광고/캠페인명", "expected_result": "기대 효과 (수치 포함)"},
    {"priority": 2, "action": "구체적 액션 + 추천 강도", "target": "대상 광고/캠페인명", "expected_result": "기대 효과 (수치 포함)"},
    {"priority": 3, "action": "구체적 액션 + 추천 강도", "target": "대상 광고/캠페인명", "expected_result": "기대 효과 (수치 포함)"}
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
신규 광고 퍼포먼스와 우수 광고 D+N 벤치마크를 중심으로 전문가 분석을 JSON으로 제공해주세요.

=== 분석 데이터 ===
{json.dumps(slim, ensure_ascii=False, indent=2)}

중요 체크포인트:
- new_ads 각 항목의 vs_benchmark: 양수(+)면 CTR/ROAS/CVR이 좋은 것, CPM/CPC/CPA는 반대
- benchmark가 null이면 비교 우수 광고 데이터 부족 (절대값으로만 판단)
- campaign_type이 "traffic"이면 ROAS가 낮아도 CTR/CPM으로 평가
- JSON만 출력 (코드블록 없이)"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 8192,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        },
        timeout=180,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip().rstrip("`").strip())


# ===========================================================================
# HTML Email Builder
# ===========================================================================

def _c(val, good_if_high=True, good_thresh=None, warn_thresh=None):
    """Color a numeric value."""
    if val is None:
        return '<span style="color:#999">-</span>'
    if good_thresh is not None:
        color = "#2e7d32" if (val >= good_thresh if good_if_high else val <= good_thresh) else \
                "#d32f2f" if (val < warn_thresh if good_if_high else val > warn_thresh) else "#f57c00"
    else:
        color = "#333"
    return f'<span style="color:{color};font-weight:bold">{val}</span>'

def _roas_cell(v):
    return _c(round(v, 2) if v else v, good_thresh=3.0, warn_thresh=2.0)

def _ctr_cell(v):
    return _c(f"{v:.2f}%" if v else v, good_thresh="1.50%", warn_thresh="0.80%", good_if_high=True) if v else "-"

def _diff_badge(pct, good_if_positive=True):
    """Show % diff vs benchmark with color."""
    if pct is None:
        return '<span style="color:#aaa">n/a</span>'
    good = (pct > 0) == good_if_positive
    color = "#2e7d32" if good else "#d32f2f"
    arrow = "▲" if pct > 0 else "▼"
    return f'<span style="color:{color};font-weight:bold">{arrow}{abs(pct):.1f}%</span>'

def _verdict_badge(verdict):
    colors = {"유망": "#2e7d32", "보통": "#f57c00", "조기개입필요": "#d32f2f"}
    color = colors.get(verdict, "#555")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:12px">{verdict}</span>'

def _status_dot(status):
    colors = {"good": "#2e7d32", "warning": "#f57c00", "danger": "#d32f2f"}
    return f'<span style="color:{colors.get(status,"#555")};font-size:18px">&#9679;</span>'


def _build_yesterday_block(ys: dict, brand_detail: list = None) -> str:
    """어제 PST 기준 전체 지출 + 브랜드×기간×타입 상세 테이블."""
    if not ys or ys.get("total", 0) == 0:
        return ""

    total   = ys["total"]
    by_type = ys.get("by_type", {})
    type_colors = {"traffic": "#1565c0", "cvr": "#2e7d32", "other": "#555"}
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
            color = "#2e7d32" if roas >= 3.0 else "#d32f2f" if roas < 2.0 else "#f57c00"
            metric = f'<span style="color:{color};font-weight:bold">{roas:.2f}x</span>'
        else:
            ctr = d.get("ctr", 0)
            cpc = d.get("cpc", 0)
            color = "#1565c0" if ctr >= 1.5 else "#d32f2f" if ctr < 0.8 else "#f57c00"
            metric = f'<span style="color:{color};font-weight:bold">{ctr:.2f}%</span>'
        return (f'<td style="padding:4px 6px;font-size:11px;text-align:right;vertical-align:top">'
                f'<div style="font-weight:bold">${sp:,.0f}</div>'
                f'<div style="font-size:10px;color:#888">{metric} {ads}개</div>'
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

        cvr_section     = _brand_section("cvr",     "#2e7d32", "CVR 캠페인 (전환 목적)")
        traffic_section = _brand_section("traffic",  "#1565c0", "Traffic 캠페인 (인지/클릭 목적)")
        detail_html = cvr_section + traffic_section

    return f"""
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:10px;padding:16px 20px;margin-bottom:24px">
      <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:10px">
        <div>
          <div style="font-size:11px;color:#f57c00;font-weight:600;letter-spacing:.5px;text-transform:uppercase">어제 실지출 (PST {ys["date"]})</div>
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
    oa_color = {"good": "#2e7d32", "warning": "#f57c00", "danger": "#d32f2f"}.get(oa, "#f57c00")

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
              <td colspan="9" style="padding:6px 12px 10px 24px;font-size:12px;color:#555;font-style:italic">
                {diagnosis.get("reason", "")}
                {f" → <strong>{diagnosis.get('action', '')}</strong>" if diagnosis.get("action") else ""}
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
        metric_label = "ROAS" if ctype == "cvr" else "CTR"

        def _sp(m):
            return f'${m.get("spend",0):,.0f}' if m.get("spend", 0) > 0 else "-"

        def _mk(m, worst=sort_worst):
            if not m.get("spend", 0):
                return ""
            if ctype == "cvr":
                roas = m.get("roas", 0)
                c = "#2e7d32" if roas >= 3.0 else "#d32f2f" if roas < 2.0 else "#f57c00"
                return f'<div style="font-size:10px;color:{c};font-weight:bold">{roas:.2f}x</div>'
            else:
                ctr = m.get("ctr", 0)
                c = "#1565c0" if ctr >= 1.5 else "#d32f2f" if ctr < 0.8 else "#f57c00"
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
                lifetime_str = f'{t["roas"]:.2f}x' if ctype == "cvr" else f'{t["ctr"]:.2f}%'
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
          <td style="padding:7px 8px;text-align:right;color:#e65100;font-weight:bold">{_sp(m1d)}{_mk(m1d)}</td>
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
                <th style="padding:7px 8px;text-align:right;color:#e65100">어제(1일)</th>
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

    top_cvr_section     = _performer_section(payload["top_performers"],   "cvr",     "#2e7d32", "CVR 우수 광고 (전환 목적, ROAS 3.0+) — 어제 지출 높은순")
    top_traffic_section = _performer_section(payload["top_performers"],   "traffic",  "#1565c0", "Traffic 우수 광고 (인지/클릭 목적, CTR 1.5%+) — 어제 지출 높은순")
    worst_cvr_section     = _performer_section(payload.get("worst_performers", []), "cvr",    "#b71c1c", "CVR 워스트 광고 (ROAS 2.0 미만) — 최악순", sort_worst=True)
    worst_traffic_section = _performer_section(payload.get("worst_performers", []), "traffic", "#e65100", "Traffic 워스트 광고 (CTR 1.0% 미만) — 최악순", sort_worst=True)

    # ── Section 3: Brand Comparison (최근 7일 / 이전 7일 / 최근 30일) ───────────────────
    brand_rows = ""
    for b in payload.get("brand_comparison", []):
        brand_insight = next((bi for bi in analysis.get("brand_insights", [])
                              if bi.get("brand") == b["brand"]), {})
        status = brand_insight.get("status", "")
        dot = _status_dot(status) if status else ""
        roas_wow = b.get("roas_wow")
        ctr_wow  = b.get("ctr_wow")
        brand_rows += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:10px 12px">{dot} <strong>{b["brand"]}</strong></td>
          <td style="padding:8px 8px;text-align:right;color:#e65100;font-weight:bold">${b.get("spend_1d",0):,.0f}</td>
          <td style="padding:8px 8px;text-align:right;font-weight:bold">${b["spend_7d"]:,.0f}</td>
          <td style="padding:8px 8px;text-align:right;color:#888">${b["spend_p7d"]:,.0f}</td>
          <td style="padding:8px 8px;text-align:right;color:#aaa">${b["spend_30d"]:,.0f}</td>
          <td style="padding:8px 8px;text-align:center;color:#e65100">{b.get("roas_1d",0):.2f}x</td>
          <td style="padding:8px 8px;text-align:center">{_roas_cell(b["roas_7d"])}</td>
          <td style="padding:8px 8px;text-align:center;color:#888">{b["roas_p7d"]:.2f}x</td>
          <td style="padding:8px 8px;text-align:center;color:#aaa">{b["roas_30d"]:.2f}x</td>
          <td style="padding:8px 8px;text-align:center">{_diff_badge(roas_wow, True) if roas_wow is not None else "-"}<br><span style="font-size:10px;color:#aaa">WoW</span></td>
          <td style="padding:8px 8px;text-align:center;color:#e65100">{b.get("ctr_1d",0):.2f}%</td>
          <td style="padding:8px 8px;text-align:center">{b["ctr_7d"]:.2f}%</td>
          <td style="padding:8px 8px;text-align:center;color:#888">{b["ctr_p7d"]:.2f}%</td>
          <td style="padding:8px 8px;text-align:center;color:#aaa">{b["ctr_30d"]:.2f}%</td>
          <td style="padding:8px 8px;text-align:center">{_diff_badge(ctr_wow, True) if ctr_wow is not None else "-"}<br><span style="font-size:10px;color:#aaa">WoW</span></td>
          <td style="padding:8px 8px;font-size:12px;color:#555">{brand_insight.get("insight","")}</td>
        </tr>"""
        if brand_insight.get("action"):
            brand_rows += f"""
        <tr style="background:#f5f5f5;border-bottom:1px solid #ddd">
          <td colspan="16" style="padding:5px 12px 8px 32px;font-size:12px;color:#1565c0">
            &#8594; {brand_insight["action"]}
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
        hdr_color = "#1565c0" if ctype == "traffic" else "#2e7d32" if ctype == "cvr" else "#555"
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
                <th style="padding:8px 10px;text-align:right;color:#e65100;font-weight:700;border-bottom:1px solid #e0e0e0">어제</th>
                <th style="padding:8px 10px;text-align:right;color:{hdr_color};font-weight:700;border-bottom:1px solid #e0e0e0">최근 7일</th>
                <th style="padding:8px 10px;text-align:right;color:#888;border-bottom:1px solid #e0e0e0">이전 7일</th>
                <th style="padding:8px 10px;text-align:right;color:#aaa;border-bottom:1px solid #e0e0e0">최근 30일</th>
                <th style="padding:8px 10px;text-align:right;color:#555;border-bottom:1px solid #e0e0e0">WoW</th>
              </tr>
            </thead>
            <tbody>
              <tr style="border-top:1px solid #f0f0f0">
                <td style="padding:7px 12px;color:#888">광고 수</td>
                <td style="padding:7px 10px;text-align:right;color:#e65100">{v1d.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">{v7.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">{vp7.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">{v30.get('ad_count',0)}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">-</td>
              </tr>
              <tr style="background:#fafafa;border-top:1px solid #f0f0f0">
                <td style="padding:7px 12px;color:#888">지출</td>
                <td style="padding:7px 10px;text-align:right;color:#e65100">${v1d.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">${v7.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">${vp7.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">${v30.get('spend',0):,.0f}</td>
                <td style="padding:7px 10px;text-align:right">-</td>
              </tr>
              <tr style="border-top:1px solid #f0f0f0;{'background:#fffde7' if is_traffic else ''}">
                <td style="padding:7px 12px;color:#888">{'CTR ★' if is_traffic else 'CTR'}</td>
                <td style="padding:7px 10px;text-align:right;color:#e65100">{v1d.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">{v7.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right;color:#888">{vp7.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">{v30.get('ctr',0):.2f}%</td>
                <td style="padding:7px 10px;text-align:right">{_pct_wow(v7.get('ctr',0), vp7.get('ctr',0), True)}</td>
              </tr>
              <tr style="border-top:1px solid #f0f0f0;{'background:#fffde7' if is_traffic else 'background:#fafafa'}">
                <td style="padding:7px 12px;color:#888">{'CPC ★' if is_traffic else 'CPC'}</td>
                <td style="padding:7px 10px;text-align:right;color:#e65100">${v1d.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">${v7.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">${vp7.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">${v30.get('cpc',0):.2f}</td>
                <td style="padding:7px 10px;text-align:right">{_pct_wow(v7.get('cpc',0), vp7.get('cpc',0), False)}</td>
              </tr>
              <tr style="border-top:1px solid #f0f0f0;{'background:#fffde7' if not is_traffic else ''}">
                <td style="padding:7px 12px;color:#888">{'ROAS ★' if not is_traffic else 'ROAS'}</td>
                <td style="padding:7px 10px;text-align:right;color:#e65100">{'N/A' if is_traffic else f'{roas_1d:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right;font-weight:bold">{'N/A' if is_traffic else f'{roas_7:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right;color:#888">{'N/A' if is_traffic else f'{roas_p7:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right;color:#aaa">{'N/A' if is_traffic else f'{roas_30:.2f}x'}</td>
                <td style="padding:7px 10px;text-align:right">{'-' if is_traffic else _pct_wow(roas_7, roas_p7, True)}</td>
              </tr>
              <tr style="background:#fafafa;border-top:1px solid #f0f0f0">
                <td style="padding:7px 12px;color:#888">CPM</td>
                <td style="padding:7px 10px;text-align:right;color:#e65100">${v1d.get('cpm',0):.2f}</td>
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
        sc = {"good": "#2e7d32", "warning": "#f57c00", "danger": "#d32f2f"}.get(bi.get("status",""), "#555")
        brand_insight_cards += f"""
        <div style="border-left:4px solid {sc};padding:10px 16px;margin:8px 0;background:#fafafa;border-radius:0 6px 6px 0">
          <strong style="color:{sc}">{bi["brand"]}</strong>
          <p style="margin:4px 0;color:#333;font-size:13px">{bi["insight"]}</p>
          <p style="margin:4px 0;color:#555;font-size:12px">&#8594; {bi["action"]}</p>
        </div>"""

    # ── Section 6: Weekly Actions ─────────────────────────────────
    action_html = ""
    for wa in analysis.get("weekly_actions", []):
        action_html += f"""
        <div style="display:flex;align-items:flex-start;margin:14px 0">
          <div style="background:#1877F2;color:white;border-radius:50%;width:28px;height:28px;
                      min-width:28px;display:flex;align-items:center;justify-content:center;
                      font-weight:bold;margin-right:14px;font-size:14px">{wa["priority"]}</div>
          <div>
            <strong style="color:#222;font-size:14px">{wa["action"]}</strong>
            <p style="margin:3px 0;color:#666;font-size:12px">대상: {wa.get("target","-")}</p>
            <p style="margin:3px 0;color:#2e7d32;font-size:12px">&#8594; {wa.get("expected_result","")}</p>
          </div>
        </div>"""

    stats = payload["stats"]
    tvc = analysis.get("traffic_vs_cvr_analysis", "")

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
      {analysis.get("executive_summary","").replace(chr(10), "<br>")}
    </div>
  </div>

  <div style="padding:24px 30px">

    <!-- Yesterday PST Spend -->
    {_build_yesterday_block(payload.get("yesterday_spend", {}), payload.get("brand_detail_table", []))}

    <!-- Campaign Type Overview -->
    <h2 style="color:#1877F2;border-bottom:2px solid #1877F2;padding-bottom:8px">캠페인 유형별 성과 <span style="font-size:14px;color:#888;font-weight:normal">— 어제 / 최근 7일 / 이전 7일 / 최근 30일</span></h2>
    <p style="font-size:12px;color:#888;margin:0 0 12px">★ = 해당 캠페인 유형의 핵심 지표 | WoW = 최근 7일 vs 이전 7일 | <span style="color:#e65100">주황 = 어제 (PST)</span></p>
    <div style="margin-bottom:8px">{type_html}</div>
    <div style="background:#e8f4fd;border-left:4px solid #1877F2;padding:12px 16px;border-radius:0 6px 6px 0;font-size:13px;color:#444;margin-top:12px">
      {tvc}
    </div>

    <!-- New Ads: CVR -->
    <h2 style="color:#2e7d32;border-bottom:2px solid #2e7d32;padding-bottom:8px;margin-top:32px">
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
      신규 광고 D+N 벤치마크의 기준. <span style="color:#e65100">주황=어제</span> | <strong>굵음=최근7일</strong> | 회색=이전7일 | 연회색=30일
    </p>
    <div style="font-size:13px;color:#444;background:#f8f9fa;padding:12px 16px;border-radius:6px;margin-bottom:16px">
      {analysis.get("top_performers_insight","")}
    </div>
    {top_cvr_section}
    {top_traffic_section}

    <!-- Worst Performers -->
    <h2 style="color:#b71c1c;border-bottom:2px solid #b71c1c;padding-bottom:8px;margin-top:32px">
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
      * <span style="color:#e65100">주황 = 어제</span> | <strong>굵은 숫자</strong> = 최근 7일 | 회색 = 이전 7일 (14일~8일전) | 연회색 = 30일 | WoW = 최근 7일 vs 이전 7일
    </p>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:12px;min-width:700px">
      <thead>
        <tr style="background:#f0f0f0">
          <th style="padding:8px 10px;text-align:left" rowspan="2">브랜드</th>
          <th style="padding:6px 8px;text-align:center;border-bottom:1px solid #ddd" colspan="4">지출</th>
          <th style="padding:6px 8px;text-align:center;border-bottom:1px solid #ddd" colspan="5">ROAS</th>
          <th style="padding:6px 8px;text-align:center;border-bottom:1px solid #ddd" colspan="5">CTR</th>
          <th style="padding:6px 8px;text-align:left" rowspan="2">인사이트</th>
        </tr>
        <tr style="background:#f5f5f5;font-size:11px;color:#666">
          <th style="padding:4px 8px;text-align:right;color:#e65100">어제</th>
          <th style="padding:4px 8px;text-align:right">7일</th>
          <th style="padding:4px 8px;text-align:right">이전7일</th>
          <th style="padding:4px 8px;text-align:right">30일</th>
          <th style="padding:4px 8px;text-align:center;color:#e65100">어제</th>
          <th style="padding:4px 8px;text-align:center">7일</th>
          <th style="padding:4px 8px;text-align:center">이전7일</th>
          <th style="padding:4px 8px;text-align:center">30일</th>
          <th style="padding:4px 8px;text-align:center">WoW</th>
          <th style="padding:4px 8px;text-align:center;color:#e65100">어제</th>
          <th style="padding:4px 8px;text-align:center">7일</th>
          <th style="padding:4px 8px;text-align:center">이전7일</th>
          <th style="padding:4px 8px;text-align:center">30일</th>
          <th style="padding:4px 8px;text-align:center">WoW</th>
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
