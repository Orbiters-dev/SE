"""
kpi_validator.py - 검증이: KPI data validation pipeline.

Validates DataKeeper data through 6 layers before KPI report generation.
Part of 골만이 Squad (validator role).

Layers:
  L1 Schema    - Pandera schema validation (types, nulls, ranges)
  L2 Identity  - Revenue identity: gross - disc = net
  L3 Coverage  - Brand/channel coverage completeness
  L4 Through   - Through-date consistency across tables
  L5 CrossTab  - Cross-table reconciliation (Amazon Shopify vs SP-API)
  L6 Anomaly   - MoM/IQR anomaly detection with seasonal adjustment

Usage:
    python tools/kpi_validator.py                              # Validate all
    python tools/kpi_validator.py --table shopify_orders_daily  # Single table
    python tools/kpi_validator.py --report-only                # JSON report, no exit code
    python tools/kpi_validator.py --days 90                    # Custom lookback

Output:
    .tmp/validation_report.json
    Console: pass/fail summary
"""

import os
import sys
import json
import argparse
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from env_loader import load_env
load_env()

# ── Constants ─────────────────────────────────────────────────────────────────

EXPECTED_BRANDS = ["Grosmimi", "Naeiae", "CHA&MOM", "Onzenna", "Alpremio"]
EXPECTED_SHOPIFY_CHANNELS = ["D2C", "Amazon", "B2B"]
EXPECTED_AMAZON_BRANDS = ["Grosmimi", "Naeiae", "CHA&MOM"]

# Tables to validate (core KPI tables)
CORE_TABLES = [
    "shopify_orders_daily",
    "amazon_sales_daily",
    "amazon_ads_daily",
    "meta_ads_daily",
    "google_ads_daily",
    "ga4_daily",
    "klaviyo_daily",
]

# Data availability start dates (from kpi-data-taxonomy.md section 6)
DATA_START = {
    "shopify_orders_daily": "2024-01",
    "amazon_sales_daily": "2024-01",
    "amazon_ads_daily": "2025-12",
    "meta_ads_daily": "2024-08",
    "google_ads_daily": "2024-01",
    "ga4_daily": "2024-01",
    "klaviyo_daily": "2024-01",
}


# ── Data Loading ──────────────────────────────────────────────────────────────

def load_dk(table: str, days: int = 800) -> list[dict]:
    from data_keeper_client import DataKeeper
    dk = DataKeeper(prefer_cache=False)
    return dk.get(table, days=days)


def compute_through_date() -> str:
    """Consistent through-date = min of latest full day across main channels (PST)."""
    PST = timezone(timedelta(hours=-8))
    yesterday_pst = (datetime.now(PST).date() - timedelta(days=1)).isoformat()

    main_tables = ["shopify_orders_daily", "amazon_ads_daily", "meta_ads_daily", "google_ads_daily"]
    latest = []
    for t in main_tables:
        try:
            rows = load_dk(t, days=30)
            dates = [r.get("date", "") for r in rows if r.get("date")]
            if dates:
                latest.append(max(dates))
        except Exception:
            pass

    through = min(latest) if latest else yesterday_pst
    return min(through, yesterday_pst)


# ── L1: Schema Validation ────────────────────────────────────────────────────

def validate_schema(table: str, rows: list[dict]) -> dict:
    """Run pandera schema validation."""
    from kpi_schemas import validate_table
    return validate_table(table, rows)


# ── L2: Identity Check ───────────────────────────────────────────────────────

def validate_identity(table: str, rows: list[dict]) -> dict:
    """Check revenue identity: gross_sales - discounts ≈ net_sales."""
    if table not in ("shopify_orders_daily",):
        return {"check": "identity", "status": "SKIP", "errors": 0, "details": []}

    errors = []
    for i, r in enumerate(rows):
        gross = float(r.get("gross_sales", 0) or 0)
        disc = float(r.get("discounts", 0) or 0)
        net = float(r.get("net_sales", 0) or 0)
        diff = abs(gross - disc - net)
        if diff > 0.02:
            errors.append(
                f"Row {i}: date={r.get('date')}, brand={r.get('brand')}, "
                f"gross={gross:.2f} - disc={disc:.2f} != net={net:.2f} (diff={diff:.2f})"
            )
            if len(errors) >= 20:
                errors.append(f"... and more (capped at 20)")
                break

    return {
        "check": "identity",
        "status": "FAIL" if errors else "PASS",
        "errors": len(errors),
        "details": errors,
    }


