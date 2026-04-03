from django.urls import path
from . import views

app_name = "onzenna"

urlpatterns = [
    # Users
    path("users/", views.create_user, name="create_user"),
    path("users/<uuid:user_id>/", views.get_or_update_user, name="get_or_update_user"),

    # Onboarding
    path("onboarding/", views.save_onboarding, name="save_onboarding"),
    path("onboarding/<uuid:user_id>/", views.get_onboarding, name="get_onboarding"),

    # Engagement
    path("engagement/", views.log_engagement, name="log_engagement"),
    path("engagement/<uuid:user_id>/", views.get_engagement, name="get_engagement"),

    # Recommendations
    path("recommendations/<uuid:user_id>/", views.get_or_update_recommendations, name="get_or_update_recommendations"),

    # Surveys
    path("loyalty-survey/", views.save_loyalty_survey, name="save_loyalty_survey"),
    path("creator-survey/", views.save_creator_survey, name="save_creator_survey"),

    # Status
    path("status/<uuid:user_id>/", views.get_status, name="get_status"),

    # Gifting Applications
    path("gifting/save/", views.save_gifting, name="save_gifting"),
    path("gifting/update/", views.update_gifting, name="update_gifting"),
    path("gifting/list/", views.list_gifting, name="list_gifting"),

    # Influencer Outreach (Outbound / Pathlight)
    path("outreach/save/", views.save_outreach, name="save_outreach"),
    path("outreach/update/", views.update_outreach, name="update_outreach"),
    path("outreach/list/", views.list_outreach, name="list_outreach"),

    # Gmail RAG Contact Lookup
    path("gmail-rag/check-contact/", views.check_gmail_contact, name="check_gmail_contact"),
    path("gmail-rag/bulk-check/", views.bulk_check_gmail_contacts, name="bulk_check_gmail_contacts"),
    path("gmail-rag/sync/", views.sync_gmail_contacts, name="sync_gmail_contacts"),

    # Pipeline Config
    path("pipeline/config/today/", views.get_pipeline_config_today, name="pipeline_config_today"),
    path("pipeline/config/history/", views.pipeline_config_history, name="pipeline_config_history"),
    path("pipeline/config/<str:config_date>/", views.get_or_save_pipeline_config, name="pipeline_config_date"),

    # Pipeline Creators (CRM Dashboard)
    path("pipeline/creators/stats/", views.pipeline_creators_stats, name="pipeline_creators_stats"),
    path("pipeline/creators/bulk-status/", views.pipeline_creators_bulk_status, name="pipeline_creators_bulk_status"),
    path("pipeline/creators/claim-approved/", views.pipeline_creators_claim_approved, name="pipeline_creators_claim_approved"),
    path("pipeline/creators/<uuid:creator_id>/", views.pipeline_creator_detail, name="pipeline_creator_detail"),
    path("pipeline/creators/", views.pipeline_creators_list, name="pipeline_creators_list"),

    # Backfill Language → Country (batch-level, from Syncly sheet)
    path("pipeline/creators/backfill-language/", views.backfill_language, name="backfill_language"),

    # Pipeline Conversations (email thread tracking)
    path("pipeline/conversations/", views.pipeline_conversations, name="pipeline_conversations"),

    # Pipeline Execution Log
    path("pipeline/execution/log/", views.pipeline_execution_log, name="pipeline_execution_log"),

    # Pipeline Syncly Discovery Import
    path("pipeline/creators/import-discovery/", views.import_syncly_discovery, name="import_syncly_discovery"),

    # Email Reply Config (n8n + dashboard)
    path("pipeline/email-config/", views.email_config_list, name="email_config_list"),
    path("pipeline/email-config/<str:brand>/", views.email_config_detail, name="email_config_detail"),
    path("pipeline/faq/", views.faq_list, name="faq_list"),
    path("pipeline/faq/<uuid:faq_id>/", views.faq_detail, name="faq_detail"),
    path("pipeline/reply-log/", views.reply_log_create, name="reply_log"),

    # Discovery Posts (JP/US content discovery pipeline)
    path("discovery/posts/stats/", views.discovery_posts_stats, name="discovery_posts_stats"),
    path("discovery/posts/bulk-update/", views.discovery_posts_bulk_update, name="discovery_posts_bulk_update"),
    path("discovery/posts/<uuid:post_id>/", views.discovery_post_detail, name="discovery_post_detail"),
    path("discovery/posts/", views.discovery_posts_list, name="discovery_posts_list"),

    # Monitoring
    path("tables/", views.list_tables, name="list_tables"),
]

