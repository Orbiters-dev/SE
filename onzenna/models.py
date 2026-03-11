import uuid
from django.db import models


class OnzUser(models.Model):
    """Master user identity - PK = Supabase auth user ID."""
    id = models.UUIDField(primary_key=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True, default="")
    pregnancy_stage = models.CharField(max_length=20, blank=True, default="")
    baby_dob = models.DateField(null=True, blank=True)
    interests = models.TextField(blank=True, default="[]")  # JSON array
    auth_provider = models.CharField(max_length=20, default="email")
    shopify_customer_id = models.CharField(max_length=50, blank=True, default="")
    klaviyo_synced = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onz_users"

    def __str__(self):
        return f"{self.email} ({self.id})"


class OnzOnboarding(models.Model):
    """Onboarding survey responses."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(OnzUser, on_delete=models.CASCADE, related_name="onboarding")
    journey_stage = models.CharField(max_length=30, blank=True, default="")
    baby_birthday = models.DateField(null=True, blank=True)
    has_other_children = models.BooleanField(default=False)
    other_children_count = models.CharField(max_length=10, blank=True, default="")
    concerns = models.TextField(blank=True, default="[]")  # JSON array
    purchase_frequency = models.CharField(max_length=30, blank=True, default="")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onz_onboarding"


class OnzEngagementEvent(models.Model):
    """User engagement tracking (view, save, share, purchase)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(OnzUser, on_delete=models.CASCADE, related_name="engagement_events")
    action = models.CharField(max_length=20)
    resource_type = models.CharField(max_length=20)
    resource_id = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onz_engagement_events"
        ordering = ["-created_at"]


class OnzRecommendationCache(models.Model):
    """AI recommendation cache - refreshed daily per user."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(OnzUser, on_delete=models.CASCADE, related_name="recommendation_cache")
    product_handles = models.TextField(blank=True, default="[]")  # JSON array
    post_slugs = models.TextField(blank=True, default="[]")  # JSON array
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onz_recommendation_cache"


class OnzLoyaltySurvey(models.Model):
    """Loyalty survey responses ($10 gift card reward)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(OnzUser, on_delete=models.CASCADE, related_name="loyalty_survey")
    purchase_factors = models.TextField(blank=True, default="[]")  # JSON
    discovery_channels = models.TextField(blank=True, default="[]")  # JSON
    content_preferences = models.TextField(blank=True, default="[]")  # JSON
    sms_opt_in = models.BooleanField(default=False)
    routine_type = models.CharField(max_length=30, blank=True, default="")
    feeding_method = models.CharField(max_length=30, blank=True, default="")
    support_network = models.TextField(blank=True, default="[]")  # JSON
    shopping_categories = models.TextField(blank=True, default="[]")  # JSON
    discount_code = models.CharField(max_length=50, blank=True, default="")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onz_loyalty_survey"


class OnzCreatorProfile(models.Model):
    """Creator/influencer profile data."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(OnzUser, on_delete=models.CASCADE, related_name="creator_profile")
    creator_level = models.CharField(max_length=20, blank=True, default="")
    primary_platform = models.CharField(max_length=30, blank=True, default="")
    primary_handle = models.CharField(max_length=200, blank=True, default="")
    other_channels = models.TextField(blank=True, default="[]")  # JSON
    following_size = models.CharField(max_length=20, blank=True, default="")
    content_types = models.TextField(blank=True, default="[]")  # JSON
    has_brand_deals = models.BooleanField(null=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onz_creator_profile"