# ── L3: Coverage Check ───────────────────────────────────────────────────────

def validate_coverage(table: str, rows: list[dict]) -> dict:
    """Check if all expected brands/channels are present."""
    if not rows:
        return {"check": "coverage", "status": "WARN", "warnings": ["No data"]}

    warnings = []

    if table == "shopify_orders_daily":
        found_brands = set(r.get("brand", "") for r in rows)
        missing_brands = [b for b in EXPECTED_BRANDS if b not in found_brands]
        if missing_brands:
            warnings.append(f"Missing brands: {missing_brands}")

        found_channels = set(r.get("channel", "") for r in rows)
        missing_channels = [c for c in EXPECTED_SHOPIFY_CHANNELS if c not in found_channels]
        if missing_channels:
            warnings.append(f"Missing channels: {missing_channels}")

    elif table == "amazon_sales_daily":
        found_brands = set(r.get("brand", "") for r in rows)
        missing = [b for b in EXPECTED_AMAZON_BRANDS if b not in found_brands]
        if missing:
            warnings.append(f"Missing Amazon brands: {missing}")

    elif table in ("amazon_ads_daily", "meta_ads_daily", "google_ads_daily"):
        found_brands = set(r.get("brand", "") for r in rows if r.get("brand"))
        if not found_brands:
            warnings.append("No brands detected in ad data")

    return {
        "check": "coverage",
        "status": "WARN" if warnings else "PASS",
        "warnings": warnings,
    }


# ── L4: Through-Date Consistency ──────────────────────────────────────────────

def validate_through_date(all_data: dict[str, list[dict]], through_date: str) -> dict:
    """Check that all tables have data up to through_date."""
    warnings = []

    for table, rows in all_data.items():
        if not rows:
            warnings.append(f"{table}: NO DATA")
            continue

        dates = [r.get("date", "") for r in rows if r.get("date")]
        if not dates:
            warnings.append(f"{table}: no date column found")
            continue

        max_date = max(dates)
        # Check gap
        try:
            max_dt = datetime.strptime(max_date, "%Y-%m-%d").date()
            through_dt = datetime.strptime(through_date, "%Y-%m-%d").date()
            gap_days = (through_dt - max_dt).days
            if gap_days > 2:
                warnings.append(f"{table}: latest={max_date}, through={through_date}, gap={gap_days}d")
        except ValueError:
            warnings.append(f"{table}: cannot parse date {max_date}")

    return {
        "check": "through_date",
        "through_date": through_date,
        "status": "WARN" if warnings else "PASS",
        "warnings": warnings,
    }


# ── L5: Cross-Table Reconciliation ───────────────────────────────────────────

def validate_cross_table(all_data: dict[str, list[dict]]) -> dict:
    """
    Cross-table checks:
    1. Amazon in Shopify vs Amazon in SP-API (SP-API should be larger)
    2. Discount rate sanity (0-50%)
    """
    warnings = []

    # 1. Amazon reconciliation
    shopify_rows = all_data.get("shopify_orders_daily", [])
    amazon_rows = all_data.get("amazon_sales_daily", [])

    shopify_amz_rev = sum(
        float(r.get("net_sales", 0) or 0)
        for r in shopify_rows
        if r.get("channel") == "Amazon"
    )
    spapi_rev = sum(float(r.get("net_sales", 0) or 0) for r in amazon_rows)

    if shopify_amz_rev > 0 and spapi_rev > 0:
        if shopify_amz_rev > spapi_rev * 1.1:  # Shopify Amazon > SP-API by 10%+
            warnings.append(
                f"Amazon reconciliation: Shopify Amazon (${shopify_amz_rev:,.0f}) > "
                f"SP-API (${spapi_rev:,.0f}). FBA MCF misclassification?"
            )

    # 2. Discount rate sanity
    for r in shopify_rows:
        gross = float(r.get("gross_sales", 0) or 0)
        disc = float(r.get("discounts", 0) or 0)
        if gross > 0:
            disc_rate = disc / gross
            if disc_rate > 0.50:
                date = r.get("date", "?")
                brand = r.get("brand", "?")
                ch = r.get("channel", "?")
                warnings.append(
                    f"High discount rate {disc_rate:.0%}: date={date}, brand={brand}, channel={ch}"
                )
                if len(warnings) > 30:
                    break

    return {
        "check": "cross_table",
        "status": "WARN" if warnings else "PASS",
        "warnings": warnings[:20],
    }


