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


class PipelineConfig(models.Model):
    """Creator Collab Pipeline daily config — replaces Airtable Config table."""
    date = models.DateField(unique=True)
    # Batch control
    update_date = models.DateField(null=True, blank=True)
    start_from_beginning = models.BooleanField(default=False)
    creators_contacted = models.IntegerField(default=10)
    ht_threshold = models.IntegerField(default=100000)       # R30D views
    ht_follower_min = models.IntegerField(default=50000)     # Minimum followers for HT
    # Brand → assignee mapping (JSON: {"Grosmimi":"Jeehoo","CHA&MOM":"Laeeka","Naeiae":"Soyeon"})
    brand_assignees = models.TextField(default='{"Grosmimi":"Jeehoo","CHA&MOM":"Laeeka","Naeiae":"Soyeon"}')
    # Feature toggles
    rag_email_dedup = models.BooleanField(default=True)
    apify_autofill = models.BooleanField(default=True)
    human_in_loop = models.CharField(max_length=10, default="on")
    sender_email = models.CharField(max_length=100, default="affiliates@onzenna.com")
    # Templates & forms
    outreach_template_id = models.CharField(max_length=100, default="1vAvPdheHFz4xIraa3NODUuFG7RagylHEYOvv6BjtxLg")
    grosmimi_form_url = models.URLField(max_length=500, blank=True, default="")
    chaenmom_form_url = models.URLField(max_length=500, blank=True, default="")
    naeiae_form_url = models.URLField(max_length=500, blank=True, default="")
    ht_form_url = models.URLField(max_length=500, blank=True, default="")
    # Computed (written by preview tool)
    eligible_total = models.IntegerField(default=0)
    eligible_grosmimi = models.IntegerField(default=0)
    eligible_chaenmom = models.IntegerField(default=0)
    eligible_naeiae = models.IntegerField(default=0)
    eligible_unknown = models.IntegerField(default=0)
    ht_count = models.IntegerField(default=0)
    lt_count = models.IntegerField(default=0)
    # Feature toggles (granular)
    apify_brand_filter = models.BooleanField(default=True)
    us_only = models.BooleanField(default=True)
    hil_draft_review = models.BooleanField(default=True)
    hil_send_approval = models.BooleanField(default=True)
    hil_sample_approval = models.BooleanField(default=False)
    # Brand allocation
    alloc_grosmimi = models.IntegerField(default=5)
    alloc_chaenmom = models.IntegerField(default=3)
    alloc_naeiae = models.IntegerField(default=2)
    # Account handles (JSON — per-brand sender accounts)
    account_handles = models.TextField(blank=True, default="{}")
    # Meta
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "onz_pipeline_config"
        ordering = ["-date"]

    def __str__(self):
        return f"Config {self.date} (batch={self.creators_contacted})"


