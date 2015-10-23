"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""

from .settings import *
from .local_settings import *

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
        'NAME': 'dev_dasdb',
        'USER': 'postgres',
        'PASSWORD': 'V68a2oRNYtMj',
        'HOST': 'at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com',
    },
    # 'default': {
    #     'ENGINE': 'django.contrib.gis.db.backends.postgis',
    #     'NAME': 'chrisj2_dasdb',
    #     'USER': 'postgres',
    #     'PASSWORD': 'V68a2oRNYtMj',
    #     'HOST': 'at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com',
    # }
}


# On Windows, install Shapely, then set the geos library path appropriately
#GEOS_LIBRARY_PATH = 'C:\python34\Lib\site-packages\shapely\DLLs\geos_c.dll'

"""
We put test fixtures in a non-conventional place, so build a list of directories here to let Django
know where to find them.
Our convention is to include fixtures in <app_name>/tests/fixtures/
"""
_ = ('%s/tests/fixtures' % x for x in ('observations', 'data_input'))
FIXTURE_DIRS = list(os.path.join(BASE_DIR, x) for x in _)

'''
We're using apscheduler to run scheduled tasks.
See http://apscheduler.readthedocs.org/en/latest/userguide.html
This settings element defines how the BackgroundScheduler is configured.
'''
SCHEDULER = {
    'db_url': 'postgres://postgres:V68a2oRNYtMj@at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com:5432/chrisj_dasdb',
    'executors': {
        'default': {'type': 'threadpool', 'max_workers': 5},
        'processpool': {'type': 'processpool', 'max_workers': 4},
    },
    'job_defaults': {
        'coalesce': False,
        'max_instances': 3
    }

}