# ── L6: Anomaly Detection ────────────────────────────────────────────────────

def validate_anomalies(all_data: dict[str, list[dict]]) -> dict:
    """Run anomaly detection on key monthly aggregates."""
    from kpi_anomaly import detect_mom_anomalies, check_spend_sanity

    all_anomalies = []
    all_spend_warnings = []

    # Aggregate monthly spend by platform
    platform_map = {
        "amazon_ads_daily": "amazon_ads",
        "meta_ads_daily": "meta_ads",
        "google_ads_daily": "google_ads",
    }

    for table, platform_key in platform_map.items():
        rows = all_data.get(table, [])
        monthly_spend = defaultdict(float)
        for r in rows:
            month = r.get("date", "")[:7]
            if month:
                monthly_spend[month] += float(r.get("spend", 0) or 0)

        if monthly_spend:
            # MoM anomalies
            anomalies = detect_mom_anomalies(
                dict(monthly_spend),
                metric_name=f"{platform_key}_spend",
            )
            all_anomalies.extend(anomalies)

            # Spend range check
            spend_warns = check_spend_sanity(dict(monthly_spend), platform_key)
            all_spend_warnings.extend(spend_warns)

    # Revenue MoM anomalies
    shopify_rows = all_data.get("shopify_orders_daily", [])
    monthly_rev = defaultdict(float)
    for r in shopify_rows:
        month = r.get("date", "")[:7]
        if month:
            monthly_rev[month] += float(r.get("net_sales", 0) or 0)

    if monthly_rev:
        rev_anomalies = detect_mom_anomalies(
            dict(monthly_rev),
            metric_name="shopify_net_revenue",
        )
        all_anomalies.extend(rev_anomalies)

    return {
        "check": "anomaly",
        "status": "WARN" if (all_anomalies or all_spend_warnings) else "PASS",
        "anomalies": all_anomalies,
        "spend_warnings": all_spend_warnings,
    }


# ── Main Orchestrator ─────────────────────────────────────────────────────────