class PipelineCreator(models.Model):
    """Unified creator identity for CRM dashboard.
    Replaces Airtable Creators table. Used by n8n workflows + dashboard.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    email = models.EmailField(unique=True, db_index=True)
    ig_handle = models.CharField(max_length=200, blank=True, default="")
    tiktok_handle = models.CharField(max_length=200, blank=True, default="")
    full_name = models.CharField(max_length=200, blank=True, default="")
    platform = models.CharField(max_length=30, blank=True, default="")

    # Pipeline status (single source of truth)
    pipeline_status = models.CharField(max_length=30, default="Not Started")
    # Not Started / Draft Ready / Sent / Replied / Needs Review /
    # Accepted / Declined / Sample Sent / Sample Shipped / Sample Delivered / Posted

    # Classification
    brand = models.CharField(max_length=30, blank=True, default="")
    assigned_to = models.CharField(max_length=30, blank=True, default="")  # Brand owner tag
    outreach_type = models.CharField(max_length=10, blank=True, default="")  # HT, LT
    source = models.CharField(max_length=30, default="outbound")  # outbound, inbound

    # Profile enrichment (from Apify profile scrapers)
    country = models.CharField(max_length=50, blank=True, default="")  # "United States", "US", etc.
    is_business_account = models.BooleanField(null=True, blank=True)  # True = brand/business
    business_category = models.CharField(max_length=100, blank=True, default="")  # e.g. "Beauty Store"
    biography = models.TextField(blank=True, default="")
    is_verified = models.BooleanField(null=True, blank=True)
    enriched_at = models.DateTimeField(null=True, blank=True)  # when profile was last enriched

    # Metrics
    followers = models.IntegerField(null=True, blank=True)
    avg_views = models.IntegerField(null=True, blank=True)

    # Discovery
    initial_discovery_date = models.DateField(null=True, blank=True)

    # Shopify refs
    shopify_customer_id = models.CharField(max_length=50, blank=True, default="")
    shopify_draft_order_id = models.CharField(max_length=50, blank=True, default="")
    shopify_draft_order_name = models.CharField(max_length=50, blank=True, default="")

    # Legacy Airtable ref
    airtable_record_id = models.CharField(max_length=50, blank=True, default="", db_index=True)

    # Notes
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onz_pipeline_creators"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ig_handle or self.email} [{self.pipeline_status}]"


class PipelineExecutionLog(models.Model):
    """Audit trail for pipeline actions triggered from dashboard or scripts."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    action_type = models.CharField(max_length=30)  # preview, draft_gen, send, status_change
    triggered_by = models.CharField(max_length=50, blank=True, default="")
    target_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="pending")  # pending, running, success, failed
    details = models.TextField(blank=True, default="{}")  # JSON
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "onz_pipeline_execution_log"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.action_type} by {self.triggered_by} [{self.status}]"


class PipelineStatusChange(models.Model):
    """Records every creator status change for audit trail."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    creator_email = models.EmailField(db_index=True)
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    changed_by = models.CharField(max_length=50, blank=True, default="")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onz_pipeline_status_changes"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.creator_email}: {self.from_status} -> {self.to_status}"


class EmailReplyConfig(models.Model):
    """Per-brand email reply handling config — consumed by n8n Reply Handler via HTTP GET."""
    brand = models.CharField(max_length=30, unique=True)  # grosmimi, chaenmom, naeiae
    is_active = models.BooleanField(default=True)

    # Reply classification (Claude AI)
    classification_prompt = models.TextField(blank=True, default="")
    classification_model = models.CharField(max_length=50, default="claude-sonnet-4-20250514")

    # Auto-send rules
    lt_auto_send = models.BooleanField(default=True)
    ht_auto_send = models.BooleanField(default=False)

    # Reply templates (supports {{name}}, {{form_url}} variables)
    accept_template = models.TextField(blank=True, default="")
    faq_gap_template = models.TextField(blank=True, default="")
    normal_template = models.TextField(blank=True, default="")
    decline_template = models.TextField(blank=True, default="")

    # Outreach draft prompt (replaces Google Sheets)
    outreach_lt_prompt = models.TextField(blank=True, default="")
    outreach_ht_prompt = models.TextField(blank=True, default="")

    # Content guidelines
    hashtags = models.TextField(blank=True, default="[]")  # JSON array
    product_mentions = models.TextField(blank=True, default="[]")  # JSON array
    deadline_days = models.IntegerField(default=30)
    gifting_form_url = models.URLField(max_length=500, blank=True, default="")

    # Version for cache-busting
    version = models.IntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "onz_email_reply_config"

    def __str__(self):
        return f"{self.brand} v{self.version} (active={self.is_active})"


class FAQEntry(models.Model):
    """FAQ knowledge base for auto-replying to FAQ_Gap classified emails."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    brand = models.CharField(max_length=30, db_index=True)  # grosmimi, chaenmom, naeiae, or "all"
    question = models.TextField()
    answer = models.TextField()
    keywords = models.TextField(blank=True, default="[]")  # JSON array
    category = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onz_faq_entries"
        ordering = ["-priority", "category"]

    def __str__(self):
        return f"[{self.brand}] {self.question[:60]}"


