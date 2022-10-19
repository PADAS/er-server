"""
Setting to run migrations, due the django-oauth-toolkit custom models,
migrations need to be run before overwrite variables in settings.
e.g. OAUTH2_PROVIDER_APPLICATION_MODEL = "core.DASApplication"

call migrations with:
    python manage.py migrate --settings=das_server.local_settings_oauth_migration

"""
from das_server.local_settings_docker import *  # noqa

del (
    OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL,
    OAUTH2_PROVIDER_APPLICATION_MODEL,
    OAUTH2_PROVIDER_GRANT_MODEL,
    OAUTH2_PROVIDER_ID_TOKEN_MODEL,
    OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL,
)
