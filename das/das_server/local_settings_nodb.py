from das_server.local_settings_docker import *  # fmt: skip

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "mydatabase",
    }
}

COLLECT_STATIC_NO_DB = True
