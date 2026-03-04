"""Dongkyun Tester - SNS Tab Sync pipeline validator.

Checks: [C] Credentials, [D] Data sources, [S] Syncly connectivity,
        [T] Target sheet, [M] Matching accuracy, [F] Filtering, [O] Output integrity.

Usage:
  python tools/dongkyun_tester.py --run            # full validation
  python tools/dongkyun_tester.py --validate-only   # skip API, check local data
  python tools/dongkyun_tester.py --results          # show last results
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

RESULTS_PATH = PROJECT_ROOT / ".tmp" / "dongkyun_test_results.json"
Q10_PATH = PROJECT_ROOT / ".tmp" / "polar_data" / "q10_influencer_orders.json"
Q11_PATH = PROJECT_ROOT / ".tmp" / "polar_data" / "q11_paypal_transactions.json"
SYNCLY_SHEET_ID = "1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc"
TARGET_SHEET_ID = "1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA"

EXPECTED_HEADERS = [
    "No", "Channel", "Account", "Product Type",
    "Influencer Fee", "Content Link",
    "Approved for Cross-Market Use",
    "D+ Days", "Curr Comment", "Curr Like", "Curr View",
]

GIVEAWAY_KW = ("giveaway", "valentine", "bfcm", "black friday", "christmas")


def _pass(code, msg):
    print(f"  PASS [{code}] {msg}")
    return {"code": code, "status": "PASS", "message": msg}


def _warn(code, msg):
    print(f"  WARN [{code}] {msg}")
    return {"code": code, "status": "WARN", "message": msg}


def _fail(code, msg):
    print(f"  FAIL [{code}] {msg}")
    return {"code": code, "status": "FAIL", "message": msg}


# ── [C] Credentials ───────────────────────────────────────────────────────

def check_credentials(skip_api=False):
    results = []
    from env_loader import load_env
    load_env()

    sa_path = os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json"
    )
    if not os.path.isabs(sa_path):
        sa_path = str(PROJECT_ROOT / sa_path)

    if os.path.exists(sa_path):
        results.append(_pass("C1", f"Service Account JSON exists: {sa_path}"))
    else:
        results.append(_fail("C1", f"Service Account JSON not found: {sa_path}"))
        return results, None

    if skip_api:
        results.append(_warn("C2", "API check skipped (--validate-only)"))
        return results, None

    try:
        from google.oauth2.service_account import Credentials
        import gspread
        creds = Credentials.from_service_account_file(
            sa_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gc = gspread.authorize(creds)
        results.append(_pass("C2", "gspread authorize OK"))
    except Exception as e:
        results.append(_fail("C2", f"gspread authorize failed: {e}"))
        return results, None

    # Test Syncly sheet access
    try:
        sh = gc.open_by_key(SYNCLY_SHEET_ID)
        tabs = [ws.title for ws in sh.worksheets()]
        results.append(_pass("C3", f"Syncly sheet accessible, tabs: {tabs}"))
    except Exception as e:
        results.append(_fail("C3", f"Syncly sheet inaccessible: {e}"))

    # Test target sheet access
    try:
        sh2 = gc.open_by_key(TARGET_SHEET_ID)
        tabs2 = [ws.title for ws in sh2.worksheets()]
        results.append(_pass("C4", f"Target sheet accessible, tabs: {tabs2}"))
    except Exception as e:
        results.append(_fail("C4", f"Target sheet inaccessible: {e}"))

    return results, gc


# ── [D] Data Sources ──────────────────────────────────────────────────────

def check_data_sources():
    results = []

    # q10
    if Q10_PATH.exists():
        try:
            with open(Q10_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            orders = data.get("orders", [])
            n = len(orders)
            if n > 100:
                results.append(_pass("D1", f"q10: {n} orders loaded"))
            elif n > 50:
                results.append(_warn("D1", f"q10: only {n} orders (expected >100)"))
            else:
                results.append(_fail("D1", f"q10: only {n} orders (expected >100)"))

            # Check required fields
            sample = orders[0] if orders else {}
            required = ["id", "tags", "fulfillment_status", "line_items", "customer_name"]
            missing = [f for f in required if f not in sample]
            if missing:
                results.append(_fail("D2", f"q10 missing fields: {missing}"))
            else:
                results.append(_pass("D2", "q10 required fields present"))

            # Count shipped + Grosmimi
            shipped_gros = sum(
                1 for o in orders
                if (o.get("fulfillment_status") or "") in ("fulfilled", "shipped")
                and any("grosmimi" in li.get("title", "").lower()
                        for li in o.get("line_items", []))
            )
            results.append(_pass("D3", f"Shipped Grosmimi orders: {shipped_gros}"))
        except Exception as e:
            results.append(_fail("D1", f"q10 parse error: {e}"))
    else:
        results.append(_fail("D1", f"q10 not found: {Q10_PATH}"))

    # q11
    if Q11_PATH.exists():
        try:
            with open(Q11_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            txns = data.get("transactions", [])
            results.append(_pass("D4", f"q11: {len(txns)} transactions loaded"))
        except Exception as e:
            results.append(_warn("D4", f"q11 parse error: {e}"))
    else:
        results.append(_warn("D4", f"q11 not found (PayPal fee data unavailable)"))

    return results


# ── [S] Syncly Connectivity ───────────────────────────────────────────────

def check_syncly(gc):
    results = []
    if gc is None:
        results.append(_warn("S1", "Skipped (no gspread client)"))
        return results

    try:
        sh = gc.open_by_key(SYNCLY_SHEET_ID)

        # Posts Master
        pm = sh.worksheet("Posts Master")
        pm_rows = pm.get_all_values()
        n_posts = len(pm_rows) - 1  # minus header
        if n_posts > 30:
            results.append(_pass("S1", f"Posts Master: {n_posts} posts"))
        elif n_posts > 10:
            results.append(_warn("S1", f"Posts Master: only {n_posts} posts"))
        else:
            results.append(_fail("S1", f"Posts Master: only {n_posts} posts"))

        # Check platforms
        platforms = set()
        for row in pm_rows[1:]:
            if len(row) > 2 and row[2]:
                platforms.add(row[2].lower())
        results.append(_pass("S2", f"Platforms found: {platforms}"))

        # D+30 Tracker
        tr = sh.worksheet("D+30 Tracker")
        tr_rows = tr.get_all_values()
        n_tracker = len(tr_rows) - 2  # minus 2 header rows
        if n_tracker > 30:
            results.append(_pass("S3", f"D+30 Tracker: {n_tracker} posts"))
        elif n_tracker > 10:
            results.append(_warn("S3", f"D+30 Tracker: only {n_tracker} posts"))
        else:
            results.append(_fail("S3", f"D+30 Tracker: only {n_tracker} posts"))

        # D+ Days range check
        d_values = []
        for row in tr_rows[2:]:
            if row[0] and len(row) > 4:
                try:
                    d = int(float(str(row[4]).replace(",", "")))
                    d_values.append(d)
                except (ValueError, TypeError):
                    pass
        if d_values:
            min_d, max_d = min(d_values), max(d_values)
            if max_d <= 60:
                results.append(_pass("S4", f"D+ range: {min_d}~{max_d} days"))
            elif max_d <= 90:
                results.append(_warn("S4", f"D+ range: {min_d}~{max_d} days (some stale)"))
            else:
                results.append(_warn("S4", f"D+ range: {min_d}~{max_d} days (very old posts)"))

    except Exception as e:
        results.append(_fail("S1", f"Syncly read error: {e}"))

    return results


# ── [T] Target Sheet ──────────────────────────────────────────────────────

def check_target(gc):
    results = []
    if gc is None:
        results.append(_warn("T1", "Skipped (no gspread client)"))
        return results

    try:
        sh = gc.open_by_key(TARGET_SHEET_ID)
        ws = sh.worksheet("SNS")
        results.append(_pass("T1", "SNS tab exists"))

        # Check headers (Row 2) — allow extra/blank columns in between
        headers = ws.row_values(2)
        actual_non_empty = [h for h in headers if h.strip()]
        expected_non_empty = [h for h in EXPECTED_HEADERS if h.strip()]
        if actual_non_empty[:len(expected_non_empty)] == expected_non_empty:
            results.append(_pass("T2", f"Headers match ({len(expected_non_empty)} cols)"))
        else:
            results.append(_warn("T2",
                f"Header order differs. Expected: {expected_non_empty}, Got: {actual_non_empty[:11]}"))

        # Check data rows
        all_vals = ws.get_all_values()
        data_rows = len(all_vals) - 2  # minus header rows
        if data_rows > 0:
            results.append(_pass("T3", f"SNS tab has {data_rows} data rows"))
        else:
            results.append(_warn("T3", "SNS tab has no data rows"))

    except Exception as e:
        results.append(_fail("T1", f"Target sheet error: {e}"))

    return results


# ── [M] Matching Accuracy ────────────────────────────────────────────────

def check_matching():
    results = []
    if not Q10_PATH.exists():
        results.append(_warn("M1", "Skipped (q10 not found)"))
        return results

    with open(Q10_PATH, "r", encoding="utf-8") as f:
        orders = json.load(f).get("orders", [])

    ig_re = re.compile(r"IG\s*\(@?([^)\s]+)\)", re.IGNORECASE)
    tt_re = re.compile(r"TikTokOrderID:\s*(\d+)", re.IGNORECASE)

    shipped_gros = [
        o for o in orders
        if (o.get("fulfillment_status") or "") in ("fulfilled", "shipped")
        and any("grosmimi" in li.get("title", "").lower()
                for li in o.get("line_items", []))
    ]
    total = len(shipped_gros)

    ig_count = 0
    tt_count = 0
    unknown_count = 0
    for o in shipped_gros:
        tags = o.get("tags", "")
        note = o.get("note", "") or ""
        text = f"{tags} {note}"
        if ig_re.search(text):
            ig_count += 1
        elif tt_re.search(tags) or "@scs.tiktokw.us" in (o.get("customer_email", "") or ""):
            tt_count += 1
        else:
            unknown_count += 1

    results.append(_pass("M1",
        f"Account extraction: {ig_count} IG, {tt_count} TT, {unknown_count} unknown / {total} total"))

    ig_pct = ig_count / total * 100 if total else 0
    if ig_pct > 30:
        results.append(_pass("M2", f"IG handle rate: {ig_pct:.0f}%"))
    else:
        results.append(_warn("M2", f"IG handle rate: {ig_pct:.0f}% (low)"))

    return results


# ── [F] Filtering ─────────────────────────────────────────────────────────

def check_filtering():
    results = []
    if not Q10_PATH.exists():
        results.append(_warn("F1", "Skipped (q10 not found)"))
        return results

    with open(Q10_PATH, "r", encoding="utf-8") as f:
        orders = json.load(f).get("orders", [])

    shipped = [o for o in orders
               if (o.get("fulfillment_status") or "") in ("fulfilled", "shipped")]

    gros_count = sum(
        1 for o in shipped
        if any("grosmimi" in li.get("title", "").lower()
               for li in o.get("line_items", []))
    )
    non_gros = len(shipped) - gros_count
    results.append(_pass("F1",
        f"Grosmimi filter: {gros_count} pass / {non_gros} filtered out of {len(shipped)} shipped"))

    # Giveaway filter
    giveaway_count = 0
    for o in shipped:
        text = f"{o.get('tags', '')} {o.get('note', '') or ''}".lower()
        if any(kw in text for kw in GIVEAWAY_KW):
            giveaway_count += 1
    results.append(_pass("F2", f"Giveaway filter: {giveaway_count} orders would be excluded"))

    # 2026 filter
    since_2026 = sum(1 for o in shipped if o.get("created_at", "")[:10] >= "2026-01-01")
    results.append(_pass("F3",
        f"Date filter: {since_2026} shipped orders since 2026-01-01"))

    return results


# ── [O] Output Integrity ─────────────────────────────────────────────────

def check_output():
    """Run sync_sns_tab.py --dry-run and validate output."""
    results = []
    try:
        from sync_sns_tab import (
            load_orders, load_paypal, load_syncly, build_rows,
            get_credentials, SNS_HEADERS,
        )
        import gspread

        orders = load_orders()
        paypal = load_paypal()
        creds = get_credentials()
        gc = gspread.authorize(creds)
        syncly = load_syncly(gc, SYNCLY_SHEET_ID)

        rows, stats = build_rows(orders, paypal, syncly, since_date="2026-01-01")

        total = stats["total"]
        matched = stats["matched"]
        no_content = stats["no_content"]

        results.append(_pass("O1", f"Rows built: {total}"))

        if total > 0:
            match_rate = matched / total * 100
            if match_rate > 20:
                results.append(_pass("O2", f"Match rate: {match_rate:.1f}% ({matched}/{total})"))
            elif match_rate > 10:
                results.append(_warn("O2", f"Match rate: {match_rate:.1f}% ({matched}/{total})"))
            else:
                results.append(_fail("O2", f"Match rate: {match_rate:.1f}% ({matched}/{total})"))
        else:
            results.append(_fail("O2", "No rows generated"))

        # Column count check
        if rows:
            col_count = len(rows[0])
            expected = len(SNS_HEADERS)
            if col_count == expected:
                results.append(_pass("O3", f"Column count: {col_count} (matches headers)"))
            else:
                results.append(_fail("O3",
                    f"Column count mismatch: rows have {col_count}, headers have {expected}"))

        # Check for bad values
        bad_rows = 0
        for row in rows:
            d_val = row[7]  # D+ Days
            if d_val != "" and not isinstance(d_val, (int, float)):
                bad_rows += 1
        if bad_rows == 0:
            results.append(_pass("O4", "D+ Days values: all numeric or empty"))
        else:
            results.append(_fail("O4", f"D+ Days: {bad_rows} rows have non-numeric values"))

    except Exception as e:
        results.append(_fail("O1", f"Output build error: {e}"))

    return results


# ── Runner ────────────────────────────────────────────────────────────────

def run_all(skip_api=False):
    all_results = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n=== Dongkyun Tester === {timestamp}\n")

    print("[C] Credentials")
    cred_results, gc = check_credentials(skip_api=skip_api)
    all_results.extend(cred_results)

    print("\n[D] Data Sources")
    all_results.extend(check_data_sources())

    print("\n[S] Syncly Connectivity")
    all_results.extend(check_syncly(gc))

    print("\n[T] Target Sheet")
    all_results.extend(check_target(gc))

    print("\n[M] Matching Accuracy")
    all_results.extend(check_matching())

    print("\n[F] Filtering")
    all_results.extend(check_filtering())

    print("\n[O] Output Integrity")
    all_results.extend(check_output())

    # Summary
    passes = sum(1 for r in all_results if r["status"] == "PASS")
    warns = sum(1 for r in all_results if r["status"] == "WARN")
    fails = sum(1 for r in all_results if r["status"] == "FAIL")
    total = len(all_results)

    print(f"\n{'='*50}")
    print(f"TOTAL: {total} checks | PASS: {passes} | WARN: {warns} | FAIL: {fails}")
    if fails > 0:
        print("RESULT: FAIL")
        for r in all_results:
            if r["status"] == "FAIL":
                print(f"  >> [{r['code']}] {r['message']}")
    elif warns > 0:
        print("RESULT: WARN")
    else:
        print("RESULT: ALL PASS")
    print(f"{'='*50}\n")

    # Save results
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "summary": {"total": total, "pass": passes, "warn": warns, "fail": fails},
            "results": all_results,
        }, f, indent=2, ensure_ascii=False)
    print(f"Results saved: {RESULTS_PATH}")


def show_results():
    if not RESULTS_PATH.exists():
        print("No results yet. Run --run first.")
        return
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"\nLast run: {data['timestamp']}")
    s = data["summary"]
    print(f"TOTAL: {s['total']} | PASS: {s['pass']} | WARN: {s['warn']} | FAIL: {s['fail']}\n")
    for r in data["results"]:
        icon = {"PASS": "  PASS", "WARN": "  WARN", "FAIL": "  FAIL"}[r["status"]]
        print(f"{icon} [{r['code']}] {r['message']}")


def main():
    parser = argparse.ArgumentParser(description="Dongkyun Tester: SNS Tab Sync validator")
    parser.add_argument("--run", action="store_true", help="Full validation (API + data)")
    parser.add_argument("--validate-only", action="store_true", help="Local data only")
    parser.add_argument("--results", action="store_true", help="Show last results")
    args = parser.parse_args()

    if args.results:
        show_results()
    elif args.run:
        run_all(skip_api=False)
    elif args.validate_only:
        run_all(skip_api=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
