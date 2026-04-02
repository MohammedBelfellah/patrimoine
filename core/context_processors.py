from django.conf import settings


def feedback_form(request):
    return {
        "FEEDBACK_FORM_URL": getattr(settings, "FEEDBACK_FORM_URL", "") or "",
    }
