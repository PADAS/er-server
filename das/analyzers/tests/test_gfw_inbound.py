import json
from unittest.mock import patch, Mock

from rest_framework import status
from django.contrib.gis.geos import Polygon

from activity.models import Event
from analyzers.tasks import download_gfw_alerts
from analyzers.models import GlobalForestWatchSubscription
from analyzers.tests.gfw_test_data import VIIRS_FIRE_ALERT, GLAD_ALERT, GLAD_ALERT_DOWNLOADED_DATA
from core.tests import BaseAPITest
from das_server.celery import app
from sensors.views import SensorObservation


def send_task(name, args=(), kwargs={}, **opts):
    task = app.tasks[name]
    return task(*args, **kwargs)


class GFWAlertHandlerTest(BaseAPITest):
    sensor_type = 'gfw-alert'
    provider = 'gfw'

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  self.sensor_type, self.provider, 'status'))

    def tearDown(self) -> None:
        app.send_task = app.send_task

    @patch('das_server.celery.app.send_task')
    def test_glad(self, mock_send_task):
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

    @patch('das_server.celery.app.send_task')
    def test_glad_with_duplicates(self, mock_send_task):
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

    def test_utils_get_geostore_id(self):
        pass

    def test_utils_build_confirmed_url_with_geostore_id(self):
        pass

    @patch('analyzers.gfw_inbound.process_downloaded_alerts')
    @patch('requests.get')
    def test_download_glad_one_subscription_unknown_geostore(self, mock_request, mock_download_process_alerts):
        download_url = 'http://production-api.globalforestwatch.org/glad-alerts/download/?period=2020-02-23,2020-02-27&gladConfirmOnly=False&aggregate_values=False&aggregate_by=False&geostore=8cfb4e52a779d2aeaa3b3877d5874e7a&format=json'
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))

        # todo: revisit. why doesn't this work.
        # app.send_task = send_task

        poly1 = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
        GlobalForestWatchSubscription.objects.create(name='Test alert', subscription_id='blah', geostore_id='blah',
                                                     additional={"alert_types": ["glad-alerts"]},
                                                     subscription_geometry=poly1)

        download_gfw_alerts(download_url, None, None)
        self.assertTrue(mock_download_process_alerts.called)

    def test_download_glad_two_subscriptions_unknown_geostore(self, mock_request, mock_download_process_alerts):
        pass

    def test_download_glad_two_subscriptions_known_geostore(self, mock_request, mock_download_process_alerts):
        pass

    def _post_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(
            request, sensor_type=self.sensor_type, provider_key=self.provider)
        return response
