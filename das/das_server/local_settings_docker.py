"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""

from .settings import *

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
EMAIL_HOST_USER = 'AKIAILB3C3SY2BHUP76Q'
EMAIL_HOST = 'email-smtp.us-west-2.amazonaws.com'
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_USE_TLS = True
EMAIL_PORT = 2587

NOTIFY_HIGH_PRIORITY_EVENT = 'high_priority_alerts'
NOTIFY_MEDIUM_PRIORITY_EVENT = 'medium_priority_alerts'
NOTIFY_LOW_PRIORITY_EVENT = 'low_priority_alerts'

EXPORT_KML_ENABLED = True
