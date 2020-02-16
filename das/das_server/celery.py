from __future__ import absolute_import
import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from django.conf import settings

from celery.signals import setup_logging
from kombu import Exchange, Queue


# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'das_server.settings')
app = Celery('das_server')
# Using a string here means the worker will not have to
# pickle the object when using Windows.

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

default_exchange = Exchange(app.conf.task_default_exchange)
app.autodiscover_tasks()

# Celery 4 changed from UPPERCASE to lower with new names. we've updated them here, but not yet in settings.py
# We want input from chis d et al.
# read more here: http://docs.celeryproject.org/en/latest/userguide/configuration.html?highlight=CELERY_DEFAULT_QUEUE#std:setting-beat_schedule
# Defining queues
app.conf.task_queues = (
    Queue(app.conf.task_default_queue, default_exchange,
          routing_key=app.conf.task_default_routing_key),
    Queue('realtime_p1', default_exchange, routing_key='realtime.tasks.p1'),
    Queue('realtime_p2', default_exchange, routing_key='realtime.tasks.p2'),
    Queue('realtime_p3', default_exchange, routing_key='realtime.tasks.p3'),
    Queue('analyzers', default_exchange, routing_key='analyzers.tasks'),
    Queue('mapping', default_exchange, routing_key='mapping.tasks'),
    Queue('maintenance', default_exchange, routing_key='maintenance.tasks'),
)


app.conf.task_routes = {
    'rt_api.tasks.handle_emit_data': {'queue': 'realtime_p1', },
    'rt_api.tasks.handle_new_event': {'queue': 'realtime_p2', },
    'rt_api.tasks.handle_update_event': {'queue': 'realtime_p2', },
    'rt_api.tasks.handle_delete_event': {'queue': 'realtime_p3', },
    'rt_api.tasks.handle_new_source_observation': {'queue': 'realtime_p3', },
    'rt_api.tasks.handle_new_subject_observation': {'queue': 'realtime_p3', },
    'rt_api.tasks.broadcast_service_status': {'queue': 'realtime_p1'},
    'observations.tasks.handle_source_with_new_observations': {'queue': 'realtime_p2'},
    'observations.tasks.maintain_subjectstatus_for_subject': {'queue': 'maintenance'},
    'observations.tasks.maintain_observation_data': {'queue': 'maintenance'},
    'mapping.tasks.download_features_from_wfs': {'queue': 'mapping'},
    # Queue analyzer tasks separately.
    'analyzers.tasks.*': {'queue': 'analyzers', },

}


# Defining scheduled tasks.
# PLUGINS_INTERVAL is in seconds, and is the ticker interval for
# triggering plugin tasks.
PLUGINS_INTERVAL = 5 * 60
app.conf.beat_schedule = {
    'plugins': {
        'task': 'tracking.tasks.run_plugins',
        'schedule': timedelta(seconds=PLUGINS_INTERVAL),
        'kwargs': {'expire_subtasks': PLUGINS_INTERVAL},
        'options': {'expires': PLUGINS_INTERVAL},
    },

    'firms-plugins': {
        'task': 'tracking.tasks.schedule_firms_plugins',
        'schedule': timedelta(minutes=15),
        'options': {'expires': 15 * 60},
    },

    'subject-status-maintenance': {
        'task': 'observations.tasks.maintain_subjectstatus_all',
        'schedule': timedelta(hours=12),
    },

    'demo-plugins': {
        'task': 'tracking.tasks.run_demo_plugins',
        'schedule': timedelta(seconds=PLUGINS_INTERVAL),
        'options': {'expires': PLUGINS_INTERVAL},
    },

    'reports': {
        'task': 'reports.tasks.subjectsource_report',
        # 6 AM local time per settings.TIME_ZONE
        'schedule': crontab(hour=6, minute=0)
    },

    'service-status': {
        'task': 'rt_api.tasks.broadcast_service_status',
        'schedule': timedelta(seconds=15),
    },

    'redis-status': {
        'task': 'rt_api.tasks.check_redis_queues',
        'schedule': timedelta(seconds=60),
    },

    'observation-lag-report': {
        'task':  'reports.tasks.alert_lag_delay',
        'schedule': timedelta(minutes=30),
    },
    'silent-source-report': {
        'task': 'reports.tasks.queue_silent_source_report',
        'schedule': timedelta(minutes=60),
    },
    'routine-delete-observational-data': {
        'task': 'observations.tasks.maintain_observation_data',
        # 4 AM local time per settings.TIME_ZONE
        'schedule': crontab(hour=4, minute=0)

    },
    'refresh-event-details-view': {
        'task': 'activity.tasks.refresh_event_details_views_task',
        'args': ('Celery',),
        'schedule': timedelta(hours=1)
    },
    'publish-daily-site-metrics': {
        'task': 'das_server.tasks.publish_daily_site_metrics',
        # 1 AM daily
        'schedule': crontab(hour=1, minute=0)
    },
    'download-features-from-wfs': {
        'task': 'mapping.tasks.download_features_from_wfs',
        # 2 AM per settings.TIME_ZONE
        'schedule': crontab(hour=2, minute=0)
    },

}

# Patch Celery's configuration with some attributes that Celery_once will
# use to control task creation.

app.conf.ONCE = {
    'backend': 'celery_once.backends.Redis',
    'settings': {

        # Co-opt the URL for Celery to use for storing celery_once semaphores.
        'url': settings.CELERY_BROKER_URL,

        # three minutes, default expiration for a celery_once semaphore.
        'default_timeout': 60 * 3
    }
}


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


@setup_logging.connect
def das_server_logging(loglevel, **kwargs):
    from das_server.log import init_logging
    init_logging()
