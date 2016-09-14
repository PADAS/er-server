import logging

from das_server import celery
from tracking.pubsub_registry import notify_new_tracks
from tracking.models import SourcePlugin, DemoSourcePlugin, InreachPlugin, runnable_plugins


logger = logging.getLogger(__name__)


# @celery.app.task(bind=True)
# def run_all_source_plugins(self, force=False):
#     '''
#     Run all SourcePlugins that are enabled.
#     :return:
#     '''
#     splist = SourcePlugin.objects.filter(status=SourcePlugin.STATUS_ENABLED)
#
#     for sp in splist:
#         if force or sp.should_run():
#             logger.debug('running source_plugin {0}'.format(sp))
#             run_source_plugin.delay(str(sp.id))
#         else:
#             logger.debug('not running source_plugin {0}'.format(sp))

@celery.app.task(bind=True)
def run_plugins(self):
    for plugin_class in runnable_plugins:
        run_plugin_class(plugin_class)

def run_plugin_class(plugin_class):
    '''
    Fetch all instances of plugin_class and execute.
    :param plugin_class:
    :return:
    '''
    for plugin in plugin_class.objects.all():
        plugin.execute()


# @celery.app.task(bind=True)
# def run_source_plugin(self, source_plugin_id):
#
#     sp = SourcePlugin.objects.get(id=source_plugin_id)
#
#     logger.debug('Running plugin {} for source {}'.format(sp, sp.source))
#     result = sp.execute()
#     if result.count > 0:
#         notify_new_tracks(result.source_id)
#     logger.debug('Finished running plugin {} for source {} with result.count={}'.format(sp, sp.source, result.count))


# @celery.app.task(bind=True)
# def run_source_plugin_for_source(self, source_id):
#     sp = SourcePlugin.objects.get(source_id=source_id)
#     if sp:
#         logger.debug('Running source plugin %s', sp)
#         run_source_plugin.delay(str(sp.id))
#     else:
#         logger.debug('No sourcePlugin found for source_id = %s', source_id)
#

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

