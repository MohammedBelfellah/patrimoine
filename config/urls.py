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
# Media: /media/ only when files live on disk. Supabase Storage uses full MEDIA_URL to the bucket (no mount needed).
_use_disk_media = not getattr(settings, "USE_SUPABASE_MEDIA", False)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    if _use_disk_media and settings.MEDIA_URL.startswith("/"):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif _use_disk_media:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
