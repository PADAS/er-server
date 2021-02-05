import json
from unittest.mock import patch, Mock
from datetime import date, timedelta

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.test import override_settings
from faker import Faker
from rest_framework import status
import urllib.parse as parser

from analyzers.clustering_utils import cluster_alerts
from activity.models import Event, EventDetails
from analyzers import gfw_utils, tasks
from analyzers.gfw_utils import (get_geostore_id, GEOSTORE_FIELD, GLAD_CONFIRM_FIELD,
                                 rebuild_glad_download_url)
from analyzers.models import GlobalForestWatchSubscription as gfw_model
# noinspection PyUnresolvedReferences
from analyzers.tasks import download_gfw_alerts  # prevent pycharm optimize import from removing this
from analyzers.tests.gfw_test_data import VIIRS_FIRE_ALERT, GLAD_ALERT, GLAD_ALERT_DOWNLOADED_DATA, \
    VIIRS_FIRE_ALERT_DOWNLOADED_DATA, VIIRS_CALLBACK_DATA
from analyzers.gfw_alert_schema import GFWLayerSlugs
from core.tests import BaseAPITest
from das_server.celery import app
from sensors.views import GFWAlertHandlerView


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
        response = GFWAlertHandlerView.as_view()(request, self.provider)
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

    def test_webhook_verify_params(self):
        sub = self._create_and_get_test_model(glad_conf=gfw_model.BOTH_CONFIRMED_UNCONFIRMED,
                                              additional={'alert_types': [GFWLayerSlugs.GLAD_ALERTS.value]})
        self.assertIsNotNone(sub)

        with patch(f'{__name__}.send_task') as mock_task:
            app.send_task = send_task
            response = self._post_data(json.dumps(GLAD_ALERT))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_task.assert_called_once()
            _, args_dict = mock_task.call_args
            download_url = args_dict['args'][0]
            self.assertTrue(parser.urlparse(settings.GFW_API_ROOT).netloc in download_url)
            self._verify_download_url(sub, download_url, date(2019, 7, 1), date(2019, 7, 2), False)

        with patch(f'{__name__}.send_task') as mock_task:
            sub.additional = {'alert_types': [GFWLayerSlugs.VIIRS_ACTIVE_FIRES.value]}
            sub.save()
            app.send_task = send_task
            response = self._post_data(json.dumps(VIIRS_FIRE_ALERT))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_task.assert_called_once()
            _, args_dict = mock_task.call_args
            self._verify_viirs_params(sub, date(2019, 6, 24), date(2019, 6, 25), args_dict['args'][0])

    @override_settings(GFW_BACKFILL_INTERVAL_DAYS=4)
    @patch('django.db.models.signals.post_delete')
    @patch('analyzers.gfw_utils.date')
    def test_poll_gfw_verify_params(self, mock_date, mock_delete):
        mock_date.today.return_value = date(2020, 12, 20)
        self._create_and_get_test_model()

        with patch(f'{__name__}.send_task') as mock_task:
            app.send_task = send_task
            tasks.poll_gfw()
            self.assertEqual(mock_task.call_count, 8)

        gfw_model.objects.all().delete()

        today = date(2020, 12, 21)
        mock_date.today.return_value = today
        start_date, end_date = today - timedelta(gfw_utils.DEFAULT_LOOKBACK_DAYS), today
        sub = self._create_and_get_test_model(additional={'alert_types': [GFWLayerSlugs.GLAD_ALERTS.value]})
        self.assertIsNotNone(sub)

        with patch(f'{__name__}.send_task') as mock_task:
            app.send_task = send_task
            tasks.poll_gfw()
            mock_task.assert_called_once()
            _, args_dict = mock_task.call_args
            download_url = args_dict['args'][0]
            self.assertTrue(parser.urlparse(settings.GFW_API_ROOT).netloc in download_url)
            self._verify_download_url(sub, download_url, start_date, end_date, True)

        with patch(f'{__name__}.send_task') as mock_task:
            sub.Deforestation_confidence = gfw_model.BOTH_CONFIRMED_UNCONFIRMED
            sub.save()
            app.send_task = send_task
            tasks.poll_gfw()
            mock_task.assert_called_once()
            _, args_dict = mock_task.call_args
            download_url = args_dict['args'][0]
            self.assertTrue(parser.urlparse(settings.GFW_API_ROOT).netloc in download_url)
            self._verify_download_url(sub, download_url, start_date, end_date, False)

        with patch(f'{__name__}.send_task') as mock_task:
            sub.additional = {'alert_types': [GFWLayerSlugs.VIIRS_ACTIVE_FIRES.value]}
            sub.save()
            app.send_task = send_task
            tasks.poll_gfw()
            mock_task.assert_called_once()
            _, args_dict = mock_task.call_args
            self._verify_viirs_params(sub, start_date, end_date, args_dict['args'][0])

    @patch('requests.get')
    def test_eventdetails_update(self, mock_request):
        mock_request.return_value = Mock(status_code=200, text=json.dumps(GLAD_ALERT_DOWNLOADED_DATA))
        app.send_task = send_task
        self._create_and_get_test_model(subscription_id=self.test_data_glad_subscription_id,
                                        geostore_id=self.test_data_geostore_id)

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())

        evt_details = EventDetails.objects.all().first()
        self.assertIsNotNone(evt_details)
        self.assertEqual(3, evt_details.data['event_details']['confidence'])  # confirmed GLAD event
        id = evt_details.id
        evt_details.data['event_details']['confidence'] = 2  # make it unconfirmed
        evt_details.save()

        response = self._post_data(json.dumps(GLAD_ALERT))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Event.objects.all().count())

        evt_details = EventDetails.objects.all().first()
        self.assertIsNotNone(evt_details)
        self.assertEqual(id, evt_details.id)
        self.assertEqual(3, evt_details.data['event_details']['confidence'])  # confidence should have updated

    @patch('analyzers.gfw_utils.date')
    def test_make_alert_infos(self, mock_date):
        test_end_date = date(2020, 12, 21)
        test_start_date = test_end_date - timedelta(days=gfw_utils.DEFAULT_LOOKBACK_DAYS)  # the default
        mock_date.today.return_value = test_end_date
        alert_types = [
            [GFWLayerSlugs.VIIRS_ACTIVE_FIRES.value],
            [GFWLayerSlugs.GLAD_ALERTS.value],
            [GFWLayerSlugs.VIIRS_ACTIVE_FIRES.value, GFWLayerSlugs.GLAD_ALERTS.value],
        ]
        for t in alert_types:
            self._create_and_get_test_model(additional={'alert_types': t})

        self.assertEqual(gfw_model.objects.count(), len(alert_types))

        for subscription in gfw_model.objects.all():
            for slug in subscription.additional['alert_types']:
                alert_infos = list(gfw_utils.make_alert_infos(slug, subscription))
                self.assertEqual(1, len(alert_infos))
                self._verify_alert_info(subscription, alert_infos[0], test_start_date, test_end_date)

    def test_generate_intervals(self):
        start, end = date(2020, 12, 1), date(2020, 12, 9)
        expected_intervals = [(start, end)]
        intervals = list(gfw_utils.generate_intervals(start, end))
        self.assertEqual(intervals, expected_intervals)

        start, end = date(2020, 12, 1), date(2020, 12, 31)
        expected_intervals = self._get_expected_intervals(start, 1)
        intervals = list(gfw_utils.generate_intervals(start, end))
        self.assertEqual(intervals, expected_intervals)

        start, end = date(2020, 11, 1), date(2020, 12, 31)
        expected_intervals = self._get_expected_intervals(start, 2)
        intervals = list(gfw_utils.generate_intervals(start, end))
        self.assertEqual(intervals, expected_intervals)

        end = date(2021, 1, 10)
        start = end - timedelta(180)
        expected_intervals = self._get_expected_intervals(start, 6)
        intervals = list(gfw_utils.generate_intervals(start, end))
        self.assertEqual(intervals, expected_intervals)

        end = date(2022, 1, 20)
        start = end - timedelta(270)
        expected_intervals = self._get_expected_intervals(start, 9)
        intervals = list(gfw_utils.generate_intervals(start, end))
        self.assertEqual(intervals, expected_intervals)

        start, end = date(2020, 1, 1), date(2020, 12, 31)
        expected_intervals = self._get_expected_intervals(start, 12)
        last_end_interval = expected_intervals[-1][1]
        expected_intervals.append((last_end_interval, end))
        intervals = list(gfw_utils.generate_intervals(start, end))
        self.assertEqual(intervals, expected_intervals)

    @override_settings(GFW_BACKFILL_INTERVAL_DAYS=4)
    @patch('analyzers.gfw_utils.date')
    def test_backfill_scheduling(self, mock_date):
        test_end_date = date(2020, 12, 20)
        test_start_date = test_end_date - timedelta(days=gfw_utils.DEFAULT_LOOKBACK_DAYS)  # the default
        mock_date.today.return_value = test_end_date

        self._create_and_get_test_model(glad_conf=gfw_model.BOTH_CONFIRMED_UNCONFIRMED,
                                        additional={'alert_types': [GFWLayerSlugs.GLAD_ALERTS.value]})
        self.assertEqual(1, gfw_model.objects.count())

        slug, subscription = GFWLayerSlugs.GLAD_ALERTS.value, gfw_model.objects.first()
        subscription.glad_confirmed_backfill_days = 180
        subscription.save()

        alert_infos = list(gfw_utils.make_alert_infos(slug, subscription))
        self.assertEqual(7, len(alert_infos))  # should get 7 alert_infos
        # first info is for the normal poll that goes back 10 days, confirmed=False
        self._verify_alert_info(subscription, alert_infos[0], test_start_date, test_end_date, False)

        # other 6 infos are for the confirmed glad backfill poll, interval sz=30
        interval_start = test_end_date - timedelta(days=180)
        for i in range(6):
            self._verify_alert_info(subscription,
                                    alert_infos[i+1],
                                    interval_start,
                                    interval_start + timedelta(days=30),
                                    True)
            interval_start += timedelta(days=30)

        # the next day, we're back to the normal poll
        test_end_date = test_end_date + timedelta(1)
        test_start_date = test_start_date + timedelta(1)
        mock_date.today.return_value = test_end_date
        alert_infos = list(gfw_utils.make_alert_infos(slug, subscription))
        self.assertEqual(1, len(alert_infos))  # should get 1 alert_info
        self._verify_alert_info(subscription, alert_infos[0], test_start_date, test_end_date, False)

    def _get_expected_intervals(self, start_date: date, num: int):
        expected_intervals = []
        int_start = start_date
        for i in range(num):
            int_end = int_start + timedelta(30)
            expected_intervals.append((int_start, int_end))
            int_start = int_end
        return expected_intervals

    def _verify_alert_info(self, subscription: gfw_model, alert_info: dict,
                           expected_start_date: date, expected_end_date: date,
                           expected_confirmed_only: bool = True):
        alert_date_begin = alert_info['alert_date_begin']
        alert_date_end = alert_info['alert_date_end']

        self.assertEqual(alert_date_begin, expected_start_date.strftime('%Y-%m-%d'))
        self.assertEqual(alert_date_end, expected_end_date.strftime('%Y-%m-%d'))
        self._verify_download_url(subscription, alert_info['downloadUrls']['json'],
                                  expected_start_date, expected_end_date, expected_confirmed_only)

    def _verify_download_url(self, subscription: gfw_model, download_url: str,
                             expected_start_date: date, expected_end_date: date, expected_confirmed_only: bool):
        query_params = parser.parse_qs(parser.urlparse(download_url).query)
        start_date, end_date = query_params['period'][0].split(',')

        self.assertEqual(query_params[GEOSTORE_FIELD][0], subscription.geostore_id)
        self.assertEqual(query_params[GLAD_CONFIRM_FIELD][0], str(expected_confirmed_only))
        self.assertEqual(start_date, expected_start_date.strftime('%Y-%m-%d'))
        self.assertEqual(end_date, expected_end_date.strftime('%Y-%m-%d'))

    def _verify_viirs_params(self, subscription: gfw_model,
                             start_date: date, end_date: date, virrs_params: dict):
        url, query = virrs_params['URL'], virrs_params['param']['q']
        self.assertEqual(settings.CARTO_URL, url)
        self.assertTrue(start_date.strftime('%Y-%m-%d') in query)
        self.assertTrue(end_date.strftime('%Y-%m-%d') in query)
        self.assertTrue(gfw_utils.confidence_level_fmt(subscription.Fire_confidence) in query)

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
