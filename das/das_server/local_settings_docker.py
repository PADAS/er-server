"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""
import platform
from .settings import *

SECRET_KEY = 'aefefsfees'
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
TEMPLATE_DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'das',
        'USER': 'das',
        'HOST': 'postgis',
        'PASSWORD': 'password',
    }
}


GEOS_LIBRARY_PATH = '/usr/local/lib/libgeos_c.so'
GDAL_LIBRARY_PATH = '/usr/lib/libgdal.so'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
DEV = True
ALLOWED_HOSTS = ['*']
CORS_ORIGIN_ALLOW_ALL = True
TIME_ZONE = 'US/Pacific'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

STATIC_URL = '/static/'

#add the path to your local copy of the das-web static root dir that contains index.html
#STATICFILES_DIRS = STATICFILES_DIRS + (os.path.join(BASE_DIR, 'www'),)

"""
We put test fixtures in a non-conventional place, so build a list of directories here to let Django
know where to find them.
Our convention is to include fixtures in <app_name>/tests/fixtures/
"""
_test_fixtures = ('%s/tests/fixtures' % x for x in ('observations',
                                                    'data_input',
                                                    'mapping',
                                                    'das_server'))
FIXTURE_DIRS = list(os.path.join(BASE_DIR, x) for x in _test_fixtures)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}


#MIDDLEWARE_CLASSES = MIDDLEWARE_CLASSES + ('django_ses',)

EMAIL_BACKEND = 'django_ses.SESBackend'
# can use console output for email in dev
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
AWS_SES_REGION_NAME = 'us-west-2'
AWS_SES_REGION_ENDPOINT = 'email.us-west-2.amazonaws.com'
# the address to send notification emails from
FROM_EMAIL = 'notifications@pamdas.org'
DEFAULT_FROM_EMAIL = 'notifications@pamdas.org'