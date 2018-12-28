"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""

from .settings import *
import os

MEDIA_ROOT = '/user-uploads'
MEDIA_URL = 'http://localhost:8000/media/user-uploads/'

SECRET_KEY = 'aefefsfees'
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
TEMPLATE_DEBUG = True

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
DEV = True
ALLOWED_HOSTS = ['*']
CORS_ORIGIN_ALLOW_ALL = True
TIME_ZONE = 'US/Pacific'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

STATIC_ROOT = '/var/www/static/'

# add the path to your local copy of the das-web static root dir that contains index.html
#STATICFILES_DIRS = STATICFILES_DIRS + (os.path.join(BASE_DIR, 'www'),)

# can use console output for email in dev
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
AWS_SES_REGION_NAME = 'us-west-2'
AWS_SES_REGION_ENDPOINT = 'email.us-west-2.amazonaws.com'
# the address to send notification emails from
FROM_EMAIL = 'notifications.demo@pamdas.org'
DEFAULT_FROM_EMAIL = 'notifications.demo@pamdas.org'
EMAIL_HOST_USER = 'AKIAJLH5VZD6IQWTWPQQ'
EMAIL_HOST = 'email-smtp.us-west-2.amazonaws.com'
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_USE_TLS = True
EMAIL_PORT = 2587

NOTIFY_HIGH_PRIORITY_EVENT = 'high_priority_alerts'
NOTIFY_MEDIUM_PRIORITY_EVENT = 'medium_priority_alerts'
NOTIFY_LOW_PRIORITY_EVENT = 'low_priority_alerts'

EXPORT_KML_ENABLED = True

USE_AZURE_STORAGE = os.getenv('USE_AZURE_STORAGE', 'false')

if USE_AZURE_STORAGE == 'true':
    # Azure storage - see https://django-storages.readthedocs.io/en/latest/backends/azure.html
    DEFAULT_FILE_STORAGE = 'storages.backends.azure_storage.AzureStorage'
    STATICFILES_STORAGE = 'storages.backends.azure_storage.AzureStorage'
    AZURE_ACCOUNT_NAME = os.getenv('STORAGE_ACCOUNT', '')
    AZURE_ACCOUNT_KEY = os.getenv('STORAGE_KEY', '')
    AZURE_CONTAINER = os.getenv('STORAGE_CONTAINER', '')
    # todo - add the blob storage keys here


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

SHOW_STATIONARY_SUBJECTS_ON_MAP = True
