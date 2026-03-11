"""
fetch_search_volume.py - Search volume data collector (Q12)

Fetches Google Ads search volume, Amazon search volume, and Google Trends
for brand keywords via DataForSEO API.

Output: .tmp/polar_data/q12_search_volume.json
Format: {"keywords": [...],
         "google_ads": {keyword: {search_volume, competition, cpc, monthly: {"YYYY-MM": int}}},
         "amazon": {keyword: {search_volume}},
         "google_trends": {keyword: {"YYYY-MM": float}},
         "merge_groups": {...}}

Usage:
    python tools/no_polar/fetch_search_volume.py
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import date
from pathlib import Path

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUTPUT_PATH = ROOT / ".tmp" / "polar_data" / "q12_search_volume.json"

API_BASE = "https://api.dataforseo.com/v3"
LOCATION_CODE = 2840  # US
LANGUAGE_CODE = "en"

KEYWORDS = [
    "onzenna", "zezebaebae", "grosmimi", "alpremio",
    "cha and mom", "cha&mom", "comme moi",
    "babyrabbit", "baby rabbit", "naeiae",
    "bamboobebe", "hattung", "beemymagic",
    "nature love mere", "ppsu", "ppsu bottle",
    "ppsu baby bottle", "phyto seline", "phytoseline",
]

MERGE_GROUPS = {
    "Cha&Mom": ["cha and mom", "cha&mom"],
    "BabyRabbit": ["babyrabbit", "baby rabbit"],
    "Phyto Seline": ["phyto seline", "phytoseline"],
}


def _get_auth():
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        print("[ERROR] DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set")
        sys.exit(1)
    return (login, password)


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def fetch_google_ads_volume(keywords, auth):
    """Google Ads search volume with monthly history."""
    print("  [Google Ads] Fetching search volume...")
    payload = [{
        "keywords": keywords,
        "location_code": LOCATION_CODE,
        "language_code": LANGUAGE_CODE,
    }]
    url = f"{API_BASE}/keywords_data/google_ads/search_volume/live"
    resp = requests.post(url, auth=auth, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    results = {}
    for task in data.get("tasks", []):
        for item in (task.get("result") or []):
            kw = (item.get("keyword") or "").lower()
            monthly_raw = item.get("monthly_searches") or []
            monthly = {}
            for m in monthly_raw:
                key = f"{m['year']}-{m['month']:02d}"
                monthly[key] = m.get("search_volume")
            results[kw] = {
                "search_volume": item.get("search_volume"),
                "competition": item.get("competition"),
                "cpc": item.get("cpc"),
                "monthly": monthly,
            }

    found = sum(1 for v in results.values() if v.get("search_volume"))
    print(f"  [Google Ads] {len(results)} keywords, {found} with data")
    return results


def fetch_amazon_volume(keywords, auth):
    """Amazon bulk search volume."""
    print("  [Amazon] Fetching search volume...")
    payload = [{
        "keywords": keywords,
        "location_code": LOCATION_CODE,
        "language_code": LANGUAGE_CODE,
    }]
    url = f"{API_BASE}/dataforseo_labs/amazon/bulk_search_volume/live"
    resp = requests.post(url, auth=auth, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    results = {}
    for task in data.get("tasks", []):
        for res in (task.get("result") or []):
            for item in (res.get("items") or []):
                kw = (item.get("keyword") or "").lower()
                results[kw] = {
                    "search_volume": item.get("search_volume"),
                }

    found = sum(1 for v in results.values() if v.get("search_volume"))
    print(f"  [Amazon] {len(results)} keywords, {found} with data")
    return results


def fetch_google_trends(keywords, auth):
    """Google Trends via DataForSEO (5 keywords per request max)."""
    print("  [Google Trends] Fetching trends data...")
    results = {}

    for chunk in _chunks(keywords, 5):
        payload = [{
            "keywords": chunk,
            "location_code": LOCATION_CODE,
            "type": "web",
            "time_range": "past_5_years",
        }]
        url = f"{API_BASE}/keywords_data/google_trends/explore/live"
        try:
            resp = requests.post(url, auth=auth, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            for task in data.get("tasks", []):
                for res in (task.get("result") or []):
                    for line in (res.get("items") or []):
                        kw = (line.get("keywords") or [""])[0].lower() if isinstance(line.get("keywords"), list) else ""
                        # line_data has time_series with date+value pairs
                        ts = line.get("data") or []
                        if isinstance(ts, dict):
                            ts = ts.get("items") or ts.get("time_series") or []

                        monthly = {}
                        for point in ts:
                            if isinstance(point, dict):
                                dt_str = point.get("date_from") or point.get("date") or ""
                                val = point.get("values") or [{}]
                                if isinstance(val, list) and val:
                                    v = val[0].get("value") if isinstance(val[0], dict) else val[0]
                                else:
                                    v = point.get("value")
                                if dt_str and v is not None:
                                    key = dt_str[:7]  # YYYY-MM
                                    monthly[key] = round(float(v), 1) if v else 0

                        if kw and monthly:
                            results[kw] = monthly

        except Exception as e:
            print(f"    [WARN] Trends chunk {chunk} failed: {e}")

        time.sleep(0.5)

    print(f"  [Google Trends] {len(results)} keywords with data")
    return results


def fetch_google_trends_fallback(keywords):
    """Fallback: use pytrends if DataForSEO Trends fails."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("  [WARN] pytrends not installed, skipping Google Trends")
        return {}

    print("  [Google Trends fallback] Using pytrends...")
    pytrends = TrendReq(hl='en-US', tz=360)
    results = {}

    for chunk in _chunks(keywords, 5):
        try:
            pytrends.build_payload(chunk, timeframe='2021-01-01 ' + date.today().strftime('%Y-%m-%d'), geo='US')
            df = pytrends.interest_over_time()
            for kw in chunk:
                if kw in df.columns:
                    monthly = {}
                    for idx, val in df[kw].items():
                        key = f"{idx.year}-{idx.month:02d}"
                        if key not in monthly:
                            monthly[key] = []
                        monthly[key].append(float(val))
                    # Average per month
                    results[kw] = {k: round(sum(v) / len(v), 1) for k, v in monthly.items() if sum(v) > 0}
            time.sleep(2)
        except Exception as e:
            print(f"    [WARN] pytrends chunk {chunk} failed: {e}")

    print(f"  [Google Trends fallback] {len(results)} keywords with data")
    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch search volume data (Q12)")
    parser.add_argument("--no-trends", action="store_true", help="Skip Google Trends (faster)")
    args = parser.parse_args()

    auth = _get_auth()
    print(f"[Search Volume Q12] {len(KEYWORDS)} keywords")

    # 1. Google Ads volume
    google_ads = fetch_google_ads_volume(KEYWORDS, auth)

    # 2. Amazon volume
    amazon = fetch_amazon_volume(KEYWORDS, auth)

    # 3. Google Trends
    google_trends = {}
    if not args.no_trends:
        google_trends = fetch_google_trends(KEYWORDS, auth)
        if not google_trends:
            google_trends = fetch_google_trends_fallback(KEYWORDS)

    # Ensure all keywords present in each section
    for kw in KEYWORDS:
        if kw not in google_ads:
            google_ads[kw] = {"search_volume": None, "competition": None, "cpc": None, "monthly": {}}
        if kw not in amazon:
            amazon[kw] = {"search_volume": None}

    output = {
        "keywords": KEYWORDS,
        "google_ads": google_ads,
        "amazon": amazon,
        "google_trends": google_trends,
        "merge_groups": MERGE_GROUPS,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Q12 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
