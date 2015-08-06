from django.test import TestCase, TransactionTestCase
from data_input.plugins.savanna import SavannaClient, SavannaTransformer, SavannaPlugin, SavannaTarget
import datetime, time, pytz

MODEL_NAME = 'SavannaTrackingRF'
class TestSavannaProvider(TransactionTestCase):

    fixtures = ['observations_source.json', ]

    def setUp(self):

        self.client = SavannaClient()
        self.transformer = SavannaTransformer()


    def test_plugin_with_target(self):
        '''
        Test savanna plugin with a mock target.
        :return:
        '''
        with SavannaTarget() as consumer:
            sp = SavannaPlugin(target=consumer)
            sp.execute()

def _ts(timetuple):
    _ = datetime.datetime(*timetuple)
    return int(time.mktime(_.timetuple()))

SAMPLE_LINE='ST2010-1352,37.54771,0.5735083,6/26/2015 5:30:18 AM,0.47,0,,873'

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