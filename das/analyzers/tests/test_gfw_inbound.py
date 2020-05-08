import json
from unittest.mock import patch, Mock

from django.conf import settings
from django.contrib.gis.geos import Polygon
from faker import Faker
from rest_framework import status
import urllib.parse as parser

from analyzers.clustering_utils import cluster_alerts
from activity.models import Event
from analyzers.gfw_utils import (get_geostore_id, GEOSTORE_FIELD, GLAD_CONFIRM_FIELD,
                                 rebuild_glad_download_url)
from analyzers.models import GlobalForestWatchSubscription as gfw_model
# noinspection PyUnresolvedReferences
from analyzers.tasks import download_gfw_alerts  # prevent pycharm optimize import from removing this
from analyzers.tests.gfw_test_data import VIIRS_FIRE_ALERT, GLAD_ALERT, GLAD_ALERT_DOWNLOADED_DATA, \
    VIIRS_FIRE_ALERT_DOWNLOADED_DATA, VIIRS_CALLBACK_DATA
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
    test_data_glad_subscription_id = '5d1f9014836a9b13000e7d1d'
    test_data_viirs_subscription_id = '5d11c24e062bed110071db94'
    test_data_geostore_id = 'a8c46db68bc4b6f7f881f38ce61a8bcb'
    subscription_poly = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
    faker = Faker()

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  self.sensor_type, self.provider, 'status'))

    def tearDown(self) -> None:
        app.send_task = app.send_task

    @patch('requests.get')
    def test_glad(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task
        self._create_and_get_test_model(subscription_id=self.test_data_glad_subscription_id,
                                        geostore_id=self.test_data_geostore_id)

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())  # GLAD_ALERT_DOWNLOADED_DATA has 1 confirmed sub

    @patch('requests.post')
    def test_virrs(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(VIIRS_FIRE_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task
        self._create_and_get_test_model(subscription_id=self.test_data_viirs_subscription_id)
        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        clustered_alerts = cluster_alerts(
            VIIRS_FIRE_ALERT_DOWNLOADED_DATA['rows'],
            settings.GFW_CLUSTER_RADIUS, 1)
        self.assertEqual(len(clustered_alerts), Event.objects.all().count())

    @patch('requests.get')
    def test_glad_with_duplicates(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task
        self._create_and_get_test_model()
        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # create again, total events in db shouldn't change
        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())

    @patch('requests.post')
    def test_viirs_with_duplicates(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(VIIRS_FIRE_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task

        self._create_and_get_test_model()

        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # create again, total events in db shouldn't change
        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        clustered_alerts = cluster_alerts(
            VIIRS_FIRE_ALERT_DOWNLOADED_DATA['rows'],
            settings.GFW_CLUSTER_RADIUS, 1)
        self.assertEqual(len(clustered_alerts), Event.objects.all().count())

    def test_with_alerts_missing(self):
        data = VIIRS_FIRE_ALERT
        data.pop('alerts')
        model = self._create_and_get_test_model()
        model.subscription_id = self.test_data_viirs_subscription_id
        model.save()
        response = self._post_data(json.dumps(data))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_geostore_id(self):
        geostore_id = get_geostore_id(self.download_url_unknown_geostore)
        self.assertEqual(geostore_id, self.unknown_geostore)

    def test_rebuild_glad_url_confirmed_only(self):
        query_params = parser.parse_qs(parser.urlparse(self.download_url_unknown_geostore).query)
        self.assertEqual(query_params[GEOSTORE_FIELD][0], self.unknown_geostore)
        self.assertEqual(query_params[GLAD_CONFIRM_FIELD][0], 'False')

        new_geostore_id = 'a hardcoded string for test'
        gfw_obj = self._create_and_get_test_model(geostore_id=new_geostore_id)
        updated_url = rebuild_glad_download_url(
            self.download_url_unknown_geostore, gfw_obj)
        updated_qp = parser.parse_qs(parser.urlparse(updated_url).query)

        self.assertEqual(updated_qp[GEOSTORE_FIELD][0], new_geostore_id)
        self.assertEqual(updated_qp[GLAD_CONFIRM_FIELD][0], 'True')

    @patch('requests.get')
    def test_download_glad_one_subscription_unknown_geostore(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task

        self._create_and_get_test_model()

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())  # GLAD_ALERT_DOWNLOADED_DATA has 1 confirmed sub

        with patch('analyzers.gfw_inbound.process_downloaded_alerts') as mock_download_process_alerts:
            self._post_data(json.dumps(GLAD_ALERT))
            self.assertEqual(mock_download_process_alerts.call_count, 1)

    @patch('requests.get')
    def test_download_glad_two_subscriptions_unknown_geostore(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task

        self._create_and_get_test_model()
        self._create_and_get_test_model()

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())  # GLAD_ALERT_DOWNLOADED_DATA has 1 confirmed sub

        with patch('analyzers.gfw_inbound.process_downloaded_alerts') as mock_download_process_alerts:
            self._post_data(json.dumps(GLAD_ALERT))
            self.assertEqual(mock_download_process_alerts.call_count, 2)

    @patch('requests.get')
    def test_download_glad_two_subscriptions_known_geostore_and_subscription(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task

        self._create_and_get_test_model()
        self._create_and_get_test_model(subscription_id=self.test_data_glad_subscription_id,
                                        geostore_id=self.test_data_geostore_id)

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())

        with patch('analyzers.gfw_inbound.process_downloaded_alerts') as mock_download_process_alerts:
            self._post_data(json.dumps(GLAD_ALERT))
            self.assertEqual(mock_download_process_alerts.call_count, 1)

    @patch('requests.get')
    def test_download_glad_two_subscriptions_unknown_geostore_known_subscription(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task

        self._create_and_get_test_model()
        self._create_and_get_test_model(subscription_id=self.test_data_glad_subscription_id)

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())

        with patch('analyzers.gfw_inbound.process_downloaded_alerts') as mock_download_process_alerts:
            self._post_data(json.dumps(GLAD_ALERT))
            self.assertEqual(mock_download_process_alerts.call_count, 1)

    def test_with_bad_subscription_id(self):
        # save glad test data's subscription_id in the db
        self._create_and_get_test_model()
        response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))  # send in viirs data, different subscription_id
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
        gfw_model.objects.create(**gfw_data)

        # Monkey-patch send_task to execute task by blocking
        # (simulate task_always_eager=True) since send_task does not respect  task_always_eager when true.
        app.send_task = send_task

        response = self._post_data(json.dumps(GLAD_ALERT))
        # There is only one alert with confidence level 3 in 'GLAD_ALERT_DOWNLOADED_DATA' (example data)
        expected_event = 1
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(expected_event, Event.objects.all().count())

        # Update the confidence level for GFWSubscription object
        # to Confirmed and Unconfirmed.
        qs = gfw_model.objects.filter(subscription_id='5d1f9014836a9b13000e7d1d')
        qs.update(Deforestation_confidence=gfw_model.BOTH_CONFIRMED_UNCONFIRMED)

        response = self._post_data(json.dumps(GLAD_ALERT))
        clustered_alerts = cluster_alerts(
            GLAD_ALERT_DOWNLOADED_DATA['data'],
            settings.GFW_CLUSTER_RADIUS, 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(clustered_alerts), Event.objects.all().count())

    # @patch('analyzers.gfw_utils.get_viirs_fire_alerts')
    @patch('analyzers.tasks.requests.post')
    def test_filter_confidence_level_for_fire(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(VIIRS_FIRE_ALERT_DOWNLOADED_DATA))
        # mock_callback.return_value = VIIRS_CALLBACK_DATA

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
        clustered_alerts = cluster_alerts(VIIRS_FIRE_ALERT_DOWNLOADED_DATA['rows'], settings.GFW_CLUSTER_RADIUS, 1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(clustered_alerts), Event.objects.all().count())

    def _create_and_get_test_model(self, subscription_id=None, geostore_id=None,
                                   glad_conf=None, viirs_conf=None, additional=None):
        if not subscription_id:
            subscription_id = self.faker.name()
        if not geostore_id:
            geostore_id = self.faker.name()
        if not glad_conf:
            glad_conf = gfw_model.CONFIRMED
        if not viirs_conf:
            viirs_conf = gfw_model.HIGH_NOMINAL
        if not additional or not additional['alert_types']:
            additional = {'alert_types': ['viirs-active-fires', 'glad-alerts']}

        return gfw_model.objects.create(name='Test alert', subscription_id=subscription_id,
                                        geostore_id=geostore_id,
                                        subscription_geometry=self.subscription_poly,
                                        Deforestation_confidence=glad_conf,
                                        Fire_confidence=viirs_conf,
                                        additional=additional)
