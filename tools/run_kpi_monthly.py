"""
run_kpi_monthly.py - Monthly KPI analysis -> Excel (kpis_model)

Sections:
  1) Discount rate by brand x channel (Shopify) — flat table with list price
  2) Ad spend by platform (Amazon Ads, Meta, Google)
  3) Influencer seeding cost (PayPal + COGS + shipping)

Data sources:
  - PG Data Keeper: shopify_orders_daily, amazon_ads_daily, meta_ads_daily, google_ads_daily
  - Polar JSON (local): q10_influencer_orders.json, q11_paypal_transactions.json
  - COGS by SKU.xlsx

Output:
  - Loads latest kpis_model_*.xlsx from Data Storage/kpi_reports/
  - Adds/replaces 3 tabs: KPI_할인율 / KPI_광고비 / KPI_시딩비용
  - Saves as next version (v+1)

Usage:
    python tools/run_kpi_monthly.py
    python tools/run_kpi_monthly.py --no-sheet   # console only
    python tools/run_kpi_monthly.py --from 2024-01 --to 2026-02
"""

import os
import sys
import json
from collections import defaultdict
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

ROOT = TOOLS_DIR.parent
POLAR = ROOT.parent / "Shared" / "동균 테스트_2026-03-06" / "polar_data"
COGS_PATH = ROOT.parent / "Shared" / "NoPolar KPIs" / "Data config sheet" / "COGS by SKU.xlsx"
# ORBI KPIs output (WJ Test1 Data Storage)
OUTPUT_DIR = ROOT / "Data Storage" / "kpi_reports"


# ── Data Keeper ───────────────────────────────────────────────────────────────

def load_dk(table, days=800):
    sys.path.insert(0, str(TOOLS_DIR))
    from data_keeper_client import DataKeeper
    dk = DataKeeper(prefer_cache=False)
    return dk.get(table, days=days)


def compute_through_date():
    """Consistent through-date = min of latest full day across all main channels (PST)."""
    from datetime import datetime, timedelta, timezone
    PST = timezone(timedelta(hours=-8))
    yesterday_pst = (datetime.now(PST).date() - timedelta(days=1)).isoformat()

    main_tables = ["shopify_orders_daily", "amazon_ads_daily", "meta_ads_daily", "google_ads_daily"]
    latest = []
    for t in main_tables:
        rows = load_dk(t, days=30)
        dates = [r.get("date", "") for r in rows if r.get("date")]
        if dates:
            latest.append(max(dates))

    # min across channels = date ALL channels have data for; cap at yesterday PST
    through = min(latest) if latest else yesterday_pst
    return min(through, yesterday_pst)


# ── COGS ─────────────────────────────────────────────────────────────────────

