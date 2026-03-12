import json
import uuid
from datetime import datetime
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    OnzUser,
    OnzOnboarding,
    OnzEngagementEvent,
    OnzRecommendationCache,
    OnzLoyaltySurvey,
    OnzCreatorProfile,
    OnzGiftingApplication,
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
    }
    return JsonResponse({"tables": tables})
