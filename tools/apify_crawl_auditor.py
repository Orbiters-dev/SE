#!/usr/bin/env python3
"""
Apify Crawl Auditor — Data Pipeline Health Checker
===================================================
Harness-compatible: Orchestrator calls this in a 3-iteration loop.
Each iteration checks a different layer, accumulating findings.

Usage:
  # Full audit (all layers)
  python tools/apify_crawl_auditor.py

  # Specific layer
  python tools/apify_crawl_auditor.py --layer infra
  python tools/apify_crawl_auditor.py --layer data
  python tools/apify_crawl_auditor.py --layer integrity

  # JSON output for harness consumption
  python tools/apify_crawl_auditor.py --json

  # Check specific region
  python tools/apify_crawl_auditor.py --region us

Layers:
  1. infra     — GitHub Actions status, secrets reachability
  2. data      — Data Storage file freshness, Google Sheets row counts
  3. integrity — D+60 column structure, brand coverage, dedup check
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from env_loader import load_env

# ── Config ────────────────────────────────────────────────────────────────── #
SHEET_ID = "1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY"
DATA_DIR = PROJECT_ROOT / "Data Storage" / "apify"
REPO = "puleaf/wj-test1"  # GitHub repo for Actions API
MAX_STALE_HOURS = 36  # data older than this = WARN
MAX_STALE_HOURS_CRIT = 72  # data older than this = CRITICAL

EXPECTED_TABS = {
    "us": ["US Posts Master", "US D+60 Tracker", "US Influencer Tracker"],
    "jp": ["JP Posts Master", "JP D+60 Tracker", "JP Influencer Tracker"],
}
EXPECTED_FILES = {
    "us": ["us_tagged_raw.json", "us_tiktok_raw.json", "us_follower_map.json"],
    "jp": ["jp_tagged_raw.json", "jp_tiktok_raw.json", "jp_follower_map.json"],
}
BRANDS = {"Grosmimi", "Cha & Mom", "Onzenna", "Babyrabbit", "Naeiae", "Goongbe", "Commemoi"}

# D+60 Tracker structure
FIXED_COLS = 9
METRICS_PER_DAY = 3
MAX_DAYS = 61
EXPECTED_COLS = FIXED_COLS + MAX_DAYS * METRICS_PER_DAY  # 192


# ── Findings ──────────────────────────────────────────────────────────────── #
class Finding:
    def __init__(self, severity, category, description, expected=None, actual=None):
        self.severity = severity      # CRITICAL / MAJOR / MINOR / INFO
        self.category = category      # INFRA / DATA / INTEGRITY
        self.description = description
        self.expected = expected
        self.actual = actual

    def to_dict(self):
        d = {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
        }
        if self.expected is not None:
            d["expected"] = str(self.expected)
        if self.actual is not None:
            d["actual"] = str(self.actual)
        return d


findings: list[Finding] = []


def add(severity, category, desc, expected=None, actual=None):
    findings.append(Finding(severity, category, desc, expected, actual))


# ── Layer 1: Infrastructure ───────────────────────────────────────────────── #
def audit_infra():
    """Check GitHub Actions workflow status and secret reachability."""
    print("\n── Layer 1: Infrastructure ──")

    # 1a. GitHub Actions — last workflow run
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        add("MINOR", "INFRA", "GITHUB_TOKEN not set — skipping Actions check")
        print("  ⚠ GITHUB_TOKEN not set, skipping Actions API")
    else:
        try:
            url = f"https://api.github.com/repos/{REPO}/actions/workflows/apify_daily.yml/runs?per_page=5"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            runs = data.get("workflow_runs", [])
            if not runs:
                add("CRITICAL", "INFRA", "No apify_daily workflow runs found")
                print("  ✗ No workflow runs found")
            else:
                latest = runs[0]
                status = latest["status"]
                conclusion = latest.get("conclusion", "in_progress")
                run_date = latest["created_at"][:10]
                run_url = latest["html_url"]

                print(f"  Latest run: {run_date} — {status}/{conclusion}")
                print(f"  URL: {run_url}")

                if conclusion == "failure":
                    add("CRITICAL", "INFRA",
                        f"Latest apify_daily run FAILED ({run_date})",
                        expected="success", actual=conclusion)
                elif conclusion == "cancelled":
                    add("MAJOR", "INFRA",
                        f"Latest apify_daily run was CANCELLED ({run_date})")
                elif status == "completed" and conclusion == "success":
                    add("INFO", "INFRA", f"Latest run succeeded ({run_date})")

                # Check consecutive failures
                fail_streak = 0
                for r in runs:
                    if r.get("conclusion") == "failure":
                        fail_streak += 1
                    else:
                        break
                if fail_streak >= 2:
                    add("CRITICAL", "INFRA",
                        f"{fail_streak} consecutive workflow failures",
                        expected="0", actual=str(fail_streak))

        except Exception as e:
            add("MAJOR", "INFRA", f"GitHub Actions API error: {e}")
            print(f"  ✗ API error: {e}")

    # 1b. Required secrets check (env vars)
    required_secrets = [
        "APIFY_API_TOKEN",
        "GOOGLE_SERVICE_ACCOUNT_PATH",
    ]
    optional_secrets = [
        "META_GRAPH_IG_TOKEN",
        "IG_BUSINESS_USER_ID_ONZENNA",
        "IG_BUSINESS_USER_ID_GROSMIMI_USA",
    ]
    for s in required_secrets:
        val = os.getenv(s)
        if not val:
            add("MAJOR", "INFRA", f"Required secret missing: {s}")
            print(f"  ✗ Missing: {s}")
        else:
            print(f"  ✓ {s} set")

    for s in optional_secrets:
        val = os.getenv(s)
        if not val:
            add("MINOR", "INFRA", f"Optional secret missing: {s} (IG Graph API fallback unavailable)")
            print(f"  △ Optional missing: {s}")
        else:
            print(f"  ✓ {s} set")

    # 1c. Google service account file
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
    sa_full = PROJECT_ROOT / sa_path
    if sa_full.exists():
        print(f"  ✓ Service account file exists")
    else:
        add("CRITICAL", "INFRA", f"Service account file missing: {sa_path}")
        print(f"  ✗ Service account file missing: {sa_path}")


# ── Layer 2: Data Freshness ───────────────────────────────────────────────── #
def audit_data(region="all"):
    """Check Data Storage files and Google Sheets freshness."""
    print("\n── Layer 2: Data Freshness ──")

    regions = ["us", "jp"] if region == "all" else [region]
    today = datetime.now()

    for reg in regions:
        print(f"\n  [{reg.upper()}] Data Storage files:")
        for fname in EXPECTED_FILES.get(reg, []):
            # Look for today's or yesterday's file
            found = False
            for days_back in range(3):
                d = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
                fpath = DATA_DIR / f"{d}_{fname}"
                if fpath.exists():
                    size = fpath.stat().st_size
                    age_h = (time.time() - fpath.stat().st_mtime) / 3600
                    print(f"    ✓ {fpath.name} ({size:,} bytes, {age_h:.1f}h ago)")

                    if age_h > MAX_STALE_HOURS_CRIT:
                        add("CRITICAL", "DATA",
                            f"{reg.upper()} {fname} is {age_h:.0f}h old",
                            expected=f"<{MAX_STALE_HOURS}h", actual=f"{age_h:.0f}h")
                    elif age_h > MAX_STALE_HOURS:
                        add("MAJOR", "DATA",
                            f"{reg.upper()} {fname} is {age_h:.0f}h old",
                            expected=f"<{MAX_STALE_HOURS}h", actual=f"{age_h:.0f}h")
                    else:
                        add("INFO", "DATA", f"{reg.upper()} {fname} fresh ({age_h:.0f}h)")

                    # Validate JSON parseable and non-empty
                    try:
                        with open(fpath) as f:
                            data = json.load(f)
                        if isinstance(data, list) and len(data) == 0:
                            add("MAJOR", "DATA", f"{reg.upper()} {fname} is empty array")
                            print(f"    ⚠ Empty array!")
                        elif isinstance(data, dict) and not data:
                            add("MAJOR", "DATA", f"{reg.upper()} {fname} is empty object")
                    except json.JSONDecodeError as e:
                        add("CRITICAL", "DATA", f"{reg.upper()} {fname} invalid JSON: {e}")
                        print(f"    ✗ Invalid JSON!")

                    found = True
                    break

            if not found:
                add("CRITICAL", "DATA",
                    f"{reg.upper()} {fname} not found (checked last 3 days)",
                    expected="file exists", actual="missing")
                print(f"    ✗ {fname} — NOT FOUND (last 3 days)")

    # 2b. Google Sheets row counts via Sheets API
    _audit_sheets(regions)


def _audit_sheets(regions):
    """Check Google Sheets tab existence and row counts."""
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
    sa_full = PROJECT_ROOT / sa_path
    if not sa_full.exists():
        add("MAJOR", "DATA", "Cannot check sheets — service account file missing")
        print("  ⚠ Skipping sheets check (no service account)")
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        add("MINOR", "DATA", "gspread not installed — skipping sheets check")
        print("  ⚠ gspread not installed, skipping sheets check")
        return

    try:
        creds = Credentials.from_service_account_file(
            str(sa_full),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        worksheets = {ws.title: ws for ws in sh.worksheets()}

        print(f"\n  Google Sheets ({SHEET_ID[:12]}...):")
        for reg in regions:
            for tab_name in EXPECTED_TABS.get(reg, []):
                if tab_name not in worksheets:
                    add("CRITICAL", "DATA", f"Tab '{tab_name}' missing from sheet")
                    print(f"    ✗ {tab_name} — MISSING")
                    continue

                ws = worksheets[tab_name]
                row_count = ws.row_count
                # Get actual used rows (approximate via col A)
                col_a = ws.col_values(1)
                used_rows = len([v for v in col_a if v.strip()])

                print(f"    ✓ {tab_name}: {used_rows} rows (capacity: {row_count})")

                if used_rows <= 1:
                    add("CRITICAL", "DATA",
                        f"Tab '{tab_name}' has no data rows",
                        expected=">1", actual=str(used_rows))
                elif "Posts Master" in tab_name and used_rows < 10:
                    add("MAJOR", "DATA",
                        f"Tab '{tab_name}' suspiciously low row count",
                        expected=">10", actual=str(used_rows))
                else:
                    add("INFO", "DATA", f"'{tab_name}' has {used_rows} rows")

    except Exception as e:
        add("MAJOR", "DATA", f"Google Sheets API error: {e}")
        print(f"  ✗ Sheets API error: {e}")


# ── Layer 3: Data Integrity ───────────────────────────────────────────────── #
def audit_integrity(region="all"):
    """Check D+60 structure, brand coverage, duplicate detection."""
    print("\n── Layer 3: Data Integrity ──")

    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/google_service_account.json")
    sa_full = PROJECT_ROOT / sa_path
    if not sa_full.exists():
        print("  ⚠ Skipping integrity check (no service account)")
        add("MAJOR", "INTEGRITY", "Cannot verify integrity — no service account")
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        add("MINOR", "INTEGRITY", "gspread not installed — skipping integrity check")
        return

    try:
        creds = Credentials.from_service_account_file(
            str(sa_full),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        worksheets = {ws.title: ws for ws in sh.worksheets()}
    except Exception as e:
        add("MAJOR", "INTEGRITY", f"Cannot connect to sheet: {e}")
        return

    regions = ["us", "jp"] if region == "all" else [region]

    for reg in regions:
        prefix = reg.upper()

        # 3a. D+60 Tracker column count
        tracker_name = f"{prefix} D+60 Tracker"
        if tracker_name in worksheets:
            ws = worksheets[tracker_name]
            header = ws.row_values(1)
            col_count = len(header)
            print(f"\n  [{prefix}] D+60 Tracker: {col_count} columns")

            if col_count < EXPECTED_COLS:
                add("MAJOR", "INTEGRITY",
                    f"{tracker_name} has fewer columns than expected",
                    expected=str(EXPECTED_COLS), actual=str(col_count))
            elif col_count > EXPECTED_COLS + 5:
                add("MINOR", "INTEGRITY",
                    f"{tracker_name} has extra columns ({col_count})",
                    expected=str(EXPECTED_COLS), actual=str(col_count))
            else:
                add("INFO", "INTEGRITY", f"{tracker_name} column count OK ({col_count})")

            # Check header pattern: D+0 Cmt, D+0 Like, D+0 View, D+1 Cmt, ...
            if col_count > FIXED_COLS + 3:
                d0_headers = header[FIXED_COLS:FIXED_COLS + 3]
                expected_d0 = ["D+0 Cmt", "D+0 Like", "D+0 View"]
                if d0_headers != expected_d0:
                    add("MAJOR", "INTEGRITY",
                        f"{tracker_name} D+0 headers mismatch",
                        expected=str(expected_d0), actual=str(d0_headers))
                    print(f"    ⚠ D+0 headers: {d0_headers} (expected {expected_d0})")
                else:
                    print(f"    ✓ D+0 header pattern correct")

        # 3b. Posts Master — brand coverage
        posts_name = f"{prefix} Posts Master"
        if posts_name in worksheets:
            ws = worksheets[posts_name]
            all_data = ws.get_all_records()

            if all_data:
                # Find brand column
                brand_col = None
                for key in all_data[0]:
                    if "brand" in key.lower():
                        brand_col = key
                        break

                if brand_col:
                    brand_values = [row.get(brand_col, "") for row in all_data]
                    non_empty = [b for b in brand_values if b.strip()]
                    empty_count = len(brand_values) - len(non_empty)

                    # Count unique brands
                    unique_brands = set()
                    for b in non_empty:
                        for brand in b.split(","):
                            unique_brands.add(brand.strip())

                    coverage = len(non_empty) / len(brand_values) * 100 if brand_values else 0
                    print(f"\n  [{prefix}] Posts Master brand coverage: {coverage:.0f}% ({len(non_empty)}/{len(brand_values)})")
                    print(f"    Brands found: {', '.join(sorted(unique_brands))}")

                    if coverage < 50:
                        add("MAJOR", "INTEGRITY",
                            f"{posts_name} brand coverage low",
                            expected=">50%", actual=f"{coverage:.0f}%")
                    elif coverage < 80:
                        add("MINOR", "INTEGRITY",
                            f"{posts_name} brand coverage moderate",
                            expected=">80%", actual=f"{coverage:.0f}%")
                    else:
                        add("INFO", "INTEGRITY",
                            f"{posts_name} brand coverage good ({coverage:.0f}%)")

                    # Check for unknown brands
                    unknown = unique_brands - BRANDS
                    if unknown:
                        add("MINOR", "INTEGRITY",
                            f"Unknown brands in {posts_name}: {unknown}")
                        print(f"    △ Unknown brands: {unknown}")

                # 3c. Duplicate check (Post ID column)
                id_col = None
                for key in all_data[0]:
                    if "post" in key.lower() and "id" in key.lower():
                        id_col = key
                        break
                if not id_col:
                    # fallback: first column
                    id_col = list(all_data[0].keys())[0]

                ids = [row.get(id_col, "") for row in all_data if row.get(id_col, "")]
                dupes = len(ids) - len(set(ids))
                if dupes > 0:
                    add("MAJOR", "INTEGRITY",
                        f"{posts_name} has {dupes} duplicate post IDs",
                        expected="0", actual=str(dupes))
                    print(f"    ✗ {dupes} duplicate IDs found!")
                else:
                    add("INFO", "INTEGRITY", f"{posts_name} no duplicates")
                    print(f"    ✓ No duplicate post IDs")


# ── Report ────────────────────────────────────────────────────────────────── #
def build_report(as_json=False, iteration=None):
    """Build and return audit report."""
    crit = [f for f in findings if f.severity == "CRITICAL"]
    major = [f for f in findings if f.severity == "MAJOR"]
    minor = [f for f in findings if f.severity == "MINOR"]
    info = [f for f in findings if f.severity == "INFO"]

    if crit:
        health = "FAIL"
    elif major:
        health = "WARN"
    else:
        health = "PASS"

    report = {
        "timestamp": datetime.now().isoformat(),
        "iteration": iteration,
        "health": health,
        "summary": {
            "critical": len(crit),
            "major": len(major),
            "minor": len(minor),
            "info": len(info),
            "total": len(findings),
        },
        "findings": [f.to_dict() for f in findings],
    }

    if as_json:
        return report

    # Pretty print
    print("\n" + "=" * 60)
    print(f"  AUDIT REPORT — {health}")
    if iteration:
        print(f"  Iteration: {iteration}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"  CRITICAL: {len(crit)}  |  MAJOR: {len(major)}  |  MINOR: {len(minor)}  |  INFO: {len(info)}")
    print("-" * 60)

    for sev_label, items in [("CRITICAL", crit), ("MAJOR", major), ("MINOR", minor)]:
        if items:
            print(f"\n  [{sev_label}]")
            for f in items:
                line = f"    • {f.description}"
                if f.expected:
                    line += f" (expected: {f.expected}, actual: {f.actual})"
                print(line)

    print("\n" + "=" * 60)
    return report


# ── Harness Entry Point ──────────────────────────────────────────────────── #
def run_audit(layer=None, region="all", iteration=None):
    """
    Run audit. Called directly or from harness loop.
    Returns dict with health status and findings.
    """
    global findings
    findings = []

    layers = {
        "infra": audit_infra,
        "data": lambda: audit_data(region),
        "integrity": lambda: audit_integrity(region),
    }

    if layer and layer in layers:
        layers[layer]()
    else:
        for name, fn in layers.items():
            fn()

    return build_report(as_json=True, iteration=iteration)


def run_harness_loop(region="all", max_iter=3):
    """
    Harness mode: run 3 iterations, each checking a different layer.
    Accumulate findings, produce final merged report.
    """
    layer_sequence = ["infra", "data", "integrity"]
    all_reports = []

    print("╔══════════════════════════════════════════╗")
    print("║  Apify Crawl Auditor — Harness Mode      ║")
    print(f"║  Iterations: {max_iter}  |  Region: {region.upper():>3}          ║")
    print("╚══════════════════════════════════════════╝")

    for i in range(min(max_iter, len(layer_sequence))):
        layer = layer_sequence[i]
        print(f"\n{'━' * 60}")
        print(f"  ITERATION {i + 1}/{max_iter} — Layer: {layer.upper()}")
        print(f"{'━' * 60}")

        report = run_audit(layer=layer, region=region, iteration=i + 1)
        all_reports.append(report)

        # Print iteration summary
        h = report["health"]
        s = report["summary"]
        icon = "✓" if h == "PASS" else ("⚠" if h == "WARN" else "✗")
        print(f"\n  {icon} Iteration {i + 1} result: {h} "
              f"(C:{s['critical']} M:{s['major']} m:{s['minor']} i:{s['info']})")

    # Merge all findings
    merged_findings = []
    for r in all_reports:
        merged_findings.extend(r["findings"])

    crit = sum(1 for f in merged_findings if f["severity"] == "CRITICAL")
    major = sum(1 for f in merged_findings if f["severity"] == "MAJOR")
    minor = sum(1 for f in merged_findings if f["severity"] == "MINOR")
    info = sum(1 for f in merged_findings if f["severity"] == "INFO")

    if crit:
        final_health = "FAIL"
    elif major:
        final_health = "WARN"
    else:
        final_health = "PASS"

    final_report = {
        "timestamp": datetime.now().isoformat(),
        "mode": "harness",
        "iterations": max_iter,
        "region": region,
        "health": final_health,
        "summary": {
            "critical": crit, "major": major, "minor": minor, "info": info,
            "total": len(merged_findings),
        },
        "iteration_reports": all_reports,
        "findings": merged_findings,
    }

    # Save to file
    out_dir = PROJECT_ROOT / ".tmp" / "crawl_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"audit_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    # Final banner
    print(f"\n{'═' * 60}")
    print(f"  FINAL AUDIT REPORT — {final_health}")
    print(f"  CRITICAL: {crit}  |  MAJOR: {major}  |  MINOR: {minor}  |  INFO: {info}")
    print(f"{'═' * 60}")

    if crit or major:
        print("\n  Action items:")
        for f in merged_findings:
            if f["severity"] in ("CRITICAL", "MAJOR"):
                line = f"    {'✗' if f['severity'] == 'CRITICAL' else '⚠'} [{f['category']}] {f['description']}"
                if f.get("expected"):
                    line += f" (expected: {f['expected']}, got: {f['actual']})"
                print(line)

    print(f"\n  Report saved: {out_path}")
    return final_report


# ── CLI ───────────────────────────────────────────────────────────────────── #
def main():
    parser = argparse.ArgumentParser(description="Apify Crawl Auditor")
    parser.add_argument("--layer", choices=["infra", "data", "integrity"],
                        help="Audit specific layer only")
    parser.add_argument("--region", default="all", choices=["us", "jp", "all"])
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--harness", action="store_true",
                        help="Harness mode: 3-iteration loop")
    parser.add_argument("--max-iter", type=int, default=3,
                        help="Max iterations in harness mode")
    args = parser.parse_args()

    if args.harness:
        report = run_harness_loop(region=args.region, max_iter=args.max_iter)
    else:
        report = run_audit(layer=args.layer, region=args.region)
        build_report(as_json=False)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    # Exit code based on health
    if report["health"] == "FAIL":
        sys.exit(2)
    elif report["health"] == "WARN":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
