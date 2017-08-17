import logging
from django.apps import apps
from das_server import celery
from tracking.models import *

logger = logging.getLogger(__name__)

EXPIRE_SUBTASKS = 300


@celery.app.task(bind=True)
def run_plugins(self, expire_subtasks=EXPIRE_SUBTASKS):
    for plugin_class in runnable_plugins:
        run_plugin_class.apply_async(args=[plugin_class.__name__, ], kwargs={'expire_subtasks': expire_subtasks},
                                     expires=expire_subtasks)


@celery.app.task(bind=True)
def run_plugin_class(self, plugin_class, expire_subtasks=EXPIRE_SUBTASKS):
    '''
    Fetch all instances of plugin_class and execute.
    :param plugin_class:
    :return:
    '''

    if isinstance(plugin_class, str):
        plugin_class = apps.get_model('tracking', plugin_class)

    for plugin in plugin_class.objects.all():

        if plugin.run_source_plugins:
            for sp in plugin.source_plugins.filter(status='enabled'):
                if sp.should_run():
                    # Expire in N seconds where N is the same as the period for the scheduled task.
                    # This is to avoid letting our task queue get jammed with
                    # redundant tasks.
                    run_source_plugin.apply_async(
                        args=[str(sp.id), ], expires=expire_subtasks)
        else:
            plugin.execute()


@celery.app.task(bind=True)
def run_spidertracks_plugins(self):

    plugins = SpiderTracksPlugin.objects.filter(
        status=SpiderTracksPlugin.STATUS_ENABLED)

    for p in plugins:
        p.execute()


@celery.app.task(bind=True)
def run_sirtrack_plugins(self):

    plugins = SirtrackPlugin.objects.filter(
        status=SirtrackPlugin.STATUS_ENABLED)

    for p in plugins:
        p.execute()


@celery.app.task(bind=True)
def run_source_plugin(self, source_plugin_id):

    sp = SourcePlugin.objects.get(id=source_plugin_id)

    logger.debug('Running plugin {} for source {}'.format(sp, sp.source))
    result = sp.execute()
    logger.debug('Finished running plugin {} for source {} with result.count={}'.format(
        sp, sp.source, result.count))


@celery.app.task(bind=True)
def run_demo_plugins(self):
    '''
    :param inline: Whether to run directly. If False, then queue tasks.
    '''
    demo_plugins = DemoSourcePlugin.objects.filter(
        status=DemoSourcePlugin.STATUS_ENABLED)

    for demo_plugin in demo_plugins:
        demo_plugin.execute()


@celery.app.task(bind=True)
def run_inreach_plugins(self, inline=True):
    '''
    :param inline: Whether to run directly. If False, then queue tasks.
    '''
    plugins = InreachPlugin.objects.filter(status=InreachPlugin.STATUS_ENABLED)

    for p in plugins:
        p.execute()


@celery.app.task(bind=True)
def run_awetelementry_plugins(self, inline=True):
    for p in AWETelemetryPlugin.objects.filter(status=AWETelemetryPlugin.STATUS_ENABLED):
        p.execute()
