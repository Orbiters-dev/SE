from django.urls import path
from . import views
from . import views_dashboard

app_name = "onzenna"

urlpatterns = [
    # Dashboards (server-rendered — replaces GitHub Pages HTML)
    path("pipeline/dashboard/", views_dashboard.pipeline_dashboard, name="pipeline_dashboard"),
    path("pipeline/dashboard/jp/", views_dashboard.pipeline_dashboard_jp, name="pipeline_dashboard_jp"),
    path("ppc/dashboard/", views_dashboard.ppc_dashboard, name="ppc_dashboard"),
    path("ppc/dashboard/<str:filename>", views_dashboard.ppc_data_js, name="ppc_data_js"),
    path("content/dashboard/", views_dashboard.content_dashboard, name="content_dashboard"),
    path("financial/dashboard/", views_dashboard.financial_dashboard, name="financial_dashboard"),
    path("financial/dashboard/fin_data.js", views_dashboard.fin_data_js, name="fin_data_js"),
    path("datapool/dashboard/", views_dashboard.datapool_dashboard, name="datapool_dashboard"),
    path("datapool/content/", views_dashboard.content_pool_dashboard, name="content_pool_dashboard"),

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
    path("pipeline/creators/datapool-stats/", views.datapool_stats, name="datapool_stats"),
    path("pipeline/content/", views.creator_content_list, name="creator_content_list"),
    path("pipeline/creators/filter-stats/", views.pipeline_filter_stats, name="pipeline_filter_stats"),
    path("pipeline/creators/bulk-status/", views.pipeline_creators_bulk_status, name="pipeline_creators_bulk_status"),
    path("pipeline/creators/cross-check/", views.pipeline_creators_cross_check, name="pipeline_creators_cross_check"),
    path("pipeline/creators/by-email/<path:email>/", views.pipeline_creator_by_email, name="pipeline_creator_by_email"),
    path("pipeline/creators/<uuid:creator_id>/", views.pipeline_creator_detail, name="pipeline_creator_detail"),
    path("pipeline/creators/", views.pipeline_creators_list, name="pipeline_creators_list"),

    # Pipeline Execution Log
    path("pipeline/execution/log/", views.pipeline_execution_log, name="pipeline_execution_log"),

    # Pipeline Syncly Discovery Import (legacy — reads gk_content_posts)
    path("pipeline/creators/import-discovery/", views.import_syncly_discovery, name="import_syncly_discovery"),

    # Syncly 3-step pipeline: Upload Excel → DB → Content Enrich
    path("pipeline/syncly/upload-excel/", views.syncly_upload_excel, name="syncly_upload_excel"),
    path("pipeline/syncly/import-excel/", views.syncly_import_excel, name="syncly_import_excel"),
    path("pipeline/syncly/status/", views.syncly_excel_status, name="syncly_excel_status"),

    # Syncly Autofill Emails (Apify + Firecrawl)
    path("pipeline/syncly/autofill-emails/", views.syncly_autofill_emails, name="syncly_autofill_emails"),

    # Pipeline Syncly Content Import (full: email + transcript + views + post_url)
    path("pipeline/creators/syncly-content-import/", views.syncly_content_import, name="syncly_content_import"),

    # JP Content Pipeline: Whisper CI trigger + transcript sync
    path("pipeline/run-ci/", views.run_ci_pipeline, name="run_ci_pipeline"),
    path("pipeline/creators/sync-transcripts/", views.sync_transcripts, name="sync_transcripts"),
    path("pipeline/creators/transcript-lang-check/", views.transcript_lang_check, name="transcript_lang_check"),
    path("pipeline/creators/email-verify/", views.email_verify, name="email_verify"),
    path("pipeline/creators/gk-transcripts/", views.gk_transcripts, name="gk_transcripts"),
    path("pipeline/creators/classify-region/", views.classify_region_by_transcript, name="classify_region"),

    # Email Reply Config (n8n + dashboard)
    path("pipeline/email-config/", views.email_config_list, name="email_config_list"),
    path("pipeline/email-config/<str:brand>/", views.email_config_detail, name="email_config_detail"),
    path("pipeline/faq/", views.faq_list, name="faq_list"),
    path("pipeline/faq/<uuid:faq_id>/", views.faq_detail, name="faq_detail"),
    path("pipeline/reply-log/", views.reply_log_create, name="reply_log"),

    # Pipeline Conversations (draft storage for n8n)
    path("pipeline/conversations/", views.pipeline_conversations, name="pipeline_conversations"),

    # Monitoring
    path("tables/", views.list_tables, name="list_tables"),
]

