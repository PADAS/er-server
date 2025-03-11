"""
Override of the `DATABASES` configuration to enable connection pooling via PgCat.
This config is based of the `local_settings_docker` settings.

NOTE:
The connection pooler will be rolled out to our different services (RT, Celery,
etc) as we confirm that it works as expected in prod environments.

WARNING:
This setting SHOULD NOT be used for running Django migrations as they will
fail for some DDL SQL queries.
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

# Connection pooler in session mode that directs all traffic to the primary instance
_DB_CONFIG_POOLER_PROXY_PRIMARY = {
    "ENGINE": "utils.db.backends.postgis",
    "NAME": env.str("DB_POOLER_PROXY_NAME", "proxy_primary"),
    "USER": env.str("DB_USER", "das"),
    "HOST": env.str("DB_POOLER_HOST", "pgcat"),
    "PORT": env.str("DB_POOLER_PORT", "6432"),
    "PASSWORD": env.str("DB_PASSWORD", "das"),
    "DISABLE_SERVER_SIDE_CURSORS": True,
    "OPTIONS": {"application_name": env.str("APPLICATION_NAME", "api")},
}

DATABASES = {
    # "default": _DB_CONFIG_POOLER_PROXY_PRIMARY,
    "default": _DB_CONFIG_POOLER,
    "proxy_primary": _DB_CONFIG_POOLER_PROXY_PRIMARY,
    "direct_db": _DB_CONFIG_DIRECT,
}
