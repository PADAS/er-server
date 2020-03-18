import json
import requests
from django.conf import settings

from rest_framework import status
from unittest.mock import patch, Mock

from analyzers.clustering_utils import cluster_alerts
from das_server.celery import app

from activity.models import Event
from analyzers.tests.gfw_test_data import VIIRS_FIRE_ALERT, GLAD_ALERT, GLAD_ALERT_DOWNLOADED_DATA, \
    VIIRS_FIRE_ALERT_DOWNLOADED_DATA, VIIRS_CALLBACK_DATA
from core.tests import BaseAPITest
from sensors.views import SensorObservation
from analyzers.models import GlobalForestWatchSubscription
from django.contrib.gis.geos import Polygon

from analyzers.tasks import download_gfw_alerts, requests
from analyzers.gfw_utils import get_viirs_fire_alerts


def send_task(name, args=(), kwargs={}, **opts):
    task = app.tasks[name]
    # return task.apply(args, kwargs, **opts)
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
        GFWSubscription = GlobalForestWatchSubscription.objects.create(**gfw_data)

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
        qs = GlobalForestWatchSubscription.objects.filter(subscription_id='5d1f9014836a9b13000e7d1d')
        qs.update(Deforestation_confidence=GlobalForestWatchSubscription.BOTH_CONFIRMED_UNCONFIRMED)

        response = self._post_data(json.dumps(GLAD_ALERT))
        clustered_alerts = cluster_alerts(
            GLAD_ALERT_DOWNLOADED_DATA['data'],
            settings.GFW_CLUSTER_RADIUS, 1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(clustered_alerts), Event.objects.all().count())

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
        GFWSubscription = GlobalForestWatchSubscription.objects.create(**gfw_data)

        # Monkey-patch send_task to execute task by blocking
        # (simulate task_always_eager=True) since send_task does not respect  task_always_eager when true.
        app.send_task = send_task

        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        clustered_alerts = cluster_alerts(VIIRS_FIRE_ALERT_DOWNLOADED_DATA['rows'], settings.GFW_CLUSTER_RADIUS, 1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(clustered_alerts), Event.objects.all().count())
