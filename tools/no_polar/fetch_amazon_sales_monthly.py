"""
fetch_amazon_sales_monthly.py - Amazon SP-API order data collector (Q3 replacement)

Uses Amazon SP-API Reports API to get order data, then aggregates by brand/month.
Source: Adapted from Orbiters11-dev/dashboard/amz_datacolletor_new.py (SP-API portion)

Outputs:
  .tmp/polar_data/q3_amazon_brand.json   — brand-level monthly (replaces Polar Q3)

Q3 format:
  {"tableData": [{
    "amazonsp_order_items.computed.total_sales_amazon": X,
    "amazonsp_order_items.computed.avg_order_value_amazon": X,
    "amazonsp_order_items.raw.gross_sales_amazon": X,
    "amazonsp_order_items.raw.promotion_discounts_amazon": X,
    "amazonsp_order_items.computed.net_sales_amazon": X,
    "amazonsp_order_items.raw.total_orders_amazon": X,
    "amazonsp_order_items.raw.total_fees_amazon": X,
    "amazonsp_order_items.raw.cost_of_products_amazon": 0,
    "custom_5036": "Brand",
    "date": "YYYY-MM-01"
  }]}

Usage:
    python tools/no_polar/fetch_amazon_sales_monthly.py --start 2024-01 --end 2026-02
"""

import os
import sys
import json
import gzip
import time
import csv
import io
import argparse
import traceback
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
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
OUTPUT_Q3 = ROOT / ".tmp" / "polar_data" / "q3_amazon_brand.json"

SP_ENDPOINT   = "https://sellingpartnerapi-na.amazon.com"
MARKETPLACE   = os.getenv("AMZ_SP_MARKETPLACE_ID", "ATVPDKIKX0DER")
SP_CLIENT_ID  = os.getenv("AMZ_SP_CLIENT_ID")
SP_CLIENT_SEC = os.getenv("AMZ_SP_CLIENT_SECRET")
SP_REFRESH    = os.getenv("AMZ_SP_REFRESH_TOKEN")

# SKU → Brand mapping from Product_Variant_Reference.xlsx
BRAND_MAP_PATH = ROOT / "Data Storage" / "polar" / "Product_Variant_Reference.xlsx"

# Polar brand rules (same as polar_financial_model.py)
BRANDS = ["Grosmimi", "Onzenna", "i-Kim", "RSL"]

PROD_RULES = [
    ("RSL",      ["rsl"]),
    ("i-Kim",    ["ikim", "i-kim", "ik-", "kim-"]),
    ("Onzenna",  ["onzenna", "onz", "oza", "ozn"]),
    ("Grosmimi", ["grosmimi", "grsmm", "ppsu", "silicone", "pebax", "straw", "spout"]),
]


# ---------------------------------------------------------------------------
# SP-API Auth
# ---------------------------------------------------------------------------