def load_cogs_map():
    try:
        import openpyxl
        wb = openpyxl.load_workbook(COGS_PATH, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        sku_col = next((i for i, h in enumerate(headers) if "sku" in h), None)
        cost_col = next((i for i, h in enumerate(headers) if "cost" in h and "type" not in h), None)
        if sku_col is None or cost_col is None:
            return {}
        out = {}
        for row in rows[1:]:
            sku = str(row[sku_col] or "").strip().lower()
            try:
                cost = float(row[cost_col] or 0)
            except (TypeError, ValueError):
                continue
            if sku and cost > 0:
                out[sku] = cost
        wb.close()
        return out
    except Exception as e:
        print(f"  [WARN] COGS load failed: {e}")
        return {}


# ── 1. DISCOUNT RATE (Golmani wide format, brand x channel, PR excluded) ──────

CHANNEL_ORDER = ["ONZ", "Amazon", "B2B", "TikTok", "Unknown"]  # PR excluded; D2C in PG = ONZ
D2C_RAW_CHANNELS = {"D2C", "Amazon", "TikTok"}  # user's "D2C" = ONZ+Amazon+TikTok
BRAND_ORDER   = ["Grosmimi", "Naeiae", "CHA&MOM", "Onzenna", "Alpremio", "Unknown"]

# Avg COGS per unit by brand (from COGS by SKU.xlsx x Product Variant)
AVG_COGS = {
    "Grosmimi": 8.41, "Naeiae": 5.35, "CHA&MOM": 7.53,
    "Onzenna": 5.35,  "Alpremio": 12.57, "Unknown": 8.00,
}

# Avg selling price per unit by brand (used to estimate units when DB has units=0 from backfill)
AVG_PRICE = {
    "Grosmimi": 28.0, "Naeiae": 18.0, "CHA&MOM": 32.0,
    "Onzenna": 22.0,  "Alpremio": 38.0, "Unknown": 25.0,
}

def load_brand_avg_cogs():
    """Recompute avg COGS per brand from files (fallback: AVG_COGS constant)."""
    try:
        import openpyxl
        sku_brand = {}
        wb = openpyxl.load_workbook(str(COGS_PATH.parent / "Product Variant by SKU.xlsx"),
                                     read_only=True, data_only=True)
        for r in list(wb.active.iter_rows(values_only=True))[1:]:
            sku, brand = str(r[0] or "").strip().lower(), str(r[3] or "").strip()
            if sku and brand:
                sku_brand[sku] = brand
        wb.close()

        wb2 = openpyxl.load_workbook(str(COGS_PATH), read_only=True, data_only=True)
        brand_costs = defaultdict(list)
        for r in list(wb2.active.iter_rows(values_only=True))[1:]:
            sku = str(r[2] or "").strip().lower()
            cost = float(r[4] or 0)
            brand = sku_brand.get(sku)
            if brand and cost > 0:
                brand_costs[brand].append(cost)
        wb2.close()
        return {b: sum(v)/len(v) for b, v in brand_costs.items() if v}
    except Exception as e:
        print(f"  [WARN] COGS map load failed: {e}, using constants")
        return AVG_COGS


def analyze_discounts(date_from, date_to, through_date=None):
    """Wide format (Golmani-style):
       Rows: Section header + TOTAL + Brand subtotal + Channel detail
       Cols: [Label, Brand, Channel] + [Jan 2024, Feb 2024, ..., YTD]
       Sections: Gross Sales / Net Sales / Discounts / Discount % /
                 Units / Avg List Price / COGS (est.) / GM / GM%
       PR channel excluded (goes to seeding cost section).
       through_date: only include daily data up to this date (consistent ceiling).
    """
    import openpyxl
    brand_cogs = load_brand_avg_cogs()

    # ── collect PG data ──────────────────────────────────────────────────────
    rows = load_dk("shopify_orders_daily")
    latest_date = "0000-00-00"
    agg = defaultdict(lambda: {"gross":0.0,"disc":0.0,"net":0.0,"orders":0,"units":0})

    for r in rows:
        raw_date = r.get("date") or ""
        if through_date and raw_date > through_date:
            continue  # skip data beyond consistent through_date
        if raw_date > latest_date:
            latest_date = raw_date
        date = raw_date[:7]
        channel = r.get("channel") or "Unknown"
        if channel == "PR":          # PR → seeding, exclude here
            continue
        if not date or date < date_from or date > date_to:
            continue
        brand = r.get("brand") or "Unknown"
        key = (date, brand, channel)
        agg[key]["gross"]  += float(r.get("gross_sales") or 0)
        agg[key]["disc"]   += float(r.get("discounts")   or 0)
        agg[key]["net"]    += float(r.get("net_sales")    or 0)
        agg[key]["orders"] += int(r.get("orders") or 0)
        agg[key]["units"]  += int(r.get("units")  or 0)

    # ── month list ───────────────────────────────────────────────────────────
    months = sorted(set(k[0] for k in agg))
    # Use passed-in through_date (consistent across sections), or compute fallback
    from datetime import datetime as _dtt, timedelta as _td, timezone as _tz
    PST = _tz(_td(hours=-8))
    today_pst = _dtt.now(PST).date()
    if not through_date:
        yesterday_pst = (today_pst - _td(days=1)).isoformat()
        through_date  = min(latest_date, yesterday_pst) if latest_date > "0000-00-00" else yesterday_pst
    partial_note = f"(through {through_date})"

    # Month labels: current month gets partial note
    def month_label(m):
        import calendar
        y, mo = int(m[:4]), int(m[5:7])
        if y == today_pst.year and mo == today_pst.month:
            return f"{calendar.month_abbr[mo]} {y}\n{partial_note}"
        return f"{calendar.month_abbr[mo]} {y}"

    col_labels = [month_label(m) for m in months] + ["YTD"]

    # ── helper: get metric dict for a set of keys ────────────────────────────
    def get_vals(keys):
        v = {"gross":0.0,"disc":0.0,"net":0.0,"units":0}
        for k in keys:
            if k in agg:
                for f in v:
                    v[f] += agg[k][f]
        return v

    def ytd_keys(base_keys):
        return [k for k in base_keys if k[0] >= f"{months[-1][:4]}-01"]

    # ── build metric rows per entity ─────────────────────────────────────────
    brands_present = sorted(
        set(k[1] for k in agg if agg[k]["gross"] > 50),
        key=lambda b: BRAND_ORDER.index(b) if b in BRAND_ORDER else 99
    )

    def entity_rows():
        """Yield (label, brand, channel, {month: vals}, ytd_vals) tuples."""
        # TOTAL
        all_keys = list(agg.keys())
        monthly = {}
        for m in months:
            monthly[m] = get_vals([k for k in all_keys if k[0] == m])
        ytd = get_vals([k for k in all_keys if k[0] >= f"{months[-1][:4]}-01"])
        yield ("TOTAL", "", "", monthly, ytd)

        for brand in brands_present:
            brand_keys = [k for k in agg if k[1] == brand]
            monthly_b = {}
            for m in months:
                monthly_b[m] = get_vals([k for k in brand_keys if k[0] == m])
            ytd_b = get_vals([k for k in brand_keys if k[0] >= f"{months[-1][:4]}-01"])
            yield (brand, brand, "", monthly_b, ytd_b)

            def ch_display(c):
                return "ONZ" if c == "D2C" else c

            channels = sorted(
                set(k[2] for k in brand_keys if agg[k]["gross"] > 10),
                key=lambda c: CHANNEL_ORDER.index(ch_display(c)) if ch_display(c) in CHANNEL_ORDER else 99
            )
            for ch in channels:
                ch_keys = [k for k in brand_keys if k[2] == ch]
                monthly_c = {}
                for m in months:
                    monthly_c[m] = get_vals([k for k in ch_keys if k[0] == m])
                ytd_c = get_vals([k for k in ch_keys if k[0] >= f"{months[-1][:4]}-01"])
                yield (f"  {ch_display(ch)}", brand, ch, monthly_c, ytd_c)

    entities = list(entity_rows())

    # ── console summary ──────────────────────────────────────────────────────
    print("=" * 80)
    print(f"1) DISCOUNT RATE BY BRAND x CHANNEL  (data through {latest_date}, PR excluded)")
    print("=" * 80)
    for label, brand, ch, monthly, ytd in entities:
        if ch == "" and brand != "":  # brand subtotals only
            g, d = ytd["gross"], ytd["disc"]
            print(f"  {brand:<12} gross=${g:>10,.0f}  disc=${d:>8,.0f}  rate={d/g*100:.1f}%" if g else "")

    # ── build wide sheet ─────────────────────────────────────────────────────
    METRIC_SECTIONS = [
        ("GROSS SALES ($)",        "gross",  lambda v: round(v["gross"],2)),
        ("NET SALES ($)",          "net",    lambda v: round(v["net"],2)),
        ("DISCOUNTS ($)",          "disc",   lambda v: round(v["disc"],2)),
        ("DISCOUNT RATE",          "rate",   lambda v: round(v["disc"]/v["gross"],4) if v["gross"] else 0),
        ("UNITS",                  "units",  lambda v: v["units"]),
        ("AVG LIST PRICE ($/unit)","price",  lambda v: round(v["gross"]/v["units"],2) if v["units"] else 0),
        ("COGS est. ($)",          "cogs",   None),   # special: units × avg_cogs[brand]
        ("GM ($)",                 "gm",     None),   # net - cogs
        ("GM %",                   "gm_pct", None),   # gm / net
    ]

    out = []  # list of rows

    # Title
    out.append([f"DISCOUNT ANALYSIS — BRAND x CHANNEL  |  {partial_note}  |  PR excluded (see Seeding tab)"])
    out.append([])

    # Header row
    hdr = ["Metric", "Brand", "Channel"] + col_labels
    out.append(hdr)

    # ── build total_monthly and d2c_monthly for Executive Summary / Summary tab ─
    brand_month = defaultdict(lambda: {"gross":0.0,"net":0.0,"disc":0.0,"units":0})
    for (date, brand, ch), v in agg.items():
        k = (date, brand)
        for f in ("gross","net","disc","units"):
            brand_month[k][f] += v[f]

    total_monthly = {}
    d2c_monthly   = {}
    for m in months:
        tm = {"gross":0.0,"net":0.0,"disc":0.0,"units":0,"cogs":0.0}
        dm = {"gross":0.0,"net":0.0,"disc":0.0,"units":0,"cogs":0.0}
        for brand in brands_present:
            bp = AVG_PRICE.get(brand, AVG_PRICE["Unknown"])
            bc = brand_cogs.get(brand, AVG_COGS.get(brand, 8.0))
            # total (all channels)
            bv = brand_month.get((m, brand), {})
            u = bv.get("units",0) or (bv.get("gross",0) / bp if bv.get("gross",0) else 0)
            tm["gross"] += bv.get("gross",0);  tm["net"] += bv.get("net",0)
            tm["disc"]  += bv.get("disc",0);   tm["units"] += bv.get("units",0)
            tm["cogs"]  += u * bc
            # D2C = ONZ(raw:D2C) + Amazon + TikTok
            for ch in D2C_RAW_CHANNELS:
                dv = agg.get((m, brand, ch), {})
                if not dv:
                    continue
                du = dv.get("units",0) or (dv.get("gross",0) / bp if dv.get("gross",0) else 0)
                dm["gross"] += dv.get("gross",0);  dm["net"] += dv.get("net",0)
                dm["disc"]  += dv.get("disc",0);   dm["units"] += dv.get("units",0)
                dm["cogs"]  += du * bc
        total_monthly[m] = tm
        d2c_monthly[m]   = dm

    for section_name, _, getter in METRIC_SECTIONS:
        # Section title row
        out.append([section_name])

        for label, brand, ch, monthly, ytd in entities:
            avg_cogs_brand  = brand_cogs.get(brand, AVG_COGS.get(brand, 8.0))
            avg_price_brand = AVG_PRICE.get(brand, AVG_PRICE["Unknown"])

            def est_units(v):
                """Units from DB; if 0 (backfill data), estimate from gross_sales / avg_price."""
                if v["units"] > 0:
                    return v["units"]
                if v["gross"] > 0 and avg_price_brand > 0:
                    return v["gross"] / avg_price_brand
                return 0

            row = [label, brand if ch else "", ch]
            ytd_val = None

            for m in months:
                v = monthly[m]
                if getter is None:
                    u = est_units(v)
                    if section_name == "COGS est. ($)":
                        val = round(u * avg_cogs_brand, 2)
                    elif section_name == "GM ($)":
                        val = round(v["net"] - u * avg_cogs_brand, 2)
                    else:  # GM %
                        cogs = u * avg_cogs_brand
                        gm   = v["net"] - cogs
                        val  = round(gm / v["net"], 4) if v["net"] else 0
                else:
                    val = getter(v)
                row.append(val)

            # YTD
            vy = ytd
            if getter is None:
                u = est_units(vy)
                if section_name == "COGS est. ($)":
                    ytd_val = round(u * avg_cogs_brand, 2)
                elif section_name == "GM ($)":
                    ytd_val = round(vy["net"] - u * avg_cogs_brand, 2)
                else:
                    cogs = u * avg_cogs_brand
                    gm   = vy["net"] - cogs
                    ytd_val = round(gm / vy["net"], 4) if vy["net"] else 0
            else:
                ytd_val = getter(vy)
            row.append(ytd_val)

            out.append(row)

    print(f"  Rows in tab: {len(out)}")
    return out, total_monthly, d2c_monthly


# ── 2. AD SPEND ───────────────────────────────────────────────────────────────

def analyze_ad_spend(date_from, date_to, through_date=None):
    """Wide format (months as columns), Amazon Ads split by brand."""
    import calendar as _cal
    from datetime import datetime as _dtt2, timedelta as _td2, timezone as _tz2

    # Amazon Ads: per brand per month
    amz_brand = defaultdict(lambda: defaultdict(float))
    for r in load_dk("amazon_ads_daily"):
        d = r.get("date") or ""
        if through_date and d > through_date:
            continue
        date = d[:7]
        if date_from <= date <= date_to:
            brand = r.get("brand") or "Unknown"
            amz_brand[brand][date] += float(r.get("spend") or 0)

    meta_monthly = defaultdict(float)
    for r in load_dk("meta_ads_daily"):
        d = r.get("date") or ""
        if through_date and d > through_date:
            continue
        date = d[:7]
        if date_from <= date <= date_to:
            meta_monthly[date] += float(r.get("spend") or 0)

    google_monthly = defaultdict(float)
    for r in load_dk("google_ads_daily"):
        d = r.get("date") or ""
        if through_date and d > through_date:
            continue
        date = d[:7]
        if date_from <= date <= date_to:
            google_monthly[date] += float(r.get("spend") or 0)

    # All months across all platforms
    all_months_set = set(meta_monthly) | set(google_monthly)
    for bd in amz_brand.values():
        all_months_set |= set(bd)
    all_months = sorted(m for m in all_months_set if date_from <= m <= date_to)

    _today_pst = _dtt2.now(_tz2(_td2(hours=-8))).date()
    _partial_note = f"(through {through_date})" if through_date else ""
    def _mlabel(m):
        y, mo = int(m[:4]), int(m[5:7])
        if y == _today_pst.year and mo == _today_pst.month and _partial_note:
            return f"{_cal.month_abbr[mo]} {y}\n{_partial_note}"
        return f"{_cal.month_abbr[mo]} {y}"

    ytd_year = all_months[-1][:4] if all_months else "2026"

    def _ytd(monthly_dict, brand_dict=None):
        if brand_dict is not None:
            return sum(v for m, v in brand_dict.items() if m >= f"{ytd_year}-01")
        return sum(v for m, v in monthly_dict.items() if m >= f"{ytd_year}-01")

    # ── Console ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("2) AD SPEND BY PLATFORM (Monthly)")
    print("=" * 80)
    print(f"\n{'Month':<10}  {'Amazon Ads':>12}  {'Meta Ads':>12}  {'Google Ads':>12}  {'TOTAL':>12}")
    print("-" * 65)
    grand_by_month = defaultdict(float)
    for month in all_months:
        amz = sum(bd.get(month, 0) for bd in amz_brand.values())
        meta = meta_monthly.get(month, 0)
        goog = google_monthly.get(month, 0)
        total = amz + meta + goog
        grand_by_month[month] = total
        print(f"{month:<10}  ${amz:>10,.0f}  ${meta:>10,.0f}  ${goog:>10,.0f}  ${total:>10,.0f}")
    print("-" * 65)
    gt_amz  = sum(sum(bd.values()) for bd in amz_brand.values())
    gt_meta = sum(meta_monthly.values())
    gt_goog = sum(google_monthly.values())
    print(f"{'TOTAL':<10}  ${gt_amz:>10,.0f}  ${gt_meta:>10,.0f}  ${gt_goog:>10,.0f}  ${gt_amz+gt_meta+gt_goog:>10,.0f}")

    # ── Data availability windows (for n.m marking) ──────────────────────────
    NM = "n.m"  # sentinel for "not measured / no data collected"
    # First month with actual non-zero data per platform
    amz_data_start = (min(m for bd in amz_brand.values() for m in bd)
                      if any(amz_brand.values()) else "9999-99")
    meta_data_start = (min(meta_monthly.keys()) if meta_monthly else "9999-99")
    goog_data_start = (min(google_monthly.keys()) if google_monthly else "9999-99")

    def amz_val(month, brand_dict):
        if month < amz_data_start:
            return NM
        return round(brand_dict.get(month, 0), 2)

    def meta_val(month):
        if month < meta_data_start:
            return NM
        return round(meta_monthly.get(month, 0), 2)

    def goog_val(month):
        if month < goog_data_start:
            return NM
        return round(google_monthly.get(month, 0), 2)

    # ── Wide-format sheet rows ────────────────────────────────────────────────
    hdr = ["Platform / Brand"] + [_mlabel(m) for m in all_months] + ["YTD"]
    sheet_rows = [hdr]

    # Amazon Ads section
    sheet_rows.append(["Amazon Ads"])
    amz_brands_sorted = sorted(
        amz_brand.keys(),
        key=lambda b: BRAND_ORDER.index(b) if b in BRAND_ORDER else 99
    )
    amz_month_totals = defaultdict(float)  # only sums real values
    for brand in amz_brands_sorted:
        bd = amz_brand[brand]
        ytd_sum = _ytd(None, bd)
        row = [f"  {brand}"]
        for m in all_months:
            v = amz_val(m, bd)
            if v != NM:
                amz_month_totals[m] += v
            row.append(v)
        row.append(round(ytd_sum, 2))
        sheet_rows.append(row)
    # Amazon subtotal: "n.m" for months before data start
    amz_ytd = sum(v for m, v in amz_month_totals.items() if m >= f"{ytd_year}-01")
    amz_sub = [NM if m < amz_data_start else round(amz_month_totals.get(m, 0), 2)
               for m in all_months]
    sheet_rows.append(["  TOTAL Amazon"] + amz_sub + [round(amz_ytd, 2)])

    # Meta Ads
    sheet_rows.append(["Meta Ads"])
    meta_ytd = _ytd(meta_monthly)
    sheet_rows.append(["  Meta"] + [meta_val(m) for m in all_months] + [round(meta_ytd, 2)])

    # Google Ads
    sheet_rows.append(["Google Ads"])
    goog_ytd = _ytd(google_monthly)
    sheet_rows.append(["  Google"] + [goog_val(m) for m in all_months] + [round(goog_ytd, 2)])

    # Grand total: sum real values only, n.m if ALL platforms are n.m
    grand_ytd = amz_ytd + meta_ytd + goog_ytd
    total_row = ["TOTAL"]
    for m in all_months:
        av = amz_month_totals.get(m, NM if m < amz_data_start else 0)
        mv = meta_monthly.get(m, 0) if m >= meta_data_start else NM
        gv = google_monthly.get(m, 0) if m >= goog_data_start else NM
        nums = [x for x in [av, mv, gv] if x != NM]
        total_row.append(NM if not nums else round(sum(nums), 2))
    total_row.append(round(grand_ytd, 2))
    sheet_rows.append(total_row)

    return sheet_rows


# ── 3. SEEDING COST ───────────────────────────────────────────────────────────

def analyze_seeding_cost(date_from, date_to):
    cogs_map = load_cogs_map()
    print(f"\n  COGS map: {len(cogs_map)} SKUs")

    # PayPal (Polar JSON)
    paypal_monthly = defaultdict(float)
    try:
        d11 = json.loads((POLAR / "q11_paypal_transactions.json").read_text(encoding="utf-8"))
        txns = d11.get("transactions", d11 if isinstance(d11, list) else [])
        for t in txns:
            amt = float(t.get("amount", 0) or 0)
            if amt >= 0:
                continue
            m = (t.get("date") or "")[:7]
            if date_from <= m <= date_to:
                paypal_monthly[m] += abs(amt)
    except Exception as e:
        print(f"  [WARN] PayPal load failed: {e}")

    # PR orders (Polar JSON)
    sample_cogs = defaultdict(float)
    shipping    = defaultdict(float)
    units       = defaultdict(int)
    unmatched   = set()
    try:
        d10 = json.loads((POLAR / "q10_influencer_orders.json").read_text(encoding="utf-8"))
        orders = d10 if isinstance(d10, list) else d10.get("orders", [])
        for order in orders:
            m = (order.get("created_at") or "")[:7]
            if not m or m < date_from or m > date_to:
                continue
            for li in order.get("line_items", []):
                sku = (li.get("sku") or "").strip().lower()
                qty = int(li.get("quantity", 1) or 1)
                cost = cogs_map.get(sku, 0)
                if cost > 0:
                    sample_cogs[m] += cost * qty
                elif sku:
                    unmatched.add(sku)
                shipping[m] += 10.0 * qty
                units[m]    += qty
        print(f"  PR orders loaded, unmatched SKUs: {len(unmatched)}")
    except Exception as e:
        print(f"  [WARN] PR orders load failed: {e}")

    all_months = sorted(set(list(paypal_monthly) + list(sample_cogs) + list(shipping)))
    all_months = [m for m in all_months if date_from <= m <= date_to]

    print("\n" + "=" * 80)
    print("3) INFLUENCER SEEDING COST (Monthly)")
    print("=" * 80)
    print(f"\n{'Month':<10}  {'PayPal':>13}  {'Sample COGS':>13}  {'Shipping':>13}  {'TOTAL':>13}  {'Units':>8}")
    print("-" * 75)

    totals = defaultdict(float)
    total_units = 0
    for m in all_months:
        pp   = paypal_monthly.get(m, 0)
        cogs = sample_cogs.get(m, 0)
        ship = shipping.get(m, 0)
        tot  = pp + cogs + ship
        u    = units.get(m, 0)
        totals["pp"] += pp; totals["cogs"] += cogs
        totals["ship"] += ship; totals["total"] += tot
        total_units += u
        print(f"{m:<10}  ${pp:>12,.0f}  ${cogs:>12,.0f}  ${ship:>12,.0f}  ${tot:>12,.0f}  {u:>8,}")

    print("-" * 75)
    print(f"{'TOTAL':<10}  ${totals['pp']:>12,.0f}  ${totals['cogs']:>12,.0f}  ${totals['ship']:>12,.0f}  ${totals['total']:>12,.0f}  {total_units:>8,}")

    # ── Wide-format sheet rows (months as columns) ────────────────────────────
    import calendar as _cal2
    from datetime import datetime as _dtt3, timedelta as _td3, timezone as _tz3
    _today3 = _dtt3.now(_tz3(_td3(hours=-8))).date()
    _pnote  = f"(through {through_date})" if hasattr(analyze_seeding_cost, '_through') else ""

    def _slabel(m):
        y, mo = int(m[:4]), int(m[5:7])
        return f"{_cal2.month_abbr[mo]} {y}"

    ytd_year = all_months[-1][:4] if all_months else "2026"
    hdr = ["Item"] + [_slabel(m) for m in all_months] + ["YTD"]

    def _row(label, monthly_dict, fmt="$"):
        ytd = sum(v for m, v in monthly_dict.items() if m >= f"{ytd_year}-01")
        return [label] + [round(monthly_dict.get(m, 0), 2) for m in all_months] + [round(ytd, 2)]

    tot_monthly = {m: paypal_monthly.get(m,0)+sample_cogs.get(m,0)+shipping.get(m,0) for m in all_months}
    ytd_units = sum(v for m, v in units.items() if m >= f"{ytd_year}-01")

    sheet_rows = [
        hdr,
        _row("PayPal", paypal_monthly),
        _row("Sample COGS", sample_cogs),
        _row("Shipping", shipping),
        ["TOTAL"] + [round(tot_monthly.get(m,0), 2) for m in all_months] + [round(totals["total"], 2)],
        ["Units"] + [units.get(m, 0) for m in all_months] + [total_units],
    ]

    return sheet_rows


# ── Excel Output ─────────────────────────────────────────────────────────────

def find_latest_model():
    """Find latest kpis_model_*.xlsx by version number (v1, v2, ... v10, v11...)."""
    import re
    files = list(OUTPUT_DIR.glob("kpis_model_*.xlsx"))
    files = [f for f in files if not f.name.startswith("~")]  # skip lock files
    if not files:
        raise FileNotFoundError(f"No kpis_model_*.xlsx in {OUTPUT_DIR}")
    def _ver(p):
        m = re.search(r'_v(\d+)\.xlsx$', p.name)
        return int(m.group(1)) if m else 0
    return max(files, key=_ver)


def next_version_path(src: Path) -> Path:
    """financial_model_2026-03-06_v1.xlsx → _v2.xlsx"""
    import re
    stem = src.stem  # financial_model_2026-03-06_v1
    m = re.match(r"(.+_v)(\d+)$", stem)
    if m:
        return src.parent / f"{m.group(1)}{int(m.group(2))+1}.xlsx"
    return src.parent / f"{stem}_v2.xlsx"


def style_header(ws, n_cols):
    from openpyxl.styles import PatternFill, Font, Alignment
    fill = PatternFill("solid", fgColor="002060")
    font = Font(bold=True, color="FFFFFF")
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")


def write_wide_tab(wb, tab_name, rows):
    """Wide-format tab: 1 label column + month columns.
    Row types detected by content:
      - Section header: row has only 1 cell (len==1) or all others empty → grey
      - TOTAL row: first cell == 'TOTAL' or 'TOTAL ...' → yellow
      - Indent row: first cell starts with '  ' → italic (channel-level)
      - Header row: row[0] index == 0 → dark blue
    Numbers formatted from column 2 onward.
    """
    from openpyxl.styles import PatternFill, Font, Alignment

    FILL_HEADER  = PatternFill("solid", fgColor="002060")
    FILL_SECTION = PatternFill("solid", fgColor="D6DCE4")
    FILL_TOTAL   = PatternFill("solid", fgColor="FFF2CC")
    FILL_GTOTAL  = PatternFill("solid", fgColor="002060")
    FILL_NM      = PatternFill("solid", fgColor="595959")  # dark grey for n.m
    FONT_WHITE   = Font(bold=True, color="FFFFFF")
    FONT_BOLD    = Font(bold=True)
    FONT_ITALIC  = Font(italic=True, color="595959")
    FONT_NM      = Font(color="FFFFFF", size=8)
    ALIGN_CTR    = Alignment(horizontal="center", wrap_text=True)
    ALIGN_NM     = Alignment(horizontal="center")

    if tab_name in wb.sheetnames:
        del wb[tab_name]
    ws = wb.create_sheet(title=tab_name)

    max_cols = max((len(r) for r in rows if r), default=1)

    for r_idx, row in enumerate(rows, 1):
        if not row:
            continue
        for c_idx, val in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=val)

        first = str(row[0] or "") if row else ""
        is_header  = (r_idx == 1)
        is_section = (len([v for v in row if v not in (None, "", 0)]) == 1
                      and not first.startswith("  "))
        is_grand   = (first.strip() == "TOTAL")
        is_total   = (not is_grand and (first.strip().startswith("TOTAL") or
                      first.strip().startswith("  TOTAL")))
        is_indent  = first.startswith("  ") and not is_total

        for c_idx in range(1, max_cols + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            if is_header:
                cell.fill = FILL_HEADER
                cell.font = FONT_WHITE
                cell.alignment = ALIGN_CTR
            elif is_section:
                cell.fill = FILL_SECTION
                cell.font = FONT_BOLD
            elif is_grand:
                cell.fill = FILL_GTOTAL
                cell.font = FONT_WHITE
            elif is_total:
                cell.fill = FILL_TOTAL
                cell.font = FONT_BOLD
            elif is_indent:
                cell.font = FONT_ITALIC

            # n.m cells: dark grey background, white text, centered
            if cell.value == "n.m":
                cell.fill = FILL_NM
                cell.font = FONT_NM
                cell.alignment = ALIGN_NM
                continue

            # Format numbers (column 2+)
            if c_idx >= 2 and cell.value is not None:
                v = cell.value
                if isinstance(v, float):
                    cell.number_format = '#,##0.00'
                elif isinstance(v, int):
                    cell.number_format = '#,##0'

    # Freeze col 2, row 2
    ws.freeze_panes = ws.cell(row=2, column=2)
    ws.row_dimensions[1].height = 42

    # Column widths
    from openpyxl.utils import get_column_letter
    ws.column_dimensions["A"].width = 22
    for i in range(2, max_cols + 1):
        ws.column_dimensions[get_column_letter(i)].width = 13

    print(f"  -> Tab '{tab_name}' written ({len(rows)} rows, wide format)")


def write_tab(wb, tab_name, rows, header_row=None):
    """Add or replace a sheet tab in workbook.
    header_row: 1-based index of the column-header row (styled dark blue).
    Section rows (only col A filled, no B/C) get grey background.
    Brand subtotal rows (col C empty) get light blue.
    """
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

    FILL_HEADER  = PatternFill("solid", fgColor="002060")
    FILL_SECTION = PatternFill("solid", fgColor="D6DCE4")
    FILL_BRAND   = PatternFill("solid", fgColor="E2EFDA")
    FILL_TOTAL   = PatternFill("solid", fgColor="FFF2CC")
    FONT_WHITE   = Font(bold=True, color="FFFFFF")
    FONT_BOLD    = Font(bold=True)
    FONT_ITALIC  = Font(italic=True, color="595959")
    ALIGN_CTR    = Alignment(horizontal="center", wrap_text=True)

    if tab_name in wb.sheetnames:
        del wb[tab_name]
    ws = wb.create_sheet(title=tab_name)

    max_cols = max((len(r) for r in rows if r), default=1)

    current_section = ""  # tracks the active metric section for format decisions

    for r_idx, row in enumerate(rows, 1):
        if not row:
            continue
        for c_idx, val in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=val)

        # Detect row type
        first = str(row[0] or "") if row else ""
        is_header = (header_row and r_idx == header_row)
        is_section = (len(row) <= 1 and first and not first.startswith("  "))
        is_total   = (first == "TOTAL")
        is_brand   = (len(row) > 2 and not first.startswith("  ") and
                      row[1] and not row[2] and first not in ("TOTAL", "Metric", "Brand"))
        is_channel = first.startswith("  ")

        if is_section:
            current_section = first.upper()

        # Percent sections: DISCOUNT RATE, GM %
        is_pct_section = ("RATE" in current_section or
                          "GM %" in current_section or
                          current_section.endswith("%"))

        for c_idx in range(1, max_cols + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            if is_header:
                cell.fill = FILL_HEADER
                cell.font = FONT_WHITE
                cell.alignment = ALIGN_CTR
            elif is_section:
                cell.fill = FILL_SECTION
                cell.font = FONT_BOLD
            elif is_total:
                cell.fill = FILL_TOTAL
                cell.font = FONT_BOLD
            elif is_brand:
                cell.fill = FILL_BRAND
                cell.font = FONT_BOLD
            elif is_channel:
                cell.font = FONT_ITALIC

            # Format numbers
            if c_idx > 3 and cell.value is not None:
                v = cell.value
                if isinstance(v, float) and is_pct_section:
                    cell.number_format = '0.0%'
                elif isinstance(v, float):
                    cell.number_format = '#,##0.00'
                elif isinstance(v, int):
                    cell.number_format = '#,##0'

    # Freeze first 3 cols + header row
    if header_row:
        ws.freeze_panes = ws.cell(row=header_row + 1, column=4)
        ws.row_dimensions[header_row].height = 42  # tall enough for 2-line month labels

    # Column widths
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 12
    for i in range(4, max_cols + 1):
        col_letter = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[col_letter].width = 13

    print(f"  -> Tab '{tab_name}' written ({len(rows)} rows)")


# ── Executive Summary COGS update ─────────────────────────────────────────────

def update_exec_summary(wb, total_monthly):
    """Update COGS / Gross Profit / GM% rows in existing Executive Summary tab."""
    import calendar
    from openpyxl.styles import numbers as num_styles

    if "Executive Summary" not in wb.sheetnames:
        print("  [WARN] Executive Summary tab not found, skipping")
        return

    ws = wb["Executive Summary"]

    # Build month -> column index map from header row (R2)
    # Normalize headers: strip suffixes like "(~Mar 6th)" or newlines so "Mar 2026 (~...)" -> "Mar 2026"
    import re as _re
    def _norm_hdr(s):
        return _re.sub(r'[\s\n]*[\(\[].*', '', str(s)).strip()

    hdr = [ws.cell(row=2, column=c).value for c in range(1, ws.max_column + 1)]
    col_map = {_norm_hdr(v): i + 1 for i, v in enumerate(hdr) if v}

    # Find COGS row (search col A)
    cogs_row = gp_row = gm_row = None
    for r in range(1, ws.max_row + 1):
        v = str(ws.cell(row=r, column=1).value or "").strip()
        if v == "COGS":
            cogs_row = r
        elif v == "Gross Profit":
            gp_row = r
        elif v in ("Gross Margin %", "GM %", "Gross Margin"):
            gm_row = r

    if not cogs_row:
        print("  [WARN] COGS row not found in Executive Summary, skipping")
        return

    # Compute YTD year from latest month
    all_months = sorted(total_monthly.keys())
    ytd_year = all_months[-1][:4] if all_months else str(__import__("datetime").date.today().year)

    ytd_cogs = ytd_net = 0.0

    for m, v in total_monthly.items():
        y, mo = int(m[:4]), int(m[5:7])
        col_label = f"{calendar.month_abbr[mo]} {y}"
        col = col_map.get(col_label)
        if not col:
            continue

        cogs = round(v["cogs"], 2)
        net  = round(v["net"],  2)
        gp   = round(net - cogs, 2)
        gm   = round(gp / net, 4) if net else 0.0

        ws.cell(row=cogs_row, column=col).value = cogs
        ws.cell(row=cogs_row, column=col).number_format = '#,##0.00'
        if gp_row:
            ws.cell(row=gp_row, column=col).value = gp
            ws.cell(row=gp_row, column=col).number_format = '#,##0.00'
        if gm_row:
            ws.cell(row=gm_row, column=col).value = gm
            ws.cell(row=gm_row, column=col).number_format = '0.0%'

        if m[:4] == ytd_year:
            ytd_cogs += v["cogs"]
            ytd_net  += v["net"]

    # YTD column
    ytd_col = col_map.get("YTD")
    if ytd_col:
        ytd_cogs = round(ytd_cogs, 2)
        ytd_gp   = round(ytd_net - ytd_cogs, 2)
        ytd_gm   = round(ytd_gp / ytd_net, 4) if ytd_net else 0.0
        ws.cell(row=cogs_row, column=ytd_col).value = ytd_cogs
        if gp_row:
            ws.cell(row=gp_row, column=ytd_col).value = ytd_gp
        if gm_row:
            ws.cell(row=gm_row, column=ytd_col).value = ytd_gm

    print(f"  -> Executive Summary COGS updated (rows {cogs_row}/{gp_row}/{gm_row})")


# ── Summary tab D2C section ────────────────────────────────────────────────────

def add_summary_d2c_section(wb, d2c_monthly, seeding_rows, adspend_rows):
    """Append a D2C KPI summary block to the existing Summary tab."""
    import calendar
    from openpyxl.styles import PatternFill, Font, Alignment

    if "Summary" not in wb.sheetnames:
        print("  [WARN] Summary tab not found, skipping")
        return

    ws = wb["Summary"]

    FILL_HEADER  = PatternFill("solid", fgColor="002060")
    FILL_SECTION = PatternFill("solid", fgColor="D6DCE4")
    FILL_TOTAL   = PatternFill("solid", fgColor="FFF2CC")
    FONT_WHITE   = Font(bold=True, color="FFFFFF")
    FONT_BOLD    = Font(bold=True)
    ALIGN_CTR    = Alignment(horizontal="center", wrap_text=True)

    # Parse wide-format rows: header row[0] has month labels, find TOTAL row
    def _parse_wide_total(rows):
        """Extract {month_str: value} from wide-format rows TOTAL row."""
        import calendar as _cal
        if not rows:
            return {}
        hdr = rows[0]  # ["Label/Platform", "Jan 2024", ..., "YTD"]
        # Build mapping: month_abbr_year -> "YYYY-MM"
        col_to_month = {}
        for ci, label in enumerate(hdr[1:], 1):
            if label == "YTD":
                continue
            try:
                parts = str(label).split()
                if len(parts) == 2:
                    mon_abbr, yr = parts
                    mon_num = list(_cal.month_abbr).index(mon_abbr)
                    col_to_month[ci] = f"{yr}-{mon_num:02d}"
            except (ValueError, IndexError):
                pass
        result = {}
        for row in rows[1:]:
            if row and str(row[0]).strip() == "TOTAL":
                for ci, month_str in col_to_month.items():
                    if ci < len(row):
                        v = row[ci]
                        result[month_str] = float(v) if v not in (None, "", "n.m") else 0.0
                break
        return result

    ad_dict = _parse_wide_total(adspend_rows)
    seed_dict = _parse_wide_total(seeding_rows)

    months = sorted(d2c_monthly.keys())
    if not months:
        print("  [WARN] No D2C monthly data, skipping Summary section")
        return

    # Month column headers
    col_labels = []
    for m in months:
        y, mo = int(m[:4]), int(m[5:7])
        col_labels.append(f"{calendar.month_abbr[mo]} {y}")
    col_labels.append("YTD")

    ytd_year = months[-1][:4]

    def ytd(d):
        return sum(v for m, v in d.items() if m[:4] == ytd_year)

    def d2c_val(field, m):
        return d2c_monthly[m].get(field, 0)

    # Build rows: [label] + [monthly values] + [YTD]
    metrics = [
        ("D2C Gross Sales ($)",   [round(d2c_val("gross", m), 2) for m in months],  round(ytd({m: d2c_val("gross",m) for m in months}), 2),  '#,##0.00', False),
        ("D2C Net Sales ($)",     [round(d2c_val("net",   m), 2) for m in months],  round(ytd({m: d2c_val("net",  m) for m in months}), 2),  '#,##0.00', False),
        ("D2C Discount ($)",      [round(d2c_val("disc",  m), 2) for m in months],  round(ytd({m: d2c_val("disc", m) for m in months}), 2),  '#,##0.00', False),
        ("D2C Discount Rate",     [round(d2c_val("disc",m)/d2c_val("gross",m), 4) if d2c_val("gross",m) else 0 for m in months],
                                   round(ytd({m: d2c_val("disc",m) for m in months}) / ytd({m: d2c_val("gross",m) for m in months}), 4)
                                   if ytd({m: d2c_val("gross",m) for m in months}) else 0,  '0.0%', True),
        ("Ad Spend (total $)",    [round(ad_dict.get(m, 0), 2) for m in months],    round(ytd({m: ad_dict.get(m,0) for m in months}), 2),    '#,##0.00', False),
        ("Seeding Cost ($)",      [round(seed_dict.get(m, 0), 2) for m in months],  round(ytd({m: seed_dict.get(m,0) for m in months}), 2),  '#,##0.00', False),
    ]

    # Start writing after last used row (+ 3 blank rows)
    start = ws.max_row + 3

    # Section title
    ws.cell(row=start, column=1).value = "D2C KPI SUMMARY  |  D2C = ONZ + Amazon + TikTok"
    for c in range(1, len(col_labels) + 2):
        ws.cell(row=start, column=c).fill = FILL_SECTION
        ws.cell(row=start, column=c).font = FONT_BOLD
    start += 1

    # Header row
    ws.cell(row=start, column=1).value = "Metric"
    for ci, label in enumerate(col_labels, 2):
        ws.cell(row=start, column=ci).value = label
        ws.cell(row=start, column=ci).fill = FILL_HEADER
        ws.cell(row=start, column=ci).font = FONT_WHITE
        ws.cell(row=start, column=ci).alignment = ALIGN_CTR
    ws.cell(row=start, column=1).fill = FILL_HEADER
    ws.cell(row=start, column=1).font = FONT_WHITE
    start += 1

    # Data rows
    for label, vals, ytd_val, fmt, is_pct in metrics:
        ws.cell(row=start, column=1).value = label
        ws.cell(row=start, column=1).font = FONT_BOLD
        for ci, v in enumerate(vals, 2):
            cell = ws.cell(row=start, column=ci)
            cell.value = v
            cell.number_format = fmt
        ytd_cell = ws.cell(row=start, column=len(col_labels) + 1)
        ytd_cell.value = ytd_val
        ytd_cell.number_format = fmt
        ytd_cell.fill = FILL_TOTAL
        start += 1

    # Column widths (only if narrower than needed)
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width, 22)
    for i in range(2, len(col_labels) + 2):
        ltr = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[ltr].width = max(ws.column_dimensions[ltr].width, 12)

    print(f"  -> Summary D2C section appended (row {ws.max_row - len(metrics) + 1} ~)")


