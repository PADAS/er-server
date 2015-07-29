import unittest

from data_input.plugins.savannah import SavannahClient, SavannahTransformer, SavannahException

SAMPLE_LINE='ST2010-1234,37.54771,0.5735083,6/26/2015 5:30:18 AM,0.47,0,,873'

SAMPLE_COLLARS = [
    {"collar_id": "ST2010-1352", "name": "Nutmeg"},
    {"collar_id": "ST2010-1234", "name": "Habiba"},
    {"collar_id": "ST2010-1316", "name": "Soutine"},
    {"collar_id": "ST2010-1351", "name": "Orchid"},
    {"collar_id": "ST2010-1230", "name": "Luna"},
    {"collar_id": "ST2010-1231", "name": "Salma"},
    {"collar_id": "ST2010-1354", "name": "Wendy"},
    {"collar_id": "ST2010-1356", "name": "Amity"},
    {"collar_id": "ST2010-1358", "name": "Tony"},
    {"collar_id": "ST2010-1359", "name": "Taurus"},
    {"collar_id": "ST2010-1360", "name": "Annabelle"},
]


import datetime, time

class TestSavannahProvider(unittest.TestCase):
    def setUp(self):
        self.client = SavannahClient()
        self.transformer = SavannahTransformer()

    def test_fetch_data_for_valid_device_id(self):
        try:
            start_time = int(time.mktime(datetime.datetime(2015, 6, 1).timetuple()))

            collar_id = SAMPLE_COLLARS[0]['collar_id']
            obs_data = self.client.fetch_observations(collar_id, start_time)

            from itertools import islice
            for obs in islice(obs_data, 50):
                tobs = self.transformer.transform(obs)
                print(tobs.ts.isoformat())
                print(tobs)

        except SavannahException as se:
            raise se

    def test_fetch_data_for_invalid_device_id(self):
        try:
            start_time = int(time.mktime(datetime.datetime(2015, 6, 1).timetuple()))

            collar_id = 'ST2010-12345'
            obs_data = self.client.fetch_observations(collar_id, start_time)

            for obs in obs_data:
                print(obs)

        except SavannahException as se:
            raise se

