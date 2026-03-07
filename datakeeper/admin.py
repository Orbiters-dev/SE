from django.contrib import admin
from .models import (
    ShopifyOrdersDaily, AmazonSalesDaily, AmazonAdsDaily, AmazonCampaigns,
    MetaAdsDaily, MetaCampaigns, GoogleAdsDaily, GA4Daily, KlaviyoDaily,
)

for model in [
    ShopifyOrdersDaily, AmazonSalesDaily, AmazonAdsDaily, AmazonCampaigns,
    MetaAdsDaily, MetaCampaigns, GoogleAdsDaily, GA4Daily, KlaviyoDaily,
]:
    admin.site.register(model)
