import json
import urllib.parse as parser
from unittest.mock import patch, Mock

from django.contrib.gis.geos import Polygon
from rest_framework import status

from activity.models import Event
from analyzers.models import GlobalForestWatchSubscription as gfw_model
from analyzers.tests.gfw_test_data import VIIRS_FIRE_ALERT, GLAD_ALERT, GLAD_ALERT_DOWNLOADED_DATA, \
    VIIRS_FIRE_ALERT_DOWNLOADED_DATA, VIIRS_CALLBACK_DATA
from analyzers.gfw_utils import (get_geostore_id, GEOSTORE_FIELD, GLAD_CONFIRM_FIELD,
                                 rebuild_glad_download_url)
from core.tests import BaseAPITest
from das_server.celery import app
from sensors.views import SensorObservation


def send_task(name, args=(), kwargs={}, **opts):
    task = app.tasks[name]
    # return task.apply(args, kwargs, **opts)
    return task(*args, **kwargs)


class GFWAlertHandlerTest(BaseAPITest):
    sensor_type = 'gfw-alert'
    provider = 'gfw'
    download_url_unknown_geostore = 'http://production-api.globalforestwatch.org/glad-alerts/download/?period=2020-02-23,2020-02-27&gladConfirmOnly=False&aggregate_values=False&aggregate_by=False&geostore=8cfb4e52a779d2aeaa3b3877d5874e7a&format=json'
    unknown_geostore = '8cfb4e52a779d2aeaa3b3877d5874e7a'

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

    def test_virrs(self):
        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch('das_server.celery.app.send_task')
    def test_glad_with_duplicates(self, mock_send_task):
        # note: see note in test_glad
        num_events_expected = len(GLAD_ALERT['alerts'])

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # create again, total events in db shouldn't change
        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_viirs_with_duplicates(self):
        num_events_expected = len(VIIRS_FIRE_ALERT['alerts'])

        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # create again, total events in db shouldn't change
        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_with_alerts_missing(self):
        data = VIIRS_FIRE_ALERT
        data.pop('alerts')
        response = self._post_data(json.dumps(data))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_utils_get_geostore_id(self):
        geostore_id = get_geostore_id(self.download_url_unknown_geostore)
        self.assertEqual(geostore_id, self.unknown_geostore)

    def test_utils_build_confirmed_url_with_geostore_id(self):
        new_geostore_id = 'a hardcoded string for test'

        poly = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
        gfw_obj = gfw_model.objects.create(name='Test alert', subscription_id='blah', geostore_id=new_geostore_id,
                                           additional={"alert_types": ["glad-alerts"]}, Deforestation_confidence=gfw_model.CONFIRMED,
                                           subscription_geometry=poly)

        query_params = parser.parse_qs(parser.urlparse(self.download_url_unknown_geostore).query)
        self.assertEqual(query_params[GEOSTORE_FIELD][0], self.unknown_geostore)
        self.assertEqual(query_params[GLAD_CONFIRM_FIELD][0], 'False')
        updated_url = rebuild_glad_download_url(
            self.download_url_unknown_geostore, gfw_obj)
        updated_qp = parser.parse_qs(parser.urlparse(updated_url).query)
        self.assertEqual(updated_qp[GEOSTORE_FIELD][0], new_geostore_id)
        self.assertEqual(updated_qp[GLAD_CONFIRM_FIELD][0], 'True')

    @patch('analyzers.gfw_inbound.process_downloaded_alerts')
    @patch('requests.get')
    def test_download_glad_one_subscription_unknown_geostore(self, mock_request, mock_download_process_alerts):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))

        # todo: revisit. why doesn't this work.
        app.send_task = send_task

        poly = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
        gfw_model.objects.create(name='Test alert', subscription_id='blah', geostore_id='blah',
                                 additional={"alert_types": ["glad-alerts"]},
                                 subscription_geometry=poly)

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # download_gfw_alerts(self.download_url_unknown_geostore, None, None)
        self.assertEqual(mock_download_process_alerts.call_count, 1)

    @patch('analyzers.gfw_inbound.process_downloaded_alerts')
    @patch('requests.get')
    def test_download_glad_two_subscriptions_unknown_geostore(self, mock_request, mock_download_process_alerts):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))

        app.send_task = send_task

        poly = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
        gfw_model.objects.create(name='Test alert', subscription_id='blah', geostore_id='blah',
                                 additional={"alert_types": ["glad-alerts"]},
                                 subscription_geometry=poly)

        gfw_model.objects.create(name='Test alert', subscription_id='blah', geostore_id='blah',
                                 additional={"alert_types": ["glad-alerts"]},
                                 subscription_geometry=poly)

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_download_process_alerts.call_count, 2)

    @patch('analyzers.gfw_inbound.process_downloaded_alerts')
    @patch('requests.get')
    def test_download_glad_two_subscriptions_known_geostore(self, mock_request, mock_download_process_alerts):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task
        test_data_geostore = 'a8c46db68bc4b6f7f881f38ce61a8bcb'

        poly = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
        gfw_model.objects.create(name='Test alert', subscription_id='blah', geostore_id=test_data_geostore,
                                 additional={"alert_types": ["glad-alerts"]},
                                 subscription_geometry=poly)

        gfw_model.objects.create(name='Test alert', subscription_id='blah', geostore_id='blah',
                                 additional={"alert_types": ["glad-alerts"]},
                                 subscription_geometry=poly)

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_download_process_alerts.call_count, 1)

    def _post_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(
            request, sensor_type=self.sensor_type, provider_key=self.provider)
        return response

    @patch('requests.get')
    def test_filter_confidence_level_for_deforestation(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))

        geom_coord = ((21.55517578125, -1.36217634666416),
                      (22.78564453125, -3.57921278586063),
                      (24.521484375, -1.36217634666416),
                      (21.55517578125, -1.36217634666416))
        gfw_data = {
            'name': 'DRC Glad alerts',
            'subscription_id': '5d1f9014836a9b13000e7d1d',
            'geostore_id': 'a8c46db68bc4b6f7f881f38ce61a8bcb',
            'additional': {"alert_types": ["glad-alerts"]},
            'subscription_geometry': Polygon(geom_coord)
        }

        # By default the confidence level for deforestation is 3 (confirmed)
        gfw_model.objects.create(**gfw_data)

        # Monkey-patch send_task to execute task by blocking
        # (simulate task_always_eager=True) since send_task does not respect  task_always_eager when true.
        app.send_task = send_task

        response = self._post_data(json.dumps(GLAD_ALERT))
        # There is only one alert with confidence level 3 in 'GLAD_ALERT_DOWNLOADED_DATA' (example data)
        expected_event = 1
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(expected_event, Event.objects.all().count())

        # Update the confidence level for GFWSubscription object
        # to Confirmed and Unconfirmed.
        qs = gfw_model.objects.filter(subscription_id='5d1f9014836a9b13000e7d1d')
        qs.update(Deforestation_confidence=gfw_model.BOTH_CONFIRMED_UNCONFIRMED)

        response = self._post_data(json.dumps(GLAD_ALERT))
        expected_event = len(GLAD_ALERT_DOWNLOADED_DATA['data'])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(expected_event, Event.objects.all().count())

    @patch('analyzers.gfw_utils.get_viirs_fire_alerts')
    @patch('analyzers.tasks.requests.get')
    def test_filter_confidence_level_for_fire(self, mock_request, mock_callback):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(VIIRS_FIRE_ALERT_DOWNLOADED_DATA))
        mock_callback.return_value = VIIRS_CALLBACK_DATA

        geom_coord = ((21.55517578125, -1.36217634666416),
                      (22.78564453125, -3.57921278586063),
                      (24.521484375, -1.36217634666416),
                      (21.55517578125, -1.36217634666416))
        gfw_data = {
            'name': 'DRC Glad alerts',
            'subscription_id': '5d11c24e062bed110071db94',
            'geostore_id': 'a8c46db68bc4b6f7f881f38ce61a8bcb',
            'additional': {"alert_types": ["viirs-active-fires"]},
            'subscription_geometry': Polygon(geom_coord)
        }

        # By default the confidence level for fire alerts is High and Nominal.
        gfw_model.objects.create(**gfw_data)

        # Monkey-patch send_task to execute task by blocking
        # (simulate task_always_eager=True) since send_task does not respect  task_always_eager when true.
        app.send_task = send_task

        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        expected_event = len(VIIRS_FIRE_ALERT_DOWNLOADED_DATA['rows'])  # ALL have confidence level: Nominal
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(expected_event, Event.objects.all().count())
