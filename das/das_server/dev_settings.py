from .local_settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'dev_dasdb',
        'USER': 'postgres',
        'HOST': 'at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com',
        'PASSWORD': 'V68a2oRNYtMj',
        'CONN_MAX_AGE': 0,
        'TEST': {
            'SERIALIZE': False,
        }
    },
}

