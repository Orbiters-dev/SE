"""Data Keeper API views.

Endpoints:
  POST /api/datakeeper/save/           - Bulk upsert rows (any table)
  POST /api/datakeeper/delete/         - Delete rows by filter
  GET  /api/datakeeper/query/          - Query rows with filters
  GET  /api/datakeeper/tables/         - List available tables
  GET  /api/datakeeper/status/         - Latest collection timestamps
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import models as db_models

from . import models

# CORS: Allow GitHub Pages dashboard to fetch directly
CORS_ALLOWED_ORIGINS = [
    "https://orbiters-dev.github.io",
    "http://localhost",
    "http://127.0.0.1",
    "null",  # file:// protocol
]


def cors_headers(view_func):
    """Add CORS headers to allow cross-origin requests from dashboard."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Handle preflight OPTIONS
        if request.method == "OPTIONS":
            response = JsonResponse({})
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response["Access-Control-Max-Age"] = "86400"
            return response
        response = view_func(request, *args, **kwargs)
        # Force single CORS header (delete any nginx-added duplicates)
        try:
            del response["Access-Control-Allow-Origin"]
        except KeyError:
            pass
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    return wrapper

# Table name -> Model class mapping
TABLE_MAP = {
    "shopify_orders_daily": models.ShopifyOrdersDaily,
    "shopify_orders_sku_daily": models.ShopifyOrdersSkuDaily,
    "amazon_sales_daily": models.AmazonSalesDaily,
    "amazon_sales_sku_daily": models.AmazonSalesSkuDaily,
    "amazon_ads_daily": models.AmazonAdsDaily,
    "amazon_campaigns": models.AmazonCampaigns,
    "meta_ads_daily": models.MetaAdsDaily,
    "meta_campaigns": models.MetaCampaigns,
    "google_ads_daily": models.GoogleAdsDaily,
    "ga4_daily": models.GA4Daily,
    "klaviyo_daily": models.KlaviyoDaily,
    "gsc_daily": models.GscDaily,
    "dataforseo_keywords": models.DataForSeoKeywords,
    "amazon_ads_search_terms": models.AmazonAdsSearchTerms,
    "amazon_ads_keywords": models.AmazonAdsKeywords,
    "content_posts": models.ContentPosts,
    "content_metrics_daily": models.ContentMetricsDaily,
    "influencer_orders": models.InfluencerOrders,
    "amazon_brand_analytics": models.AmazonBrandAnalytics,
    "google_ads_search_terms": models.GoogleAdsSearchTerms,
}


def _get_unique_fields(model):
    """Extract unique_together fields from model Meta."""
    meta = model._meta
    # Check unique_together
    if meta.unique_together:
        return list(meta.unique_together[0])
    # Check unique fields
    unique = [f.name for f in meta.get_fields()
              if hasattr(f, "unique") and f.unique and f.name != "id"]
    return unique


