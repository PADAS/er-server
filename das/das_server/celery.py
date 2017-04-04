from __future__ import absolute_import
import os
from datetime import timedelta

from celery import Celery
from celery.signals import setup_logging
from kombu import Exchange, Queue


# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'das_server.settings')
app = Celery('das_server')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

default_exchange = Exchange(app.conf.CELERY_DEFAULT_EXCHANGE)

# Defining queues
CELERY_QUEUES = (
    Queue(app.conf.CELERY_DEFAULT_QUEUE, default_exchange, routing_key=app.conf.CELERY_DEFAULT_ROUTING_KEY),
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

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


@setup_logging.connect
def das_server_logging(loglevel, **kwargs):
    from das_server.log import init_logging
    init_logging()
