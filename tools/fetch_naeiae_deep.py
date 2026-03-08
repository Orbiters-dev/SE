"""
fetch_naeiae_deep.py - Fleeters Inc 키워드/서치텀/캠페인 상세 데이터 수집
Usage: python tools/fetch_naeiae_deep.py
Output: .tmp/naeiae_deep_YYYYMMDD.json
"""
import gzip, json, os, sys, time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from env_loader import load_env
load_env()

import requests

ROOT    = TOOLS_DIR.parent
TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(exist_ok=True)
OUTPUT  = TMP_DIR / f"naeiae_deep_{date.today().strftime('%Y%m%d')}.json"

AD_CLIENT_ID     = os.getenv("AMZ_ADS_CLIENT_ID")
AD_CLIENT_SECRET = os.getenv("AMZ_ADS_CLIENT_SECRET")
AD_REFRESH_TOKEN = os.getenv("AMZ_ADS_REFRESH_TOKEN")
API_BASE         = "https://advertising-api.amazon.com"
PROFILE_ID       = 1766270639560191  # Fleeters Inc

# ── Auth ─────────────────────────────────────────────────────────────────────
def get_token():
    r = requests.post("https://api.amazon.com/auth/o2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": AD_REFRESH_TOKEN,
        "client_id": AD_CLIENT_ID,
        "client_secret": AD_CLIENT_SECRET,
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

_token = None
_expires = 0.0

def token():
    global _token, _expires
    if _token and time.time() < _expires - 60:
        return _token
    _token = get_token()
    _expires = time.time() + 3600
    return _token

def hdrs():
    return {"Authorization": f"Bearer {token()}", "Amazon-Advertising-API-ClientId": AD_CLIENT_ID, "Amazon-Advertising-API-Scope": str(PROFILE_ID)}
def hdrs_sp():
    return {**hdrs(), "Accept": "application/vnd.spCampaign.v3+json", "Content-Type": "application/vnd.spCampaign.v3+json"}
def hdrs_rpt():
    return {**hdrs(), "Accept": "application/vnd.adreporting.v3+json", "Content-Type": "application/vnd.adreporting.v3+json"}

# ── Campaigns ────────────────────────────────────────────────────────────────
def fetch_campaigns():
    print("[1/4] Fetching campaigns (name, budget, targeting type)...")
    campaigns = []
    start_index = 0
    while True:
        r = requests.get(
            f"{API_BASE}/sp/campaigns",
            headers=hdrs(),
            params={"startIndex": start_index, "count": 100, "stateFilter": "enabled,paused"},
            timeout=30,
        )
        if not r.ok:
            print(f"  [WARN] campaigns GET {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        items = data if isinstance(data, list) else data.get("campaigns", [])
        for c in items:
            campaigns.append({
                "campaignId": str(c.get("campaignId", "")),
                "name": c.get("name", ""),
                "state": c.get("state", ""),
                "dailyBudget": float(c.get("dailyBudget", 0) or 0),
                "targetingType": c.get("targetingType", "UNKNOWN"),
            })
        if len(items) < 100:
            break
        start_index += 100
        time.sleep(1)
    print(f"  -> {len(campaigns)} campaigns")
    return campaigns

# ── Report helper ─────────────────────────────────────────────────────────────
def run_report(body, label):
    r = requests.post(f"{API_BASE}/reporting/reports", headers=hdrs_rpt(), json=body, timeout=60)
    if r.status_code == 425:
        time.sleep(30)
        r = requests.post(f"{API_BASE}/reporting/reports", headers=hdrs_rpt(), json=body, timeout=60)
    if not r.ok:
        print(f"  [WARN] {label} failed: {r.status_code} {r.text[:200]}")
        return []
    report_id = r.json()["reportId"]
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(15)
        st = requests.get(f"{API_BASE}/reporting/reports/{report_id}", headers=hdrs_rpt(), timeout=30)
        st.raise_for_status()
        info = st.json()
        if info.get("status") == "COMPLETED":
            url = info.get("url")
            if url:
                dl = requests.get(url, timeout=300)
                raw = dl.content
                if raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                rows = json.loads(raw.decode("utf-8"))
                if isinstance(rows, dict):
                    for k in ("data", "results", "records"):
                        if k in rows:
                            rows = rows[k]; break
                return rows
            return []
        if info.get("status") == "FAILED":
            print(f"  [WARN] {label} report FAILED")
            return []
    return []

# ── Keyword Report (14d) ──────────────────────────────────────────────────────
def fetch_keyword_report(start: date, end: date):
    print(f"[2/4] Keyword report {start} ~ {end}...")
    body = {
        "name": f"KW {start}~{end}",
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": ["keyword"],
            "columns": ["campaignId", "adGroupId", "keywordId", "keywordText",
                        "matchType", "keywordBid", "impressions", "clicks",
                        "cost", "sales14d", "purchases14d"],
            "reportTypeId": "spKeywords",
            "timeUnit": "SUMMARY",
            "format": "GZIP_JSON",
        },
    }
    rows = run_report(body, "keyword")
    print(f"  -> {len(rows)} keyword rows")
    return rows

# ── Search Term Report (14d) ──────────────────────────────────────────────────
def fetch_search_term_report(start: date, end: date):
    print(f"[3/4] Search term report {start} ~ {end}...")
    body = {
        "name": f"ST {start}~{end}",
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": ["searchTerm"],
            "columns": ["campaignId", "adGroupId", "keywordId", "searchTerm",
                        "impressions", "clicks", "cost", "sales14d", "purchases14d"],
            "reportTypeId": "spSearchTerm",
            "timeUnit": "SUMMARY",
            "format": "GZIP_JSON",
        },
    }
    rows = run_report(body, "searchTerm")
    print(f"  -> {len(rows)} search term rows")
    return rows

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    end   = date.today() - timedelta(days=2)   # 2d attribution lag
    start = end - timedelta(days=13)            # 14d window

    campaigns  = fetch_campaigns()
    kw_rows    = fetch_keyword_report(start, end)
    st_rows    = fetch_search_term_report(start, end)

    # Build campaign lookup
    camp_map = {c["campaignId"]: c for c in campaigns}

    # Aggregate keyword metrics by campaign
    kw_by_camp = defaultdict(list)
    for kw in kw_rows:
        cid = str(kw.get("campaignId", ""))
        kw_by_camp[cid].append({
            "keywordText": kw.get("keywordText", ""),
            "matchType": kw.get("matchType", ""),
            "keywordBid": float(kw.get("keywordBid", 0) or 0),
            "impressions": int(kw.get("impressions", 0) or 0),
            "clicks": int(kw.get("clicks", 0) or 0),
            "cost": float(kw.get("cost", 0) or 0),
            "sales14d": float(kw.get("sales14d", 0) or 0),
            "purchases14d": int(kw.get("purchases14d", 0) or 0),
            "roas": round(float(kw.get("sales14d", 0) or 0) / float(kw.get("cost", 0) or 1), 2),
            "acos": round(float(kw.get("cost", 0) or 0) / max(float(kw.get("sales14d", 0) or 0), 0.01), 3),
        })

    # Aggregate ST metrics
    st_agg = defaultdict(lambda: {"spend": 0, "sales": 0, "clicks": 0, "purchases": 0})
    for st in st_rows:
        key = st.get("searchTerm", "")
        st_agg[key]["spend"]     += float(st.get("cost", 0) or 0)
        st_agg[key]["sales"]     += float(st.get("sales14d", 0) or 0)
        st_agg[key]["clicks"]    += int(st.get("clicks", 0) or 0)
        st_agg[key]["purchases"] += int(st.get("purchases14d", 0) or 0)
        st_agg[key]["campaignId"] = str(st.get("campaignId", ""))

    st_list = []
    for term, v in st_agg.items():
        roas = round(v["sales"] / max(v["spend"], 0.01), 2)
        acos = round(v["spend"] / max(v["sales"], 0.01), 3)
        st_list.append({**v, "searchTerm": term, "roas": roas, "acos": acos,
                        "campaignName": camp_map.get(v["campaignId"], {}).get("name", "")})

    # Sort by spend desc
    st_list.sort(key=lambda x: x["spend"], reverse=True)

    print(f"[4/4] Saving to {OUTPUT}...")
    out = {
        "date": str(date.today()),
        "analysis_window": f"{start} ~ {end}",
        "campaigns": campaigns,
        "keyword_rows": [
            {**kw, "campaignName": camp_map.get(str(kw_rows[i].get("campaignId","")), {}).get("name",""),
             "targetingType": camp_map.get(str(kw_rows[i].get("campaignId","")), {}).get("targetingType","UNKNOWN")}
            for i, kw in enumerate(kw_rows)
        ] if kw_rows else [],
        "keywords_by_campaign": {
            cid: {
                "campaignName": camp_map.get(cid, {}).get("name", cid),
                "targetingType": camp_map.get(cid, {}).get("targetingType", "UNKNOWN"),
                "dailyBudget": camp_map.get(cid, {}).get("dailyBudget", 0),
                "keywords": sorted(kws, key=lambda x: x["cost"], reverse=True)
            }
            for cid, kws in kw_by_camp.items()
        },
        "search_terms_top50": st_list[:50],
        "search_terms_zero_sales": [s for s in st_list if s["sales"] == 0 and s["spend"] > 5][:30],
        "search_terms_harvest_candidates": [
            s for s in st_list
            if s["acos"] < 0.25 and s["clicks"] >= 5 and s["purchases"] >= 1
        ][:20],
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {OUTPUT}")
    print(f"  Campaigns: {len(campaigns)}, Keywords: {len(kw_rows)}, SearchTerms: {len(st_rows)}")

if __name__ == "__main__":
    main()
