__author__ = 'chris'
from celery.schedules import crontab
from datetime import timedelta
from kombu import Exchange, Queue

# CELERY
BROKER_URL = 'redis://localhost:6379'
CELERY_RESULT_BACKEND = BROKER_URL
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ENABLE_UTC = True
CELERY_TIMEZONE = 'US/Pacific'

CELERY_RESULT_PERSISTENT = False
CELERY_TASK_RESULT_EXPIRES = 300
CELERY_IGNORE_RESULT = True
CELERY_STORE_ERRORS_EVEN_IF_IGNORED = True
# TODO: update in production
CELERYD_PREFETCH_MULTIPLIER = 1
# Enables error emails.
CELERY_SEND_TASK_ERROR_EMAILS = False

# Name and email addresses of recipients
ADMINS = (
    ("Chris Doehring", "chrisdo@vulcan.com"),
)

# Email address used as sender (From field).
SERVER_EMAIL = "chrisdo@vulcan.com"

# Mailserver configuration
EMAIL_HOST = "hurricane.corp.vnw.com"
EMAIL_PORT = 25

BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': 3600,
    'fanout_prefix': True
}


# Defining queues
CELERY_QUEUES = (
    Queue('default', Exchange('default')),
)

# CELERY_ROUTES = {
#     'activity.celery.debug_task': {'routing_key': 'default'},
#     'data_input.tasks.source_update_task': {
#         'routing_key': 'observations.update',
#     }
# }

CELERY_DEFAULT_QUEUE = 'default'
CELERY_DEFAULT_EXCHANGE = 'default'
CELERY_DEFAULT_ROUTING_KEY = 'default'


# Defining scheduled tasks.
CELERYBEAT_SCHEDULE = {
    'plugins': {
      'task': 'tracking.tasks.run_all_source_plugins',
        'schedule': timedelta(minutes=29),
    },
    'demo-plugins': {
      'task': 'tracking.tasks.run_demo_plugins',
        'schedule': timedelta(minutes=5),
    },
}