def validate_all(
    tables: list[str] | None = None,
    days: int = 800,
    report_only: bool = False,
) -> dict:
    """
    Run all validation layers.

    Returns:
        Full validation report dict.
    """
    PST = timezone(timedelta(hours=-8))
    now_pst = datetime.now(PST)

    tables_to_check = tables or CORE_TABLES
    all_data: dict[str, list[dict]] = {}
    table_results = {}

    print(f"\n{'='*60}")
    print(f"  검증이 (KPI Validator) - {now_pst.strftime('%Y-%m-%d %H:%M PST')}")
    print(f"{'='*60}\n")

    # Load data
    for table in tables_to_check:
        print(f"  Loading {table}...", end=" ", flush=True)
        try:
            rows = load_dk(table, days=days)
            all_data[table] = rows
            print(f"{len(rows)} rows")
        except Exception as e:
            all_data[table] = []
            print(f"FAILED: {e}")

    # Through-date
    through_date = compute_through_date()
    print(f"\n  Through-date: {through_date}\n")

    # Run validations per table
    for table in tables_to_check:
        rows = all_data.get(table, [])
        print(f"  Validating {table}...")

        # L1: Schema
        schema_result = validate_schema(table, rows)
        status_icon = {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "-"}
        print(f"    [{status_icon.get(schema_result['status'], '?')}] L1 Schema: {schema_result['status']} ({schema_result.get('schema_errors', 0)} errors)")

        # L2: Identity
        identity_result = validate_identity(table, rows)
        print(f"    [{status_icon.get(identity_result['status'], '?')}] L2 Identity: {identity_result['status']} ({identity_result.get('errors', 0)} errors)")

        # L3: Coverage
        coverage_result = validate_coverage(table, rows)
        print(f"    [{status_icon.get(coverage_result['status'], '?')}] L3 Coverage: {coverage_result['status']}")
        for w in coverage_result.get("warnings", []):
            print(f"        {w}")

        table_results[table] = {
            "rows": len(rows),
            "schema": schema_result,
            "identity": identity_result,
            "coverage": coverage_result,
        }

    # L4: Through-date
    print(f"\n  Cross-table checks...")
    through_result = validate_through_date(all_data, through_date)
    print(f"    [{status_icon.get(through_result['status'], '?')}] L4 Through-date: {through_result['status']}")
    for w in through_result.get("warnings", []):
        print(f"        {w}")

    # L5: Cross-table
    cross_result = validate_cross_table(all_data)
    print(f"    [{status_icon.get(cross_result['status'], '?')}] L5 Cross-table: {cross_result['status']}")
    for w in cross_result.get("warnings", [])[:5]:
        print(f"        {w}")

    # L6: Anomaly
    anomaly_result = validate_anomalies(all_data)
    n_anomalies = len(anomaly_result.get("anomalies", []))
    n_spend = len(anomaly_result.get("spend_warnings", []))
    print(f"    [{status_icon.get(anomaly_result['status'], '?')}] L6 Anomaly: {anomaly_result['status']} ({n_anomalies} anomalies, {n_spend} spend warnings)")
    for a in anomaly_result.get("anomalies", [])[:5]:
        print(f"        {a['metric']}: {a['month']} MoM {a['mom_change']:+.1f}%")
    for w in anomaly_result.get("spend_warnings", [])[:5]:
        print(f"        {w['metric']}: {w['month']} ${w['value']:,.0f} ({w['type']})")

    # Overall status
    has_fail = any(
        tr["schema"]["status"] == "FAIL" or tr["identity"]["status"] == "FAIL"
        for tr in table_results.values()
    )
    has_warn = (
        through_result["status"] == "WARN"
        or cross_result["status"] == "WARN"
        or anomaly_result["status"] == "WARN"
        or any(tr["coverage"]["status"] == "WARN" for tr in table_results.values())
    )

    overall = "FAIL" if has_fail else ("WARN" if has_warn else "PASS")

    report = {
        "timestamp": now_pst.isoformat(),
        "through_date": through_date,
        "tables_validated": len(tables_to_check),
        "total_rows": sum(len(all_data.get(t, [])) for t in tables_to_check),
        "overall_status": overall,
        "table_results": table_results,
        "cross_table": {
            "through_date": through_result,
            "reconciliation": cross_result,
            "anomalies": anomaly_result,
        },
    }

    # Summary
    print(f"\n{'='*60}")
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}
    print(f"  Overall: {icon.get(overall, overall)}")
    print(f"  Tables: {len(tables_to_check)}, Total rows: {report['total_rows']:,}")
    print(f"{'='*60}\n")

    # Save report
    output_dir = TOOLS_DIR.parent / ".tmp"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Report saved: {report_path}\n")

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="검증이: KPI Data Validator")
    parser.add_argument("--table", type=str, help="Validate single table")
    parser.add_argument("--days", type=int, default=800, help="Lookback days (default 800)")
    parser.add_argument("--report-only", action="store_true", help="No exit code on failure")
    args = parser.parse_args()

    tables = [args.table] if args.table else None
    report = validate_all(tables=tables, days=args.days, report_only=args.report_only)

    if not args.report_only and report["overall_status"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
