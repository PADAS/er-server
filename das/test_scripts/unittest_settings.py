from das_server.local_settings_docker import *  # noqa

SHOW_TRACK_DAYS = 16

TIME_ZONE = "US/Pacific"

PATROL_ENABLED = True

MEDIA_ROOT = "/tmp/"
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

TMS_API = {
    "CLIENT": "core.tms.TestClient",
}

if env.bool("IS_OAUTH2_PROVIDER_MIGRATION", False):
    del (
        OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL,
        OAUTH2_PROVIDER_APPLICATION_MODEL,
        OAUTH2_PROVIDER_GRANT_MODEL,
        OAUTH2_PROVIDER_ID_TOKEN_MODEL,
        OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL,
    )
