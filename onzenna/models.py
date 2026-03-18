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


class OnzGiftingApplication(models.Model):
    """Inbound influencer gifting applications from the Shopify form."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Personal info
    email = models.EmailField(db_index=True)
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True, default="")
    instagram = models.CharField(max_length=200, blank=True, default="")
    tiktok = models.CharField(max_length=200, blank=True, default="")

    # Baby info
    child_1_birthday = models.DateField(null=True, blank=True)
    child_1_age_months = models.IntegerField(null=True, blank=True)
    child_2_birthday = models.DateField(null=True, blank=True)
    child_2_age_months = models.IntegerField(null=True, blank=True)

    # Selected products (JSON array)
    selected_products = models.TextField(blank=True, default="[]")

    # Shipping address
    address_street = models.CharField(max_length=300, blank=True, default="")
    address_apt = models.CharField(max_length=100, blank=True, default="")
    address_city = models.CharField(max_length=100, blank=True, default="")
    address_state = models.CharField(max_length=10, blank=True, default="")
    address_zip = models.CharField(max_length=20, blank=True, default="")
    address_country = models.CharField(max_length=10, default="US")

    # Shopify references
    shopify_customer_id = models.CharField(max_length=50, blank=True, default="")
    shopify_draft_order_id = models.CharField(max_length=50, blank=True, default="")
    shopify_draft_order_name = models.CharField(max_length=50, blank=True, default="")

    # Airtable sync
    airtable_record_id = models.CharField(max_length=50, blank=True, default="")

    # Status tracking
    status = models.CharField(max_length=30, default="submitted")  # submitted, approved, shipped, delivered, posted, declined
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onz_gifting_applications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.email}) - {self.status}"


class OnzInfluencerOutreach(models.Model):
    """Outbound influencer outreach pipeline (Pathlight).
    Separate from inbound gifting applications (OnzGiftingApplication).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Creator identity
    email = models.EmailField(db_index=True)
    ig_handle = models.CharField(max_length=200, blank=True, default="")
    tiktok_handle = models.CharField(max_length=200, blank=True, default="")
    platform = models.CharField(max_length=30, blank=True, default="")  # Instagram, TikTok
    full_name = models.CharField(max_length=200, blank=True, default="")

    # Outreach metadata
    outreach_type = models.CharField(max_length=10, blank=True, default="")   # LT, HT
    outreach_status = models.CharField(max_length=30, default="Not Started")
    # Not Started / Draft Ready / Sent / Replied / Needs Review / Accepted / Declined

    # Airtable sync (source of truth for status)
    airtable_base_id = models.CharField(max_length=30, blank=True, default="")
    airtable_record_id = models.CharField(max_length=30, blank=True, default="", db_index=True)
    airtable_conversation_id = models.CharField(max_length=30, blank=True, default="")

    # Shopify (set after gifting accepted)
    shopify_customer_id = models.CharField(max_length=50, blank=True, default="")
    shopify_draft_order_id = models.CharField(max_length=50, blank=True, default="")
    shopify_draft_order_name = models.CharField(max_length=50, blank=True, default="")

    # Source tracking
    source = models.CharField(max_length=30, default="pathlight_outbound")
    environment = models.CharField(max_length=10, default="wj_test")  # wj_test / production

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onz_influencer_outreach"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ig_handle or self.email} [{self.outreach_status}]"


class GmailContact(models.Model):
    """Gmail RAG contact index — tracks who we've emailed."""
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    domain = models.CharField(max_length=255, blank=True, default="", db_index=True)
    account = models.CharField(max_length=50, default="zezebaebae")  # zezebaebae or onzenna
    first_contact_date = models.DateTimeField(null=True, blank=True)
    last_contact_date = models.DateTimeField(null=True, blank=True)
    last_subject = models.CharField(max_length=500, blank=True, default="")
    total_sent = models.IntegerField(default=0)
    total_received = models.IntegerField(default=0)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_gmail_contacts"

    def __str__(self):
        return f"{self.email} ({self.account}) sent={self.total_sent}"
