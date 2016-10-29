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

CELERY_DEFAULT_QUEUE = 'default'
CELERY_DEFAULT_EXCHANGE = 'default'
CELERY_DEFAULT_ROUTING_KEY = 'default'

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

default_exchange = Exchange(CELERY_DEFAULT_EXCHANGE)

# Defining queues
CELERY_QUEUES = (
    Queue(CELERY_DEFAULT_QUEUE, default_exchange, routing_key=CELERY_DEFAULT_ROUTING_KEY),
    Queue('realtime_p1', default_exchange, routing_key='realtime.tasks.p1'),
    Queue('realtime_p2', default_exchange, routing_key='realtime.tasks.p2'),
    Queue('realtime_p3', default_exchange, routing_key='realtime.tasks.p3'),
)

CELERY_ROUTES = {
    'rt_api.tasks.handle_emit_data': {'routing_key': 'realtime.tasks.p1'},
    'rt_api.tasks.handle_new_event': {'routing_key': 'realtime.tasks.p2'},
    'rt_api.tasks.handle_update_event': {'routing_key': 'realtime.tasks.p2'},
    'rt_api.tasks.handle_delete_event': {'routing_key': 'realtime.tasks.p3'},
    'rt_api.tasks.handle_new_source_observation': {'routing_key': 'realtime.tasks.p3'},
    'rt_api.tasks.handle_new_subject_observation': {'routing_key': 'realtime.tasks.p3'},
}


# Defining scheduled tasks.
CELERYBEAT_SCHEDULE = {
    'plugins': {
      'task': 'tracking.tasks.run_plugins',
        'schedule': timedelta(minutes=5),
    },
    'demo-plugins': {
      'task': 'tracking.tasks.run_demo_plugins',
        'schedule': timedelta(minutes=5),
    },
}


try:
    from das_server.local_celery_settings import *
except ImportError:
    pass

