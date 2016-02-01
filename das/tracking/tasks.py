import datetime

import logging
from das_server import celery
from tracking.pubsub_registry import notify_new_tracks
from tracking.models import SourcePlugin, SavannahPlugin
import observations

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
        # result = sp.execute()
        # if result.count > 0:
        #     notify_new_tracks(result.source_id)


@celery.app.task(bind=True, )
def run_source_plugin(self, source_plugin_id):
    sp = SourcePlugin.objects.get(id=source_plugin_id)
    result = sp.execute()
    if result.count > 0:
        notify_new_tracks(result.source_id)

# def add_sourceplugin():
#     src = observations.models.Source.objects.get(manufacturer_id='ST2010-1233')
#
#
#     sp = SavannahPlugin(min_time=datetime.datetime.utcnow(),
#                                         max_time=datetime.datetime.utcnow(),
#                                         status=SourcePlugin.STATUS_ENABLED,
#                                         additional=dict(note='Test'),
#                                         service_user_id='ste',
#                                         service_password='ndovu4',
#                                         service_api_host='41.207.72.20')
#
#     sp.save()
#
#     ss = SourcePlugin(source=src, plugin=sp)
#
#     ss.save()

