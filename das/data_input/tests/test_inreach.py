from django.test import TestCase, TransactionTestCase
from data_input.plugins.inreach import InreachPlugin
from data_input.plugins.plugin import DasDefaultTarget
from data_input.models import PluginConf

class TestInreachProvider(TransactionTestCase):

    fixtures = ['observations_source.json', 'data_input_pluginconf.json', 'data_input_pluginconfsource.json']

    def setUp(self):
        pass

    def test_plugin_with_target(self):
        '''
        Test savanna plugin with a mock target.
        :return:
        '''

        pc = PluginConf.objects.get(plugin_name='inreach')
        print(pc)

        with DasDefaultTarget() as consumer:
            sp = InreachPlugin(config=pc, target=consumer)
            sp.execute()

    # def test_account_plugin_with_target(self):
    #     '''
    #     Test savanna plugin with a mock target.
    #     :return:
    #     '''
    #
    #     try:
    #         pc = PluginConf.objects.get(plugin_name='inreach-account')
    #     except:
    #         pc = None
    #
    #     with InreachAccountTarget() as consumer:
    #         sp = InreachAccountPlugin(pc, target=consumer)
    #         sp.execute()
    #
    #
    #     x = input('Go on?')


