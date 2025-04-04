"""
Override of the `DATABASES` configuration to enable connection pooling via PgCat.
This config is based of the `local_settings_docker` settings.

WARNING:
This setting SHOULD NOT be used for running Django migrations as they will
fail for some DDL SQL queries. Migrations are required to use a direct DB
connection.
"""

from .local_settings_docker import *

# Direct connection to the primary instance of the database without any connection pooler
_DB_CONFIG_DIRECT = {
    "ENGINE": "utils.db.backends.postgis",
    "NAME": env.str("DB_NAME", "das"),
    "USER": env.str("DB_USER", "das"),
    "HOST": env.str("DB_HOST", "postgis"),
    "PORT": env.str("DB_PORT", "5432"),
    "PASSWORD": env.str("DB_PASSWORD", "das"),
    "DISABLE_SERVER_SIDE_CURSORS": True,
    "OPTIONS": {"application_name": env.str("APPLICATION_NAME", "api")},
}

# Connection pooler in transaction mode using reads/writes parsing
_DB_CONFIG_POOLER = {
    "ENGINE": "utils.db.backends.postgis",
    "NAME": env.str("DB_POOLER_NAME", "main"),
    "USER": env.str("DB_USER", "das"),
    "HOST": env.str("DB_POOLER_HOST", "pgcat"),
    "PORT": env.str("DB_POOLER_PORT", "6432"),
    "PASSWORD": env.str("DB_PASSWORD", "das"),
    "DISABLE_SERVER_SIDE_CURSORS": True,
    "OPTIONS": {"application_name": env.str("APPLICATION_NAME", "api")},
}

DATABASES = {
    "default": _DB_CONFIG_POOLER,
    "direct_db": _DB_CONFIG_DIRECT,
}
