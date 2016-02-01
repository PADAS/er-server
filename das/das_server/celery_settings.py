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
        'schedule': timedelta(minutes=15),
    },
    # 'savannah': {
    #     'task': 'data_input.tasks.run_savannah',
    #     'schedule': timedelta(minutes=60),
    # },
    # 'awt-http': {
    #     'task': 'data_input.tasks.run_awt_http',
    #     'schedule': timedelta(minutes=53),
    # },
    # 'demo': {
    #     'task': 'data_input.tasks.run_demo',
    #     'schedule': timedelta(minutes=15),
    # },
    # 'firms': {
    #     'task': 'data_input.tasks.run_firms',
    #     'schedule': timedelta(minutes=31),
    # },
    # 'skygistics': {
    #     'task': 'data_input.tasks.run_skygistics',
    #     'schedule': timedelta(minutes=61),
    # },
    # 'inreach': {
    #     'task': 'data_input.tasks.run_inreach',
    #     'schedule': timedelta(minutes=23),
    # },
    # 'inreachkml': {
    #     'task': 'data_input.tasks.run_inreachkml',
    #     'schedule': timedelta(minutes=17),
    # },

}


