from django.test import TestCase, TransactionTestCase
from data_input.plugins.firms import FirmsPlugin, FirmsTarget
from data_input.models import PluginConf

class TestFirmsProvider(TransactionTestCase):

    fixtures = ['observations_source.json', 'data_input_pluginconf.json',]

    def setUp(self):
        pass

    def test_plugin_with_target(self):
        '''
        Test savanna plugin with a mock target.
        :return:
        '''

        pc = PluginConf.objects.get(plugin_name='firms')
        print(pc)

        with FirmsTarget() as consumer:
            sp = FirmsPlugin(pc, target=consumer)
            sp.execute()


