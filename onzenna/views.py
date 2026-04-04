import json
import uuid
from datetime import datetime
from decimal import Decimal

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# CORS origins allowed for GH Pages dashboards
_CORS_ORIGINS = (
    'https://orbiters-dev.github.io',
)


def _cors_headers(request, response):
    """Add CORS headers if origin matches allowed list."""
    origin = request.META.get('HTTP_ORIGIN', '')
    if origin in _CORS_ORIGINS:
        response['Access-Control-Allow-Origin'] = origin
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response['Access-Control-Max-Age'] = '86400'
    return response

from .models import (
    OnzUser,
    OnzOnboarding,
    OnzEngagementEvent,
    OnzRecommendationCache,
    OnzLoyaltySurvey,
    OnzCreatorProfile,
    OnzGiftingApplication,
    OnzInfluencerOutreach,
    GmailContact,
    PipelineConfig,
    PipelineCreator,
    PipelineExecutionLog,
    PipelineStatusChange,
    EmailReplyConfig,
    FAQEntry,
    EmailReplyLog,
)


def _json_body(request):
    """Parse JSON body from request."""
    return json.loads(request.body.decode("utf-8"))


def _serialize(obj):
    """Convert model instance to dict."""
    data = {}
    for field in obj._meta.fields:
        val = getattr(obj, field.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        elif isinstance(val, Decimal):
            val = float(val)
        data[field.name] = val
    # Deserialize JSON text fields
    for key in ("interests", "concerns", "purchase_factors", "discovery_channels",
                "content_preferences", "support_network", "shopping_categories",
                "other_channels", "content_types", "product_handles", "post_slugs"):
        if key in data and isinstance(data[key], str):
            try:
                data[key] = json.loads(data[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return data


def _parse_date(val):
    """Parse date string to date object."""
    if not val:
        return None
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
    return None


def _json_field(val):
    """Convert list/dict to JSON string for TextField storage."""
    if isinstance(val, (list, dict)):
        return json.dumps(val)
    if isinstance(val, str):
        return val
    return "[]"


# --- Users ---


@csrf_exempt
@require_http_methods(["POST"])
def create_user(request):
    """Create or update user profile (upsert by id or email)."""
    body = _json_body(request)
    user_id = body.get("id")
    email = body.get("email")

    if not email:
        return JsonResponse({"error": "email is required"}, status=400)

    defaults = {
        "full_name": body.get("full_name", ""),
        "pregnancy_stage": body.get("pregnancy_stage", ""),
        "auth_provider": body.get("auth_provider", "email"),
        "interests": _json_field(body.get("interests", [])),
    }
    if body.get("baby_dob"):
        defaults["baby_dob"] = _parse_date(body["baby_dob"])
    if body.get("shopify_customer_id"):
        defaults["shopify_customer_id"] = body["shopify_customer_id"]

    if user_id:
        user, created = OnzUser.objects.update_or_create(
            id=user_id, defaults={**defaults, "email": email}
        )
    else:
        user, created = OnzUser.objects.update_or_create(
            email=email, defaults=defaults
        )

    return JsonResponse(_serialize(user), status=201 if created else 200)


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def get_or_update_user(request, user_id):
    """Get or update user profile by ID."""
    try:
        user = OnzUser.objects.get(id=user_id)
    except OnzUser.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    if request.method == "PUT":
        body = _json_body(request)
        for field in ("full_name", "pregnancy_stage", "auth_provider", "shopify_customer_id"):
            if field in body:
                setattr(user, field, body[field])
        if "baby_dob" in body:
            user.baby_dob = _parse_date(body["baby_dob"])
        if "interests" in body:
            user.interests = _json_field(body["interests"])
        if "klaviyo_synced" in body:
            user.klaviyo_synced = body["klaviyo_synced"]
        user.save()

    return JsonResponse(_serialize(user))


# --- Onboarding ---


@csrf_exempt
@require_http_methods(["POST"])
def save_onboarding(request):
    """Save or update onboarding data."""
    body = _json_body(request)
    user_id = body.get("user_id")
    if not user_id:
        return JsonResponse({"error": "user_id is required"}, status=400)

    try:
        user = OnzUser.objects.get(id=user_id)
    except OnzUser.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    defaults = {
        "journey_stage": body.get("journey_stage", ""),
        "has_other_children": body.get("has_other_children", False),
        "other_children_count": body.get("other_children_count", ""),
        "concerns": _json_field(body.get("concerns", [])),
        "purchase_frequency": body.get("purchase_frequency", ""),
    }
    if body.get("baby_birthday"):
        defaults["baby_birthday"] = _parse_date(body["baby_birthday"])

    ob, created = OnzOnboarding.objects.update_or_create(user=user, defaults=defaults)
    return JsonResponse(_serialize(ob), status=201 if created else 200)


@csrf_exempt
@require_http_methods(["GET"])
def get_onboarding(request, user_id):
    """Get onboarding data for a user."""
    try:
        ob = OnzOnboarding.objects.get(user_id=user_id)
    except OnzOnboarding.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse(_serialize(ob))


# --- Engagement Events ---


@csrf_exempt
@require_http_methods(["POST"])
def log_engagement(request):
    """Log a user engagement event."""
    body = _json_body(request)
    user_id = body.get("user_id")
    action = body.get("action")
    resource_type = body.get("resource_type")
    resource_id = body.get("resource_id")

    if not all([user_id, action, resource_type, resource_id]):
        return JsonResponse({"error": "user_id, action, resource_type, resource_id required"}, status=400)

    event = OnzEngagementEvent.objects.create(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return JsonResponse(_serialize(event), status=201)


@csrf_exempt
@require_http_methods(["GET"])
def get_engagement(request, user_id):
    """Get recent engagement events for a user."""
    limit = int(request.GET.get("limit", 10))
    events = OnzEngagementEvent.objects.filter(user_id=user_id)[:limit]
    return JsonResponse([_serialize(e) for e in events], safe=False)


# --- Recommendation Cache ---


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def get_or_update_recommendations(request, user_id):
    """Get or upsert recommendation cache."""
    if request.method == "PUT":
        body = _json_body(request)
        rec, created = OnzRecommendationCache.objects.update_or_create(
            user_id=user_id,
            defaults={
                "product_handles": _json_field(body.get("product_handles", [])),
                "post_slugs": _json_field(body.get("post_slugs", [])),
            },
        )
        return JsonResponse(_serialize(rec), status=201 if created else 200)

    # GET
    try:
        rec = OnzRecommendationCache.objects.get(user_id=user_id)
    except OnzRecommendationCache.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse(_serialize(rec))


# --- Loyalty Survey ---


@csrf_exempt
@require_http_methods(["POST"])
def save_loyalty_survey(request):
    """Save loyalty survey responses."""
    body = _json_body(request)
    user_id = body.get("user_id")
    if not user_id:
        return JsonResponse({"error": "user_id is required"}, status=400)

    defaults = {
        "purchase_factors": _json_field(body.get("purchase_factors", [])),
        "discovery_channels": _json_field(body.get("discovery_channels", [])),
        "content_preferences": _json_field(body.get("content_preferences", [])),
        "sms_opt_in": body.get("sms_opt_in", False),
        "routine_type": body.get("routine_type", ""),
        "feeding_method": body.get("feeding_method", ""),
        "support_network": _json_field(body.get("support_network", [])),
        "shopping_categories": _json_field(body.get("shopping_categories", [])),
        "discount_code": body.get("discount_code", ""),
    }

    survey, created = OnzLoyaltySurvey.objects.update_or_create(
        user_id=user_id, defaults=defaults
    )
    return JsonResponse(_serialize(survey), status=201 if created else 200)


# --- Creator Survey ---


@csrf_exempt
@require_http_methods(["POST"])
def save_creator_survey(request):
    """Save creator/influencer profile data."""
    body = _json_body(request)
    user_id = body.get("user_id")
    if not user_id:
        return JsonResponse({"error": "user_id is required"}, status=400)

    defaults = {
        "creator_level": body.get("creator_level", ""),
        "primary_platform": body.get("primary_platform", ""),
        "primary_handle": body.get("primary_handle", ""),
        "other_channels": _json_field(body.get("other_channels", [])),
        "following_size": body.get("following_size", ""),
        "content_types": _json_field(body.get("content_types", [])),
        "has_brand_deals": body.get("has_brand_deals"),
    }

    profile, created = OnzCreatorProfile.objects.update_or_create(
        user_id=user_id, defaults=defaults
    )
    return JsonResponse(_serialize(profile), status=201 if created else 200)


# --- Status ---


@csrf_exempt
@require_http_methods(["GET"])
def get_status(request, user_id):
    """Get completion status for all onboarding stages."""
    try:
        user = OnzUser.objects.get(id=user_id)
    except OnzUser.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({
        "user_id": str(user.id),
        "has_profile": True,
        "has_onboarding": OnzOnboarding.objects.filter(user=user).exists(),
        "has_loyalty_survey": OnzLoyaltySurvey.objects.filter(user=user).exists(),
        "has_creator_profile": OnzCreatorProfile.objects.filter(user=user).exists(),
        "engagement_count": OnzEngagementEvent.objects.filter(user=user).count(),
        "has_recommendations": OnzRecommendationCache.objects.filter(user=user).exists(),
    })


# --- Gifting Applications ---


@csrf_exempt
@require_http_methods(["POST"])
def save_gifting(request):
    """Save or update a gifting application (upsert by email + draft_order)."""
    body = _json_body(request)
    email = body.get("email", "").strip().lower()
    if not email:
        return JsonResponse({"error": "email is required"}, status=400)

    # Parse nested structures from n8n payload (supports both nested and flat formats)
    personal = body.get("personal_info", {})
    baby = body.get("baby_info", {})
    addr = body.get("shipping_address", {})
    child_1 = baby.get("child_1") or {}
    child_2 = baby.get("child_2") or {}

    defaults = {
        "full_name": body.get("full_name") or personal.get("full_name", ""),
        "phone": body.get("phone") or personal.get("phone", ""),
        "instagram": body.get("instagram") or personal.get("instagram", ""),
        "tiktok": body.get("tiktok") or personal.get("tiktok", ""),
        "child_1_birthday": _parse_date(child_1.get("birthday") or body.get("child_1_birthday")),
        "child_1_age_months": child_1.get("age_months") or body.get("child_1_age_months"),
        "child_2_birthday": _parse_date(child_2.get("birthday") or body.get("child_2_birthday")),
        "child_2_age_months": child_2.get("age_months") or body.get("child_2_age_months"),
        "selected_products": _json_field(body.get("selected_products", [])),
        "address_street": addr.get("street", "") or body.get("street", ""),
        "address_apt": addr.get("apt", "") or body.get("apt", ""),
        "address_city": addr.get("city", "") or body.get("city", ""),
        "address_state": addr.get("state", "") or body.get("state", ""),
        "address_zip": addr.get("zip", "") or body.get("zip", ""),
        "address_country": addr.get("country", "US") or body.get("country", "US"),
        "shopify_customer_id": str(body.get("shopify_customer_id") or ""),
    }

    # Optional fields that may come from n8n after draft order creation
    if body.get("shopify_draft_order_id"):
        defaults["shopify_draft_order_id"] = str(body["shopify_draft_order_id"])
    if body.get("shopify_draft_order_name"):
        defaults["shopify_draft_order_name"] = body["shopify_draft_order_name"]
    if body.get("airtable_record_id"):
        defaults["airtable_record_id"] = body["airtable_record_id"]
    if body.get("status"):
        defaults["status"] = body["status"]
    if body.get("submitted_at"):
        try:
            defaults["submitted_at"] = datetime.fromisoformat(
                body["submitted_at"].replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            pass

    # Upsert: match by email. If draft_order_id given, use that for more precise match.
    draft_id = defaults.get("shopify_draft_order_id", "")
    if draft_id:
        app, created = OnzGiftingApplication.objects.update_or_create(
            email=email, shopify_draft_order_id=draft_id,
            defaults=defaults,
        )
    else:
        app, created = OnzGiftingApplication.objects.update_or_create(
            email=email, status="submitted",
            defaults=defaults,
        )

    return JsonResponse(_serialize(app), status=201 if created else 200)


@csrf_exempt
@require_http_methods(["POST"])
def update_gifting(request):
    """Update gifting application fields (from Airtable sync, status changes, etc.)."""
    body = _json_body(request)
    app_id = body.get("id")
    email = body.get("email", "").strip().lower()

    if not app_id and not email:
        return JsonResponse({"error": "id or email required"}, status=400)

    try:
        if app_id:
            app = OnzGiftingApplication.objects.get(id=app_id)
        else:
            app = OnzGiftingApplication.objects.filter(email=email).order_by("-created_at").first()
            if not app:
                return JsonResponse({"error": "Not found"}, status=404)
    except OnzGiftingApplication.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    # Update allowed fields
    for field in ("status", "airtable_record_id", "shopify_draft_order_id",
                  "shopify_draft_order_name", "shopify_customer_id",
                  "instagram", "tiktok"):
        if field in body:
            setattr(app, field, body[field])
    app.save()

    return JsonResponse(_serialize(app))


@csrf_exempt
@require_http_methods(["GET"])
def list_gifting(request):
    """List gifting applications with optional filters."""
    qs = OnzGiftingApplication.objects.all()

    # Filters
    email = request.GET.get("email")
    status = request.GET.get("status")
    if email:
        qs = qs.filter(email=email.lower())
    if status:
        qs = qs.filter(status=status)

    limit = int(request.GET.get("limit", 50))
    apps = qs[:limit]

    return JsonResponse([_serialize(a) for a in apps], safe=False)


# --- Influencer Outreach (Outbound / Pathlight pipeline) ---


@csrf_exempt
@require_http_methods(["POST"])
def save_outreach(request):
    """Upsert an outbound influencer outreach record (Pathlight pipeline).
    Separate from inbound gifting applications.
    Upsert key: airtable_record_id (if given), else email.
    """
    body = _json_body(request)
    email = body.get("email", "").strip().lower()
    airtable_record_id = body.get("airtable_record_id", "").strip()

    if not email and not airtable_record_id:
        return JsonResponse({"error": "email or airtable_record_id required"}, status=400)

    defaults = {
        "email": email,
        "ig_handle": body.get("ig_handle", body.get("instagram", "")),
        "tiktok_handle": body.get("tiktok_handle", body.get("tiktok", "")),
        "platform": body.get("platform", ""),
        "full_name": body.get("full_name", ""),
        "outreach_type": body.get("outreach_type", ""),
        "outreach_status": body.get("outreach_status", "Not Started"),
        "airtable_base_id": body.get("airtable_base_id", ""),
        "airtable_conversation_id": body.get("airtable_conversation_id", ""),
        "source": body.get("source", "pathlight_outbound"),
        "environment": body.get("environment", "wj_test"),
    }
    for field in ("shopify_customer_id", "shopify_draft_order_id", "shopify_draft_order_name"):
        if body.get(field):
            defaults[field] = str(body[field])

    if airtable_record_id:
        obj, created = OnzInfluencerOutreach.objects.update_or_create(
            airtable_record_id=airtable_record_id, defaults=defaults
        )
    else:
        obj, created = OnzInfluencerOutreach.objects.update_or_create(
            email=email, defaults=defaults
        )

    return JsonResponse(_serialize(obj), status=201 if created else 200)


@csrf_exempt
@require_http_methods(["POST"])
def update_outreach(request):
    """Update outreach record fields (status, shopify IDs, etc.)."""
    body = _json_body(request)
    airtable_record_id = body.get("airtable_record_id", "").strip()
    email = body.get("email", "").strip().lower()

    if not airtable_record_id and not email:
        return JsonResponse({"error": "airtable_record_id or email required"}, status=400)

    try:
        if airtable_record_id:
            obj = OnzInfluencerOutreach.objects.get(airtable_record_id=airtable_record_id)
        else:
            obj = OnzInfluencerOutreach.objects.filter(email=email).order_by("-created_at").first()
            if not obj:
                return JsonResponse({"error": "Not found"}, status=404)
    except OnzInfluencerOutreach.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    for field in ("outreach_status", "outreach_type", "shopify_customer_id",
                  "shopify_draft_order_id", "shopify_draft_order_name",
                  "airtable_conversation_id", "ig_handle", "tiktok_handle"):
        if field in body:
            setattr(obj, field, body[field])
    obj.save()

    return JsonResponse(_serialize(obj))


@csrf_exempt
@require_http_methods(["GET"])
def list_outreach(request):
    """List outreach records with optional filters."""
    qs = OnzInfluencerOutreach.objects.all()

    email = request.GET.get("email")
    status = request.GET.get("status")
    environment = request.GET.get("environment")
    airtable_record_id = request.GET.get("airtable_record_id")

    if email:
        qs = qs.filter(email=email.lower())
    if status:
        qs = qs.filter(outreach_status=status)
    if environment:
        qs = qs.filter(environment=environment)
    if airtable_record_id:
        qs = qs.filter(airtable_record_id=airtable_record_id)

    limit = int(request.GET.get("limit", 50))
    return JsonResponse([_serialize(o) for o in qs[:limit]], safe=False)


# --- Pipeline Config ---


def _serialize_config(obj):
    """Serialize PipelineConfig to dict with proper date handling."""
    data = {}
    for field in obj._meta.fields:
        val = getattr(obj, field.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, 'isoformat'):  # date objects
            val = val.isoformat() if val else None
        data[field.name] = val
    return data


@csrf_exempt
def get_pipeline_config_today(request):
    """Get today's pipeline config. Creates default if none exists."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))
    from datetime import date as date_cls
    today = date_cls.today()
    config, created = PipelineConfig.objects.get_or_create(date=today)
    return _cors_headers(request, JsonResponse(_serialize_config(config)))


@csrf_exempt
def get_or_save_pipeline_config(request, config_date):
    """Get or update pipeline config for a specific date."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))
    from datetime import date as date_cls
    try:
        d = datetime.strptime(config_date, "%Y-%m-%d").date()
    except ValueError:
        return _cors_headers(request, JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400))

    if request.method == "GET":
        try:
            config = PipelineConfig.objects.get(date=d)
        except PipelineConfig.DoesNotExist:
            return _cors_headers(request, JsonResponse({"error": "Config not found for this date"}, status=404))
        return _cors_headers(request, JsonResponse(_serialize_config(config)))

    # POST — upsert
    body = _json_body(request)
    defaults = {}
    # Batch control
    if "update_date" in body:
        defaults["update_date"] = _parse_date(body["update_date"])
    if "start_from_beginning" in body:
        defaults["start_from_beginning"] = bool(body["start_from_beginning"])
    if "creators_contacted" in body:
        defaults["creators_contacted"] = int(body["creators_contacted"])
    if "ht_threshold" in body:
        defaults["ht_threshold"] = int(body["ht_threshold"])
    # Feature toggles
    for field in ("rag_email_dedup", "apify_autofill"):
        if field in body:
            defaults[field] = bool(body[field])
    if "human_in_loop" in body:
        defaults["human_in_loop"] = body["human_in_loop"]
    if "sender_email" in body:
        defaults["sender_email"] = body["sender_email"]
    # Templates & forms
    for field in ("outreach_template_id", "grosmimi_form_url", "chaenmom_form_url",
                  "naeiae_form_url", "ht_form_url"):
        if field in body:
            defaults[field] = body[field]
    # Computed fields (from preview tool)
    for field in ("eligible_total", "eligible_grosmimi", "eligible_chaenmom",
                  "eligible_naeiae", "eligible_unknown", "ht_count", "lt_count"):
        if field in body:
            defaults[field] = int(body[field])
    # Meta
    if "updated_by" in body:
        defaults["updated_by"] = body["updated_by"]

    config, created = PipelineConfig.objects.update_or_create(
        date=d, defaults=defaults
    )
    return _cors_headers(request, JsonResponse(_serialize_config(config), status=201 if created else 200))


@csrf_exempt
def pipeline_config_history(request):
    """Get recent pipeline config history (last 30 days by default)."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))
    limit = int(request.GET.get("limit", 30))
    configs = PipelineConfig.objects.all()[:limit]
    return _cors_headers(request, JsonResponse([_serialize_config(c) for c in configs], safe=False))


# --- Tables (for monitoring) ---


@csrf_exempt
@require_http_methods(["GET"])
def list_tables(request):
    """List all onzenna tables with row counts."""
    tables = {
        "onz_users": OnzUser.objects.count(),
        "onz_onboarding": OnzOnboarding.objects.count(),
        "onz_engagement_events": OnzEngagementEvent.objects.count(),
        "onz_recommendation_cache": OnzRecommendationCache.objects.count(),
        "onz_loyalty_survey": OnzLoyaltySurvey.objects.count(),
        "onz_creator_profile": OnzCreatorProfile.objects.count(),
        "onz_gifting_applications": OnzGiftingApplication.objects.count(),
        "onz_influencer_outreach": OnzInfluencerOutreach.objects.count(),
        "gk_gmail_contacts": GmailContact.objects.count(),
        "onz_pipeline_config": PipelineConfig.objects.count(),
        "onz_pipeline_creators": PipelineCreator.objects.count(),
        "onz_pipeline_execution_log": PipelineExecutionLog.objects.count(),
        "onz_pipeline_status_changes": PipelineStatusChange.objects.count(),
    }
    return JsonResponse({"tables": tables})


# --- Gmail RAG Contact Lookup ---


@csrf_exempt
@require_http_methods(["GET"])
def check_gmail_contact(request):
    """Check if an email exists in the Gmail RAG contact index."""
    email = request.GET.get("email", "").strip().lower()
    if not email:
        return JsonResponse({"error": "email parameter required"}, status=400)
    try:
        c = GmailContact.objects.get(email=email)
        return JsonResponse({
            "found": True,
            "email": c.email,
            "name": c.name,
            "account": c.account,
            "total_sent": c.total_sent,
            "total_received": c.total_received,
            "last_contact_date": c.last_contact_date.isoformat() if c.last_contact_date else None,
            "last_subject": c.last_subject,
        })
    except GmailContact.DoesNotExist:
        return JsonResponse({"found": False, "email": email})


@csrf_exempt
@require_http_methods(["POST"])
def bulk_check_gmail_contacts(request):
    """Bulk check multiple emails against Gmail RAG contact index."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    emails = body.get("emails", [])
    if not emails or not isinstance(emails, list):
        return JsonResponse({"error": "emails array required"}, status=400)

    emails_lower = [e.strip().lower() for e in emails if isinstance(e, str)]
    found = GmailContact.objects.filter(email__in=emails_lower)
    found_map = {}
    for c in found:
        found_map[c.email] = {
            "name": c.name,
            "account": c.account,
            "total_sent": c.total_sent,
            "last_contact_date": c.last_contact_date.isoformat() if c.last_contact_date else None,
        }

    results = {}
    for e in emails_lower:
        results[e] = found_map.get(e, None)

    return JsonResponse({"results": results, "total_checked": len(emails_lower), "total_found": len(found_map)})


@csrf_exempt
@require_http_methods(["POST"])
def sync_gmail_contacts(request):
    """Batch upsert Gmail contacts from SQLite sync script."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    contacts = body.get("contacts", [])
    if not contacts or not isinstance(contacts, list):
        return JsonResponse({"error": "contacts array required"}, status=400)

    created = 0
    updated = 0
    for c in contacts:
        email = c.get("email", "").strip().lower()
        if not email:
            continue
        obj, was_created = GmailContact.objects.update_or_create(
            email=email,
            defaults={
                "name": c.get("name", ""),
                "domain": c.get("domain", ""),
                "account": c.get("account", "zezebaebae"),
                "first_contact_date": c.get("first_contact_date"),
                "last_contact_date": c.get("last_contact_date"),
                "last_subject": c.get("last_subject", ""),
                "total_sent": c.get("total_sent", 0),
                "total_received": c.get("total_received", 0),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return JsonResponse({"created": created, "updated": updated, "total": len(contacts)})


# --- Pipeline Creators (CRM Dashboard) ---


def _serialize_creator(obj):
    """Serialize PipelineCreator / PipelineExecutionLog to dict."""
    data = {}
    for field in obj._meta.fields:
        val = getattr(obj, field.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        elif hasattr(val, 'isoformat'):
            val = val.isoformat() if val else None
        data[field.name] = val
    # JSONFields are already native list/dict from Django — no extra parsing needed
    return data


@csrf_exempt
def pipeline_creators_list(request):
    """GET: list creators with filters. POST: upsert creator."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    if request.method == 'POST':
        body = _json_body(request)
        email = body.get("email", "").strip().lower()
        if not email:
            return _cors_headers(request, JsonResponse({"error": "email is required"}, status=400))

        defaults = {
            "ig_handle": body.get("ig_handle", ""),
            "tiktok_handle": body.get("tiktok_handle", ""),
            "full_name": body.get("full_name", ""),
            "platform": body.get("platform", ""),
            "pipeline_status": body.get("pipeline_status", "Not Started"),
            "brand": body.get("brand", ""),
            "outreach_type": body.get("outreach_type", ""),
            "source": body.get("source", "outbound"),
            "notes": body.get("notes", ""),
        }
        if body.get("followers") is not None:
            defaults["followers"] = int(body["followers"]) if body["followers"] else None
        if body.get("avg_views") is not None:
            defaults["avg_views"] = int(body["avg_views"]) if body["avg_views"] else None
        if body.get("initial_discovery_date"):
            defaults["initial_discovery_date"] = _parse_date(body["initial_discovery_date"])
        # Content fields (from Syncly)
        for f in ("top_post_url", "top_post_transcript", "top_post_caption"):
            if body.get(f) is not None:
                defaults[f] = str(body[f])
        for f in ("top_post_views", "views_30d", "likes_30d"):
            if body.get(f) is not None:
                defaults[f] = int(body[f]) if body[f] else None
        if body.get("top_post_date"):
            defaults["top_post_date"] = _parse_date(body["top_post_date"])
        for f in ("shopify_customer_id", "shopify_draft_order_id",
                   "shopify_draft_order_name", "airtable_record_id"):
            if body.get(f):
                defaults[f] = str(body[f])

        # New multi-source fields
        for f in ("sources", "gmail_accounts", "pr_products",
                   "apify_posted_brands", "apify_posts"):
            if f in body and isinstance(body[f], list):
                defaults[f] = body[f]
        for f in ("phone", "child_1_birthday", "child_2_birthday", "collaboration_status"):
            if f in body:
                defaults[f] = str(body[f])
        for f in ("is_shopify_pr", "is_apify_tagged", "is_manychat_contact"):
            if f in body:
                defaults[f] = bool(body[f])
        for f in ("contact_count", "gmail_total_sent", "gmail_total_received", "apify_post_count"):
            if body.get(f) is not None:
                defaults[f] = int(body[f])
        if body.get("gmail_first_contact"):
            defaults["gmail_first_contact"] = _parse_date(body["gmail_first_contact"])
        if body.get("gmail_last_contact"):
            defaults["gmail_last_contact"] = _parse_date(body["gmail_last_contact"])
        if body.get("apify_last_post_date"):
            defaults["apify_last_post_date"] = _parse_date(body["apify_last_post_date"])
        if body.get("first_contacted_at"):
            try:
                defaults["first_contacted_at"] = datetime.fromisoformat(
                    body["first_contacted_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        if body.get("last_contacted_at"):
            try:
                defaults["last_contacted_at"] = datetime.fromisoformat(
                    body["last_contacted_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        if body.get("apify_last_crawled_at"):
            try:
                defaults["apify_last_crawled_at"] = datetime.fromisoformat(
                    body["apify_last_crawled_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        creator, created = PipelineCreator.objects.update_or_create(
            email=email, defaults=defaults
        )

        # Record status change if status explicitly set and not default
        if body.get("pipeline_status") and body["pipeline_status"] != "Not Started":
            PipelineStatusChange.objects.create(
                creator_email=email,
                from_status="Not Started",
                to_status=body["pipeline_status"],
                changed_by=body.get("changed_by", "api"),
            )

        return _cors_headers(request, JsonResponse(_serialize_creator(creator), status=201 if created else 200))

    # GET — list with filters
    qs = PipelineCreator.objects.all()

    search = request.GET.get("search", "").strip()
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(email__icontains=search) |
            Q(ig_handle__icontains=search) |
            Q(tiktok_handle__icontains=search) |
            Q(full_name__icontains=search)
        )

    status = request.GET.get("status")
    if status:
        qs = qs.filter(pipeline_status=status)

    brand = request.GET.get("brand")
    if brand:
        qs = qs.filter(brand=brand)

    source = request.GET.get("source")
    if source:
        qs = qs.filter(source=source)

    outreach_type = request.GET.get("type")
    if outreach_type:
        qs = qs.filter(outreach_type=outreach_type)

    # assigned_to filter: maps owner name → brand(s)
    _OWNER_BRANDS = {
        "Jeehoo": ["Grosmimi"],
        "Laeeka": ["CHA&MOM"],
        "Soyeon": ["Naeiae"],
    }
    assigned_to = request.GET.get("assigned_to")
    if assigned_to is not None:
        if assigned_to == "":
            # Unassigned = brands not in any owner mapping
            all_owned = [b for bs in _OWNER_BRANDS.values() for b in bs]
            qs = qs.exclude(brand__in=all_owned)
        elif assigned_to in _OWNER_BRANDS:
            qs = qs.filter(brand__in=_OWNER_BRANDS[assigned_to])

    # Cross-check filters
    email_suffix = request.GET.get("email_suffix")
    if email_suffix:
        qs = qs.filter(email__endswith=email_suffix)

    if request.GET.get("is_shopify_pr") == "true":
        qs = qs.filter(is_shopify_pr=True)

    if request.GET.get("is_apify_tagged") == "true":
        qs = qs.filter(is_apify_tagged=True)

    if request.GET.get("is_manychat_contact") == "true":
        qs = qs.filter(is_manychat_contact=True)

    # Ordering
    order = request.GET.get("order", "-created_at")
    qs = qs.order_by(order)

    # Pagination
    page = int(request.GET.get("page", 1))
    limit = int(request.GET.get("limit", 50))
    total = qs.count()
    offset = (page - 1) * limit
    creators = qs[offset:offset + limit]

    return _cors_headers(request, JsonResponse({
        "results": [_serialize_creator(c) for c in creators],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }))


@csrf_exempt
def pipeline_creator_detail(request, creator_id):
    """GET: creator detail. PUT: update creator (with status audit)."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    try:
        creator = PipelineCreator.objects.get(id=creator_id)
    except PipelineCreator.DoesNotExist:
        return _cors_headers(request, JsonResponse({"error": "Creator not found"}, status=404))

    if request.method == 'PUT':
        body = _json_body(request)
        old_status = creator.pipeline_status

        for field in ("ig_handle", "tiktok_handle", "full_name", "platform",
                      "pipeline_status", "brand", "outreach_type", "source", "notes",
                      "shopify_customer_id", "shopify_draft_order_id",
                      "shopify_draft_order_name", "airtable_record_id",
                      "phone", "child_1_birthday", "child_2_birthday", "collaboration_status"):
            if field in body:
                setattr(creator, field, body[field])

        if "followers" in body:
            creator.followers = int(body["followers"]) if body["followers"] else None
        if "avg_views" in body:
            creator.avg_views = int(body["avg_views"]) if body["avg_views"] else None
        if "initial_discovery_date" in body:
            creator.initial_discovery_date = _parse_date(body["initial_discovery_date"])

        # JSONField updates
        for f in ("sources", "gmail_accounts", "pr_products",
                   "apify_posted_brands", "apify_posts"):
            if f in body and isinstance(body[f], list):
                setattr(creator, f, body[f])
        # Boolean flags
        for f in ("is_shopify_pr", "is_apify_tagged", "is_manychat_contact"):
            if f in body:
                setattr(creator, f, bool(body[f]))
        # Integer fields
        for f in ("contact_count", "gmail_total_sent", "gmail_total_received", "apify_post_count"):
            if f in body and body[f] is not None:
                setattr(creator, f, int(body[f]))
        # Date fields
        for f in ("gmail_first_contact", "gmail_last_contact", "apify_last_post_date"):
            if f in body:
                setattr(creator, f, _parse_date(body[f]))
        # Datetime fields
        for f in ("first_contacted_at", "last_contacted_at", "apify_last_crawled_at"):
            if f in body and body[f]:
                try:
                    setattr(creator, f, datetime.fromisoformat(
                        body[f].replace("Z", "+00:00")))
                except (ValueError, AttributeError):
                    pass

        creator.save()

        # Audit status change
        new_status = creator.pipeline_status
        if new_status != old_status:
            PipelineStatusChange.objects.create(
                creator_email=creator.email,
                from_status=old_status,
                to_status=new_status,
                changed_by=body.get("changed_by", "dashboard"),
            )

        return _cors_headers(request, JsonResponse(_serialize_creator(creator)))

    # GET
    return _cors_headers(request, JsonResponse(_serialize_creator(creator)))


@csrf_exempt
def pipeline_creators_stats(request):
    """Aggregate stats: by status, by brand, recent activity."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    from django.db.models import Count, Q
    from datetime import timedelta
    from datetime import date as date_cls

    total = PipelineCreator.objects.count()

    # Status breakdown
    status_counts = dict(
        PipelineCreator.objects.values_list('pipeline_status')
        .annotate(c=Count('id'))
        .values_list('pipeline_status', 'c')
    )

    # Brand breakdown
    brand_counts = dict(
        PipelineCreator.objects.values_list('brand')
        .annotate(c=Count('id'))
        .values_list('brand', 'c')
    )

    # This week's new creators
    week_ago = date_cls.today() - timedelta(days=7)
    new_this_week = PipelineCreator.objects.filter(created_at__date__gte=week_ago).count()

    # Type breakdown
    type_counts = dict(
        PipelineCreator.objects.values_list('outreach_type')
        .annotate(c=Count('id'))
        .values_list('outreach_type', 'c')
    )

    # LT/HT status breakdown (for Y-fork funnel)
    lt_status = dict(
        PipelineCreator.objects.filter(outreach_type='LT')
        .values_list('pipeline_status')
        .annotate(c=Count('id'))
        .values_list('pipeline_status', 'c')
    )
    ht_status = dict(
        PipelineCreator.objects.filter(outreach_type='HT')
        .values_list('pipeline_status')
        .annotate(c=Count('id'))
        .values_list('pipeline_status', 'c')
    )

    # @discovered.syncly email count (unconfirmed)
    discovered_email_count = PipelineCreator.objects.filter(
        email__endswith="@discovered.syncly"
    ).count()

    # Cross-check summary
    shopify_pr_count = PipelineCreator.objects.filter(is_shopify_pr=True).count()
    apify_tagged_count = PipelineCreator.objects.filter(is_apify_tagged=True).count()
    manychat_count = PipelineCreator.objects.filter(is_manychat_contact=True).count()

    # Data source freshness (from gk_* tables)
    from django.db import connection
    data_sources = {}
    try:
        with connection.cursor() as cur:
            # Syncly (source='syncly' in content_posts)
            cur.execute("SELECT COUNT(*), MAX(collected_at) FROM gk_content_posts WHERE source='syncly'")
            row = cur.fetchone()
            data_sources["syncly"] = {"count": row[0] or 0, "last_collected": str(row[1]) if row[1] else None}

            # Apify (source='apify' or all posts)
            cur.execute("SELECT COUNT(*), MAX(collected_at) FROM gk_content_posts")
            row = cur.fetchone()
            data_sources["apify"] = {"count": row[0] or 0, "last_collected": str(row[1]) if row[1] else None}

            # Shopify PR orders
            cur.execute("SELECT COUNT(*), MAX(collected_at) FROM gk_influencer_orders")
            row = cur.fetchone()
            data_sources["shopify_pr"] = {"count": row[0] or 0, "last_collected": str(row[1]) if row[1] else None}

            # Gmail contacts
            cur.execute("SELECT COUNT(*), MAX(synced_at) FROM gk_gmail_contacts")
            row = cur.fetchone()
            data_sources["gmail"] = {"count": row[0] or 0, "last_collected": str(row[1]) if row[1] else None}
    except Exception:
        pass  # gk_ tables may not exist in all envs

    return _cors_headers(request, JsonResponse({
        "total": total,
        "by_status": status_counts,
        "by_status_lt": lt_status,
        "by_status_ht": ht_status,
        "by_brand": brand_counts,
        "by_type": type_counts,
        "new_this_week": new_this_week,
        "discovered_email_count": discovered_email_count,
        "shopify_pr_count": shopify_pr_count,
        "apify_tagged_count": apify_tagged_count,
        "manychat_count": manychat_count,
        "data_sources": data_sources,
    }))


@csrf_exempt
def pipeline_creators_bulk_status(request):
    """Bulk update status for multiple creators."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    if request.method != 'POST':
        return _cors_headers(request, JsonResponse({"error": "POST required"}, status=405))

    body = _json_body(request)
    creator_ids = body.get("ids", [])
    new_status = body.get("status", "")
    changed_by = body.get("changed_by", "dashboard")

    if not creator_ids or not new_status:
        return _cors_headers(request, JsonResponse({"error": "ids and status required"}, status=400))

    updated = 0
    for cid in creator_ids:
        try:
            creator = PipelineCreator.objects.get(id=cid)
            old_status = creator.pipeline_status
            if old_status != new_status:
                creator.pipeline_status = new_status
                creator.save()
                PipelineStatusChange.objects.create(
                    creator_email=creator.email,
                    from_status=old_status,
                    to_status=new_status,
                    changed_by=changed_by,
                )
                updated += 1
        except PipelineCreator.DoesNotExist:
            continue

    return _cors_headers(request, JsonResponse({"updated": updated, "total": len(creator_ids)}))


# --- Pipeline Execution Log ---


@csrf_exempt
def pipeline_execution_log(request):
    """GET: list execution logs. POST: add new log entry."""
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    if request.method == 'POST':
        body = _json_body(request)
        action_type = body.get("action_type", "")
        if not action_type:
            return _cors_headers(request, JsonResponse({"error": "action_type required"}, status=400))

        log = PipelineExecutionLog.objects.create(
            action_type=action_type,
            triggered_by=body.get("triggered_by", ""),
            target_count=int(body.get("target_count", 0)),
            status=body.get("status", "pending"),
            details=json.dumps(body.get("details", {})) if isinstance(body.get("details"), dict) else body.get("details", "{}"),
        )
        if body.get("completed_at"):
            try:
                log.completed_at = datetime.fromisoformat(body["completed_at"].replace("Z", "+00:00"))
                log.save()
            except (ValueError, AttributeError):
                pass

        return _cors_headers(request, JsonResponse(_serialize_creator(log), status=201))

    # GET — list
    limit = int(request.GET.get("limit", 50))
    action_type = request.GET.get("action_type")
    qs = PipelineExecutionLog.objects.all()
    if action_type:
        qs = qs.filter(action_type=action_type)

    logs = qs[:limit]
    results = []
    for log in logs:
        d = {}
        for field in log._meta.fields:
            val = getattr(log, field.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            elif isinstance(val, uuid.UUID):
                val = str(val)
            d[field.name] = val
        # Parse details JSON
        if isinstance(d.get("details"), str):
            try:
                d["details"] = json.loads(d["details"])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)

    return _cors_headers(request, JsonResponse({"results": results, "total": qs.count()}, safe=False))


# --- Syncly Discovery Import ---


@csrf_exempt
def import_syncly_discovery(request):
    """POST: Import creators from gk_content_posts into pipeline_creators.

    Finds creators in content_posts that don't exist in pipeline_creators yet.
    Creates them with status='Not Started', source='syncly'.

    Body (optional):
      brand: filter by brand (default: all)
      limit: max creators to import (default: 50)
      days: look back N days (default: 30)
    """
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    if request.method != 'POST':
        return _cors_headers(request, JsonResponse({"error": "POST required"}, status=405))

    body = _json_body(request)
    brand_filter = body.get("brand", "")
    limit = int(body.get("limit", 50))
    days = int(body.get("days", 30))

    from django.db import connection
    from datetime import timedelta
    from datetime import date as date_cls

    cutoff = date_cls.today() - timedelta(days=days)

    # Query gk_content_posts for unique creators not already in pipeline
    sql = """
        SELECT DISTINCT ON (cp.username)
            cp.username, cp.nickname, cp.followers, cp.platform,
            cp.brand, cp.caption, cp.url, cp.post_date
        FROM gk_content_posts cp
        LEFT JOIN onz_pipeline_creators pc
            ON LOWER(cp.username) = LOWER(pc.ig_handle)
            OR LOWER(cp.username) = LOWER(pc.tiktok_handle)
        WHERE pc.id IS NULL
          AND cp.post_date >= %s
          AND cp.username IS NOT NULL
          AND cp.username != ''
    """
    params = [cutoff]

    if brand_filter:
        sql += " AND LOWER(cp.brand) = LOWER(%s)"
        params.append(brand_filter)

    sql += " ORDER BY cp.username, cp.followers DESC NULLS LAST LIMIT %s"
    params.append(limit)

    created = 0
    skipped = 0
    imported = []

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        for row in rows:
            username, nickname, followers, platform, brand, caption, url, post_date = row

            # Clean handle (remove @)
            handle = (username or "").lstrip("@").strip()
            if not handle:
                skipped += 1
                continue

            # Determine platform
            plat = (platform or "").lower()
            ig_handle = handle if "tiktok" not in plat else ""
            tiktok_handle = handle if "tiktok" in plat else ""

            # Generate placeholder email
            email = f"{handle.replace('.', '_')}@discovered.syncly"

            # Check if already exists by handle
            exists = PipelineCreator.objects.filter(
                ig_handle__iexact=handle
            ).exists() or PipelineCreator.objects.filter(
                tiktok_handle__iexact=handle
            ).exists() or PipelineCreator.objects.filter(
                email=email
            ).exists()

            if exists:
                skipped += 1
                continue

            creator = PipelineCreator.objects.create(
                email=email,
                ig_handle=ig_handle,
                tiktok_handle=tiktok_handle,
                full_name=nickname or handle,
                platform="TikTok" if "tiktok" in plat else "Instagram",
                pipeline_status="Not Started",
                brand=brand or "",
                outreach_type="LT" if (followers or 0) < 100000 else "HT",
                source="syncly",
                followers=followers,
                avg_views=int((followers or 0) * (0.15 if "tiktok" in plat else 0.08)),
                initial_discovery_date=post_date or date_cls.today(),
                notes=f"Syncly discovery. Post: {url or 'N/A'}",
            )
            created += 1
            imported.append({
                "id": str(creator.id),
                "handle": handle,
                "brand": brand,
                "followers": followers,
            })

    except Exception as e:
        return _cors_headers(request, JsonResponse({
            "error": str(e),
            "created": created,
            "skipped": skipped,
        }, status=500))

    return _cors_headers(request, JsonResponse({
        "created": created,
        "skipped": skipped,
        "imported": imported,
    }, status=201))


@csrf_exempt
def syncly_content_import(request):
    """POST: Import creators from Syncly Google Sheets with full content data.

    Reads Creators_updated + Output_updated, JOINs best post per creator,
    upserts into PipelineCreator with transcript, post_url, views, etc.

    Body (optional):
      days: only import creators discovered in last N days (default: 30)
      limit: max creators per run (default: 500)
      dry_run: if true, return preview without DB changes
    """
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    if request.method != 'POST':
        return _cors_headers(request, JsonResponse({"error": "POST required"}, status=405))

    body = _json_body(request)
    days = int(body.get("days", 30))
    limit = int(body.get("limit", 500))
    dry_run = body.get("dry_run", False)

    import os as _os
    import gspread
    from google.oauth2.service_account import Credentials as SACredentials
    from datetime import timedelta, date as date_cls

    PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    SHEET_ID = "1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o"

    # Output column indices (0-based)
    OUT_COL = {
        "username": 6, "level": 8, "post_url": 15, "text": 18,
        "transcript": 19, "caption": 20, "post_date": 21,
        "followers": 32, "avg_view": 33, "views_30d": 39, "likes_30d": 40,
    }

    def _safe_int(val):
        if not val:
            return None
        try:
            return int(str(val).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    try:
        creds = SACredentials.from_service_account_file(
            _os.path.join(PROJECT_ROOT, "credentials", "google_service_account.json"),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)

        # Read Output_updated — build best post map
        ws_out = sh.worksheet("Output_updated")
        out_data = ws_out.get_all_values()
        out_rows = out_data[1:]

        best_posts = {}
        for row in out_rows:
            def _col(key):
                idx = OUT_COL.get(key, -1)
                return (row[idx] or "").strip() if 0 <= idx < len(row) else ""

            if _col("level").lower() != "full_matched":
                continue

            uname = _col("username").lstrip("@").lower()
            if not uname:
                continue

            views = _safe_int(_col("views_30d")) or _safe_int(_col("avg_view")) or 0
            current = best_posts.get(uname)
            if not current or views > (current.get("_v") or 0):
                transcript = _col("transcript") or _col("text") or _col("caption") or ""
                best_posts[uname] = {
                    "top_post_url": _col("post_url"),
                    "top_post_transcript": transcript,
                    "top_post_caption": _col("caption"),
                    "top_post_views": _safe_int(_col("views_30d")) or _safe_int(_col("avg_view")),
                    "top_post_date": _col("post_date"),
                    "views_30d": _safe_int(_col("views_30d")),
                    "likes_30d": _safe_int(_col("likes_30d")),
                    "avg_view": _safe_int(_col("avg_view")),
                    "followers": _safe_int(_col("followers")),
                    "_v": views,
                }

        # Read Creators_updated
        ws_cr = sh.worksheet("Creators_updated")
        cr_data = ws_cr.get_all_values()
        cr_headers = cr_data[0]
        cr_rows = cr_data[1:]

        def _cr_col_idx(name):
            for i, h in enumerate(cr_headers):
                if name.lower() in h.lower():
                    return i
            return -1

        idx_email = _cr_col_idx("Email")
        idx_username = _cr_col_idx("Username")
        idx_platform = _cr_col_idx("Platform")
        idx_blacklist = _cr_col_idx("Blacklist")
        idx_collab = _cr_col_idx("\uc81c\ud734 \uc0c1\ud0dc")
        if idx_collab < 0:
            idx_collab = _cr_col_idx("제휴 상태")
        idx_discovery = _cr_col_idx("\ucd5c\ucd08 \ubc1c\uacac")
        if idx_discovery < 0:
            idx_discovery = _cr_col_idx("발견")

        cutoff = date_cls.today() - timedelta(days=days)
        ht_threshold = 100000
        try:
            cfg = PipelineConfig.objects.order_by('-date').first()
            if cfg and cfg.ht_threshold:
                ht_threshold = cfg.ht_threshold
        except Exception:
            pass

        created = 0
        updated = 0
        skipped = 0

        for row in cr_rows:
            if created + updated >= limit:
                break

            def _cell(idx):
                return str(row[idx] or "").strip() if 0 <= idx < len(row) else ""

            email = _cell(idx_email)
            if not email or "@" not in email or "@discovered." in email.lower():
                continue

            blacklist = _cell(idx_blacklist)
            if blacklist.upper() == "TRUE":
                continue

            collab = _cell(idx_collab)
            if collab:
                continue

            username = _cell(idx_username).lstrip("@").lower()
            if not username:
                continue

            # Parse discovery date
            disc_date = None
            disc_raw = _cell(idx_discovery)
            if disc_raw and "-" in disc_raw:
                try:
                    parts = disc_raw.split("-")
                    y = int(parts[0])
                    if y < 100:
                        y += 2000
                    disc_date = date_cls(y, int(parts[1]), int(parts[2]))
                except Exception:
                    pass

            # Filter by days
            if disc_date and disc_date < cutoff:
                continue

            bp = best_posts.get(username, {})
            plat_raw = _cell(idx_platform).lower()
            plat = "TikTok" if "tiktok" in plat_raw else "Instagram"
            ig_handle = username if plat == "Instagram" else ""
            tiktok_handle = username if plat == "TikTok" else ""

            avg_v = bp.get("avg_view") or bp.get("views_30d") or 0
            outreach_type = "HT" if avg_v >= ht_threshold else "LT"

            content_fields = {}
            if bp:
                content_fields = {
                    "top_post_url": bp.get("top_post_url", ""),
                    "top_post_transcript": bp.get("top_post_transcript", ""),
                    "top_post_caption": bp.get("top_post_caption", ""),
                    "top_post_views": bp.get("top_post_views"),
                    "views_30d": bp.get("views_30d"),
                    "likes_30d": bp.get("likes_30d"),
                }
                # Parse post date
                pd_raw = bp.get("top_post_date", "")
                if pd_raw and "-" in pd_raw:
                    try:
                        pp = pd_raw.split("-")
                        content_fields["top_post_date"] = date_cls(int(pp[0]), int(pp[1]), int(pp[2]))
                    except Exception:
                        pass

            existing = PipelineCreator.objects.filter(ig_handle__iexact=username).first() or \
                       PipelineCreator.objects.filter(tiktok_handle__iexact=username).first() or \
                       PipelineCreator.objects.filter(email__iexact=email).first()

            if existing:
                changed = False
                if "@discovered." in (existing.email or "") and email:
                    if not PipelineCreator.objects.filter(email=email).exclude(id=existing.id).exists():
                        existing.email = email
                        changed = True
                if bp:
                    for f, v in content_fields.items():
                        if v is not None and v != "":
                            setattr(existing, f, v)
                            changed = True
                if avg_v and (not existing.avg_views or avg_v > existing.avg_views):
                    existing.avg_views = avg_v
                    changed = True
                followers = bp.get("followers")
                if followers and (not existing.followers or followers > existing.followers):
                    existing.followers = followers
                    changed = True
                if changed:
                    if not dry_run:
                        existing.save()
                    updated += 1
            else:
                if PipelineCreator.objects.filter(email=email).exists():
                    skipped += 1
                    continue
                if not dry_run:
                    PipelineCreator.objects.create(
                        email=email,
                        ig_handle=ig_handle,
                        tiktok_handle=tiktok_handle,
                        full_name=username,
                        platform=plat,
                        pipeline_status="Not Started",
                        outreach_type=outreach_type,
                        source="syncly",
                        followers=bp.get("followers"),
                        avg_views=avg_v or None,
                        initial_discovery_date=disc_date or date_cls.today(),
                        notes="Syncly content import (real email + content)",
                        **content_fields,
                    )
                created += 1

        return _cors_headers(request, JsonResponse({
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total_output_creators": len(best_posts),
            "total_sheet_rows": len(cr_rows),
            "dry_run": dry_run,
        }, status=201))

    except Exception as e:
        import traceback
        return _cors_headers(request, JsonResponse({
            "error": str(e),
            "traceback": traceback.format_exc(),
        }, status=500))


# ========== EMAIL REPLY CONFIG ==========

def _serialize_email_config(cfg, include_faq=False):
    """Serialize EmailReplyConfig to dict, optionally including FAQ entries."""
    data = {
        "brand": cfg.brand,
        "is_active": cfg.is_active,
        "version": cfg.version,
        "classification": {
            "prompt": cfg.classification_prompt,
            "model": cfg.classification_model,
        },
        "auto_send": {
            "lt": cfg.lt_auto_send,
            "ht": cfg.ht_auto_send,
        },
        "templates": {
            "accept": cfg.accept_template,
            "faq_gap": cfg.faq_gap_template,
            "normal": cfg.normal_template,
            "decline": cfg.decline_template,
        },
        "outreach_prompts": {
            "lt": cfg.outreach_lt_prompt,
            "ht": cfg.outreach_ht_prompt,
        },
        "content_guidelines": {
            "hashtags": json.loads(cfg.hashtags) if cfg.hashtags else [],
            "product_mentions": json.loads(cfg.product_mentions) if cfg.product_mentions else [],
            "deadline_days": cfg.deadline_days,
        },
        "gifting_form_url": cfg.gifting_form_url,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
        "updated_by": cfg.updated_by,
    }
    if include_faq:
        faqs = FAQEntry.objects.filter(
            brand__in=[cfg.brand, "all"], is_active=True
        ).order_by("-priority", "category")
        data["faq_entries"] = [
            {
                "id": str(f.id),
                "brand": f.brand,
                "question": f.question,
                "answer": f.answer,
                "keywords": json.loads(f.keywords) if f.keywords else [],
                "category": f.category,
                "priority": f.priority,
            }
            for f in faqs
        ]
    return data


@csrf_exempt
def email_config_list(request):
    """GET: list all brand configs. POST not used here."""
    if request.method == "OPTIONS":
        return _cors_headers(request, HttpResponse(status=204))
    configs = EmailReplyConfig.objects.all()
    data = [_serialize_email_config(c) for c in configs]
    return _cors_headers(request, JsonResponse(data, safe=False))


@csrf_exempt
def email_config_detail(request, brand):
    """GET: n8n fetches full config + FAQ for a brand. POST: create/update."""
    if request.method == "OPTIONS":
        return _cors_headers(request, HttpResponse(status=204))

    if request.method == "GET":
        try:
            cfg = EmailReplyConfig.objects.get(brand=brand)
        except EmailReplyConfig.DoesNotExist:
            return _cors_headers(request, JsonResponse({"error": f"No config for brand '{brand}'"}, status=404))
        return _cors_headers(request, JsonResponse(_serialize_email_config(cfg, include_faq=True)))

    if request.method == "POST":
        body = _json_body(request)
        cfg, created = EmailReplyConfig.objects.update_or_create(
            brand=brand,
            defaults={
                "is_active": body.get("is_active", True),
                "classification_prompt": body.get("classification_prompt", ""),
                "classification_model": body.get("classification_model", "claude-sonnet-4-20250514"),
                "lt_auto_send": body.get("lt_auto_send", True),
                "ht_auto_send": body.get("ht_auto_send", False),
                "accept_template": body.get("accept_template", ""),
                "faq_gap_template": body.get("faq_gap_template", ""),
                "normal_template": body.get("normal_template", ""),
                "decline_template": body.get("decline_template", ""),
                "outreach_lt_prompt": body.get("outreach_lt_prompt", ""),
                "outreach_ht_prompt": body.get("outreach_ht_prompt", ""),
                "hashtags": json.dumps(body.get("hashtags", [])),
                "product_mentions": json.dumps(body.get("product_mentions", [])),
                "deadline_days": body.get("deadline_days", 30),
                "gifting_form_url": body.get("gifting_form_url", ""),
                "updated_by": body.get("updated_by", ""),
            },
        )
        if not created:
            cfg.version += 1
            cfg.save(update_fields=["version"])
        return _cors_headers(request, JsonResponse(
            _serialize_email_config(cfg), status=201 if created else 200
        ))

    return _cors_headers(request, JsonResponse({"error": "Method not allowed"}, status=405))


@csrf_exempt
def faq_list(request):
    """GET: list FAQ entries (optional ?brand=X). POST: create new."""
    if request.method == "OPTIONS":
        return _cors_headers(request, HttpResponse(status=204))

    if request.method == "GET":
        qs = FAQEntry.objects.filter(is_active=True)
        brand = request.GET.get("brand")
        if brand:
            qs = qs.filter(brand__in=[brand, "all"])
        data = [
            {
                "id": str(f.id),
                "brand": f.brand,
                "question": f.question,
                "answer": f.answer,
                "keywords": json.loads(f.keywords) if f.keywords else [],
                "category": f.category,
                "priority": f.priority,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            }
            for f in qs
        ]
        return _cors_headers(request, JsonResponse(data, safe=False))

    if request.method == "POST":
        body = _json_body(request)
        f = FAQEntry.objects.create(
            brand=body.get("brand", "all"),
            question=body.get("question", ""),
            answer=body.get("answer", ""),
            keywords=json.dumps(body.get("keywords", [])),
            category=body.get("category", ""),
            priority=body.get("priority", 0),
        )
        return _cors_headers(request, JsonResponse({"id": str(f.id), "created": True}, status=201))

    return _cors_headers(request, JsonResponse({"error": "Method not allowed"}, status=405))


@csrf_exempt
def faq_detail(request, faq_id):
    """PUT: update. DELETE: soft-delete."""
    if request.method == "OPTIONS":
        return _cors_headers(request, HttpResponse(status=204))

    try:
        f = FAQEntry.objects.get(id=faq_id)
    except FAQEntry.DoesNotExist:
        return _cors_headers(request, JsonResponse({"error": "FAQ not found"}, status=404))

    if request.method == "PUT":
        body = _json_body(request)
        for field in ("brand", "question", "answer", "category"):
            if field in body:
                setattr(f, field, body[field])
        if "keywords" in body:
            f.keywords = json.dumps(body["keywords"])
        if "priority" in body:
            f.priority = body["priority"]
        if "is_active" in body:
            f.is_active = body["is_active"]
        f.save()
        return _cors_headers(request, JsonResponse({"updated": True}))

    if request.method == "DELETE":
        f.is_active = False
        f.save(update_fields=["is_active"])
        return _cors_headers(request, JsonResponse({"deleted": True}))

    return _cors_headers(request, JsonResponse({"error": "Method not allowed"}, status=405))


@csrf_exempt
def reply_log_create(request):
    """POST: n8n writes audit log. GET: dashboard reads recent logs."""
    if request.method == "OPTIONS":
        return _cors_headers(request, HttpResponse(status=204))

    if request.method == "GET":
        days = int(request.GET.get("days", 7))
        cutoff = datetime.now() - __import__("datetime").timedelta(days=days)
        qs = EmailReplyLog.objects.filter(processed_at__gte=cutoff)
        brand = request.GET.get("brand")
        if brand:
            qs = qs.filter(brand=brand)
        data = [
            {
                "id": str(r.id),
                "creator_email": r.creator_email,
                "brand": r.brand,
                "outreach_type": r.outreach_type,
                "intent": r.intent,
                "confidence": r.confidence,
                "auto_sent": r.auto_sent,
                "template_used": r.template_used,
                "incoming_subject": r.incoming_subject,
                "config_version": r.config_version,
                "processed_at": r.processed_at.isoformat() if r.processed_at else None,
            }
            for r in qs[:100]
        ]
        return _cors_headers(request, JsonResponse(data, safe=False))

    if request.method == "POST":
        body = _json_body(request)
        r = EmailReplyLog.objects.create(
            creator_email=body.get("creator_email", ""),
            brand=body.get("brand", ""),
            outreach_type=body.get("outreach_type", ""),
            intent=body.get("intent", "Unknown"),
            confidence=body.get("confidence"),
            auto_sent=body.get("auto_sent", False),
            template_used=body.get("template_used", ""),
            faq_entry_id=body.get("faq_entry_id"),
            incoming_subject=body.get("incoming_subject", ""),
            incoming_snippet=body.get("incoming_snippet", ""),
            outgoing_body=body.get("outgoing_body", ""),
            config_version=body.get("config_version", 1),
        )
        return _cors_headers(request, JsonResponse({"id": str(r.id), "created": True}, status=201))

    return _cors_headers(request, JsonResponse({"error": "Method not allowed"}, status=405))


# --- Cross-Check: Gmail + Apify + Shopify PR batch match ---


@csrf_exempt
def pipeline_creators_cross_check(request):
    """POST: Batch cross-check PipelineCreators against Gmail, Apify, Shopify PR.

    Query params:
        sources=gmail,apify,shopify_pr  (comma-separated, default: all)

    Gmail: match email → enrich gmail_* fields
    Apify: match ig_handle/tiktok_handle against gk_content_posts → enrich apify_* fields
    Shopify PR: match ig_handle/email against gk_influencer_orders → enrich pr_* fields
    """
    if request.method == 'OPTIONS':
        return _cors_headers(request, HttpResponse(status=204))

    if request.method != 'POST':
        return _cors_headers(request, JsonResponse({"error": "POST required"}, status=405))

    from django.db import connection

    requested = request.GET.get("sources", "gmail,apify,shopify_pr")
    run_sources = [s.strip() for s in requested.split(",")]

    total_creators = PipelineCreator.objects.count()
    result = {"total_creators": total_creators}

    # --- Gmail cross-check ---
    if "gmail" in run_sources:
        gmail_matched = 0
        gmail_updated = 0
        all_gmail = {c.email: c for c in GmailContact.objects.all()}

        batch_size = 500
        off = 0
        while off < total_creators:
            creators = list(PipelineCreator.objects.all()[off:off + batch_size])
            for cr in creators:
                gc = all_gmail.get(cr.email)
                if not gc:
                    continue
                gmail_matched += 1
                changed = False
                if gc.first_contact_date and not cr.gmail_first_contact:
                    cr.gmail_first_contact = gc.first_contact_date.date() if hasattr(gc.first_contact_date, 'date') else gc.first_contact_date
                    changed = True
                if gc.last_contact_date:
                    gc_date = gc.last_contact_date.date() if hasattr(gc.last_contact_date, 'date') else gc.last_contact_date
                    if not cr.gmail_last_contact or gc_date > cr.gmail_last_contact:
                        cr.gmail_last_contact = gc_date
                        changed = True
                if gc.total_sent and gc.total_sent > cr.gmail_total_sent:
                    cr.gmail_total_sent = gc.total_sent
                    changed = True
                if gc.total_received and gc.total_received > cr.gmail_total_received:
                    cr.gmail_total_received = gc.total_received
                    changed = True
                acct = gc.account or "zezebaebae"
                current_accounts = cr.gmail_accounts or []
                if acct not in current_accounts:
                    cr.gmail_accounts = current_accounts + [acct]
                    changed = True
                current_sources = cr.sources or []
                if "gmail_inbound" not in current_sources:
                    cr.sources = current_sources + ["gmail_inbound"]
                    changed = True
                if changed:
                    cr.save()
                    gmail_updated += 1
            off += batch_size

        result["gmail_matched"] = gmail_matched
        result["gmail_updated"] = gmail_updated
        result["total_gmail_contacts"] = len(all_gmail)

    # --- Apify cross-check (gk_content_posts → PipelineCreator) ---
    if "apify" in run_sources:
        apify_matched = 0
        apify_updated = 0

        # Build handle→posts map from gk_content_posts
        with connection.cursor() as cur:
            cur.execute("""
                SELECT username, platform, brand, post_date, url,
                       views_30d, likes_30d, comments_30d, post_id
                FROM gk_content_posts
                ORDER BY post_date DESC
            """)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Group by lowercase handle
        handle_posts = {}
        for r in rows:
            h = (r["username"] or "").lower().lstrip("@")
            if not h:
                continue
            handle_posts.setdefault(h, []).append(r)

        # Match against PipelineCreator
        batch_size = 500
        off = 0
        while off < total_creators:
            creators = list(PipelineCreator.objects.all()[off:off + batch_size])
            for cr in creators:
                ig = (cr.ig_handle or "").lower().lstrip("@")
                tt = (cr.tiktok_handle or "").lower().lstrip("@")
                posts = []
                if ig and ig in handle_posts:
                    posts.extend(handle_posts[ig])
                if tt and tt in handle_posts:
                    posts.extend(handle_posts[tt])
                if not posts:
                    continue

                apify_matched += 1
                changed = False

                # Deduplicate by post_id
                seen = set()
                unique_posts = []
                for p in posts:
                    if p["post_id"] not in seen:
                        seen.add(p["post_id"])
                        unique_posts.append(p)

                new_count = len(unique_posts)
                brands = list(set(p["brand"] for p in unique_posts if p.get("brand")))
                last_date = max((p["post_date"] for p in unique_posts if p.get("post_date")), default=None)

                # Build apify_posts JSON (top 50 by date)
                top_posts = sorted(unique_posts, key=lambda x: x.get("post_date") or "", reverse=True)[:50]
                apify_json = [{
                    "post_id": p["post_id"],
                    "url": p.get("url", ""),
                    "platform": p.get("platform", ""),
                    "post_date": str(p["post_date"]) if p.get("post_date") else "",
                    "views": p.get("views_30d", 0),
                    "likes": p.get("likes_30d", 0),
                    "comments": p.get("comments_30d", 0),
                } for p in top_posts]

                if not cr.is_apify_tagged:
                    cr.is_apify_tagged = True
                    changed = True
                if new_count != cr.apify_post_count:
                    cr.apify_post_count = new_count
                    changed = True
                if sorted(brands) != sorted(cr.apify_posted_brands or []):
                    cr.apify_posted_brands = brands
                    changed = True
                if last_date and (not cr.apify_last_post_date or last_date > cr.apify_last_post_date):
                    cr.apify_last_post_date = last_date
                    changed = True

                cr.apify_posts = apify_json
                cr.apify_last_crawled_at = datetime.utcnow()
                changed = True

                src = cr.sources or []
                if "apify" not in src:
                    cr.sources = src + ["apify"]
                    changed = True

                if not cr.collaboration_status and new_count > 0:
                    cr.collaboration_status = "active"
                    changed = True

                if changed:
                    cr.save()
                    apify_updated += 1
            off += batch_size

        result["apify_matched"] = apify_matched
        result["apify_updated"] = apify_updated
        result["apify_total_posts"] = len(rows)

    # --- Shopify PR cross-check (gk_influencer_orders → PipelineCreator) ---
    if "shopify_pr" in run_sources:
        pr_matched = 0
        pr_updated = 0

        with connection.cursor() as cur:
            cur.execute("""
                SELECT account_handle, customer_email, brand,
                       product_names, product_types, shipping_date, order_name
                FROM gk_influencer_orders
                ORDER BY shipping_date DESC NULLS LAST
            """)
            cols = [c[0] for c in cur.description]
            pr_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Build handle→orders and email→orders maps
        handle_orders = {}
        email_orders = {}
        for r in pr_rows:
            h = (r.get("account_handle") or "").lower().lstrip("@")
            e = (r.get("customer_email") or "").lower()
            if h:
                handle_orders.setdefault(h, []).append(r)
            if e:
                email_orders.setdefault(e, []).append(r)

        batch_size = 500
        off = 0
        while off < total_creators:
            creators = list(PipelineCreator.objects.all()[off:off + batch_size])
            for cr in creators:
                ig = (cr.ig_handle or "").lower().lstrip("@")
                email_lower = (cr.email or "").lower()
                orders = []
                if ig and ig in handle_orders:
                    orders.extend(handle_orders[ig])
                if email_lower and email_lower in email_orders:
                    orders.extend(email_orders[email_lower])
                if not orders:
                    continue

                pr_matched += 1
                changed = False

                # Deduplicate by order_name
                seen = set()
                unique_orders = []
                for o in orders:
                    key = o.get("order_name", "")
                    if key and key not in seen:
                        seen.add(key)
                        unique_orders.append(o)

                # Build pr_products JSON
                pr_products = []
                for o in unique_orders:
                    products = (o.get("product_names") or "").split(",")
                    for prod in products:
                        prod = prod.strip()
                        if prod:
                            pr_products.append({
                                "brand": o.get("brand", ""),
                                "product": prod,
                                "order_date": str(o["shipping_date"]) if o.get("shipping_date") else "",
                            })

                if not cr.is_shopify_pr:
                    cr.is_shopify_pr = True
                    changed = True
                if pr_products and pr_products != (cr.pr_products or []):
                    cr.pr_products = pr_products
                    changed = True

                src = cr.sources or []
                if "shopify_pr" not in src:
                    cr.sources = src + ["shopify_pr"]
                    changed = True

                if changed:
                    cr.save()
                    pr_updated += 1
            off += batch_size

        result["shopify_pr_matched"] = pr_matched
        result["shopify_pr_updated"] = pr_updated
        result["shopify_pr_total_orders"] = len(pr_rows)

    # Always include current flag counts
    result["shopify_pr_count"] = PipelineCreator.objects.filter(is_shopify_pr=True).count()
    result["apify_tagged_count"] = PipelineCreator.objects.filter(is_apify_tagged=True).count()
    result["manychat_count"] = PipelineCreator.objects.filter(is_manychat_contact=True).count()

    return _cors_headers(request, JsonResponse(result, status=200))