class SpTokenManager:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        resp = requests.post(
            "https://api.amazon.com/auth/o2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def headers(self) -> Dict:
        return {
            "x-amz-access-token": self.get_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


# ---------------------------------------------------------------------------
# SP-API Reports: flat-file all orders
# ---------------------------------------------------------------------------

REPORT_TYPE = "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL"


def request_report(tm: SpTokenManager, start: date, end: date) -> str:
    """Submit report request, return reportId."""
    url = f"{SP_ENDPOINT}/reports/2021-06-30/reports"
    body = {
        "reportType": REPORT_TYPE,
        "dataStartTime": start.strftime("%Y-%m-%dT00:00:00Z"),
        "dataEndTime":   end.strftime("%Y-%m-%dT23:59:59Z"),
        "marketplaceIds": [MARKETPLACE],
    }
    resp = requests.post(url, headers=tm.headers(), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["reportId"]


def wait_for_report(tm: SpTokenManager, report_id: str, max_wait: int = 600) -> str:
    """Poll until report is DONE. Returns reportDocumentId."""
    url = f"{SP_ENDPOINT}/reports/2021-06-30/reports/{report_id}"
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(20)
        resp = requests.get(url, headers=tm.headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("processingStatus")
        print(f"    report {report_id}: {status}")
        if status == "DONE":
            return data["reportDocumentId"]
        if status in ("FATAL", "CANCELLED"):
            raise RuntimeError(f"Report {report_id} failed: {status} — {data}")
    raise TimeoutError(f"Report {report_id} did not complete in {max_wait}s")


def download_report(tm: SpTokenManager, doc_id: str) -> str:
    """Download report document, return content as string."""
    url = f"{SP_ENDPOINT}/reports/2021-06-30/documents/{doc_id}"
    resp = requests.get(url, headers=tm.headers(), timeout=30)
    resp.raise_for_status()
    doc = resp.json()
    dl = requests.get(doc["url"], timeout=300)
    dl.raise_for_status()

    comp = doc.get("compressionAlgorithm", "")
    raw = dl.content
    if comp == "GZIP" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Brand inference
# ---------------------------------------------------------------------------

def _build_sku_brand_map() -> Dict[str, str]:
    """Load Product_Variant_Reference.xlsx SKU→Brand mapping."""
    if not BRAND_MAP_PATH.exists():
        return {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(BRAND_MAP_PATH, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {}
        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        sku_col = next((i for i, h in enumerate(headers) if "sku" in h), None)
        brand_col = next((i for i, h in enumerate(headers) if "brand" in h), None)
        if sku_col is None or brand_col is None:
            return {}
        out = {}
        for row in rows[1:]:
            sku = str(row[sku_col] or "").strip()
            brand = str(row[brand_col] or "").strip()
            if sku and brand:
                out[sku.lower()] = brand
        return out
    except Exception as e:
        print(f"[WARN] SKU map load failed: {e}")
        return {}


def infer_brand(sku: str, title: str, sku_map: Dict[str, str]) -> str:
    sku_l = sku.strip().lower()
    if sku_l in sku_map:
        return sku_map[sku_l]
    combined = f"{sku} {title}".lower()
    for brand, keywords in PROD_RULES:
        if any(kw in combined for kw in keywords):
            return brand
    return "Grosmimi"  # default


# ---------------------------------------------------------------------------
# Parse flat-file TSV report
# ---------------------------------------------------------------------------

FEE_TYPES_NEGATIVE = {
    "FBAPerUnitFulfillmentFee", "VariableClosingFee", "Commission",
    "FBATransactionFee", "FulfillmentFee", "ReferralFee",
}


def parse_orders_report(content: str, sku_map: Dict[str, str]) -> List[Dict]:
    """
    Parse GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL TSV.
    Returns list of per-order-item dicts with brand, date, gross_sales, discounts.
    """
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    rows = []
    for r in reader:
        # Skip non-Shipped or cancelled
        status = r.get("order-status", "").strip()
        if status not in ("Shipped", "Pending", "Unshipped", "PartiallyShipped"):
            continue

        order_id = r.get("amazon-order-id", "").strip()
        sku      = r.get("sku", "").strip()
        title    = r.get("product-name", "").strip()
        qty      = int(float(r.get("quantity", 0) or 0))
        if qty <= 0:
            continue

        # Date: purchase-date or last-updated-date
        dt_str = r.get("purchase-date", r.get("last-updated-date", ""))[:10]
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        price_each = float(r.get("item-price", 0) or 0)
        promo      = float(r.get("item-promotion-discount", 0) or 0)
        gross      = price_each  # already total for the line (qty * unit price in some reports)

        brand = infer_brand(sku, title, sku_map)

        rows.append({
            "order_id": order_id,
            "date": dt,
            "brand": brand,
            "gross_sales": gross,
            "promotion_discounts": -abs(promo),  # negative
        })
    return rows


# ---------------------------------------------------------------------------
# Fetch orders report for a date range, with chunking
# ---------------------------------------------------------------------------

MAX_REPORT_DAYS = 30  # SP-API report max window


def _date_windows(start: date, end: date, max_days: int = MAX_REPORT_DAYS):
    cur = start
    while cur <= end:
        win_end = min(end, cur + timedelta(days=max_days - 1))
        yield cur, win_end
        cur = win_end + timedelta(days=1)


def fetch_orders_for_range(tm: SpTokenManager, start: date, end: date, sku_map: Dict[str, str]) -> List[Dict]:
    all_rows = []
    for s, e in _date_windows(start, end):
        print(f"  [Amazon SP] requesting report {s} ~ {e}")
        try:
            rid = request_report(tm, s, e)
            doc_id = wait_for_report(tm, rid)
            content = download_report(tm, doc_id)
            rows = parse_orders_report(content, sku_map)
            print(f"    -> {len(rows)} order items")
            all_rows.extend(rows)
        except Exception as e2:
            print(f"  [WARN] report {s}~{e} failed: {e2}")
            traceback.print_exc()
        time.sleep(2)
    return all_rows


# ---------------------------------------------------------------------------
# Monthly aggregation → Q3 format
# ---------------------------------------------------------------------------

def aggregate_q3(rows: List[Dict]) -> List[Dict]:
    """Aggregate order items by (brand, YYYY-MM-01) → Q3 tableData."""
    bucket: Dict[Tuple, Dict] = defaultdict(lambda: {
        "gross_sales": 0.0,
        "promotion_discounts": 0.0,
        "order_ids": set(),
    })

    for r in rows:
        dt = r["date"]
        month_key = date(dt.year, dt.month, 1).strftime("%Y-%m-%d")
        key = (r["brand"], month_key)
        bucket[key]["gross_sales"]          += r["gross_sales"]
        bucket[key]["promotion_discounts"]  += r["promotion_discounts"]
        bucket[key]["order_ids"].add(r["order_id"])

    out = []
    for (brand, month_key), v in sorted(bucket.items()):
        gross = v["gross_sales"]
        discounts = v["promotion_discounts"]
        net = gross + discounts  # discounts are negative
        total_orders = len(v["order_ids"])
        avg_aov = (net / total_orders) if total_orders else 0.0

        out.append({
            "amazonsp_order_items.computed.total_sales_amazon":   round(net, 6),
            "amazonsp_order_items.computed.avg_order_value_amazon": round(avg_aov, 6),
            "amazonsp_order_items.raw.gross_sales_amazon":        round(gross, 6),
            "amazonsp_order_items.raw.promotion_discounts_amazon": round(discounts, 6),
            "amazonsp_order_items.computed.net_sales_amazon":     round(net, 6),
            "amazonsp_order_items.raw.total_orders_amazon":       total_orders,
            "amazonsp_order_items.raw.total_fees_amazon":         0,   # TODO: Finances API
            "amazonsp_order_items.raw.cost_of_products_amazon":   0,   # TODO: COGS sheet
            "custom_5036": brand,
            "date": month_key,
        })
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch Amazon SP-API order data (Q3)")
    parser.add_argument("--start", default="2024-01", help="Start month YYYY-MM")
    parser.add_argument("--end",   default=None,      help="End month YYYY-MM (default: current month)")
    args = parser.parse_args()

    today = date.today()
    start_date = datetime.strptime(args.start, "%Y-%m").date().replace(day=1)
    end_str    = args.end or today.strftime("%Y-%m")
    end_first  = datetime.strptime(end_str, "%Y-%m").date().replace(day=1)
    end_date   = (end_first + relativedelta(months=1)) - timedelta(days=1)
    if end_date > today:
        end_date = today

    if not all([SP_CLIENT_ID, SP_CLIENT_SEC, SP_REFRESH]):
        print("[ERROR] AMZ_SP_CLIENT_ID / AMZ_SP_CLIENT_SECRET / AMZ_SP_REFRESH_TOKEN not set in .env")
        sys.exit(1)

    print(f"[Amazon SP] {start_date} ~ {end_date} | marketplace: {MARKETPLACE}")

    tm = SpTokenManager(SP_CLIENT_ID, SP_CLIENT_SEC, SP_REFRESH)

    # Load SKU→Brand mapping
    sku_map = _build_sku_brand_map()
    print(f"[Amazon SP] SKU map: {len(sku_map)} entries")

    # Fetch
    rows = fetch_orders_for_range(tm, start_date, end_date, sku_map)
    print(f"[Amazon SP] Total order items: {len(rows)}")

    # Aggregate Q3
    q3_rows = aggregate_q3(rows)
    print(f"[Amazon SP] Q3 monthly rows: {len(q3_rows)}")
    total_gross = sum(r["amazonsp_order_items.raw.gross_sales_amazon"] for r in q3_rows)
    print(f"[Amazon SP] Total gross sales: ${total_gross:,.0f}")

    OUTPUT_Q3.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_Q3, "w", encoding="utf-8") as f:
        json.dump({"tableData": q3_rows, "totalData": {}}, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] Q3 -> {OUTPUT_Q3}")


if __name__ == "__main__":
    main()
