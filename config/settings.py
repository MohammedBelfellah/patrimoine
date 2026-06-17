from pathlib import Path
import importlib.util
import os
from urllib.parse import parse_qsl, unquote, urlparse
import warnings
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

WHITENOISE_AVAILABLE = importlib.util.find_spec("whitenoise") is not None
if not WHITENOISE_AVAILABLE:
    WHITENOISE_AVAILABLE = False
    warnings.warn(
        "WhiteNoise is not installed. Static files compression and manifest storage are disabled.",
        RuntimeWarning,
    )

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"

allowed_hosts_raw = os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_raw.split(",") if host.strip()]
railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
# Railway sets RAILWAY_PUBLIC_DOMAIN; avoid 400 DisallowedHost if env list omits it.
if railway_public_domain and railway_public_domain not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(railway_public_domain)

csrf_trusted_origins_raw = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in csrf_trusted_origins_raw.split(",") if origin.strip()
]

if railway_public_domain:
    CSRF_TRUSTED_ORIGINS.append(f"https://{railway_public_domain}")

# Keep the list stable and avoid duplicates when both env vars include the same domain.
CSRF_TRUSTED_ORIGINS = sorted(set(CSRF_TRUSTED_ORIGINS))
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_API_URL = os.getenv(
    "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
).strip()

# Public feedback (Google Form). Override with env; set to false/0/off to hide the navbar button.
_feedback_raw = os.getenv(
    "FEEDBACK_FORM_URL",
    "https://forms.gle/LqXUASKzBPhthe2w6",
).strip()
FEEDBACK_FORM_URL = (
    ""
    if _feedback_raw.lower() in ("0", "false", "off", "disable", "none")
    else _feedback_raw
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "core.apps.CoreConfig",
    "patrimoine.apps.PatrimoineConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if WHITENOISE_AVAILABLE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.media",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.feedback_form",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

database_url = os.getenv("DATABASE_URL", "").strip()
if database_url:
    parsed_db_url = urlparse(database_url)
    db_options = dict(parse_qsl(parsed_db_url.query))
    if "sslmode" not in db_options:
        db_options["sslmode"] = os.getenv("POSTGRES_SSLMODE", "require")

    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.postgis",
            "NAME": parsed_db_url.path.lstrip("/")
            or os.getenv("POSTGRES_DB", "patrimoine"),
            "USER": (
                unquote(parsed_db_url.username)
                if parsed_db_url.username
                else os.getenv("POSTGRES_USER", "patrimoine")
            ),
            "PASSWORD": (
                unquote(parsed_db_url.password)
                if parsed_db_url.password
                else os.getenv("POSTGRES_PASSWORD", "patrimoine")
            ),
            "HOST": parsed_db_url.hostname or os.getenv("POSTGRES_HOST", "db"),
            "PORT": str(parsed_db_url.port or os.getenv("POSTGRES_PORT", "5432")),
            "OPTIONS": db_options,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.postgis",
            "NAME": os.getenv("POSTGRES_DB", "patrimoine"),
            "USER": os.getenv("POSTGRES_USER", "patrimoine"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "patrimoine"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "OPTIONS": {
                "sslmode": os.getenv("POSTGRES_SSLMODE", "prefer"),
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Casablanca"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

_staticfiles_backend = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if WHITENOISE_AVAILABLE
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)

# Supabase project URL (Dashboard → Settings → API → Project URL), not the Postgres host.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "").strip()
SUPABASE_S3_ACCESS_KEY_ID = os.getenv("SUPABASE_S3_ACCESS_KEY_ID", "").strip()
SUPABASE_S3_SECRET_ACCESS_KEY = os.getenv("SUPABASE_S3_SECRET_ACCESS_KEY", "").strip()

USE_SUPABASE_MEDIA = bool(
    SUPABASE_URL
    and SUPABASE_STORAGE_BUCKET
    and SUPABASE_S3_ACCESS_KEY_ID
    and SUPABASE_S3_SECRET_ACCESS_KEY
)

# Media files (uploads): local /media/ by default; optional Supabase Storage on Railway.
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

if USE_SUPABASE_MEDIA:
    AWS_ACCESS_KEY_ID = SUPABASE_S3_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY = SUPABASE_S3_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = SUPABASE_STORAGE_BUCKET
    AWS_S3_ENDPOINT_URL = f"{SUPABASE_URL}/storage/v1/s3"
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_ADDRESSING_STYLE = "path"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_VERIFY = True
    MEDIA_URL = (
        f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/"
    )
    STORAGES = {
        "default": {"BACKEND": "patrimoine.storage.SupabasePublicS3Storage"},
        "staticfiles": {"BACKEND": _staticfiles_backend},
    }
else:
    STATICFILES_STORAGE = _staticfiles_backend

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "public-map"

AUTHENTICATION_BACKENDS = [
    "core.auth_backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "15"))
EMAIL_SEND_ASYNC = os.getenv("EMAIL_SEND_ASYNC", "1") == "1"
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
BREVO_API_URL = os.getenv("BREVO_API_URL", "https://api.brevo.com/v3/smtp/email").strip()
BREVO_API_TIMEOUT = int(os.getenv("BREVO_API_TIMEOUT", "15"))
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "Geo Patrimoine Hub <noreply@geopatrimoinehub.com>"
)
SERVER_EMAIL = os.getenv("SERVER_EMAIL", "noreply@geopatrimoinehub.com")

# Railway/Reverse proxies forward scheme in this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
