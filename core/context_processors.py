import os

from django.conf import settings


def feedback_form(request):
    return {
        "FEEDBACK_FORM_URL": getattr(settings, "FEEDBACK_FORM_URL", "") or "",
    }


def carto_basemap_api_key(request):
    return {"carto_basemap_api_key": os.environ.get("CARTO_BASEMAP_API_KEY", "")}
