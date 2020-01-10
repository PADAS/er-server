"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""

from .settings import *
import os

import environ
env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

# this reads the .env file in the local dir. You can
# specify specific envs if needed.
environ.Env.read_env()

MEDIA_ROOT = '/user-uploads'
MEDIA_URL = 'http://localhost:8000/media/user-uploads/'

SECRET_KEY = 'aefefsfees'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('ENABLE_DEBUG', False)
TEMPLATE_DEBUG = env.bool('ENABLE_DEBUG', False)
DEV = env.bool('ENABLE_DEV', False)

SHOW_TRACK_DAYS = env.int('SHOW_TRACK_DAYS', 14)
SHOW_STATIONARY_SUBJECTS_ON_MAP = env.bool('SHOW_STATIONARY_SUBJECTS_ON_MAP', False)

TIME_ZONE = env.str('TIME_ZONE', 'US/Pacific')

SERVER_FQDN = env.str('FQDN', '')
ALLOWED_HOSTS = ['localhost:9000', SERVER_FQDN,'localhost','*']
# TODO - Make this default to False
CORS_ORIGIN_ALLOW_ALL = env.bool('CORS_ORIGIN_ALLOW_ALL', True)

CORS_ORIGIN_WHITELIST = (
        'localhost:9000','http://localhost:9000', SERVER_FQDN, f'https://{SERVER_FQDN}', f'http://{SERVER_FQDN}'
    )
CORS_REPLACE_HTTPS_REFERER = env.bool('CORS_REPLACE_HTTPS_REFERER', True)

SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', True)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = ('localhost:9000', SERVER_FQDN)

STATIC_ROOT = '/var/www/static/'

# add the path to your local copy of the das-web static root dir that contains index.html
#STATICFILES_DIRS = STATICFILES_DIRS + (os.path.join(BASE_DIR, 'www'),)

# TODO can use aws mail short term, until we source a commercial mailer
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
AWS_SES_REGION_NAME = 'us-west-2'
AWS_SES_REGION_ENDPOINT = 'email.us-west-2.amazonaws.com'
# the address to send notification emails from
# TODO - Do we need both fields?
FROM_EMAIL = env.str('FROM_EMAIL', '')
DEFAULT_FROM_EMAIL = env.str('DEFAULT_FROM_EMAIL', '')
EMAIL_HOST_USER = env.str('EMAIL_HOST_USER', '')
EMAIL_HOST = env.str('EMAIL_HOST', 'email-smtp.us-west-2.amazonaws.com')
EMAIL_HOST_PASSWORD = env.str('EMAIL_PASSWORD', '')
EMAIL_USE_TLS = True
EMAIL_PORT = env.int('EMAIL_PORT', 2587)

NOTIFY_HIGH_PRIORITY_EVENT = 'high_priority_alerts'
NOTIFY_MEDIUM_PRIORITY_EVENT = 'medium_priority_alerts'
NOTIFY_LOW_PRIORITY_EVENT = 'low_priority_alerts'

EXPORT_KML_ENABLED = env.bool('KML_EXPORT', True)

DATABASES = {
    'default': {
        # 'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'ENGINE': 'core.databases.postgis',
        'NAME': env.str('DB_NAME', 'das'),
        'USER': env.str('DB_USER','das'),
        'HOST': env.str('DB_HOST', 'postgis'),
        'PORT': env.str('DB_PORT', '5432'),
        'PASSWORD': env.str('DB_PASSWORD','password'),
    },
}

# use these when you want to send SMS from kenya
# TODO - set sms provider by type
SENDSMS_AFRICAS_TALKING_USERNAME = env.str('SMS_ID', '')
SENDSMS_AFRICAS_TALKING_API_KEY = env.str('SMS_TOKEN', '')

# TODO: Use variables for these values (first of all Bucket Name).
DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
GS_BUCKET_NAME = 'earthranger-das-4765'
GS_AUTO_CREATE_BUCKET = True

EUS_SETTINGS = {
    # 'zendesk' or 'email'
    'type': env.str('EUS_TYPE', 'email'),
    'name': env.str('EUS_NAME', 'eus test user'),
    'email': env.str('EUS_EMAIL', 'eus_test@pamdas.org'),
    'organization': env.str('EUS_ORG', 'pamdas.org')
}

ALERTS_ENABLED = env.bool('ALERTS_ENABLED', True)

# Django Debug Toolbar Settings enabled if DEV=True
if DEV:
    INSTALLED_APPS += ('debug_toolbar',)

    DEBUG_TOOLBAR_APP = 'debug_toolbar.middleware.DebugToolbarMiddleware'
    if 'debug_toolbar' in INSTALLED_APPS and DEBUG_TOOLBAR_APP not in MIDDLEWARE:
        DEBUG = DEV = True
        atindex = MIDDLEWARE.index('django.contrib.sessions.middleware.SessionMiddleware') + 1
        MIDDLEWARE = list(MIDDLEWARE)
        MIDDLEWARE.insert(atindex, DEBUG_TOOLBAR_APP)
        MIDDLEWARE = tuple(MIDDLEWARE)

    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda x: True,
    }
