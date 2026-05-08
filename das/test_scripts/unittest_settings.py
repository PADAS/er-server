from das_server.local_settings_docker import *  # noqa

# Silk profiling middleware adds its own DB queries (inserts, EXPLAIN ANALYZE,
# per-query counter updates) that corrupt CaptureQueriesContext counts in tests.
ENABLE_SILK = False
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "silk"]
MIDDLEWARE = [m for m in MIDDLEWARE if "silk" not in m.lower()]

SHOW_TRACK_DAYS = 16

TIME_ZONE = "America/Los_Angeles"

PATROL_ENABLED = True

MEDIA_ROOT = "/tmp/"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# django testrunner already uses this backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
VECTOR_TILE_CACHE_ALIAS = "vector_tiles"


SERVER_FQDN = "zoo.com"

TMS_API = {
    "CLIENT": "core.tms.TestClient",
}

TENANT_DOCUMENT_CACHE = {
    "CLIENT": "utils.persistent.RedisStorage",
    "HOST": "redis",
    "PORT": "6379",
    "DATABASE": "10",
    "API_KEY": "",
}

AUTH0_CUSTOM_DOMAIN = "tenant.auth0.com"
AUTH0_TENANT_DOMAIN = "tenant.auth0.com"
AUTH0_RESOURCE_SERVER = "https://example.com"

"""
We put test fixtures in a non-conventional place, so build a list of directories here to let Django
know where to find them.
Our convention is to include fixtures in <app_name>/tests/fixtures/
"""
_test_fixtures = (
    "%s/tests/fixtures" % x
    for x in (
        "observations",
        "data_input",
        "mapping",
        "das_server",
        "activity",
    )
)
FIXTURE_DIRS = list(os.path.join(BASE_DIR, x) for x in _test_fixtures)
