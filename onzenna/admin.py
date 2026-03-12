from django.contrib import admin

from .models import (
    OnzUser,
    OnzOnboarding,
    OnzEngagementEvent,
    OnzRecommendationCache,
    OnzLoyaltySurvey,
    OnzCreatorProfile,
    OnzGiftingApplication,
)


@admin.register(OnzUser)
class OnzUserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "full_name", "pregnancy_stage", "created_at")
    search_fields = ("email", "full_name")
    list_filter = ("pregnancy_stage", "auth_provider")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(OnzOnboarding)
class OnzOnboardingAdmin(admin.ModelAdmin):
    list_display = ("user", "journey_stage", "has_other_children", "completed_at")
    list_filter = ("journey_stage",)
    readonly_fields = ("id", "completed_at")


@admin.register(OnzEngagementEvent)
class OnzEngagementEventAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "resource_type", "resource_id", "created_at")
    list_filter = ("action", "resource_type")
    readonly_fields = ("id", "created_at")


@admin.register(OnzRecommendationCache)
class OnzRecommendationCacheAdmin(admin.ModelAdmin):
    list_display = ("user", "generated_at")
    readonly_fields = ("id", "generated_at")


@admin.register(OnzLoyaltySurvey)
class OnzLoyaltySurveyAdmin(admin.ModelAdmin):
    list_display = ("user", "routine_type", "feeding_method", "sms_opt_in", "completed_at")
    list_filter = ("sms_opt_in",)
    readonly_fields = ("id", "completed_at")


@admin.register(OnzCreatorProfile)
class OnzCreatorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "creator_level", "primary_platform", "following_size", "completed_at")
    list_filter = ("creator_level", "primary_platform")
    readonly_fields = ("id", "completed_at")


@admin.register(OnzGiftingApplication)
class OnzGiftingApplicationAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "status", "instagram", "shopify_draft_order_name", "created_at")
    search_fields = ("email", "full_name", "instagram", "tiktok")
    list_filter = ("status",)
    readonly_fields = ("id", "created_at", "updated_at")
