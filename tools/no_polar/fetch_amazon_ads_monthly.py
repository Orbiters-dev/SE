"""
fetch_amazon_ads_monthly.py - Amazon Ads SP campaign daily data collector (Q5 replacement)

Source: Adapted from Orbiters11-dev/dashboard/amz_datacolletor_new.py
Output: .tmp/polar_data/q5_amazon_ads_campaign.json
Format: {"tableData": [{"amazonads_campaign.raw.cost": X, "amazonads_campaign.raw.attributed_sales": X,
                        "amazonads_campaign.raw.clicks": X, "amazonads_campaign.raw.impressions": X,
                        "campaign": "name", "date": "YYYY-MM-01"}]}

Usage:
    python tools/no_polar/fetch_amazon_ads_monthly.py --start 2024-01 --end 2026-02
"""

import os
import sys
import json
import gzip
import time
import hashlib
import argparse
import traceback
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
from pathlib import Path

import requests
from dateutil.relativedelta import relativedelta

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUTPUT_PATH = ROOT / ".tmp" / "polar_data" / "q5_amazon_ads_campaign.json"

# --- credentials from .env ---
AD_CLIENT_ID     = os.getenv("AMZ_ADS_CLIENT_ID")
AD_CLIENT_SECRET = os.getenv("AMZ_ADS_CLIENT_SECRET")
AD_REFRESH_TOKEN = os.getenv("AMZ_ADS_REFRESH_TOKEN")

API_BASE = "https://advertising-api.amazon.com"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


class TokenManager:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        self._token = get_access_token(self.client_id, self.client_secret, self.refresh_token)
        self._expires_at = time.time() + 3600
        return self._token


def _headers_reporting(tm: TokenManager, profile_id: int) -> Dict:
    tok = tm.get_token()
    return {
        "Authorization": f"Bearer {tok}",
        "Amazon-Advertising-API-ClientId": tm.client_id,
        "Amazon-Advertising-API-Scope": str(profile_id),
        "Accept": "application/vnd.adreporting.v3+json",
        "Content-Type": "application/vnd.adreporting.v3+json",
    }


# ---------------------------------------------------------------------------
# Profile discovery
# ---------------------------------------------------------------------------

def get_us_profiles(tm: TokenManager) -> List[Dict]:
    tok = tm.get_token()
    resp = requests.get(
        f"{API_BASE}/v2/profiles",
        headers={
            "Authorization": f"Bearer {tok}",
            "Amazon-Advertising-API-ClientId": tm.client_id,
        },
        timeout=30,
    )
    resp.raise_for_status()
    profiles = resp.json()
    out = []
    for p in profiles:
        if p.get("countryCode") == "US" and p.get("accountInfo", {}).get("type") == "seller":
            out.append({
                "profile_id": p["profileId"],
                "seller": p["accountInfo"].get("name", ""),
                "seller_id": p["accountInfo"].get("id", ""),
            })
    return out


# ---------------------------------------------------------------------------
# SP campaign static metadata
# ---------------------------------------------------------------------------

