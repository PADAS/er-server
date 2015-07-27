import unittest

from data_input.plugins.skygistics import SkygisticsSatelliteClient, SkygisticsLoginError


class TestSkygisticsFetch(unittest.TestCase):
    def setUp(self):
        self.client = SkygisticsSatelliteClient()

    def test_attempting_to_get_replay_count_with_no_login_fails(self):
        with self.assertRaises(SkygisticsLoginError):
            self.client.get_replay_data_count(None, None, None)

    def test_attempting_to_get_replay_data_with_no_login_fails(self):
        with self.assertRaises(SkygisticsLoginError):
            self.client.get_replay_data(None, None, None, None, None)

    def test_login_with_bad_user_fails(self):
        self.assertFalse(self.client.login('user', 'password'))

    def test_login_with_good_user_succeeds(self):
        try:
            import das_server.test_settings as settings
            username = settings.SKYGISTICS_TEST['username']
            password = settings.SKYGISTICS_TEST['password']
            self.assertTrue(self.client.login(username, password))
        except ImportError:
            self.skipTest('Settings unavailable.')

    def test_attempting_to_get_replay_count_with_bad_imei_fails(self):
        try:
            import das_server.test_settings as settings
            username = settings.SKYGISTICS_TEST['username']
            password = settings.SKYGISTICS_TEST['password']
            self.assertTrue(self.client.login(username, password))

            imei = '0000'
            start_datetime = settings.SKYGISTICS_TEST['start_datetime']
            end_datetime = settings.SKYGISTICS_TEST['end_datetime']
            with self.assertRaises(SkygisticsLoginError):
                self.client.get_replay_data_count(imei, start_datetime, end_datetime)
        except ImportError:
            self.skipTest('Settings unavailable.')

    def test_attempting_to_get_replay_count_with_good_imei(self):
        try:
            import das_server.test_settings as settings
            username = settings.SKYGISTICS_TEST['username']
            password = settings.SKYGISTICS_TEST['password']
            self.assertTrue(self.client.login(username, password))

            imei = settings.SKYGISTICS_TEST['imei']
            start_datetime = settings.SKYGISTICS_TEST['start_datetime']
            end_datetime = settings.SKYGISTICS_TEST['end_datetime']
            self.client.get_replay_data_count(imei, start_datetime, end_datetime)
        except ImportError:
            self.skipTest('Settings unavailable.')

    def test_attempting_to_get_replay_with_good_imei(self):
        try:
            import das_server.test_settings as settings
            username = settings.SKYGISTICS_TEST['username']
            password = settings.SKYGISTICS_TEST['password']
            self.assertTrue(self.client.login(username, password))

            imei = settings.SKYGISTICS_TEST['imei']
            start_datetime = settings.SKYGISTICS_TEST['start_datetime']
            end_datetime = settings.SKYGISTICS_TEST['end_datetime']
            replay_data = self.client.get_replay_data(imei, start_datetime, end_datetime, skip=0, limit=100)
        except ImportError:
            self.skipTest('Settings unavailable.')