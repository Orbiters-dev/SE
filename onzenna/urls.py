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

    # Monitoring
    path("tables/", views.list_tables, name="list_tables"),
]

