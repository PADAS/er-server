from data_input.models import PluginConf
from data_input.plugins.savanna import SavannaPlugin
from data_input.plugins.firms import FirmsPlugin
from data_input.plugins.inreach import InreachPlugin
from data_input.plugins.inreachkml import InreachKMLPlugin
from data_input.plugins.skygistics import SkygisticsSatellitePlugin, SkygisticsTarget
from data_input.plugins.trackgenerator import DemoPlugin
from data_input.plugins.plugin import DasDefaultTarget
import logging

logger = logging.getLogger(__name__)

def run_savanna():
    '''
    run Savanna plugin to ingest collar data.
    :return:
    '''

    logger.info('Running savanna job.')
    try:
        pc = PluginConf.objects.get(plugin_name='savanna')
    except Exception:
        raise Exception("Looks like data hasn't been loaded for plugin_conf.")
    else:
        with DasDefaultTarget() as consumer:
            sp = SavannaPlugin(pc, target=consumer)
            sp.execute()


def run_trackgenerator():
    logger.info('Running trackgenerator job.')
    try:
        pc = PluginConf.objects.get(plugin_name='demo-wildlife')
    except Exception:
        raise Exception("Looks like data hasn't been loaded for plugin_conf.")
    else:
        with DasDefaultTarget() as consumer:
            sp = DemoPlugin(pc, target=consumer)
            sp.execute()

def run_firms():
    logger.info('Running firms job.')
    try:
        pc = PluginConf.objects.get(plugin_name='firms')
    except Exception:
        raise Exception("Looks like data hasn't been loaded for plugin_conf.")
    else:
        with DasDefaultTarget() as consumer:
            sp = FirmsPlugin(pc, target=consumer)
            sp.execute()


def run_inreach():

    for pn in ('inreach', 'ap-garamba-inreach'):
        logger.info('Running %s job.', pn)
        try:
            pc = PluginConf.objects.get(plugin_name=pn)
        except Exception:
            logger.error("No PluginConf data for job %s", pn)
        else:
            with DasDefaultTarget() as consumer:
                sp = InreachPlugin(pc, target=consumer)
                sp.execute()


def run_inreachkml():

    for pn in ('ap-odzala-inreachkml',):
        logger.info('Running %s job.', pn)
        try:
            pc = PluginConf.objects.get(plugin_name=pn)
        except Exception:
            logger.error("No PluginConf data for job %s", pn)
        else:
            with DasDefaultTarget() as consumer:
                sp = InreachKMLPlugin(pc, target=consumer)
                sp.execute()


def run_skygistics():
    for pn in ('lewa-skygistics', 'ap-skygistics'):
        logger.info('Running %s satellite job.', pn)
        try:
            pc = PluginConf.objects.get(plugin_name=pn)
        except Exception:
            logger.error("No PluginConf data for job %s", pn)
        else:
            with SkygisticsTarget() as consumer:
                sp = SkygisticsSatellitePlugin(pc, target=consumer)
                sp.execute()

