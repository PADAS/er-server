from das_server.local_settings_docker import *  # noqa

SHOW_TRACK_DAYS = 16

TIME_ZONE = "US/Pacific"

PATROL_ENABLED = True

MEDIA_ROOT = "/tmp/"
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"


SERVER_FQDN = "zoo.com"

TMS_API = {
    "CLIENT": "core.tms.TestClient",
}

MEMORY_STORE = {
    "CLIENT": "utils.persistent.RedisStorageReadOnly",
    "HOST": "redis",
    "PORT": "6379",
    "DATABASE": "10",
    "API_KEY": "",
}

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
