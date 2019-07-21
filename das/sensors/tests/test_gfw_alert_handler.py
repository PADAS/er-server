import json

from rest_framework import status

from activity.models import Event
from analyzers.tests.gfw_test_data import VIIRS_FIRE_ALERT, GLAD_ALERT, TERRAI_ALERT, GLAD_ALERT_DOWNLOADED_DATA
from core.tests import BaseAPITest
from sensors.views import SensorObservation


class GFWAlertHandlerTest(BaseAPITest):
    sensor_type = 'gfw-alert'
    provider = 'gfw'

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors', self.sensor_type, self.provider, 'status'))

    def test_glad(self):
        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # note: this doesn't test downloads done by celery task...
        self.assertEqual(len(GLAD_ALERT['alerts']),
                         Event.objects.all().count())

    def test_virrs(self):
        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(VIIRS_FIRE_ALERT['alerts']),
                         Event.objects.all().count())

    def test_terrai(self):
        response = self._post_data(json.dumps(TERRAI_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(TERRAI_ALERT['alerts']),
                         Event.objects.all().count())

    def test_glad_with_duplicates(self):
        # note: see note in test_glad
        num_events_expected = len(GLAD_ALERT['alerts'])

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(num_events_expected,
                         Event.objects.all().count())

        # create again, total events in db shouldn't change
        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(num_events_expected,
                         Event.objects.all().count())

    def test_terrai_with_duplicates(self):
        num_events_expected = len(TERRAI_ALERT['alerts'])

        response = self._post_data(json.dumps(TERRAI_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(num_events_expected,
                         Event.objects.all().count())

        # create again, total events in db shouldn't change
        response = self._post_data(json.dumps(TERRAI_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(num_events_expected,
                         Event.objects.all().count())

    def test_viirs_with_duplicates(self):
        num_events_expected = len(VIIRS_FIRE_ALERT['alerts'])

        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(num_events_expected,
                         Event.objects.all().count())

        # create again, total events in db shouldn't change
        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(num_events_expected,
                         Event.objects.all().count())

    def test_with_alerts_missing(self):
        data = VIIRS_FIRE_ALERT
        data.pop('alerts')
        response = self._post_data(json.dumps(data))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def _post_data(self, payload):
        request = self.factory.post(self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(request, sensor_type=self.sensor_type, provider_key=self.provider)
        return response
