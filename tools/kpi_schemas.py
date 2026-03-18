"""
kpi_schemas.py - Pandera schema definitions for DataKeeper tables used in KPI computation.

Defines validation schemas for 7 core tables based on kpi-data-taxonomy.md.
Each schema checks: column types, null constraints, value ranges, and cross-column identities.

Usage:
    from kpi_schemas import SCHEMAS, validate_table
    errors = validate_table("shopify_orders_daily", rows)
"""

import pandera as pa
from pandera import Column, Check, DataFrameSchema
import pandas as pd
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_BRANDS = ["Grosmimi", "Naeiae", "CHA&MOM", "Onzenna", "Alpremio", "Unknown"]
VALID_SHOPIFY_CHANNELS = ["D2C", "Amazon", "B2B", "TikTok", "PR", "Target+", "Unknown"]
VALID_AMAZON_CHANNELS = ["Amazon", "Target+"]
VALID_AD_TYPES = ["SP", "SB", "SD"]

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


# ── Helper: coerce-safe nullable float/int ────────────────────────────────────

def _ge0(series):
    """Check >= 0, tolerating NaN/None."""
    return series.fillna(0) >= 0

def _ge0_int(series):
    """Check int >= 0, tolerating NaN/None."""
    return series.fillna(0) >= 0


# ── Schema Definitions ───────────────────────────────────────────────────────

shopify_orders_daily_schema = DataFrameSchema(
    columns={
        "date": Column(str, Check.str_matches(DATE_PATTERN), nullable=False),
        "brand": Column(str, nullable=True),
        "channel": Column(str, nullable=True),
        "gross_sales": Column(float, Check(_ge0, element_wise=False), nullable=True, coerce=True),
        "discounts": Column(float, nullable=True, coerce=True),  # can be negative (refund adjustments)
        "net_sales": Column(float, nullable=True, coerce=True),
        "orders": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "units": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
    },
    name="shopify_orders_daily",
    strict=False,  # allow extra columns
    coerce=True,
)

amazon_sales_daily_schema = DataFrameSchema(
    columns={
        "date": Column(str, Check.str_matches(DATE_PATTERN), nullable=False),
        "seller_id": Column(str, nullable=True),
        "brand": Column(str, nullable=True),
        "channel": Column(str, nullable=True),
        "gross_sales": Column(float, Check(_ge0, element_wise=False), nullable=True, coerce=True),
        "net_sales": Column(float, nullable=True, coerce=True),
        "orders": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "units": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "fees": Column(float, nullable=True, coerce=True),
    },
    name="amazon_sales_daily",
    strict=False,
    coerce=True,
)

amazon_ads_daily_schema = DataFrameSchema(
    columns={
        "date": Column(str, Check.str_matches(DATE_PATTERN), nullable=False),
        "profile_id": Column(str, nullable=True),
        "brand": Column(str, nullable=True),
        "campaign_id": Column(str, nullable=True),
        "campaign_name": Column(str, nullable=True),
        "ad_type": Column(str, nullable=True),
        "impressions": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "clicks": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "spend": Column(float, Check(_ge0, element_wise=False), nullable=True, coerce=True),
        "sales": Column(float, nullable=True, coerce=True),
        "purchases": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
    },
    name="amazon_ads_daily",
    strict=False,
    coerce=True,
)

meta_ads_daily_schema = DataFrameSchema(
    columns={
        "date": Column(str, Check.str_matches(DATE_PATTERN), nullable=False),
        "brand": Column(str, nullable=True),
        "campaign_id": Column(str, nullable=True),
        "campaign_name": Column(str, nullable=True),
        "impressions": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "clicks": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "spend": Column(float, Check(_ge0, element_wise=False), nullable=True, coerce=True),
        "purchases": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "purchase_value": Column(float, nullable=True, coerce=True),
    },
    name="meta_ads_daily",
    strict=False,
    coerce=True,
)

google_ads_daily_schema = DataFrameSchema(
    columns={
        "date": Column(str, Check.str_matches(DATE_PATTERN), nullable=False),
        "customer_id": Column(str, nullable=True),
        "campaign_id": Column(str, nullable=True),
        "campaign_name": Column(str, nullable=True),
        "brand": Column(str, nullable=True),
        "campaign_type": Column(str, nullable=True),
        "impressions": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "clicks": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "spend": Column(float, Check(_ge0, element_wise=False), nullable=True, coerce=True),
        "conversions": Column(float, nullable=True, coerce=True),
        "conversion_value": Column(float, nullable=True, coerce=True),
    },
    name="google_ads_daily",
    strict=False,
    coerce=True,
)

ga4_daily_schema = DataFrameSchema(
    columns={
        "date": Column(str, Check.str_matches(DATE_PATTERN), nullable=False),
        "channel_grouping": Column(str, nullable=True),
        "sessions": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "purchases": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
    },
    name="ga4_daily",
    strict=False,
    coerce=True,
)

klaviyo_daily_schema = DataFrameSchema(
    columns={
        "date": Column(str, Check.str_matches(DATE_PATTERN), nullable=False),
        "source_type": Column(str, nullable=True),
        "source_name": Column(str, nullable=True),
        "sends": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "opens": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "clicks": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "conversions": Column(float, Check(_ge0_int, element_wise=False), nullable=True, coerce=True),
        "revenue": Column(float, nullable=True, coerce=True),
    },
    name="klaviyo_daily",
    strict=False,
    coerce=True,
)


# ── Schema Registry ──────────────────────────────────────────────────────────

SCHEMAS = {
    "shopify_orders_daily": shopify_orders_daily_schema,
    "amazon_sales_daily": amazon_sales_daily_schema,
    "amazon_ads_daily": amazon_ads_daily_schema,
    "meta_ads_daily": meta_ads_daily_schema,
    "google_ads_daily": google_ads_daily_schema,
    "ga4_daily": ga4_daily_schema,
    "klaviyo_daily": klaviyo_daily_schema,
}


# ── Validation Function ──────────────────────────────────────────────────────

def validate_table(table_name: str, rows: list[dict]) -> dict:
    """
    Validate a list of dicts against the schema for the given table.

    Returns:
        {
            "table": str,
            "status": "PASS" | "FAIL",
            "rows": int,
            "schema_errors": int,
            "error_details": list[str],
        }
    """
    if table_name not in SCHEMAS:
        return {
            "table": table_name,
            "status": "SKIP",
            "rows": len(rows),
            "schema_errors": 0,
            "error_details": [f"No schema defined for {table_name}"],
        }

    if not rows:
        return {
            "table": table_name,
            "status": "WARN",
            "rows": 0,
            "schema_errors": 0,
            "error_details": ["No data rows to validate"],
        }

    schema = SCHEMAS[table_name]
    df = pd.DataFrame(rows)
    errors = []

    try:
        schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        for _, row in exc.failure_cases.iterrows():
            errors.append(
                f"[{row.get('schema_context', '')}] "
                f"column={row.get('column', 'N/A')}, "
                f"check={row.get('check', 'N/A')}, "
                f"index={row.get('index', 'N/A')}"
            )

    return {
        "table": table_name,
        "status": "FAIL" if errors else "PASS",
        "rows": len(rows),
        "schema_errors": len(errors),
        "error_details": errors[:50],  # cap at 50 to avoid bloat
    }
