"""Data Keeper Django models.

Centralized data warehouse for all advertising and sales metrics.
Collected twice daily (PST 0:00, 12:00) by data_keeper.py.
All consumers read from these tables instead of calling APIs directly.
"""

from django.db import models


class ShopifyOrdersDaily(models.Model):
    """Daily Shopify orders aggregated by brand and channel."""
    date = models.DateField()
    brand = models.CharField(max_length=100)
    channel = models.CharField(max_length=50)  # D2C, Amazon, TikTok, B2B, PR
    gross_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discounts = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    orders = models.IntegerField(default=0)
    units = models.IntegerField(default=0)
    refunds = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_shopify_orders_daily"
        unique_together = ("date", "brand", "channel")

    def __str__(self):
        return f"{self.date} {self.brand} {self.channel}"


class AmazonSalesDaily(models.Model):
    """Daily Amazon sales by seller/brand."""
    date = models.DateField()
    seller_id = models.CharField(max_length=50)
    brand = models.CharField(max_length=100)
    channel = models.CharField(max_length=50, default="Amazon")  # Amazon, Target+
    gross_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    orders = models.IntegerField(default=0)
    units = models.IntegerField(default=0)
    fees = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    refunds = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_sales_daily"
        unique_together = ("date", "seller_id", "channel")

    def __str__(self):
        return f"{self.date} {self.brand} {self.channel}"


class AmazonAdsDaily(models.Model):
    """Daily Amazon Ads campaign-level metrics (Reporting v3)."""
    date = models.DateField()
    profile_id = models.CharField(max_length=50)
    brand = models.CharField(max_length=100)
    campaign_id = models.CharField(max_length=50)
    campaign_name = models.CharField(max_length=500)
    ad_type = models.CharField(max_length=30, default="SP")  # SP, SB, SD
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    purchases = models.IntegerField(default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_ads_daily"
        unique_together = ("date", "campaign_id")

    def __str__(self):
        return f"{self.date} {self.brand} {self.campaign_name}"


class AmazonCampaigns(models.Model):
    """Amazon Ads campaign metadata (refreshed daily)."""
    campaign_id = models.CharField(max_length=50, unique=True)
    profile_id = models.CharField(max_length=50)
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=500)
    status = models.CharField(max_length=30)  # ENABLED, PAUSED, ARCHIVED
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    bid_strategy = models.CharField(max_length=50, blank=True, default="")
    campaign_type = models.CharField(max_length=30, default="SP")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_campaigns"

    def __str__(self):
        return f"{self.brand} {self.name}"


class MetaAdsDaily(models.Model):
    """Daily Meta Ads ad-level metrics."""
    date = models.DateField()
    ad_id = models.CharField(max_length=50)
    ad_name = models.CharField(max_length=500)
    campaign_id = models.CharField(max_length=50)
    campaign_name = models.CharField(max_length=500)
    adset_id = models.CharField(max_length=50, blank=True, default="")
    adset_name = models.CharField(max_length=500, blank=True, default="")
    brand = models.CharField(max_length=100)
    campaign_type = models.CharField(max_length=30, default="cvr")  # cvr, traffic
    objective = models.CharField(max_length=50, blank=True, default="")
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reach = models.IntegerField(default=0)
    frequency = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    purchases = models.IntegerField(default=0)
    purchase_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    landing_url = models.URLField(max_length=1000, blank=True, default="")
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_meta_ads_daily"
        unique_together = ("date", "ad_id")

    def __str__(self):
        return f"{self.date} {self.brand} {self.ad_name}"


class MetaCampaigns(models.Model):
    """Meta Ads campaign metadata."""
    campaign_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=500)
    objective = models.CharField(max_length=50)
    status = models.CharField(max_length=30)
    brand = models.CharField(max_length=100)
    campaign_type = models.CharField(max_length=30, default="cvr")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_meta_campaigns"

    def __str__(self):
        return f"{self.brand} {self.name}"