def fetch_sp_campaign_static(tm: TokenManager, profile_id: int) -> Dict[int, Dict]:
    tok = tm.get_token()
    headers = {
        "Authorization": f"Bearer {tok}",
        "Amazon-Advertising-API-ClientId": tm.client_id,
        "Amazon-Advertising-API-Scope": str(profile_id),
        "Accept": "application/vnd.spCampaign.v3+json",
        "Content-Type": "application/vnd.spCampaign.v3+json",
    }
    payload = {
        "stateFilter": {"include": ["ENABLED", "PAUSED", "ARCHIVED"]},
        "includeExtendedDataFields": False,
    }
    out: Dict[int, Dict] = {}
    start_index = 0
    while True:
        body = {**payload, "startIndex": start_index, "count": 1000}
        resp = requests.post(
            f"{API_BASE}/sp/campaigns/list",
            headers=headers,
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("campaigns", {}).get("items", [])
        for c in items:
            cid = c.get("campaignId")
            if cid:
                out[int(cid)] = {
                    "campaignName": c.get("name", ""),
                    "startDate": c.get("startDate"),
                    "status": c.get("state"),
                    "budget": c.get("budget", {}).get("budget"),
                }
        if len(items) < 1000:
            break
        start_index += 1000
    return out


# ---------------------------------------------------------------------------
# Reporting v3 (async gzip)
# ---------------------------------------------------------------------------

def _parse_gzip(resp: requests.Response) -> List[Dict]:
    ct = resp.headers.get("Content-Type", "")
    raw = resp.content
    if "gzip" in ct or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8")
    obj = json.loads(text)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("data", "results", "records"):
            if k in obj:
                return obj[k]
    return [obj]


def create_report_v3(
    tm: TokenManager,
    profile_id: int,
    start: date,
    end: date,
    columns: List[str],
    name: str = "report",
    max_wait_secs: int = 600,
) -> List[Dict]:
    body = {
        "name": name,
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": ["campaign"],
            "columns": columns,
            "reportTypeId": "spCampaigns",
            "timeUnit": "DAILY",
            "format": "GZIP_JSON",
        },
    }
    headers = _headers_reporting(tm, profile_id)

    # submit
    resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
    if resp.status_code == 401:
        tm._token = None
        headers = _headers_reporting(tm, profile_id)
        resp = requests.post(f"{API_BASE}/reporting/reports", headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    report_id = resp.json()["reportId"]

    # poll
    deadline = time.time() + max_wait_secs
    while time.time() < deadline:
        time.sleep(15)
        st = requests.get(f"{API_BASE}/reporting/reports/{report_id}", headers=headers, timeout=30)
        if st.status_code == 401:
            headers = _headers_reporting(tm, profile_id)
            st = requests.get(f"{API_BASE}/reporting/reports/{report_id}", headers=headers, timeout=30)
        st.raise_for_status()
        status = st.json().get("status")
        if status == "COMPLETED":
            url = st.json().get("url")
            if not url:
                return []
            dl = requests.get(url, timeout=300)
            dl.raise_for_status()
            return _parse_gzip(dl)
        if status == "FAILED":
            raise RuntimeError(f"Report {report_id} FAILED: {st.text}")
    raise TimeoutError(f"Report {report_id} did not complete within {max_wait_secs}s")


# ---------------------------------------------------------------------------
# Daily campaign enrichment
# ---------------------------------------------------------------------------

def enrich_daily(raw_rows: List[Dict], static_by_id: Dict[int, Dict]) -> List[Dict]:
    out = []
    for r in raw_rows:
        imp  = int(r.get("impressions", 0) or 0)
        clk  = int(r.get("clicks", 0) or 0)
        cost = float(r.get("cost", 0.0) or 0.0)
        sal  = float(r.get("sales14d", 0.0) or 0.0)
        pur  = int(r.get("purchases14d", 0) or 0)

        cid = r.get("campaignId")
        stc = static_by_id.get(int(cid), {}) if cid else {}

        out.append({
            "date": r.get("date"),
            "campaignId": cid,
            "campaignName": stc.get("campaignName", str(cid)),
            "impressions": imp,
            "clicks": clk,
            "cost": cost,
            "attributed_sales": sal,
            "purchases": pur,
        })
    return out


# ---------------------------------------------------------------------------
# Collect all SP campaign daily for a date window (chunked by 28d)
# ---------------------------------------------------------------------------

def _date_windows(start: date, end: date, max_days: int = 28):
    cur = start
    while cur <= end:
        win_end = min(end, cur + timedelta(days=max_days - 1))
        yield cur, win_end
        cur = win_end + timedelta(days=1)


def collect_sp_campaign_daily(
    tm: TokenManager,
    profile_id: int,
    start: date,
    end: date,
) -> List[Dict]:
    static_by_id = fetch_sp_campaign_static(tm, profile_id)
    all_rows: List[Dict] = []

    columns = ["date", "campaignId", "impressions", "clicks", "cost", "sales14d", "purchases14d"]

    for s, e in _date_windows(start, end):
        print(f"  [Amazon Ads] fetching {s} ~ {e} (profile {profile_id})")
        chunk = create_report_v3(
            tm, profile_id, s, e,
            columns=columns,
            name=f"SP campaign DAILY {s}~{e}",
        )
        all_rows.extend(enrich_daily(chunk, static_by_id))

    return all_rows


# ---------------------------------------------------------------------------
# Monthly aggregation → Q5 format
# ---------------------------------------------------------------------------

def aggregate_monthly(rows: List[Dict]) -> List[Dict]:
    """
    Aggregate daily rows by (campaign_name, YYYY-MM-01) and emit Q5 format.
    """
    bucket: Dict[Tuple, Dict] = defaultdict(lambda: {
        "cost": 0.0, "attributed_sales": 0.0, "clicks": 0, "impressions": 0
    })

    for r in rows:
        d = r.get("date")
        if not d:
            continue
        try:
            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        month_key = date(dt.year, dt.month, 1).strftime("%Y-%m-%d")
        name = (r.get("campaignName") or str(r.get("campaignId", ""))).lower().replace(" ", "_")
        key = (name, month_key)
        bucket[key]["cost"]             += float(r.get("cost", 0) or 0)
        bucket[key]["attributed_sales"] += float(r.get("attributed_sales", 0) or 0)
        bucket[key]["clicks"]           += int(r.get("clicks", 0) or 0)
        bucket[key]["impressions"]      += int(r.get("impressions", 0) or 0)

    out = []
    for (campaign, month_key), v in sorted(bucket.items()):
        out.append({
            "amazonads_campaign.raw.cost":              round(v["cost"], 4),
            "amazonads_campaign.raw.attributed_sales":  round(v["attributed_sales"], 4),
            "amazonads_campaign.raw.clicks":            v["clicks"],
            "amazonads_campaign.raw.impressions":       v["impressions"],
            "campaign":                                 campaign,
            "date":                                     month_key,
        })
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch Amazon Ads SP campaign data (Q5)")
    parser.add_argument("--start", default="2024-01", help="Start month YYYY-MM")
    parser.add_argument("--end",   default=None,      help="End month YYYY-MM (default: current month)")
    args = parser.parse_args()

    today = date.today()
    start_month = datetime.strptime(args.start, "%Y-%m").date().replace(day=1)
    end_str = args.end or today.strftime("%Y-%m")
    end_month_first = datetime.strptime(end_str, "%Y-%m").date().replace(day=1)
    # last day of end month
    end_date = (end_month_first + relativedelta(months=1)) - timedelta(days=1)
    if end_date > today:
        end_date = today

    if not all([AD_CLIENT_ID, AD_CLIENT_SECRET, AD_REFRESH_TOKEN]):
        print("[ERROR] AMZ_ADS_CLIENT_ID / AMZ_ADS_CLIENT_SECRET / AMZ_ADS_REFRESH_TOKEN not set in .env")
        sys.exit(1)

    print(f"[Amazon Ads] {start_month} ~ {end_date}")

    tm = TokenManager(AD_CLIENT_ID, AD_CLIENT_SECRET, AD_REFRESH_TOKEN)

    profiles = get_us_profiles(tm)
    if not profiles:
        print("[ERROR] No US seller profiles found")
        sys.exit(1)

    print(f"[Amazon Ads] Found {len(profiles)} US profiles: {[p['seller'] for p in profiles]}")

    all_daily: List[Dict] = []
    for prof in profiles:
        pid = prof["profile_id"]
        seller = prof["seller"]
        print(f"\n[Amazon Ads] Profile: {seller} (id={pid})")
        try:
            rows = collect_sp_campaign_daily(tm, pid, start_month, end_date)
            print(f"  -> {len(rows)} daily rows")
            all_daily.extend(rows)
        except Exception as e:
            print(f"  [WARN] Profile {pid} failed: {e}")
            traceback.print_exc()

    monthly = aggregate_monthly(all_daily)
    print(f"\n[Amazon Ads] Monthly rows: {len(monthly)}")

    total_cost  = sum(r["amazonads_campaign.raw.cost"] for r in monthly)
    total_sales = sum(r["amazonads_campaign.raw.attributed_sales"] for r in monthly)
    print(f"[Amazon Ads] Total spend: ${total_cost:,.0f} | attributed sales: ${total_sales:,.0f}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"tableData": monthly, "totalData": {}}, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
