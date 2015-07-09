"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""

from .settings import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

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
    }
}


# On Windows, install Shapely, then set the geos library path appropriately
#GEOS_LIBRARY_PATH = 'C:\python34\Lib\site-packages\shapely\DLLs\geos_c.dll'