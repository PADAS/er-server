from datetime import date, datetime, timedelta
from xml.etree.ElementTree import Element
from unittest import skip

from django.test import TestCase
from django.utils import timezone

from data_input.plugins.plugin import DasPluginFetchError
from data_input.plugins.skygistics import SkygisticsSatellitePlugin, SkygisticsClient, SkygisticsTarget, \
    SkygisticsLoginError, DasPluginConfigurationError
from data_input.tests.mocks import MockTarget, MockConfig
from data_input.models import PluginConf
from observations.models import Observation


class SkygisticsMockClient(SkygisticsClient):
    SKYGISTICS_API_XMLNS = '{http://www.skygistics.com/SkygisticsAPI}'

    def begin_session(self):
        pass

    def fetch_observations(self, imei, start_time, end_time=None):
        mock_replay_data_dict = [
            {
                'imei': '01086046SKY4213',
                'lat': 0.0,
                'lon': 0.0,
                'voltage': 1.123,
                'fix_time': (datetime.now() - timedelta(2)).isoformat(),
                'received_time': datetime.now().isoformat()
            },
            {
                'imei': '01086046SKY4213',
                'lat': 0.0,
                'lon': 0.0,
                'voltage': 1.123,
                'fix_time': (datetime.now() - timedelta(1)).isoformat(),
                'received_time': datetime.now().isoformat()
            },
            {
                'imei': '01086046SKY4213',
                'lat': 0.0,
                'lon': 0.0,
                'voltage': 1.123,
                'fix_time': datetime.now().isoformat(),
                'received_time': datetime.now().isoformat()
            },
        ]
        for unit_info in mock_replay_data_dict:
            yield {
                '{0}IMEI'.format(self.SKYGISTICS_API_XMLNS): [
                    {
                        '_text': unit_info['imei']
                    }],
                '{0}Latitude'.format(self.SKYGISTICS_API_XMLNS): [
                    {
                        '_text': unit_info['lat']
                    }],
                '{0}Longitude'.format(self.SKYGISTICS_API_XMLNS): [
                    {
                        '_text': unit_info['lon']
                    }],
                '{0}Voltage'.format(self.SKYGISTICS_API_XMLNS): [
                    {
                        '_text': unit_info['voltage']
                    }],
                '{0}Time'.format(self.SKYGISTICS_API_XMLNS): [
                    {
                        '_text': unit_info['fix_time']
                    }],
                '{0}ReceivedTime'.format(self.SKYGISTICS_API_XMLNS): [
                    {
                        '_text': unit_info['received_time']
                    }],
            }



class TestSkygisticsInit(TestCase):
    def test_plugin_init_with_no_config_and_no_target(self):
        config = None
        target = None
        with self.assertRaises(DasPluginConfigurationError):
            SkygisticsSatellitePlugin(config, target)

    def test_plugin_init_with_no_target(self):
        config = PluginConf.objects.create(plugin_name='test config')
        target = None
        with self.assertRaises(DasPluginConfigurationError):
            SkygisticsSatellitePlugin(config, target)

    def test_plugin_init_with_no_config(self):
        config = None
        target = MockTarget()
        with self.assertRaises(DasPluginConfigurationError):
            SkygisticsSatellitePlugin(config, target)

    def test_plugin_init_with_config_and_target(self):
        config = PluginConf.objects.create(plugin_name='test config')
        target = MockTarget()
        SkygisticsSatellitePlugin(config, target)


