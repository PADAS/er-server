from __future__ import absolute_import

import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from celery.signals import (setup_logging, task_failure, task_postrun,
                            task_prerun, task_revoked, task_success)
from kombu import Exchange, Queue

from django.conf import settings

import utils.stats

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
    'rt_api.tasks.handle_new_patrol': {'queue': 'realtime_p2', },
    'rt_api.tasks.handle_update_patrol': {'queue': 'realtime_p2', },
    'rt_api.tasks.handle_delete_patrol': {'queue': 'realtime_p3', },
    'activity.tasks.periodically_maintain_patrol_state': {'queue': 'realtime_p2'},
    'observations.tasks.handle_source_with_new_observations': {'queue': 'realtime_p2'},
    'observations.tasks.maintain_subjectstatus_for_subject': {'queue': 'maintenance'},
    'observations.tasks.maintain_observation_data': {'queue': 'maintenance'},
    'mapping.tasks.automate_download_features_from_wfs': {'queue': 'maintenance'},
    'mapping.tasks.load_features_from_wfs': {'queue': 'maintenance'},
    # Queue analyzer tasks separately.
    'analyzers.tasks.*': {'queue': 'analyzers', },
    'tracking.tasks.schedule_firms_plugins': {'queue': 'analyzers'},
    'tracking.tasks.run_firms_plugin': {'queue': 'analyzers'},

    'das_server.tasks.celerybeat_pulse': {'queue': 'realtime_p1', },

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
    "check-sources-threshold": {
        "task": "reports.tasks.run_check_sources_threshold",
        "schedule": timedelta(hours=1)
    },
    'routine-delete-observational-data': {
        'task': 'observations.tasks.maintain_observation_data',
        # 4 AM local time per settings.TIME_ZONE
        'schedule': crontab(hour=4, minute=0)

    },
    'refresh-event-details-view': {
        'task': 'activity.tasks.refresh_event_details_view_task',
        'args': ('Celery',),
        'schedule': timedelta(hours=1)
    },
    'publish-daily-site-metrics': {
        'task': 'das_server.tasks.publish_daily_site_metrics',
        # 1 AM daily
        'schedule': crontab(hour=1, minute=0)
    },
    'download-features-from-wfs': {
        'task': 'mapping.tasks.automate_download_features_from_wfs',
        # 2 AM per settings.TIME_ZONE
        'schedule': crontab(hour=2, minute=0)
    },
    'poll-gfw': {
        'task': 'analyzers.tasks.poll_gfw',
        # 3 AM per settings.TIME_ZONE
        'schedule': crontab(hour=3, minute=0)
    },
    # Run pulse routine frequently and on a high-priority queue.
    'beat-pulse': {
        'task': 'das_server.tasks.celerybeat_pulse',
        'schedule': timedelta(seconds=60)
    },
    'auto-resolve': {
        'task': 'activity.tasks.automatically_update_event_state',
        'schedule': timedelta(minutes=5)
    },
    'refresh_patrols_view': {
        'task': 'observations.tasks.refresh_patrols_view',
        'schedule': timedelta(hours=getattr(settings, 'PATROL_VIEW_REFRESH_HOURS', 1))
    },
    'poll_news_gcs_bucket': {
        'task': 'observations.tasks.poll_news_gcs_bucket',
        'schedule': timedelta(minutes=5)
    },
    'periodically_maintain_patrol_state': {
        'task': 'activity.tasks.periodically_maintain_patrol_state',
        'schedule': timedelta(minutes=1)
    }
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


@task_prerun.connect
def task_prerun_handler(task, *args, **kwargs):
    utils.stats.increment("task",
                          tags=[
                              f"name:{task.name}",
                              "state:prerun"])


@task_postrun.connect
def task_postrun_handler(task, *args, **kwargs):
    utils.stats.increment("task",
                          tags=[
                              f"name:{task.name}",
                              "state:postrun"])


@task_success.connect
def task_success_handler(sender, *args, **kwargs):
    utils.stats.increment("task",
                          tags=[
                              f"name:{sender.name}",
                              "state:success"])


@task_failure.connect
def task_failure_handler(sender, *args, **kwargs):
    utils.stats.increment("task",
                          tags=[
                              f"name:{sender.name}",
                              "state:failure"])


@task_revoked.connect
def task_revoked_handler(request, *args, **kwargs):
    utils.stats.increment("task",
                          tags=[
                              f"name:{request.name}",
                              "state:revoked"])
