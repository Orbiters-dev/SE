from django.urls import path
from . import views

app_name = "datakeeper"

urlpatterns = [
    path("save/", views.save_rows, name="save"),
    path("query/", views.query_rows, name="query"),
    path("tables/", views.list_tables, name="tables"),
    path("status/", views.status, name="status"),
]
