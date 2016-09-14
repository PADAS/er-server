import logging

from das_server import celery
from tracking.pubsub_registry import notify_new_tracks
from tracking.models import SourcePlugin, DemoSourcePlugin, InreachPlugin, runnable_plugins


logger = logging.getLogger(__name__)


@celery.app.task(bind=True)
def run_plugins(self):
    for plugin_class in runnable_plugins:
        run_plugin_class.delay(plugin_class)

@celery.app.task(bind=True)
def run_plugin_class(self, plugin_class):
    '''
    Fetch all instances of plugin_class and execute.
    :param plugin_class:
    :return:
    '''
    for plugin in plugin_class.objects.all():
        plugin.execute()


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

