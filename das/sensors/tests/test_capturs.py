import json

from django.urls import resolve
from rest_framework import status

from core.tests import BaseAPITest
from observations.models import Observation, Source
from sensors.capturs import CaptursPushHandler
from sensors.views import CaptursHandlerView


class CaptursPushHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'capturs-provider'

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  CaptursPushHandler.SENSOR_TYPE,
                                  self.PROVIDER_KEY, 'status'))
        self.test_data = {
            "result": 1,
            "position": [
                {
                    "id": "3637431", "latitude": 43.63947, "longitude": 1.44846, "altitude": 210,
                    "speed": 3, "move": 0, "device": "1AC32E", "type": 1, "typeOrder": 0, "label": 0,
                    "sigSeqNumber": 3019, "timestamp": 1485384864, "date": "WedJan25201722:54:24GMT"
                },
                {
                    "id": "9937431", "latitude": 12.88876, "longitude": 83.99344, "altitude": 390,
                    "speed": 7, "move": 0, "device": "KA132E", "type": 1, "typeOrder": 0, "label": 0,
                    "sigSeqNumber": 8089, "timestamp": 2121214864, "date": "FriMar29201722:54:24GMT"
                }
            ]
        }

        self.new_test_data = {
            'label': 2, 'move': 0, 'latitude': -11.7671, 'longitude': 32.1729, 'latitudeInt': -11.767,
            'longitudeInt': 32.1729, 'latitudeInt2': -11.767, 'longitudeInt2': 32.173, 'latitudeHist': -11.767,
            'longitudeHist': 32.1728, 'device': 'CDCD30', 'time': 1598445769, 'signal': '13.67',
            'station': 'A9D9', 'avgSignal': 'null', 'rssi': '-141.00', 'seqNumber': '1956',
            'inhibitAlert': False, 'stationLat': 'null', 'stationLng': 'null', 'group': 'capturs',
            'deviceName': 'Monitoring 4', 'deviceType': 'capturs', 'deviceconnectionid': 'CAPTURS_BCDCD30',
            'deviceId': 'CDCD30', 'reception': [{'id': 'A9D9', 'RSSI': '-141.00', 'SNR': '13.67'}]}

    def _post_capturs_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload,
            content_type='application/json')

        self.force_authenticate(request, self.app_user)
        response = CaptursHandlerView.as_view()(
            request, self.PROVIDER_KEY)
        return response

    def test_url_handler(self):
        resolver = resolve(self.api_path + "/")
        assert resolver.func.cls == CaptursHandlerView

    def test_post_capturs_observations(self):
        response = self._post_capturs_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        source = Source.objects.get(
            manufacturer_id=self.test_data['position'][0]['device'])
        self.assertIsNotNone(source)
        self.assertEqual(Observation.objects.count(), 2)

        # post capturs observations with new test data
        self._post_capturs_data(json.dumps(self.new_test_data))
        source = Source.objects.get(
            manufacturer_id=self.new_test_data.get('device'))
        self.assertIsNotNone(source)

    def test_post_duplicate_observations(self):
        self._post_capturs_data(json.dumps(self.test_data))
        response = self._post_capturs_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})

    def test_invalid_observation_data(self):
        self.test_data['position'][0]['latitude'] = "errored"
        response = self._post_capturs_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_event_observation_with_unset_position_skipped_data(self):
        data = self.test_data['position'][0]
        data['latitude'], data['longitude'] = 0, 0
        response = self._post_capturs_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Only one observation created, 0,0 position skipped
        self.assertEqual(Observation.objects.count(), 1)
