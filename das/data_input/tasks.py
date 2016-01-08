from data_input.models import PluginConf
from data_input.plugins.savanna import SavannaPlugin
from data_input.plugins.firms import FirmsPlugin
from data_input.plugins.inreach import InreachPlugin
from data_input.plugins.inreachkml import InreachKMLPlugin
from data_input.plugins.skygistics import SkygisticsSatellitePlugin, SkygisticsTarget
from data_input.plugins.awtgsm import AWTHttpPlugin
from data_input.plugins.trackgenerator import DemoPlugin
from data_input.plugins.plugin import DasDefaultTarget

# from django.core.cache import cache
from data_input import lock, get_cache


import logging

from functools import namedtuple

from das_server import celery

logger = logging.getLogger(__name__)

PluginTargetPair = namedtuple('PluginTargetPair', ('plugin_class', 'target_class'))

# This a list of Plugin/Target pairs, that can be run on schedule.
plugin_target_pairs = (PluginTargetPair(SavannaPlugin, DasDefaultTarget),
                       PluginTargetPair(DemoPlugin, DasDefaultTarget),
                       PluginTargetPair(FirmsPlugin, DasDefaultTarget),
                       PluginTargetPair(SkygisticsSatellitePlugin, SkygisticsTarget),
                       PluginTargetPair(InreachPlugin, DasDefaultTarget),
                       PluginTargetPair(InreachKMLPlugin, DasDefaultTarget),
                       PluginTargetPair(AWTHttpPlugin, DasDefaultTarget),
                       )
# Map plugin_key to plugin_target_pair
ptp_map = dict((p.plugin_class.plugin_key, p) for p in plugin_target_pairs)

def run_all_plugins():
    for ptp in plugin_target_pairs.values():
        run_plugin(ptp)


# TODO: Adjust this lock expires, after we've moved to a bigger box.
LOCK_EXPIRE = 60 * 15  # expire task lock in 15 minutes.

def run_plugin(plugin_key):

    logger.debug('Running %s plugin...', plugin_key)
    lock_id = 'ingest-lock-{0}'.format(plugin_key)

    ptp = ptp_map.get(plugin_key)

    if not ptp:
        raise ValueError('No plugin target pair exists for name %s' % (plugin_key,))

    with lock(redis_client=get_cache(), key=lock_id, timeout=LOCK_EXPIRE, blocking=False) as lock_acquired:

        if lock_acquired:
            logger.debug('Acquired lock for plugin %s', plugin_key)
            pconfs = PluginConf.objects.filter(plugin_class=ptp.plugin_class.plugin_key)

            for pc in pconfs:
                try:
                    with ptp.target_class() as consumer:
                        p = ptp.plugin_class(pc, target=consumer)
                        p.execute()
                except Exception:
                    logger.exception('Failed to run plugin %s' % (p,))

            logger.debug('Finished running plugin %s', plugin_key)
        else:
            logger.debug("Plugin %s is already running.", plugin_key)


# Celery tasks.
@celery.app.task(bind=True)
def run_savannah(self):
    run_plugin(SavannaPlugin.plugin_key)

@celery.app.task(bind=True)
def run_awt_http(self):
    run_plugin(AWTHttpPlugin.plugin_key)

@celery.app.task(bind=True)
def run_demo(self):
    run_plugin(DemoPlugin.plugin_key)

@celery.app.task(bind=True)
def run_firms(self):
    run_plugin(FirmsPlugin.plugin_key)

@celery.app.task(bind=True)
def run_skygistics(self):
    run_plugin(SkygisticsSatellitePlugin.plugin_key)

@celery.app.task(bind=True)
def run_inreach(self):
    run_plugin(InreachPlugin.plugin_key)

@celery.app.task(bind=True)
def run_inreachkml(self):
    run_plugin(InreachKMLPlugin.plugin_key)