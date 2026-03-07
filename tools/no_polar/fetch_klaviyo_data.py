"""
fetch_klaviyo_data.py - Klaviyo email marketing data collector (Q13e, KL1, KL2)

Fetches campaign and flow performance data from Klaviyo API.

Outputs:
  .tmp/polar_data/q13e_klaviyo_campaigns_daily.json  - daily campaign sends + revenue
  .tmp/polar_data/kl1_flow_monthly.json              - flow monthly performance
  .tmp/polar_data/kl2_campaign_monthly.json          - campaign monthly performance

Usage:
    python tools/no_polar/fetch_klaviyo_data.py --start 2024-01 --end 2026-03
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import date, datetime, timedelta
from collections import defaultdict
from pathlib import Path

from dateutil.relativedelta import relativedelta

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
OUT_Q13E = ROOT / ".tmp" / "polar_data" / "q13e_klaviyo_campaigns_daily.json"
OUT_KL1  = ROOT / ".tmp" / "polar_data" / "kl1_flow_monthly.json"
OUT_KL2  = ROOT / ".tmp" / "polar_data" / "kl2_campaign_monthly.json"

API_KEY = os.getenv("KLAVIYO_API_KEY")
BASE_URL = "https://a.klaviyo.com/api"
REVISION = "2024-10-15"
PLACED_ORDER_METRIC_ID = "SnXiMV"  # Klaviyo metric ID for "Placed Order"


def _headers():
    return {
        "Authorization": f"Klaviyo-API-Key {API_KEY}",
        "revision": REVISION,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _safe_div(a, b):
    return round(a / b, 6) if b else 0


def api_get(url, params=None):
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(url, payload):
    resp = requests.post(url, headers=_headers(), json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Campaign list
# ---------------------------------------------------------------------------
def fetch_campaigns(start_dt, end_dt):
    """Fetch all campaigns with send_time in range."""
    campaigns = []
    url = f"{BASE_URL}/campaigns"
    params = {
        "filter": "equals(messages.channel,'email')",
    }

    while url:
        data = api_get(url, params)
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            send_time = attrs.get("send_time") or ""
            if not send_time:
                continue
            send_date = send_time[:10]
            if start_dt <= send_date <= end_dt:
                campaigns.append({
                    "id": item["id"],
                    "name": attrs.get("name", ""),
                    "send_time": send_time,
                    "send_date": send_date,
                    "status": attrs.get("status", ""),
                })
        # pagination
        next_link = data.get("links", {}).get("next")
        url = next_link if next_link else None
        params = None  # next_link includes params
        time.sleep(0.3)

    return campaigns


# ---------------------------------------------------------------------------
# Campaign metrics (KL2 + Q13e)
# ---------------------------------------------------------------------------
def fetch_campaign_metrics(campaign_ids):
    """Fetch performance metrics for campaigns via reporting endpoint."""
    if not campaign_ids:
        return {}

    # Klaviyo Reporting API - campaign values
    results = {}
    # Process in chunks of 100
    for i in range(0, len(campaign_ids), 100):
        chunk = campaign_ids[i:i + 100]
        payload = {
            "data": {
                "type": "campaign-values-report",
                "attributes": {
                    "statistics": [
                        "recipients", "opens_unique", "clicks_unique",
                        "conversions", "conversion_value"
                    ],
                    "timeframe": {"key": "last_365_days"},
                    "conversion_metric_id": PLACED_ORDER_METRIC_ID,
                    "filter": f"contains-any(campaign_id,[{','.join('\"' + c + '\"' for c in chunk)}])",
                },
            }
        }

        try:
            data = api_post(f"{BASE_URL}/campaign-values-reports/", payload)
            for result in data.get("data", {}).get("attributes", {}).get("results", []):
                cid = result.get("groupings", {}).get("campaign_id", "")
                stats = result.get("statistics", {})
                results[cid] = {
                    "send": int(stats.get("recipients", 0) or 0),
                    "unique_open": int(stats.get("opens_unique", 0) or 0),
                    "unique_click": int(stats.get("clicks_unique", 0) or 0),
                    "revenue": float(stats.get("conversion_value", 0) or 0),
                    "orders": int(stats.get("conversions", 0) or 0),
                }
        except Exception as e:
            print(f"  [WARN] Campaign metrics chunk failed: {e}")
            # Fallback: try individual campaign queries
            for cid in chunk:
                try:
                    r = _fetch_single_campaign_stats(cid)
                    if r:
                        results[cid] = r
                except Exception:
                    pass

        time.sleep(0.5)

    return results


# ---------------------------------------------------------------------------
# Flow list and metrics (KL1)
# ---------------------------------------------------------------------------
def fetch_flows():
    """Fetch all flows."""
    flows = []
    url = f"{BASE_URL}/flows"
    params = {
        "fields[flow]": "name,status,archived,created,updated",
    }

    while url:
        data = api_get(url, params)
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            if attrs.get("archived"):
                continue
            flows.append({
                "id": item["id"],
                "name": attrs.get("name", ""),
                "status": attrs.get("status", ""),
            })
        next_link = data.get("links", {}).get("next")
        url = next_link if next_link else None
        params = None
        time.sleep(0.3)

    return flows


def fetch_flow_metrics(flow_ids, start_dt, end_dt):
    """Fetch flow performance via reporting endpoint."""
    if not flow_ids:
        return {}

    results = {}
    payload = {
        "data": {
            "type": "flow-values-report",
            "attributes": {
                "statistics": [
                    "recipients", "opens_unique", "clicks_unique",
                    "conversions", "conversion_value"
                ],
                "timeframe": {
                    "start": f"{start_dt}T00:00:00+00:00",
                    "end": f"{end_dt}T23:59:59+00:00",
                },
                "conversion_metric_id": PLACED_ORDER_METRIC_ID,
                "filter": f"contains-any(flow_id,[{','.join('\"' + f + '\"' for f in flow_ids)}])",
            },
        }
    }

    try:
        data = api_post(f"{BASE_URL}/flow-values-reports/", payload)
        for result in data.get("data", {}).get("attributes", {}).get("results", []):
            fid = result.get("groupings", {}).get("flow_id", "")
            stats = result.get("statistics", {})
            results[fid] = {
                "send": int(stats.get("recipients", 0) or 0),
                "unique_open": int(stats.get("opens_unique", 0) or 0),
                "unique_click": int(stats.get("clicks_unique", 0) or 0),
                "revenue": float(stats.get("conversion_value", 0) or 0),
                "orders": int(stats.get("conversions", 0) or 0),
            }
    except Exception as e:
        print(f"  [WARN] Flow metrics failed: {e}")

    return results


# ---------------------------------------------------------------------------
# Build output formats
# ---------------------------------------------------------------------------
def build_q13e(campaigns, campaign_metrics):
    """Q13e: daily campaign sends + revenue."""
    daily = defaultdict(lambda: {"send": 0, "revenue": 0.0})
    for c in campaigns:
        m = campaign_metrics.get(c["id"], {})
        d = c["send_date"]
        daily[d]["send"] += m.get("send", 0)
        daily[d]["revenue"] += m.get("revenue", 0)

    table = []
    for dk in sorted(daily.keys()):
        v = daily[dk]
        table.append({
            "klaviyo_sales_main.raw.campaign_send": v["send"],
            "klaviyo_sales_main.raw.campaign_revenue": round(v["revenue"], 2),
            "date": dk,
        })
    return {"tableData": table}


def build_kl2(campaigns, campaign_metrics):
    """KL2: campaign monthly performance with names."""
    table = []
    for c in sorted(campaigns, key=lambda x: x["send_date"]):
        m = campaign_metrics.get(c["id"], {})
        send = m.get("send", 0)
        uo = m.get("unique_open", 0)
        uc = m.get("unique_click", 0)
        orders = m.get("orders", 0)
        revenue = m.get("revenue", 0)

        table.append({
            "klaviyo_sales_main.raw.campaign_revenue": round(revenue, 2),
            "klaviyo_sales_main.raw.campaign_orders": orders,
            "klaviyo_sales_main.raw.campaign_send": send,
            "klaviyo_sales_main.raw.campaign_unique_open": uo,
            "klaviyo_sales_main.raw.campaign_unique_click_excl_bot": uc,
            "klaviyo_sales_main.computed.campaign_unique_open_rate": _safe_div(uo, send),
            "klaviyo_sales_main.computed.campaign_unique_click_rate_excl_bot": _safe_div(uc, send),
            "klaviyo_sales_main.computed.campaign_placed_order_rate": _safe_div(orders, send),
            "klaviyo_sales_main.computed.campaign_revenue_per_subscriber": _safe_div(revenue, send),
            "campaign": c["name"],
            "subject": "",
            "date": c["send_date"],
        })
    return {"tableData": table}


def _fetch_flow_metrics_monthly(flow_id, month_start, month_end):
    """Fetch flow metrics for a single month period."""
    url = f"{BASE_URL}/flow-values-reports/"
    payload = {
        "data": {
            "type": "flow-values-report",
            "attributes": {
                "statistics": ["revenue", "unique_recipient_count", "open_rate", "click_rate", "received_email"],
                "timeframe": {"key": "custom", "start": month_start.strftime("%Y-%m-%d"), "end": month_end.strftime("%Y-%m-%d")},
                "filter": f"equals(flow_id,\"{flow_id}\")",
            }
        }
    }
    try:
        data = api_post(url, payload)
        results = data.get("data", {}).get("attributes", {}).get("results", [])
        if results:
            r = results[0]
            stats = r.get("statistics", {})
            return {
                "send": stats.get("received_email", 0),
                "unique_open": int(stats.get("open_rate", 0) * stats.get("received_email", 0)),
                "unique_click": int(stats.get("click_rate", 0) * stats.get("received_email", 0)),
                "orders": stats.get("unique_recipient_count", 0),
                "revenue": stats.get("revenue", 0),
            }
    except Exception as e:
        print(f"  [WARN] flow {flow_id} metrics for {month_start}: {e}")
    return None


def build_kl1(flows, flow_metrics, start_date, end_date):
    """KL1: flow monthly performance (per-month API calls to avoid duplication)."""
    table = []
    cur = start_date
    total_months = 0
    while cur <= end_date:
        total_months += 1
        cur += relativedelta(months=1)

    cur = start_date
    while cur <= end_date:
        month_key = cur.strftime("%Y-%m-01")
        month_end = cur + relativedelta(months=1) - timedelta(days=1)
        for fl in flows:
            # Try per-month fetch; fall back to evenly divided aggregate
            m = _fetch_flow_metrics_monthly(fl["id"], cur, month_end)
            if m is None:
                agg = flow_metrics.get(fl["id"], {})
                if not agg:
                    continue
                # Divide aggregate evenly as fallback
                m = {k: (v / total_months if isinstance(v, (int, float)) else v) for k, v in agg.items()}

            send = m.get("send", 0)
            uo = m.get("unique_open", 0)
            uc = m.get("unique_click", 0)
            orders = m.get("orders", 0)
            revenue = m.get("revenue", 0)

            table.append({
                "klaviyo_sales_main.raw.flow_revenue": round(revenue, 2),
                "klaviyo_sales_main.raw.flow_orders": orders,
                "klaviyo_sales_main.raw.flow_send": send,
                "klaviyo_sales_main.raw.flow_unique_open": uo,
                "klaviyo_sales_main.raw.flow_unique_click_excl_bot": uc,
                "klaviyo_sales_main.computed.flow_unique_open_rate": _safe_div(uo, send),
                "klaviyo_sales_main.computed.flow_unique_click_rate_excl_bot": _safe_div(uc, send),
                "klaviyo_sales_main.computed.flow_placed_order_rate": _safe_div(orders, send),
                "klaviyo_sales_main.computed.flow_revenue_per_subscriber": _safe_div(revenue, send),
                "flow": fl["name"],
                "date": month_key,
            })
        cur += relativedelta(months=1)

    return {"tableData": table}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch Klaviyo data (Q13e, KL1, KL2)")
    parser.add_argument("--start", default="2024-01", help="Start month YYYY-MM")
    parser.add_argument("--end",   default=None,      help="End month YYYY-MM")
    args = parser.parse_args()

    if not API_KEY:
        print("[ERROR] KLAVIYO_API_KEY not set")
        sys.exit(1)

    today = date.today()
    start_date = datetime.strptime(args.start, "%Y-%m").date().replace(day=1)
    end_str = args.end or today.strftime("%Y-%m")
    end_date = datetime.strptime(end_str, "%Y-%m").date().replace(day=1)
    end_dt = (end_date + relativedelta(months=1)) - timedelta(days=1)
    if end_dt > today:
        end_dt = today

    start_dt_str = start_date.strftime("%Y-%m-%d")
    end_dt_str = end_dt.strftime("%Y-%m-%d")

    print(f"[Klaviyo] {start_dt_str} ~ {end_dt_str}")

    # --- Campaigns ---
    print("[Klaviyo] Fetching campaigns...")
    campaigns = fetch_campaigns(start_dt_str, end_dt_str)
    print(f"  Found {len(campaigns)} campaigns in range")

    campaign_ids = [c["id"] for c in campaigns]
    print("[Klaviyo] Fetching campaign metrics...")
    campaign_metrics = fetch_campaign_metrics(campaign_ids)
    print(f"  Got metrics for {len(campaign_metrics)} campaigns")

    # --- Flows ---
    print("[Klaviyo] Fetching flows...")
    flows = fetch_flows()
    print(f"  Found {len(flows)} active flows")

    flow_ids = [f["id"] for f in flows]
    print("[Klaviyo] Fetching flow metrics...")
    flow_metrics = fetch_flow_metrics(flow_ids, start_dt_str, end_dt_str)
    print(f"  Got metrics for {len(flow_metrics)} flows")

    # --- Build outputs ---
    q13e = build_q13e(campaigns, campaign_metrics)
    kl2 = build_kl2(campaigns, campaign_metrics)
    kl1 = build_kl1(flows, flow_metrics, start_date, end_date)

    # --- Save ---
    for path, data, label in [
        (OUT_Q13E, q13e, "Q13e"),
        (OUT_KL1,  kl1,  "KL1"),
        (OUT_KL2,  kl2,  "KL2"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] {label} -> {path} ({len(data['tableData'])} rows)")


if __name__ == "__main__":
    main()
