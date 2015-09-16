from data_input.models import PluginConf
from data_input.plugins.savanna import SavannaPlugin, SavannaTarget
from data_input.plugins.firms import FirmsPlugin, FirmsTarget
from data_input.plugins.inreach import InreachPlugin, InreachTarget

def run_savanna():
    '''
    run Savanna plugin to ingest collar data.
    :return:
    '''
    print('Running savanna job')
    try:
        pc = PluginConf.objects.get(plugin_name='savanna')
    except Exception:
        raise Exception("Looks like data hasn't been loaded for plugin_conf.")

    with SavannaTarget() as consumer:
        sp = SavannaPlugin(pc, target=consumer)
        sp.execute()

def run_firms():
    print('Running firms job')
    try:
        pc = PluginConf.objects.get(plugin_name='firms')
    except Exception:
        raise Exception("Looks like data hasn't been loaded for plugin_conf.")

    with FirmsTarget() as consumer:
        sp = FirmsPlugin(pc, target=consumer)
        sp.execute()

def run_inreach():
    print('Running firms job')
    try:
        pc = PluginConf.objects.get(plugin_name='inreach')
    except Exception:
        raise Exception("Looks like data hasn't been loaded for plugin_conf.")

    with InreachTarget() as consumer:
        sp = InreachPlugin(pc, target=consumer)
        sp.execute()