class EmailReplyLog(models.Model):
    """Audit log for every reply processed by the Reply Handler workflow."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    creator_email = models.EmailField(db_index=True)
    brand = models.CharField(max_length=30)
    outreach_type = models.CharField(max_length=10)  # LT, HT
    intent = models.CharField(max_length=20)  # Accept, FAQ_Gap, Normal, Unknown
    confidence = models.FloatField(null=True, blank=True)
    auto_sent = models.BooleanField(default=False)
    template_used = models.CharField(max_length=20, blank=True, default="")
    faq_entry_id = models.UUIDField(null=True, blank=True)
    incoming_subject = models.CharField(max_length=500, blank=True, default="")
    incoming_snippet = models.TextField(blank=True, default="")
    outgoing_body = models.TextField(blank=True, default="")
    config_version = models.IntegerField(default=1)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onz_email_reply_log"
        ordering = ["-processed_at"]

    def __str__(self):
        return f"{self.creator_email} [{self.intent}] auto={self.auto_sent}"


class PipelineConversation(models.Model):
    """Email conversation records for pipeline creators.
    Tracks both outbound (we sent) and inbound (they replied) emails.
    Consumed by dashboard Email History panel and n8n Reply Handler.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    creator_email = models.EmailField(db_index=True)
    direction = models.CharField(max_length=10)  # Inbound, Outbound
    subject = models.CharField(max_length=500, blank=True, default="")
    message_content = models.TextField(blank=True, default="")
    brand = models.CharField(max_length=30, blank=True, default="")
    outreach_type = models.CharField(max_length=10, blank=True, default="")  # LT, HT
    gmail_message_id = models.CharField(max_length=200, blank=True, default="")
    gmail_thread_id = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onz_pipeline_conversations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.creator_email} [{self.direction}] {self.subject[:50]}"


class DiscoveryPost(models.Model):
    """Discovery pipeline posts — JP (and later US) content discovered via Apify.
    Separate from PipelineCreator (outreach CRM) and content_posts (Syncly).
    One row = one social media post discovered by hashtag/keyword search.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Post identity
    handle = models.CharField(max_length=200, db_index=True)
    full_name = models.CharField(max_length=200, blank=True, default="")
    platform = models.CharField(max_length=30, db_index=True)  # instagram, tiktok
    url = models.URLField(max_length=500, unique=True, db_index=True)
    post_date = models.DateField(null=True, blank=True)

    # Content
    content_type = models.CharField(max_length=30, blank=True, default="")  # Video, Image, Sidecar
    caption = models.TextField(blank=True, default="")
    hashtags = models.TextField(blank=True, default="")
    mentions = models.CharField(max_length=500, blank=True, default="")
    transcript = models.TextField(blank=True, default="")

    # Metrics
    followers = models.IntegerField(null=True, blank=True)
    views = models.IntegerField(null=True, blank=True)
    likes = models.IntegerField(null=True, blank=True)
    comments_count = models.IntegerField(null=True, blank=True)

    # Discovery metadata
    source = models.CharField(max_length=100, blank=True, default="")  # apify/#育児, apify/tt:育児
    region = models.CharField(max_length=10, db_index=True, default="jp")  # jp, us
    discovery_batch = models.CharField(max_length=50, blank=True, default="")  # e.g. "Mar24-Mar31"

    # Outreach tracking
    outreach_status = models.CharField(max_length=30, default="discovered")
    # discovered / shortlisted / contacted / replied / declined / posted
    outreach_email = models.EmailField(blank=True, default="")
    outreach_date = models.DateField(null=True, blank=True)
    outreach_notes = models.TextField(blank=True, default="")

    # Link to PipelineCreator (after outreach begins)
    pipeline_creator_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onz_discovery_posts"
        ordering = ["-post_date", "-followers"]
        indexes = [
            models.Index(fields=["region", "outreach_status"]),
            models.Index(fields=["handle", "platform"]),
        ]

    def __str__(self):
        return f"@{self.handle} [{self.platform}] {self.post_date} ({self.outreach_status})"


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
