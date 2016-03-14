import logging

from das_server import celery
from tracking.pubsub_registry import notify_new_tracks
from tracking.models import SourcePlugin, DemoSourcePlugin

logger = logging.getLogger(__name__)


@celery.app.task(bind=True)
def run_all_source_plugins(self):
    '''
    Run all SourcePlugins that are enabled.
    :return:
    '''
    splist = SourcePlugin.objects.filter(status=SourcePlugin.STATUS_ENABLED)

    for sp in splist:
        run_source_plugin.delay(str(sp.id))

@celery.app.task(bind=True)
def run_source_plugin(self, source_plugin_id):

    sp = SourcePlugin.objects.get(id=source_plugin_id)

    logger.debug('Running plugin {} for source {}'.format(sp, sp.source))
    result = sp.execute()
    if result.count > 0:
        notify_new_tracks(result.source_id)
    logger.debug('Finished running plugin {} for source {} with result.count={}'.format(sp, sp.source, result.count))


@celery.app.task(bind=True)
def run_source_plugin_for_source(self, source_id):
    sp = SourcePlugin.objects.get(source_id=source_id)
    if sp:
        run_source_plugin.delay(str(sp.id))


@celery.app.task(bind=True)
def run_demo_plugins(self, inline=True):
    '''
    :param inline: Whether to run directly. If False, then queue tasks.
    '''
    demo_plugins = DemoSourcePlugin.objects.filter(status=DemoSourcePlugin.STATUS_ENABLED)

    func = run_source_plugin if inline else run_source_plugin.delay
    for demo_plugin in demo_plugins:
        for sp in demo_plugin.source_plugins.all():
            func(str(sp.id))

