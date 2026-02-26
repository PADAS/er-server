"""
Used in our production docker images
"""

import os

from .settings import (
    BASE_DIR,
    CACHES,
    DEFAULT_CACHE_ALIAS,
    REDIS_SERVER,
    SHARED_CACHE_ALIAS,
    UPLOAD_SESSION_CACHE_ALIAS,
    env,
)

CACHES[DEFAULT_CACHE_ALIAS] = {
    "BACKEND": "django_redis.cache.RedisCache",
    "LOCATION": REDIS_SERVER,
    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    "KEY_FUNCTION": "utils.tenant.cache.make_cache_key",
}

CACHES[SHARED_CACHE_ALIAS] = {
    "BACKEND": "django_redis.cache.RedisCache",
    "LOCATION": REDIS_SERVER,
    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    "KEY_PREFIX": "shared",
}

CACHES[UPLOAD_SESSION_CACHE_ALIAS] = {
    "BACKEND": "django_redis.cache.RedisCache",
    "LOCATION": REDIS_SERVER,
    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    "KEY_PREFIX": "upload_session",
}


MEDIA_ROOT = "/user-uploads"
MEDIA_URL = "http://localhost:8000/media/user-uploads/"
DOCS_ROOT = os.path.join(BASE_DIR, "sphinx_docs")

SECRET_KEY = "aefefsfees"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("ENABLE_DEBUG", False)
TEMPLATE_DEBUG = env.bool("ENABLE_DEBUG", False)
DEV = env.bool("ENABLE_DEV", False)
ENABLE_SILK = env.bool("ENABLE_SILK", False)

SHOW_TRACK_DAYS = env.int("SHOW_TRACK_DAYS", 14)
DEFAULT_EVENT_FILTER_FROM_DAYS = env.int("DEFAULT_EVENT_FILTER_FROM_DAYS", -1)
DEFAULT_PATROL_FILTER_FROM_DAYS = env.int("DEFAULT_PATROL_FILTER_FROM_DAYS", -1)
SHOW_STATIONARY_SUBJECTS_ON_MAP = env.bool("SHOW_STATIONARY_SUBJECTS_ON_MAP", True)

TIME_ZONE = env.str("TIME_ZONE", "America/Los_Angeles")

SERVER_FQDN = env.str("FQDN", "")

# Re-use the server's domain-name as a folder for daily-report template.
DAILY_REPORT_TEMPLATE_SUBFOLDER = SERVER_FQDN

# Build a list to include legacy names for APN, FZS and WPS sites. This will be temporary
# during a period when clients and users might still be browsing to our
# old partner subdomains.
SERVER_NAMES = [
    SERVER_FQDN,
    "localhost:9000",
]

# Allow providing a list of alternate server names on environment.
# export ALT_SERVER_NAMES=foo.bar.org,bar.baz.org
ALT_SERVER_NAMES = env.list("ALT_SERVER_NAMES", default=[])
SERVER_NAMES.extend(ALT_SERVER_NAMES)

# Django allowed-hosts
ALLOWED_HOSTS = SERVER_NAMES

CORS_ALLOW_CREDENTIALS = True
# CORS_ORIGIN_ALLOW_ALL is deprecated, CORS_ALLOW_ALL_ORIGINS replaces it
CORS_ORIGIN_ALLOW_ALL = env.bool("CORS_ORIGIN_ALLOW_ALL", False)
CORS_ALLOW_ALL_ORIGINS = CORS_ORIGIN_ALLOW_ALL

# Rest and realtime API allowed hosts.
# CORS_ORIGIN_WHITELIST is deprecated, CORS_ALLOWED_ORIGINS replaces it
CORS_ALLOWED_ORIGINS = [f"{prefix}{servername}" for servername in SERVER_NAMES for prefix in ("http://", "https://")]
CORS_ORIGIN_WHITELIST = CORS_ALLOWED_ORIGINS

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CSRF_TRUSTED_ORIGINS format differs between Django versions:
# - Django 3.2 and earlier: expects domains WITHOUT schemes (e.g., "example.com")
# - Django 4.0+: requires full URLs WITH schemes (e.g., "https://example.com")
# Since we're on Django 3.2, use SERVER_NAMES directly (domains without schemes)
CSRF_TRUSTED_ORIGINS = list(SERVER_NAMES)


STATIC_ROOT = env.str("STATIC_ROOT", "/var/www/static/")

# TODO can use aws mail short term, until we source a commercial mailer
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
AWS_SES_REGION_NAME = "us-west-2"
AWS_SES_REGION_ENDPOINT = "email.us-west-2.amazonaws.com"
# the address to send notification emails from
# TODO - Do we need both fields?
FROM_EMAIL = env.str("FROM_EMAIL", "notifications@pamdas.org")
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", "notifications@earthranger.com")
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", "info@pamdas.org")
EMAIL_HOST = env.str("EMAIL_HOST", "email-smtp.us-west-2.amazonaws.com")
EMAIL_HOST_PASSWORD = env.str("EMAIL_PASSWORD", "")
EMAIL_USE_TLS = True
EMAIL_PORT = env.int("EMAIL_PORT", 2587)

DAILY_REPORT_ENABLED = env.bool("DAILY_REPORT_ENABLED", False)

EXPORT_KML_ENABLED = env.bool("KML_EXPORT", True)
KML_OVERLAY_IMAGE = env.str("KML_OVERLAY_IMAGE", None)
KML_FEED_TITLE = env.str("KML_FEED_TITLE", KML_FEED_TITLE)

