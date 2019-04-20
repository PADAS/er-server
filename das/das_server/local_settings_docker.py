"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""

from .settings import *
import os
from utils import env

MEDIA_ROOT = '/user-uploads'
MEDIA_URL = 'http://localhost:8000/media/user-uploads/'

SECRET_KEY = 'aefefsfees'

# SECURITY WARNING: don't run with debug turned on in production!
# To simplify k8 deployment, set an .env for ENABLE_DEV when using
# docker compose
DEBUG = env.str_to_bool(os.getenv('ENABLE_DEBUG', False))
TEMPLATE_DEBUG = env.str_to_bool(os.getenv('ENABLE_DEBUG', False))
DEV = env.str_to_bool(os.getenv('ENABLE_DEV', False))

SHOW_TRACK_DAYS = int(os.getenv('SHOW_TRACK_DAYS', '14'))
SHOW_STATIONARY_SUBJECTS_ON_MAP = env.str_to_bool(os.getenv('SHOW_STATIONARY_SUBJECTS_ON_MAP', False))

TIME_ZONE = os.getenv('TIME_ZONE', 'US/Pacific')

# TODO - Import terraform generated FQDN
# CORS_ORIGN_FQDN = os.getenv('CORS_ORIGIN_FQDN')
# ALLOWED_HOSTS = ['localhost:9000','CORS_ORIGIN_FQDN,'localhost','*']
ALLOWED_HOSTS = ['*']
# TODO - Make this default to False
CORS_ORIGIN_ALLOW_ALL = env.str_to_bool(os.getenv('CORS_ORIGIN_ALLOW_ALL', False))
SERVER_FQDN = os.getenv('FQDN', '')
CORS_ORIGIN_WHITELIST = (
        'localhost:9000','http://localhost:9000', SERVER_FQDN, f'https://{SERVER_FQDN}', f'http://{SERVER_FQDN}'
    )

SESSION_COOKIE_SECURE = env.str_to_bool(os.getenv('SESSION_COOKIE_SECURE', True))
CSRF_COOKIE_SECURE = env.str_to_bool(os.getenv('CSRF_COOKIE_SECURE', True))
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

STATIC_ROOT = '/var/www/static/'

# add the path to your local copy of the das-web static root dir that contains index.html
#STATICFILES_DIRS = STATICFILES_DIRS + (os.path.join(BASE_DIR, 'www'),)

# TODO can use aws mail short term, until we source a commercial mailer
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
AWS_SES_REGION_NAME = 'us-west-2'
AWS_SES_REGION_ENDPOINT = 'email.us-west-2.amazonaws.com'
# the address to send notification emails from
# TODO - Do we need both fields?
FROM_EMAIL = os.getenv('FROM_EMAIL')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'email-smtp.us-west-2.amazonaws.com')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_USE_TLS = True
EMAIL_PORT = 2587

NOTIFY_HIGH_PRIORITY_EVENT = 'high_priority_alerts'
NOTIFY_MEDIUM_PRIORITY_EVENT = 'medium_priority_alerts'
NOTIFY_LOW_PRIORITY_EVENT = 'low_priority_alerts'

EXPORT_KML_ENABLED = True

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.getenv('DB_NAME', 'das'),
        'USER': os.getenv('DB_USER','das'),
        'HOST': os.getenv('DB_HOST', 'postgis'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'PASSWORD': os.getenv('DB_PASSWORD','password'),
    },
}

# use these when you want to send SMS from kenya
# TODO - set sms provider by type
SENDSMS_AFRICAS_TALKING_USERNAME = os.getenv('SMS_ID')
SENDSMS_AFRICAS_TALKING_API_KEY = os.getenv('SMS_TOKEN')

USE_AZURE_STORAGE = os.getenv('USE_AZURE_STORAGE', 'false')

if USE_AZURE_STORAGE == 'true':
    # Azure storage - see https://django-storages.readthedocs.io/en/latest/backends/azure.html
    DEFAULT_FILE_STORAGE = 'storages.backends.azure_storage.AzureStorage'
    STATICFILES_STORAGE = 'storages.backends.azure_storage.AzureStorage'
    AZURE_ACCOUNT_NAME = os.getenv('STORAGE_ACCOUNT', '')
    AZURE_ACCOUNT_KEY = os.getenv('STORAGE_ACCOUNT_KEY', '')
    AZURE_CONTAINER = os.getenv('STORAGE_CONTAINER', '')
    # enable SSL for Azure DBs
    DATABASES['default']['OPTIONS'] = {'sslmode': 'require'}

EUS_SETTINGS = {
    # 'zendesk' or 'email'
    'type': os.getenv('EUS_TYPE'),
    'name': os.getenv('EUS_NAME'),
    'email': os.getenv('EUS_EMAIL'),
    'organization': os.getenv('EUS_ORG')
}
