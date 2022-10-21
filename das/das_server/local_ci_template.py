from .settings import *

"""
In Jenkins:

python manage.py jenkins --enable-coverage --settings=das_server.local_settings.py
"""


DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'unittest_dasdb',
        'USER': 'postgres',
        'HOST': '127.0.0.1',
        'PASSWORD': 'postgres',
        'CONN_MAX_AGE': 5,
    },
}

global INSTALLED_APPS
INSTALLED_APPS = (
    'django_jenkins',
) + INSTALLED_APPS

JENKINS_TASKS = (
    'django_jenkins.tasks.run_pylint',
    'django_jenkins.tasks.run_pep8',
    'django_jenkins.tasks.run_sloccount'
)

_test_fixtures = ('%s/tests/fixtures' % x for x in ('observations',
                                                    'data_input',
                                                    'mapping',
                                                    'das_server'))
FIXTURE_DIRS = list(os.path.join(BASE_DIR, x) for x in _test_fixtures)

LOGGING['handlers']['file']['filename'] = './das.log'
