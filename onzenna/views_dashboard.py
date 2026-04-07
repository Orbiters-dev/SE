"""Server-side rendered dashboards.

Replaces GitHub Pages HTML dashboards with Django templates
served from the same EC2 server. No CORS, no Basic Auth needed.
"""
import os
from pathlib import Path

from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_sameorigin

# Base directories for data JS / shared CSS files
_PPC_DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "ppc-dashboard"
_FIN_DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "financial-dashboard"
_SHARED_DIR = Path(__file__).resolve().parent.parent / "docs" / "shared"


@xframe_options_sameorigin
def pipeline_dashboard(request):
    """Pipeline CRM dashboard (US)."""
    return render(request, "onzenna/pipeline_dashboard.html")


@xframe_options_sameorigin
def pipeline_dashboard_jp(request):
    """Pipeline CRM dashboard (JP)."""
    return render(request, "onzenna/pipeline_dashboard_jp.html")


@xframe_options_sameorigin
def ppc_dashboard(request):
    """Amazon PPC Intelligence dashboard."""
    return render(request, "onzenna/ppc_dashboard.html")


@xframe_options_sameorigin
def content_dashboard(request):
    """Content Intelligence dashboard."""
    return render(request, "onzenna/content_dashboard.html")


@xframe_options_sameorigin
def financial_dashboard(request):
    """Financial KPIs dashboard (hub — embeds other dashboards via iframe)."""
    return render(request, "onzenna/financial_dashboard.html")


@xframe_options_sameorigin
def datapool_dashboard(request):
    """Creator Datapool Explorer — view-sorted table + composition charts."""
    return render(request, "onzenna/datapool_dashboard.html")


@xframe_options_sameorigin
def content_pool_dashboard(request):
    """Content Pool Explorer — browse CreatorContent posts."""
    return render(request, "onzenna/content_pool_dashboard.html")


def ppc_data_js(request, filename):
    """Serve PPC data JS files (data.js, pl_data.js, bt_data.js)."""
    allowed = {"data.js", "pl_data.js", "bt_data.js"}
    if filename not in allowed:
        raise Http404
    filepath = _PPC_DATA_DIR / filename
    if not filepath.is_file():
        raise Http404
    return HttpResponse(filepath.read_text(encoding="utf-8"), content_type="application/javascript")


def fin_data_js(request):
    """Serve Financial KPIs data (fin_data.js)."""
    filepath = _FIN_DATA_DIR / "fin_data.js"
    if not filepath.is_file():
        raise Http404
    return HttpResponse(filepath.read_text(encoding="utf-8"), content_type="application/javascript")


def dashboard_base_css(request):
    """Serve shared dashboard base CSS."""
    filepath = _SHARED_DIR / "dashboard_base.css"
    if not filepath.is_file():
        raise Http404
    return HttpResponse(filepath.read_text(encoding="utf-8"), content_type="text/css")
