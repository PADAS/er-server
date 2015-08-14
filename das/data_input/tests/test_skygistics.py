import mock
import datetime
from django.test import TestCase
from django.utils import timezone

from data_input.plugins.plugin import DasPluginFetchError
from observations.models import Source
from data_input.models import PluginConf, PluginConfSource
from data_input.plugins.skygistics import SkygisticsSatellitePlugin, SkygisticsLoginError, \
    DasPluginConfigurationError


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
        target = None
        with self.assertRaises(DasPluginConfigurationError):
            SkygisticsSatellitePlugin(config, target)

    def test_plugin_init_with_config_and_target(self):
        config = PluginConf.objects.create(plugin_name='test config')
        target = None
        SkygisticsSatellitePlugin(config, target)


class TestSkygisticsFetch(TestCase):
    def setUp(self):
        target = None
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

    def test_login_with_bad_user_fails(self):
        self.assertFalse(self.bad_plugin.client._login())

    def test_login_with_good_user_succeeds(self):
        self.assertTrue(self.plugin.client._login())

    def test_attempting_to_get_replay_count_with_bad_imei_fails(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')
        imei = '0000'
        start_datetime = datetime.date(1900, 1, 1)
        end_datetime = datetime.date(1900, 1, 1)
        with self.assertRaises(DasPluginFetchError):
            self.plugin.client._get_replay_data_count(imei, start_datetime, end_datetime)

    def test_attempting_to_get_replay_count_with_good_imei_and_old_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = datetime.date(1900, 1, 1)
        end_datetime = datetime.date(1900, 1, 1)
        self.plugin.client._get_replay_data_count(imei, start_datetime, end_datetime)

    def test_attempting_to_get_replay_with_good_imei_and_old_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = datetime.date(1900, 1, 1)
        end_datetime = datetime.date(1900, 1, 1)
        self.plugin.client._get_replay_data(imei,
                                            start_datetime,
                                            end_datetime,
                                            skip=0,
                                            limit=10)

    def test_attempting_to_get_replay_count_with_good_imei_and_current_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = datetime.date(1900, 1, 1)
        end_datetime = timezone.now()
        self.plugin.client._get_replay_data_count(imei, start_datetime, end_datetime)

    def test_attempting_to_get_replay_with_good_imei_and_current_date(self):
        self.assertTrue(self.plugin.client._login(), 'login failed: no testing.')

        imei = '01086046SKY4213'
        start_datetime = datetime.date(1900, 1, 1)
        end_datetime = timezone.now()
        self.plugin.client._get_replay_data(imei,
                                            start_datetime,
                                            end_datetime,
                                            skip=0,
                                            limit=10)


class TestSkygisticsTransform(TestCase):
    def setUp(self):
        target = None
        config = PluginConf.objects.create(plugin_name='test good plugin',
                                           configuration={
                                               'credentials': {
                                                   'username': 'awtian',
                                                   'password': 'kenya'
                                               },
                                               'host': 'http://skyq1.skygistics.com',
                                           })
        source_1 = Source.objects.create(manufacturer_id='01086046SKY4213')
        PluginConfSource.objects.create(source=source_1,
                                        plugin_conf=config)
        source_2 = Source.objects.create(manufacturer_id='01086046SKY0000')
        PluginConfSource.objects.create(source=source_2,
                                        plugin_conf=config)
        self.plugin = SkygisticsSatellitePlugin(config, target)