def _coerce_value(field, value):
    """Coerce value to match Django field type."""
    if value is None:
        return None
    if isinstance(field, (db_models.DecimalField,)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal(0)
    if isinstance(field, (db_models.IntegerField,)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    if isinstance(field, (db_models.DateField,)):
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
    return value


@csrf_exempt
@require_http_methods(["POST"])
def save_rows(request):
    """Bulk upsert rows into a Data Keeper table.

    POST body:
    {
        "table": "amazon_ads_daily",
        "rows": [
            {"date": "2026-03-06", "campaign_id": "123", ...},
            ...
        ]
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    table_name = body.get("table", "")
    rows = body.get("rows", [])

    if table_name not in TABLE_MAP:
        return JsonResponse({
            "error": f"Unknown table: {table_name}",
            "available": list(TABLE_MAP.keys()),
        }, status=400)

    if not rows:
        return JsonResponse({"error": "No rows provided"}, status=400)

    model = TABLE_MAP[table_name]
    unique_fields = _get_unique_fields(model)
    field_map = {f.name: f for f in model._meta.get_fields()
                 if hasattr(f, "column")}

    created = 0
    updated = 0
    errors = []

    for i, row in enumerate(rows):
        try:
            # Build lookup dict from unique fields
            lookup = {}
            for uf in unique_fields:
                if uf not in row:
                    raise ValueError(f"Missing unique field: {uf}")
                lookup[uf] = _coerce_value(field_map.get(uf), row[uf])

            # Build defaults dict from remaining fields
            defaults = {}
            for key, val in row.items():
                if key in unique_fields or key == "id":
                    continue
                if key in field_map:
                    defaults[key] = _coerce_value(field_map[key], val)

            obj, was_created = model.objects.update_or_create(
                **lookup, defaults=defaults
            )
            if was_created:
                created += 1
            else:
                updated += 1

        except Exception as e:
            errors.append({"row": i, "error": str(e)})
            if len(errors) > 10:
                errors.append({"row": "...", "error": "Too many errors, stopping"})
                break

    return JsonResponse({
        "table": table_name,
        "created": created,
        "updated": updated,
        "total": len(rows),
        "errors": errors,
    })


@csrf_exempt
@require_http_methods(["POST"])
def delete_rows(request):
    """Delete rows from a Data Keeper table by field filters.

    POST body:
    {
        "table": "content_posts",
        "filters": {"username__in": ["grosmimi_usa", "baby.boutique.kh"]}
    }
    Supported lookups: field=value, field__in=[...], field__contains=value
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    table_name = body.get("table", "")
    filters = body.get("filters", {})

    if table_name not in TABLE_MAP:
        return JsonResponse({
            "error": f"Unknown table: {table_name}",
            "available": list(TABLE_MAP.keys()),
        }, status=400)

    if not filters:
        return JsonResponse({"error": "Filters required (safety)"}, status=400)

    model = TABLE_MAP[table_name]
    qs = model.objects.filter(**filters)
    count = qs.count()
    qs.delete()

    return JsonResponse({
        "table": table_name,
        "deleted": count,
        "filters": filters,
    })


@csrf_exempt
@cors_headers
@require_http_methods(["GET", "OPTIONS"])
def query_rows(request):
    """Query rows from a Data Keeper table.

    GET /api/datakeeper/query/?table=amazon_ads_daily&date_from=2026-03-01&date_to=2026-03-06&brand=CHA%26MOM&limit=1000

    Supported filters: date_from, date_to, brand, campaign_id, channel, ad_id, source_type
    """
    table_name = request.GET.get("table", "")
    if table_name not in TABLE_MAP:
        return JsonResponse({
            "error": f"Unknown table: {table_name}",
            "available": list(TABLE_MAP.keys()),
        }, status=400)

    model = TABLE_MAP[table_name]
    qs = model.objects.all()

    # Apply filters
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    brand = request.GET.get("brand")
    campaign_id = request.GET.get("campaign_id")
    channel = request.GET.get("channel")
    ad_id = request.GET.get("ad_id")
    source_type = request.GET.get("source_type")

    field_names = [f.name for f in model._meta.get_fields() if hasattr(f, "column")]

    if date_from and "date" in field_names:
        qs = qs.filter(date__gte=date_from)
    if date_to and "date" in field_names:
        qs = qs.filter(date__lte=date_to)
    if brand and "brand" in field_names:
        qs = qs.filter(brand=brand)
    if campaign_id and "campaign_id" in field_names:
        qs = qs.filter(campaign_id=campaign_id)
    if channel and "channel" in field_names:
        qs = qs.filter(channel=channel)
    if ad_id and "ad_id" in field_names:
        qs = qs.filter(ad_id=ad_id)
    if source_type and "source_type" in field_names:
        qs = qs.filter(source_type=source_type)

    username = request.GET.get("username")
    if username and "username" in field_names:
        qs = qs.filter(username__iexact=username)

    # Order by date desc if available
    if "date" in field_names:
        qs = qs.order_by("-date")

    limit = min(int(request.GET.get("limit", 5000)), 10000)
    qs = qs[:limit]

    # Serialize
    rows = []
    for obj in qs:
        row = {}
        for fname in field_names:
            val = getattr(obj, fname)
            if isinstance(val, Decimal):
                val = float(val)
            elif isinstance(val, datetime):
                val = val.isoformat()
            elif hasattr(val, "isoformat"):
                val = val.isoformat()
            row[fname] = val
        rows.append(row)

    return JsonResponse({
        "table": table_name,
        "count": len(rows),
        "rows": rows,
    })


@csrf_exempt
@cors_headers
@require_http_methods(["GET", "OPTIONS"])
def list_tables(request):
    """List all available Data Keeper tables with row counts."""
    result = {}
    for name, model in TABLE_MAP.items():
        result[name] = {
            "count": model.objects.count(),
            "unique_fields": _get_unique_fields(model),
        }
    return JsonResponse({"tables": result})


def _safe_iso(val):
    """Convert date/datetime to ISO string, handling already-string values."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return val.isoformat()


@csrf_exempt
@cors_headers
@require_http_methods(["GET", "OPTIONS"])
def status(request):
    """Get latest collection timestamps per table."""
    result = {}
    for name, model in TABLE_MAP.items():
        try:
            field_names = [f.name for f in model._meta.get_fields()
                           if hasattr(f, "column")]
            info = {"count": model.objects.count()}
            if "collected_at" in field_names:
                latest = model.objects.order_by("-collected_at").first()
                info["latest_collected"] = (
                    _safe_iso(latest.collected_at) if latest else None
                )
            if "date" in field_names:
                latest = model.objects.order_by("-date").first()
                info["latest_date"] = (
                    _safe_iso(latest.date) if latest else None
                )
            result[name] = info
        except Exception as e:
            result[name] = {"error": str(e)}
    return JsonResponse({"status": result})
