from data_input.models import PluginConf
from data_input.plugins.savanna import SavannaPlugin, SavannaTarget

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

