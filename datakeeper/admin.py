from django.contrib import admin
from .models import (
    ShopifyOrdersDaily, AmazonSalesDaily, AmazonAdsDaily, AmazonCampaigns,
    MetaAdsDaily, MetaCampaigns, GoogleAdsDaily, GA4Daily, KlaviyoDaily,
    ContentPosts, ContentMetricsDaily, InfluencerOrders,
    AmazonBrandAnalytics, GoogleAdsSearchTerms,
)

for model in [
    ShopifyOrdersDaily, AmazonSalesDaily, AmazonAdsDaily, AmazonCampaigns,
    MetaAdsDaily, MetaCampaigns, GoogleAdsDaily, GA4Daily, KlaviyoDaily,
    ContentPosts, ContentMetricsDaily, InfluencerOrders,
    AmazonBrandAnalytics, GoogleAdsSearchTerms,
]:
    admin.site.register(model)
