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
