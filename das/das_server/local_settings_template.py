"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""
import itertools
import os
import platform

from .settings import *

DEV = True
DEBUG = True
TEMPLATE_DEBUG = True
TIME_ZONE = 'US/Pacific'

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
        'USER': 'das',
        'HOST': 'localhost',
        'PORT': 5432,
        'PASSWORD': 'password',
        'CONN_MAX_AGE': 0,
    },
}

APPEND_SLASH = False
MAPPING_FEATURES_V2 = True
ACCEPT_EULA = False
UI_SITE_NAME = 'EarthRanger local dev'
UI_SITE_URL = 'http://localhost:8000'
SERVER_FQDN = os.getenv('FQDN', 'localhost:8000')
PATROL_ENABLED = True
SUBJECT_REGION_ENABLED = True
KML_OVERLAY_IMAGE = "ste_overlay_image.png"

MEDIA_ROOT = '/tmp/user-uploads'
MEDIA_URL = 'http://localhost:8000/media/user-uploads/'

RASTER_WORKDIR = '\\tmp\\raster'

REDIS_SERVER = "redis://host.docker.internal:6379"
REALTIME_BROKER_URL = f"{REDIS_SERVER}/2"
REALTIME_BROKER_OPTIONS = {'max_connections': 200}
PUBSUB_BROKER_URL = f"{REDIS_SERVER}/1"
PUBSUB_BROKER_OPTIONS = {'max_connections': 200}

# Celery Settings
CELERY_BROKER_URL = REDIS_SERVER

CELERY_RESULT_BACKEND = CELERY_BROKER_URL

INTERNAL_IPS = ('127.0.0.1', '10.0.106.1', 'localhost')
MIDDLEWARE = ('debug_toolbar.middleware.DebugToolbarMiddleware',)\
    + MIDDLEWARE
INSTALLED_APPS = tuple(itertools.takewhile(lambda x: x != 'django.contrib.staticfiles', INSTALLED_APPS))\
    + ('debug_toolbar',)\
    + tuple(itertools.dropwhile(lambda x: x !=
            'django.contrib.staticfiles', INSTALLED_APPS))


def show_toolbar(request):
    return True


DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": show_toolbar,
}

# override GDAL library location as needed,
# you won't need to when using the .devcontainer
#GEOS_LIBRARY_PATH = '/usr/local/lib/libgeos_c.so'
#GDAL_LIBRARY_PATH = '/usr/lib/libgdal.so'
if platform.system().lower() == 'windows':
    # On Windows, after pip install GDAL, set the geos library path
    # appropriately
    GEOS_LIBRARY_PATH = 'C:\projects\das\dasvir\Lib\site-packages\osgeo\geos_c.dll'
    GDAL_LIBRARY_PATH = 'C:\projects\das\dasvir\Lib\site-packages\osgeo\gdal202.dll'
    # also set environment variables
    # GDAL_DATA=C:\projects\das\dasvir\Lib\site-packages\osgeo\data\gdal
    # GDAL_DRIVER_PATH=C:\projects\das\dasvir\Lib\site-packages\osgeo\gdalplugins
    # PATH=C:\projects\das\dasvir\Lib\site-packages\osgeo

SHOW_TRACK_DAYS = 3
SHOW_STATIONARY_SUBJECTS_ON_MAP = True
ANALYZER_SUBJECT_TYPES = []

STATIC_URL = '/static/'
# add the path to your local copy of the das-web static root dir that contains index.html
#STATICFILES_DIRS = STATICFILES_DIRS + (os.path.join(BASE_DIR, 'www'),)

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = (
    'http://127.0.0.1:9000',
    'http://localhost:9000',
    'http://localhost:8000'
)


SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CSRF_TRUSTED_ORIGINS = ('localhost:9000',
                        'localhost',
                        '127.0.0.1:9000',
                        '127.0.0.1',
                        'localhost:8000')


SECURE_PROXY_SSL_HEADER = ('HOST', 'localhost',)

"""
We put test fixtures in a non-conventional place, so build a list of directories here to let Django
know where to find them.
Our convention is to include fixtures in <app_name>/tests/fixtures/
"""
_test_fixtures = ('%s/tests/fixtures' % x for x in ('observations',
                                                    'data_input',
                                                    'mapping',
                                                    'das_server',
                                                    'activity',))
FIXTURE_DIRS = list(os.path.join(BASE_DIR, x) for x in _test_fixtures)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# can use console output for email in dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# the address to send notification emails from
FROM_EMAIL = 'developer-notifications@pamdas.org'
DEFAULT_FROM_EMAIL = 'developer-notifications@pamdas.org'
