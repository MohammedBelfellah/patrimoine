from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve


def healthcheck(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", include("core.urls")),
    path("", include("patrimoine.urls")),
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
]

# Static: WhiteNoise serves STATIC_ROOT in production; django helper is for local dev parity.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # User uploads (MEDIA_ROOT). Railway disk is ephemeral — prefer object storage for production durability.
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
