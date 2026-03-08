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


def analyze_discounts(date_from, date_to):
    """Wide format (Golmani-style):
       Rows: Section header + TOTAL + Brand subtotal + Channel detail
       Cols: [Label, Brand, Channel] + [Jan 2024, Feb 2024, ..., YTD]
       Sections: Gross Sales / Net Sales / Discounts / Discount % /
                 Units / Avg List Price / COGS (est.) / GM / GM%
       PR channel excluded (goes to seeding cost section).
    """
    import openpyxl
    brand_cogs = load_brand_avg_cogs()

    # ── collect PG data ──────────────────────────────────────────────────────
    rows = load_dk("shopify_orders_daily")
    latest_date = "0000-00-00"
    agg = defaultdict(lambda: {"gross":0.0,"disc":0.0,"net":0.0,"orders":0,"units":0})

    for r in rows:
        raw_date = r.get("date") or ""
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
    # "through" date = yesterday PST (last full day)
    from datetime import datetime as _dtt, timedelta as _td, timezone as _tz
    PST = _tz(_td(hours=-8))
    today_pst     = _dtt.now(PST).date()
    yesterday_pst = (today_pst - _td(days=1)).isoformat()
    through_date  = min(latest_date, yesterday_pst) if latest_date > "0000-00-00" else yesterday_pst
    partial_note  = f"(through {through_date})"

    # Month labels: last month gets partial note
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

def analyze_ad_spend(date_from, date_to):
    result = defaultdict(lambda: defaultdict(float))

    for r in load_dk("amazon_ads_daily"):
        date = (r.get("date") or "")[:7]
        if date_from <= date <= date_to:
            result[date]["Amazon Ads"] += float(r.get("spend") or 0)

    for r in load_dk("meta_ads_daily"):
        date = (r.get("date") or "")[:7]
        if date_from <= date <= date_to:
            result[date]["Meta Ads"] += float(r.get("spend") or 0)

    for r in load_dk("google_ads_daily"):
        date = (r.get("date") or "")[:7]
        if date_from <= date <= date_to:
            result[date]["Google Ads"] += float(r.get("spend") or 0)

    platforms = ["Amazon Ads", "Meta Ads", "Google Ads"]
    totals = defaultdict(float)

    print("\n" + "=" * 80)
    print("2) AD SPEND BY PLATFORM (Monthly)")
    print("=" * 80)
    print(f"\n{'Month':<10}", end="")
    for p in platforms:
        print(f"  {p:>12}", end="")
    print(f"  {'TOTAL':>12}")
    print("-" * (10 + 14 * (len(platforms) + 1)))

    sheet_rows = [["Month"] + platforms + ["TOTAL"]]

    for month in sorted(result.keys()):
        print(f"{month:<10}", end="")
        row = [month]
        row_total = 0.0
        for p in platforms:
            v = result[month][p]
            totals[p] += v
            row_total += v
            print(f"  ${v:>10,.0f}", end="")
            row.append(round(v, 2))
        print(f"  ${row_total:>10,.0f}")
        row.append(round(row_total, 2))
        sheet_rows.append(row)

    print("-" * (10 + 14 * (len(platforms) + 1)))
    print(f"{'TOTAL':<10}", end="")
    grand = 0.0
    total_row = ["TOTAL"]
    for p in platforms:
        print(f"  ${totals[p]:>10,.0f}", end="")
        grand += totals[p]
        total_row.append(round(totals[p], 2))
    print(f"  ${grand:>10,.0f}")
    total_row.append(round(grand, 2))
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

    sheet_rows = [["Month", "PayPal", "Sample COGS", "Shipping", "TOTAL", "Units"]]
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
        sheet_rows.append([m, round(pp,2), round(cogs,2), round(ship,2), round(tot,2), u])

    print("-" * 75)
    print(f"{'TOTAL':<10}  ${totals['pp']:>12,.0f}  ${totals['cogs']:>12,.0f}  ${totals['ship']:>12,.0f}  ${totals['total']:>12,.0f}  {total_units:>8,}")
    sheet_rows.append(["TOTAL", round(totals["pp"],2), round(totals["cogs"],2),
                        round(totals["ship"],2), round(totals["total"],2), total_units])

    return sheet_rows


# ── Excel Output ─────────────────────────────────────────────────────────────

def find_latest_model():
    """Find latest kpis_model_*.xlsx in Output dir."""
    files = sorted(OUTPUT_DIR.glob("kpis_model_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No kpis_model_*.xlsx in {OUTPUT_DIR}")
    return files[-1]


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
    hdr = [ws.cell(row=2, column=c).value for c in range(1, ws.max_column + 1)]
    col_map = {str(v): i + 1 for i, v in enumerate(hdr) if v}

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

    # Build seeding monthly dict {month: total}
    seed_dict = {}
    for row in seeding_rows[1:]:
        if row and row[0] != "TOTAL":
            seed_dict[str(row[0])[:7]] = float(row[4] or 0)

    # Build adspend monthly dict {month: total}
    ad_dict = {}
    for row in adspend_rows[1:]:
        if row and row[0] != "TOTAL":
            ad_dict[str(row[0])[:7]] = float(row[4] or 0)

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

    rows_discount, total_monthly, d2c_monthly = analyze_discounts(args.date_from, args.date_to)
    rows_adspend  = analyze_ad_spend(args.date_from, args.date_to)
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
    write_tab(wb, "KPI_광고비",   rows_adspend,  header_row=1)
    write_tab(wb, "KPI_시딩비용", rows_seeding,  header_row=1)

    update_exec_summary(wb, total_monthly)
    add_summary_d2c_section(wb, d2c_monthly, rows_seeding, rows_adspend)

    wb.save(str(dst))
    print(f"\nSaved: {dst.name}")
    print("DONE")


if __name__ == "__main__":
    main()
