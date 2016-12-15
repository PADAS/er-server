import logging
from django.apps import apps
from das_server import celery
from tracking.models import *

logger = logging.getLogger(__name__)


@celery.app.task(bind=True)
def run_plugins(self):
    for plugin_class in runnable_plugins:
        run_plugin_class.delay(plugin_class.__name__)


@celery.app.task(bind=True)
def run_plugin_class(self, plugin_class):
    '''
    Fetch all instances of plugin_class and execute.
    :param plugin_class:
    :return:
    '''

    if isinstance(plugin_class, str):
        plugin_class = apps.get_model('tracking', plugin_class)

    for plugin in plugin_class.objects.all():

        if plugin.run_source_plugins:
            for sp in plugin.source_plugins.all():
                if sp.should_run():
                    run_source_plugin.delay(str(sp.id))
        else:
            plugin.execute()


@celery.app.task(bind=True)
def run_source_plugin(self, source_plugin_id):

    sp = SourcePlugin.objects.get(id=source_plugin_id)

    logger.debug('Running plugin {} for source {}'.format(sp, sp.source))
    result = sp.execute()
    logger.debug('Finished running plugin {} for source {} with result.count={}'.format(sp, sp.source, result.count))


@celery.app.task(bind=True)
def run_demo_plugins(self):
    '''
    :param inline: Whether to run directly. If False, then queue tasks.
    '''
    demo_plugins = DemoSourcePlugin.objects.filter(status=DemoSourcePlugin.STATUS_ENABLED)

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