class GoogleAdsDaily(models.Model):
    """Daily Google Ads campaign-level metrics."""
    date = models.DateField()
    customer_id = models.CharField(max_length=50)
    campaign_id = models.CharField(max_length=50)
    campaign_name = models.CharField(max_length=500)
    brand = models.CharField(max_length=100)
    campaign_type = models.CharField(max_length=50, blank=True, default="")
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    conversion_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_google_ads_daily"
        unique_together = ("date", "campaign_id")

    def __str__(self):
        return f"{self.date} {self.brand} {self.campaign_name}"


class GA4Daily(models.Model):
    """Daily GA4 sessions and purchases by channel."""
    date = models.DateField()
    channel_grouping = models.CharField(max_length=100, default="(all)")
    sessions = models.IntegerField(default=0)
    purchases = models.IntegerField(default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_ga4_daily"
        unique_together = ("date", "channel_grouping")

    def __str__(self):
        return f"{self.date} {self.channel_grouping}"


class KlaviyoDaily(models.Model):
    """Daily Klaviyo campaign/flow metrics."""
    date = models.DateField()
    source_type = models.CharField(max_length=20)  # campaign, flow
    source_name = models.CharField(max_length=500)
    source_id = models.CharField(max_length=100, blank=True, default="")
    sends = models.IntegerField(default=0)
    opens = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    conversions = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_klaviyo_daily"
        unique_together = ("date", "source_type", "source_id")

    def __str__(self):
        return f"{self.date} {self.source_type} {self.source_name}"


class GscDaily(models.Model):
    """Daily Google Search Console search analytics per site and query."""
    date = models.DateField()
    site_url = models.CharField(max_length=200)
    query = models.CharField(max_length=500)
    clicks = models.IntegerField(default=0)
    impressions = models.IntegerField(default=0)
    ctr = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    position = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_gsc_daily"
        unique_together = ("date", "site_url", "query")

    def __str__(self):
        return f"{self.date} {self.site_url} {self.query}"


class DataForSeoKeywords(models.Model):
    """DataForSEO keyword search volumes and competition data (updated weekly)."""
    date = models.DateField()
    keyword = models.CharField(max_length=500)
    brand = models.CharField(max_length=100)
    search_volume = models.IntegerField(default=0)
    cpc = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    competition_index = models.IntegerField(default=0)
    competition = models.CharField(max_length=20, blank=True, default="")
    monthly_searches = models.TextField(blank=True, default="[]")  # JSON list
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_dataforseo_keywords"
        unique_together = ("date", "keyword")

    def __str__(self):
        return f"{self.date} {self.keyword} vol={self.search_volume}"


class AmazonAdsSearchTerms(models.Model):
    """Amazon Ads search term report data (weekly chunks).

    date is a CharField because Amazon reports use range format "2026-03-01~2026-03-07".
    """
    date = models.CharField(max_length=30)  # "YYYY-MM-DD~YYYY-MM-DD" range
    profile_id = models.CharField(max_length=50)
    brand = models.CharField(max_length=100)
    campaign_id = models.CharField(max_length=50)
    ad_group_id = models.CharField(max_length=50)
    keyword_id = models.CharField(max_length=50, blank=True, default="")
    search_term = models.CharField(max_length=500)
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    purchases = models.IntegerField(default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_ads_search_terms"
        unique_together = ("date", "profile_id", "campaign_id", "ad_group_id", "search_term")

    def __str__(self):
        return f"{self.date} {self.brand} {self.search_term}"


class AmazonAdsKeywords(models.Model):
    """Amazon Ads keyword-level report data (weekly chunks).

    date is a CharField because Amazon reports use range format "2026-03-01~2026-03-07".
    """
    date = models.CharField(max_length=30)  # "YYYY-MM-DD~YYYY-MM-DD" range
    profile_id = models.CharField(max_length=50)
    brand = models.CharField(max_length=100)
    campaign_id = models.CharField(max_length=50)
    ad_group_id = models.CharField(max_length=50)
    keyword_id = models.CharField(max_length=50, blank=True, default="")
    keyword_text = models.CharField(max_length=500, blank=True, default="")
    match_type = models.CharField(max_length=30, blank=True, default="")
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    purchases = models.IntegerField(default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_ads_keywords"
        unique_together = ("date", "profile_id", "campaign_id", "ad_group_id", "keyword_id")

    def __str__(self):
        return f"{self.date} {self.brand} {self.keyword_text}"


class ShopifyOrdersSkuDaily(models.Model):
    """Daily Shopify orders at SKU/variant level (most granular breakdown).

    Aggregated by (date, brand, channel, variant_id).
    Same pricing logic as ShopifyOrdersDaily — D2C uses compare_at_price, Amazon uses base price.
    Collected as a side effect of collect_shopify() — no extra API calls.
    """
    date = models.DateField()
    brand = models.CharField(max_length=100)
    channel = models.CharField(max_length=50)       # D2C, Amazon, TikTok, B2B, PR
    variant_id = models.CharField(max_length=50, blank=True, default="")
    sku = models.CharField(max_length=200, blank=True, default="")
    product_title = models.CharField(max_length=500, blank=True, default="")
    gross_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discounts = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    units = models.IntegerField(default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_shopify_orders_sku_daily"
        unique_together = ("date", "brand", "channel", "variant_id")

    def __str__(self):
        return f"{self.date} {self.brand} {self.channel} {self.sku}"


class AmazonSalesSkuDaily(models.Model):
    """Daily Amazon sales at ASIN/SKU level from SP-API flat-file orders report.

    Aggregated by (date, seller_id, channel, asin, sku).
    Collected as a side effect of collect_amazon_sales() — no extra API calls.
    """
    date = models.DateField()
    seller_id = models.CharField(max_length=50)
    brand = models.CharField(max_length=100)
    channel = models.CharField(max_length=50, default="Amazon")  # Amazon, Target+
    asin = models.CharField(max_length=20, blank=True, default="")
    sku = models.CharField(max_length=200, blank=True, default="")
    product_name = models.CharField(max_length=500, blank=True, default="")
    units = models.IntegerField(default=0)
    ordered_product_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_sales_sku_daily"
        unique_together = ("date", "seller_id", "channel", "asin", "sku")

    def __str__(self):
        return f"{self.date} {self.brand} {self.asin} {self.sku}"


class ContentPosts(models.Model):
    """Master table for influencer content posts (Syncly + Apify sources)."""
    post_id = models.CharField(max_length=200, unique=True)
    url = models.URLField(max_length=1000, blank=True, default="")
    platform = models.CharField(max_length=20)  # instagram, tiktok
    username = models.CharField(max_length=200)
    nickname = models.CharField(max_length=200, blank=True, default="")
    followers = models.IntegerField(default=0)
    caption = models.TextField(blank=True, default="")  # U열 Caption
    transcript = models.TextField(blank=True, default="")  # T열 Transcript (full 대사)
    text = models.TextField(blank=True, default="")  # S열 Text
    bio_text = models.TextField(blank=True, default="")  # W열 Bio text
    hashtags = models.TextField(blank=True, default="")
    tagged_account = models.CharField(max_length=200, blank=True, default="")
    post_date = models.DateField()
    brand = models.CharField(max_length=100, blank=True, default="")
    # 30-day aggregate metrics (AM~AP열)
    videos_30d = models.IntegerField(default=0)  # AM열 최근 30일 Video 수
    views_30d = models.BigIntegerField(default=0)  # AN열 최근 30일 조회 수 총합
    likes_30d = models.BigIntegerField(default=0)  # AO열 최근 30일 좋아요 수 총합
    comments_30d = models.BigIntegerField(default=0)  # AP열 최근 30일 댓글 수 총합
    product_types = models.CharField(max_length=500, blank=True, default="")  # comma-separated: "PPSU Straw Cup,Stainless Tumbler"
    region = models.CharField(max_length=10, default="us")  # us, jp
    source = models.CharField(max_length=20, default="syncly")  # syncly, apify
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_content_posts"
        unique_together = (("post_id",),)

    def __str__(self):
        return f"{self.post_date} {self.platform} @{self.username}"


class ContentMetricsDaily(models.Model):
    """Daily engagement metrics snapshot per post."""
    post_id = models.CharField(max_length=200)
    date = models.DateField()
    comments = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    views = models.IntegerField(default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_content_metrics_daily"
        unique_together = (("post_id", "date"),)

    def __str__(self):
        return f"{self.date} {self.post_id}"


class InfluencerOrders(models.Model):
    """Shopify PR/sample orders sent to influencers."""
    order_id = models.CharField(max_length=50, unique=True)
    order_name = models.CharField(max_length=50, blank=True, default="")
    customer_name = models.CharField(max_length=200)
    customer_email = models.CharField(max_length=200, blank=True, default="")
    account_handle = models.CharField(max_length=200, blank=True, default="")
    channel = models.CharField(max_length=20, blank=True, default="")
    product_types = models.TextField(blank=True, default="")
    product_names = models.TextField(blank=True, default="")
    influencer_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_date = models.DateField(null=True, blank=True)
    fulfillment_status = models.CharField(max_length=50, blank=True, default="")
    brand = models.CharField(max_length=100, blank=True, default="")
    tags = models.TextField(blank=True, default="")
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_influencer_orders"
        unique_together = (("order_id",),)

    def __str__(self):
        return f"{self.order_name} {self.customer_name}"


class AmazonBrandAnalytics(models.Model):
    """Amazon Brand Analytics weekly search term report.

    One row per (week_start, search_term, asin).
    Data is marketplace-wide; is_ours flag marks our ASINs.
    """
    date = models.DateField()  # week start (Sunday)
    week_end = models.DateField()  # week end (Saturday)
    brand = models.CharField(max_length=100)
    is_ours = models.BooleanField(default=False)
    department = models.CharField(max_length=200, blank=True, default="")
    search_term = models.CharField(max_length=500)
    search_frequency_rank = models.IntegerField(default=0)
    asin = models.CharField(max_length=20)
    asin_name = models.CharField(max_length=200, blank=True, default="")
    asin_rank = models.IntegerField(default=0)  # 1, 2, or 3
    click_share = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    conversion_share = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_brand_analytics"
        unique_together = ("date", "search_term", "asin")

    def __str__(self):
        return f"{self.date} {self.search_term} {self.asin}"


class AmazonSQPBrand(models.Model):
    """Amazon Search Query Performance - Brand View weekly data.

    Downloaded manually from Seller Central (Search Query Performance → Brand View).
    One row per (week_end, brand, search_query).
    """
    week_end = models.DateField()
    brand = models.CharField(max_length=100)
    search_query = models.CharField(max_length=500)
    search_query_score = models.IntegerField(default=0)   # rank within brand (1=top)
    search_query_volume = models.IntegerField(default=0)  # actual weekly search count
    impressions_brand = models.IntegerField(default=0)
    clicks_brand = models.IntegerField(default=0)
    clicks_brand_share = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    purchases_brand = models.IntegerField(default=0)
    purchases_brand_share = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_amazon_sqp_brand"
        unique_together = ("week_end", "brand", "search_query")

    def __str__(self):
        return f"{self.week_end} {self.brand} {self.search_query}"


class GoogleAdsSearchTerms(models.Model):
    """Google Ads search term view daily metrics."""
    date = models.DateField()
    customer_id = models.CharField(max_length=50)
    campaign_id = models.CharField(max_length=50)
    campaign_name = models.CharField(max_length=500)
    ad_group_id = models.CharField(max_length=50)
    ad_group_name = models.CharField(max_length=500)
    search_term = models.CharField(max_length=500)
    brand = models.CharField(max_length=100)
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    conversion_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    collected_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gk_google_ads_search_terms"
        unique_together = ("date", "campaign_id", "ad_group_id", "search_term")

    def __str__(self):
        return f"{self.date} {self.brand} {self.search_term}"
