from django.contrib import admin
from .models import (
    ShopifyOrdersDaily, AmazonSalesDaily, AmazonAdsDaily, AmazonCampaigns,
    MetaAdsDaily, MetaCampaigns, GoogleAdsDaily, GA4Daily, KlaviyoDaily,
    ContentPosts, ContentMetricsDaily, InfluencerOrders,
)

for model in [
    ShopifyOrdersDaily, AmazonSalesDaily, AmazonAdsDaily, AmazonCampaigns,
    MetaAdsDaily, MetaCampaigns, GoogleAdsDaily, GA4Daily, KlaviyoDaily,
    ContentPosts, ContentMetricsDaily, InfluencerOrders,
]:
    admin.site.register(model)