# ── Amazon Discount Debug Tab ─────────────────────────────────────────────────

def add_amazon_discount_tab(wb, through_date):
    """Add KPI_Amazon할인_상세 tab showing per-day Amazon channel discount breakdown."""
    from openpyxl.styles import PatternFill, Font, Alignment

    TAB = "KPI_Amazon할인_상세"
    if TAB in wb.sheetnames:
        del wb[TAB]
    ws = wb.create_sheet(TAB)

    FILL_HDR  = PatternFill("solid", fgColor="002060")
    FILL_NOTE = PatternFill("solid", fgColor="FFF2CC")
    FONT_W    = Font(bold=True, color="FFFFFF")
    FONT_B    = Font(bold=True)
    ALIGN_C   = Alignment(horizontal="center", wrap_text=True)

    # ── Methodology note ─────────────────────────────────────────────────────
    notes = [
        "Amazon 채널 할인 계산 방식",
        "gross_sales = sell_price × qty  (Amazon 판매가 × 수량)",
        "discounts   = line_disc only  (실제 쿠폰/프로모 할인만; compare_at_price 차이 제외)",
        "net_sales   = gross_sales - discounts",
        f"Data through: {through_date}  |  Channel = 'Amazon' orders in Shopify only",
    ]
    for i, note in enumerate(notes, 1):
        c = ws.cell(row=i, column=1, value=note)
        c.fill = FILL_NOTE
        c.font = FONT_B if i == 1 else Font()
    ws.merge_cells(f"A1:I1")
    ws.row_dimensions[1].height = 16

    # ── Header row ───────────────────────────────────────────────────────────
    HDR_ROW = len(notes) + 2
    headers = ["Date", "Brand", "Gross Sales ($)", "Discounts ($)", "Net Sales ($)",
               "Orders", "Units", "Disc Rate (%)", "Note"]
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=HDR_ROW, column=ci, value=h)
        cell.fill = FILL_HDR
        cell.font = FONT_W
        cell.alignment = ALIGN_C
    ws.row_dimensions[HDR_ROW].height = 30

    # ── Data ─────────────────────────────────────────────────────────────────
    rows = load_dk("shopify_orders_daily", days=800)
    amz = [r for r in rows if r.get("channel") == "Amazon"
           and (r.get("date") or "") <= through_date]
    amz.sort(key=lambda r: (r.get("date", ""), r.get("brand", "")))

    FILL_ALT = PatternFill("solid", fgColor="EBF3FB")
    FILL_TOT = PatternFill("solid", fgColor="FFF2CC")

    brand_agg = defaultdict(lambda: {"gross":0.0,"disc":0.0,"net":0.0,"orders":0,"units":0})
    month_agg = defaultdict(lambda: {"gross":0.0,"disc":0.0,"net":0.0,"orders":0,"units":0})
    grand     = {"gross":0.0,"disc":0.0,"net":0.0,"orders":0,"units":0}

    dr = HDR_ROW + 1
    for i, r in enumerate(amz):
        gross  = float(r.get("gross_sales") or 0)
        disc   = float(r.get("discounts")   or 0)
        net    = float(r.get("net_sales")   or 0)
        orders = int(r.get("orders") or 0)
        units  = int(r.get("units")  or 0)
        rate   = disc / gross if gross else 0.0
        date   = r.get("date", "")
        brand  = r.get("brand", "")
        month  = date[:7]
        note   = "BFCM" if month == "2025-11" else ("No promo" if disc == 0 else "Promo")

        fill = FILL_ALT if i % 2 == 1 else None
        vals = [date, brand, gross, disc, net, orders, units, rate, note]
        fmts = [None, None, '#,##0.00', '#,##0.00', '#,##0.00', '#,##0', '#,##0', '0.00%', None]
        for ci, (v, fmt) in enumerate(zip(vals, fmts), 1):
            cell = ws.cell(row=dr, column=ci, value=v)
            if fmt: cell.number_format = fmt
            if fill: cell.fill = fill
        dr += 1

        for k, v in [("gross",gross),("disc",disc),("net",net),("orders",orders),("units",units)]:
            brand_agg[brand][k] += v
            month_agg[month][k] += v
            grand[k] += v

    # ── Monthly summary (wide format: brands as rows, months as columns) ──────
    dr += 1
    ws.cell(row=dr, column=1, value="Monthly Summary — Wide Format (months as columns)").font = FONT_B
    ws.cell(row=dr, column=1).fill = PatternFill("solid", fgColor="D6DCE4")
    for ci in range(2, len(sorted(month_agg)) + 3):
        ws.cell(row=dr, column=ci).fill = PatternFill("solid", fgColor="D6DCE4")
    dr += 1

    sorted_months = sorted(month_agg)

    # Metric sections: Gross / Discounts / Disc Rate per brand row
    # Header row: [Metric / Brand] + [month1, month2, ..., TOTAL]
    for ci, h in enumerate(["Metric / Brand"] + sorted_months + ["TOTAL"], 1):
        cell = ws.cell(row=dr, column=ci, value=h)
        cell.fill = PatternFill("solid", fgColor="002060")
        cell.font = FONT_W
        cell.alignment = ALIGN_C
    dr += 1

    # Collect brands present in Amazon channel
    amz_brands_present = sorted(
        set(r.get("brand","") for r in amz if r.get("brand")),
        key=lambda b: ["Grosmimi","Naeiae","CHA&MOM","Unknown"].index(b)
            if b in ["Grosmimi","Naeiae","CHA&MOM","Unknown"] else 99
    )

    for metric, field, fmt in [
        ("Gross Sales ($)", "gross", '#,##0.00'),
        ("Discounts ($)",   "disc",  '#,##0.00'),
        ("Disc Rate (%)",   "rate",  '0.00%'),
    ]:
        # Section header
        cell = ws.cell(row=dr, column=1, value=metric)
        cell.fill = PatternFill("solid", fgColor="D6DCE4")
        cell.font = FONT_B
        for ci in range(2, len(sorted_months) + 3):
            ws.cell(row=dr, column=ci).fill = PatternFill("solid", fgColor="D6DCE4")
        dr += 1

        # Per brand + TOTAL
        for brand in amz_brands_present + ["TOTAL"]:
            row_data = [f"  {brand}" if brand != "TOTAL" else "TOTAL"]
            brand_total = 0.0
            for m in sorted_months:
                if brand == "TOTAL":
                    mv = month_agg[m]
                else:
                    # filter amz rows for this brand+month
                    mv_g = sum(float(r.get("gross_sales",0) or 0)
                               for r in amz if r.get("brand")==brand and r.get("date","")[:7]==m)
                    mv_d = sum(float(r.get("discounts",0) or 0)
                               for r in amz if r.get("brand")==brand and r.get("date","")[:7]==m)
                    mv_n = mv_g - mv_d
                    mv = {"gross": mv_g, "disc": mv_d, "net": mv_n}
                if field == "rate":
                    val = mv["disc"] / mv["gross"] if mv["gross"] else 0.0
                else:
                    val = mv[field]
                row_data.append(round(val, 4) if field == "rate" else round(val, 2))
                if field != "rate":
                    brand_total += val
            # TOTAL column
            if field == "rate":
                g_tot = grand["gross"] if brand == "TOTAL" else sum(
                    float(r.get("gross_sales",0) or 0) for r in amz if r.get("brand")==brand)
                d_tot = grand["disc"] if brand == "TOTAL" else sum(
                    float(r.get("discounts",0) or 0) for r in amz if r.get("brand")==brand)
                row_data.append(round(d_tot/g_tot, 4) if g_tot else 0.0)
            else:
                g_t = grand[field] if brand == "TOTAL" else brand_total
                row_data.append(round(g_t, 2))

            for ci, val in enumerate(row_data, 1):
                cell = ws.cell(row=dr, column=ci, value=val)
                if brand == "TOTAL":
                    cell.fill = FILL_TOT
                    cell.font = FONT_B
                if ci >= 2 and isinstance(val, float):
                    cell.number_format = fmt
            dr += 1

    # Column widths
    from openpyxl.utils import get_column_letter
    for ci, w in enumerate([12, 14, 15, 14, 14, 9, 9, 12, 12], 1):
        ws.column_dimensions[get_column_letter(ci)].width = w

    ws.freeze_panes = ws.cell(row=HDR_ROW + 1, column=1)
    print(f"  -> Tab '{TAB}' written ({len(amz)} rows, {len(month_agg)} months)")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="date_from", default="2024-01")
    parser.add_argument("--to",   dest="date_to",   default="2099-12")
    parser.add_argument("--no-sheet", action="store_true", help="Skip Google Sheet write")
    args = parser.parse_args()

    print(f"\nKPI Monthly Analysis  [{args.date_from} ~ {args.date_to}]")
    print(f"Data source: PG Data Keeper + Polar JSON\n")

    # Compute consistent through_date from all main channels (PST)
    through_date = compute_through_date()
    print(f"Consistent through_date: {through_date}\n")

    rows_discount, total_monthly, d2c_monthly = analyze_discounts(args.date_from, args.date_to, through_date)
    rows_adspend  = analyze_ad_spend(args.date_from, args.date_to, through_date)
    rows_seeding  = analyze_seeding_cost(args.date_from, args.date_to)

    print("\n" + "=" * 80)

    if args.no_sheet:
        print("--no-sheet: Excel write skipped.")
        return

    import openpyxl
    src = find_latest_model()
    dst = next_version_path(src)
    print(f"\nLoading: {src.name}")
    wb = openpyxl.load_workbook(str(src))

    write_tab(wb, "KPI_할인율",   rows_discount, header_row=3)
    write_wide_tab(wb, "KPI_광고비",   rows_adspend)
    write_wide_tab(wb, "KPI_시딩비용", rows_seeding)

    update_exec_summary(wb, total_monthly)
    add_summary_d2c_section(wb, d2c_monthly, rows_seeding, rows_adspend)
    add_amazon_discount_tab(wb, through_date)

    wb.save(str(dst))
    print(f"\nSaved: {dst.name}")
    print("DONE")


if __name__ == "__main__":
    main()
