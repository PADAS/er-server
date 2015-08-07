from django.test import TestCase, TransactionTestCase
from data_input.plugins.savanna import SavannaPlugin, SavannaTarget
from data_input.models import PluginConf

class TestSavannaProvider(TransactionTestCase):

    fixtures = ['observations_source.json', 'data_input_pluginconf.json',]

    def setUp(self):
        pass

    def test_plugin_with_target(self):
        '''
        Test savanna plugin with a mock target.
        :return:
        '''

        pc = PluginConf.objects.get(plugin_name='savanna')
        print(pc)

        with SavannaTarget() as consumer:
            sp = SavannaPlugin(pc, target=consumer)
            sp.execute()