class TestSkygisticsFetch(TestCase):
    def setUp(self):
        target = MockTarget()
        bad_config = PluginConf.objects.create(plugin_name='test bad sky login',
                                               configuration={
                                                   'credentials': {
                                                       'username': 'bad',
                                                       'password': 'bad'
                                                   },
                                                   'host': 'http://skyq1.skygistics.com',
                                               })
        self.bad_plugin = SkygisticsSatellitePlugin(bad_config, target)

        config = PluginConf.objects.create(plugin_name='test good sky login',
                                           configuration={
                                               'credentials': {
                                                   'username': 'awtian',
                                                   'password': 'kenya'
                                               },
                                               'host': 'http://skyq1.skygistics.com',
                                           })
        self.plugin = SkygisticsSatellitePlugin(config, target)

    def test_attempting_to_get_replay_count_with_no_login_fails(self):
        with self.assertRaises(SkygisticsLoginError):
            self.plugin.client._get_replay_data_count(None, None, None)

    def test_attempting_to_get_replay_data_with_no_login_fails(self):
        with self.assertRaises(SkygisticsLoginError):
            self.plugin.client._get_replay_data(None, None, None, None, None)

    @skip("skip:  no network for now")
    def test_login_with_bad_user_fails(self):
        self.assertFalse(self.bad_plugin.client._login())

    @skip("skip:  no network for now")
    def test_login_with_good_user_succeeds(self):
        self.assertTrue(self.plugin.client._login())

    @skip("skip:  no network for now")
    def test_attempting_to_get_replay_count_with_bad_imei_fails(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')
        imei = '0000'
        start_datetime = date(1900, 1, 1)
        end_datetime = date(1900, 1, 1)
        with self.assertRaises(DasPluginFetchError):
            self.plugin.client._get_replay_data_count(imei, start_datetime, end_datetime)

    @skip("skip:  no network for now")
    def test_attempting_to_get_replay_count_with_good_imei_and_old_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = date(1900, 1, 1)
        end_datetime = date(1900, 1, 1)
        self.plugin.client._get_replay_data_count(imei, start_datetime, end_datetime)

    @skip("skip:  no network for now")
    def test_attempting_to_get_replay_with_good_imei_and_old_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = date(1900, 1, 1)
        end_datetime = date(1900, 1, 1)
        self.plugin.client._get_replay_data(imei,
                                            start_datetime,
                                            end_datetime,
                                            skip=0,
                                            limit=10)

    @skip("skip:  no network for now")
    def test_attempting_to_get_replay_count_with_good_imei_and_current_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = date(1900, 1, 1)
        end_datetime = timezone.now()
        self.plugin.client._get_replay_data_count(imei, start_datetime, end_datetime)

    @skip("skip:  no network for now")
    def test_attempting_to_get_replay_with_good_imei_and_current_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = date(1900, 1, 1)
        end_datetime = timezone.now()
        replay_data = self.plugin.client._get_replay_data(imei,
                                                          start_datetime,
                                                          end_datetime,
                                                          skip=0,
                                                          limit=10)
        self.assertIsInstance(replay_data, Element)


class TestSkygisticsPluginWithMockTarget(TestCase):
    fixtures = [
        'data_input/tests/fixtures/data_input_pluginconf',
        'data_input/tests/fixtures/data_input_pluginconfsource',
        'observations/tests/fixtures/observations_source',
    ]

    def setUp(self):
        target = MockTarget()
        config = PluginConf.objects.get(plugin_name='skygistics')
        self.plugin = SkygisticsSatellitePlugin(config, target)
        self.plugin.client = SkygisticsMockClient()

    def test_fetch_returns_dicts(self):
        for result in self.plugin._fetch():
            print(result)
            self.assertIsNotNone(result)

    @skip('skip:  still working on this')
    def test_transform_returns_observations(self):
        for result in self.plugin._fetch():
            observation = self.plugin._transform(result)
            self.assertIsInstance(observation, Observation)

    @skip('skip:  still working on this')
    def test_insert(self):
        for result in self.plugin._fetch():
            observation = self.plugin._transform(result)
            self.assertIsInstance(observation, Observation)


class TestSkygisticsPluginWithSkygisticsTarget(TestCase):
    fixtures = [
        'data_input/tests/fixtures/data_input_pluginconf',
        'data_input/tests/fixtures/data_input_pluginconfsource',
        'observations/tests/fixtures/observations_source',
    ]

    def test_target(self):
        config = PluginConf.objects.get(plugin_name='skygistics')
        with SkygisticsTarget() as target:
            plugin = SkygisticsSatellitePlugin(config, target)
            # todo:  need an assert here ... hmmm.
            plugin.execute()
        self.assertGreater(Observation.objects.count(), 0)