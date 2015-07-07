"""Put your local overrides in this and rename it to local_settings.py

call your project be overriding the settings file
 --settings=local_settings

"""

from .settings import *

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
# we use postgis, create the db from the spatial db template
# createdb -T template_postgis geodjango ENCODING 'utf8';
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'dasdb',
        'USER': 'postgres',
        'HOST': 'at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com',
    }
}
