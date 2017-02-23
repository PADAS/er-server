"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""
import platform
from .settings import *

SECRET_KEY = ''
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
TEMPLATE_DEBUG = True

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
# we use postgis, create the db from the spatial db template
# CREATE DATABASE dasdb ENCODING 'utf8';
# \c dasdb;
# CREATE EXTENSION postgis;
# CREATE EXTENSION postgis_topology;
#
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'dasdb',
        'USER': 'postgres',
        'HOST': 'localhost',
        #'PASSWORD': '',
        'OPTIONS': {
            'sslmode': 'require',
        },
    },
    'vectronics': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'gpsplus_wildlife',
        'USER': 'vect_owner',
        'HOST': 'localhost',
        #'PASSWORD': '',
    }
}


GEOS_LIBRARY_PATH = '/usr/local/lib/libgeos_c.so'
GDAL_LIBRARY_PATH = '/usr/lib/libgdal.so'
if platform.system().lower() == 'windows':
    # On Windows, after pip install GDAL, set the geos library path appropriately
    GEOS_LIBRARY_PATH = 'C:\projects\das\dasvir\Lib\site-packages\osgeo\geos_c.dll'
    GDAL_LIBRARY_PATH = 'C:\projects\das\dasvir\Lib\site-packages\osgeo\gdal111.dll'
    #also set environment variables
    # GDAL_DATA=C:\projects\das\dasvir\Lib\site-packages\osgeo\data\gdal
    # GDAL_DRIVER_PATH=C:\projects\das\dasvir\Lib\site-packages\osgeo\gdalplugins
    # PATH=C:\projects\das\dasvir\Lib\site-packages\osgeo

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
DEV = True
ALLOWED_HOSTS = ['*']
CORS_ORIGIN_ALLOW_ALL = True
TIME_ZONE = 'US/Pacific'

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