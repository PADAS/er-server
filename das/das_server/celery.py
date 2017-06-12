from __future__ import absolute_import
import os
from datetime import timedelta

from celery import Celery
from celery.signals import setup_logging
from kombu import Exchange, Queue


# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'das_server.settings')
app = Celery('das_server')
app.autodiscover_tasks()
# Using a string here means the worker will not have to
# pickle the object when using Windows.

app.config_from_object('django.conf:settings', namespace='CELERY')
default_exchange = Exchange(app.conf.task_default_exchange)
# Celery 4 changed from UPPERCASE to lower with new names. we've updated them here, but not yet in settings.py
# We want input from chis d et al.
# read more here: http://docs.celeryproject.org/en/latest/userguide/configuration.html?highlight=CELERY_DEFAULT_QUEUE#std:setting-beat_schedule
# Defining queues
app.conf.task_queues = (
    Queue(app.conf.task_default_queue, default_exchange, routing_key=app.conf.task_default_routing_key),
    Queue('realtime_p1', default_exchange, routing_key='realtime.tasks.p1'),
    Queue('realtime_p2', default_exchange, routing_key='realtime.tasks.p2'),
    Queue('realtime_p3', default_exchange, routing_key='realtime.tasks.p3'),
    Queue('analyzers', default_exchange, routing_key='analyzers.tasks'),
)

app.conf.task_routes = {
    'rt_api.tasks.handle_emit_data': {'routing_key': 'realtime.tasks.p1'},
    'rt_api.tasks.handle_new_event': {'routing_key': 'realtime.tasks.p2'},
    'rt_api.tasks.handle_update_event': {'routing_key': 'realtime.tasks.p2'},
    'rt_api.tasks.handle_delete_event': {'routing_key': 'realtime.tasks.p3'},
    'rt_api.tasks.handle_new_source_observation': {'routing_key': 'realtime.tasks.p3'},
    'rt_api.tasks.handle_new_subject_observation': {'routing_key': 'realtime.tasks.p3'},

    # Queue analyzer tasks separately.
    'analyzers.tasks.analyze_subject': {'routing_key': 'analyzers.tasks'},
}


# Defining scheduled tasks.
# PLUGINS_INTERVAL is in seconds, and is the ticker interval for triggering plugin tasks.
PLUGINS_INTERVAL = 5*60
app.conf.beat_schedule = {
    'plugins': {
      'task': 'tracking.tasks.run_plugins',
        'schedule': timedelta(seconds=PLUGINS_INTERVAL),
        'kwargs': {'expire_subtasks': PLUGINS_INTERVAL},
        'options': {'expires': PLUGINS_INTERVAL},
    },
    'demo-plugins': {
      'task': 'tracking.tasks.run_demo_plugins',
        'schedule': timedelta(seconds=PLUGINS_INTERVAL),
        'options': {'expires': PLUGINS_INTERVAL},
    },
}

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


@setup_logging.connect
def das_server_logging(loglevel, **kwargs):
    from das_server.log import init_logging
    init_logging()