DATABASES = {
    "default": {
        "ENGINE": "utils.db.backends.postgis",
        "NAME": env.str("DB_NAME", "das"),
        "USER": env.str("DB_USER", "das"),
        "HOST": env.str("DB_HOST", "postgis"),
        "PORT": env.str("DB_PORT", "5432"),
        "PASSWORD": env.str("DB_PASSWORD", "password"),
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {"application_name": env.str("APPLICATION_NAME", "api")},
    },
}

# use these when you want to send SMS from kenya
# TODO - set sms provider by type
SENDSMS_AFRICAS_TALKING_USERNAME = env.str("SMS_ID", "")
SENDSMS_AFRICAS_TALKING_API_KEY = env.str("SMS_TOKEN", "")

DEFAULT_FILE_STORAGE = "core.storages.TenantGoogleCloudStorage"
GS_BUCKET_NAME = env.str("GS_BUCKET_NAME", "earthranger-uploads-default")

EUS_SETTINGS = {
    # 'zendesk' or 'email'
    "type": env.str("EUS_TYPE", "email"),
    "name": env.str("EUS_NAME", "eus test user"),
    "email": env.str("EUS_EMAIL", "eus_test@pamdas.org"),
    "organization": env.str("EUS_ORG", "pamdas.org"),
}

ALERTS_ENABLED = env.bool("ALERTS_ENABLED", True)
PATROL_ENABLED = env.bool("PATROL_ENABLED", True)
ACCEPT_EULA = env.bool("ACCEPT_EULA", False)
GS_BLOB_CHUNK_SIZE = env.int("GS_BLOB_CHUNK_SIZE", 10485760)
SUBJECT_REGION_ENABLED = env.bool("SUBJECT_REGION_ENABLED", True)

UI_SITE_NAME = f"EarthRanger {SERVER_FQDN}"
UI_SITE_URL = f"https://{SERVER_FQDN}"

if ENABLE_SILK:
    INSTALLED_APPS += ("silk",)
    SILK_MIDDLEWARE = "silk.middleware.SilkyMiddleware"
    if "silk" in INSTALLED_APPS and SILK_MIDDLEWARE not in MIDDLEWARE:
        atindex = MIDDLEWARE.index("django.contrib.sessions.middleware.SessionMiddleware") + 1
        MIDDLEWARE = list(MIDDLEWARE)
        MIDDLEWARE.insert(atindex, SILK_MIDDLEWARE)
        MIDDLEWARE = tuple(MIDDLEWARE)

        SILKY_PYTHON_PROFILER = True
        SILKY_AUTHENTICATION = True
        SILKY_MAX_RESPONSE_BODY_SIZE = 2048
        SILKY_MAX_REQUEST_BODY_SIZE = -1
        SILKY_META = True
        SILKY_ANALYZE_QUERIES = True
        SILKY_EXPLAIN_FLAGS = {"format": "JSON", "costs": True}

# Django Debug Toolbar Settings enabled if DEV=True
if DEV:
    INSTALLED_APPS += ("debug_toolbar",)
    DEBUG_TOOLBAR_APP = "debug_toolbar.middleware.DebugToolbarMiddleware"
    if "debug_toolbar" in INSTALLED_APPS and DEBUG_TOOLBAR_APP not in MIDDLEWARE:
        DEBUG = DEV = True
        atindex = MIDDLEWARE.index("django.contrib.sessions.middleware.SessionMiddleware") + 1
        MIDDLEWARE = list(MIDDLEWARE)
        MIDDLEWARE.insert(atindex, DEBUG_TOOLBAR_APP)
        MIDDLEWARE = tuple(MIDDLEWARE)

        DEBUG_TOOLBAR_CONFIG = {
            "SHOW_TOOLBAR_CALLBACK": lambda x: True,
        }

GFW_CLUSTER_RADIUS = env.int("GFW_CLUSTER_RADIUS", 5)
GFW_BACKFILL_INTERVAL_DAYS = env.int("GFW_BACKFILL_INTERVAL_DAYS", 10)


TABLEAU_ENABLED = env.bool("TABLEAU_ENABLED", False)
TABLEAU_API_USERNAME = env.str("TABLEAU_API_USERNAME", None)
TABLEAU_API_PASSWORD = env.str("TABLEAU_API_PASSWORD", None)
TABLEAU_API_TOKEN = env.str("TABLEAU_API_TOKEN", None)
TABLEAU_DEFAULT_DASHBOARD = env.str("TABLEAU_DEFAULT_DASHBOARD", None)
# allow to override for testing
TABLEAU_SITE_ID = env.str("TABLEAU_SITE_ID", None)
TRACK_LENGTH = env.int("TRACK_LENGTH", 21)

# Google Analytics
GA_MEASUREMENT_ID = env.str("GA_MEASUREMENT_ID", "")

GEO_PERMISSION_RADIUS_METERS = env.int("GEO_PERMISSION_RADIUS_METERS", 3704)
GEO_PERMISSION_SPEED_KM_H = env.int("GEO_PERMISSION_SPEED_KM_H", 75)
GEO_PERMISSION_VIOLATION_BAN_DURATION_MIN = env.int("GEO_PERMISSION_VIOLATION_BAN_DURATION_MIN", 10)

# disable metrics on development pipelines
DISABLE_STATSD = SERVER_FQDN.lower().startswith("das-") or SERVER_FQDN.lower().startswith("era-")

ALERTS_RATE_LIMIT = env.int("ALERTS_RATE_LIMIT", 20)
