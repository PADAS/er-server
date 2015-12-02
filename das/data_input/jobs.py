from data_input.models import PluginConf
from data_input.plugins.savanna import SavannaPlugin
from data_input.plugins.firms import FirmsPlugin
from data_input.plugins.inreach import InreachPlugin
from data_input.plugins.inreachkml import InreachKMLPlugin
from data_input.plugins.skygistics import SkygisticsSatellitePlugin, SkygisticsTarget
from data_input.plugins.awtgsm import AWTHttpPlugin
from data_input.plugins.trackgenerator import DemoPlugin
from data_input.plugins.plugin import DasDefaultTarget
import logging
from functools import namedtuple

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

def run_plugin(plugin_key):

    ptp = ptp_map.get(plugin_key)

    if not ptp:
        raise ValueError('No plugin target pair exists for name %s' % (plugin_key,))

    pconfs = PluginConf.objects.filter(plugin_class=ptp.plugin_class.plugin_key)

    for pc in pconfs:
        try:
            with ptp.target_class() as consumer:
                p = ptp.plugin_class(pc, target=consumer)
                p.execute()
        except Exception:
            logger.exception('Failed to run plugin %s' % (p,))


# Convenience methods.
def run_savanna():
    run_plugin(SavannaPlugin.plugin_key)

def run_awt_http():
    run_plugin(AWTHttpPlugin.plugin_key)

def run_demo():
    run_plugin(DemoPlugin.plugin_key)

def run_firms():
    run_plugin(FirmsPlugin.plugin_key)

def run_skygistics():
    run_plugin(SkygisticsSatellitePlugin.plugin_key)

def run_inreach():
    run_plugin(InreachPlugin.plugin_key)

def run_inreachkml():
    run_plugin(InreachKMLPlugin.plugin_key)