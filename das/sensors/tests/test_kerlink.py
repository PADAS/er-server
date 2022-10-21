import json
from unittest import mock

from django.urls import resolve, reverse
from rest_framework import status

from core.tests import BaseAPITest, fake_get_pool
from sensors.kerlink_push_handler import KerlinkMixin, KerlinkPushDataUp
from sensors.views import KerlinkHandlerView

test_data2 = {
    "id": "5f58ac3077d8d40001cf1103",
    "endDevice": {
        "devAddr": "021F523A",
        "cluster": {
            "id": 6
        },
        "devEui": "000DB538085F3865"
    },
    "fPort": 2,
    "fCntDown": 498,
    "fCntUp": 2980,
    "confirmed": False,
    "payload": "0c2902592712025abbd6ff46642fac585f0000",
    "encrypted": False,
    "ulFrequency": 868.1,
    "modulation": "LORA",
    "dataRate": "SF7BW125",
    "recvTime": 1599646768225,
    "gwCnt": 2,
    "gwInfo": [
        {
            "gwEui": "7276FF002E062405",
            "rfRegion": "EU868",
            "rssi": -111,
            "snr": 3.0,
            "latitude": -2.7827697,
            "longitude": 34.65938,
            "altitude": None,
            "channel": 5,
            "radioId": 65557,
            "rssis": -112,
            "rssisd": 0,
            "fineTimestamp": None,
            "antenna": 0,
            "frequencyOffset": -10246
        },
        {
            "gwEui": "7276FF002E062405",
            "rfRegion": "EU868",
            "rssi": -109,
            "snr": 4.0,
            "latitude": -2.7827697,
            "longitude": 34.65938,
            "altitude": None,
            "channel": 5,
            "radioId": 65557,
            "rssis": -110,
            "rssisd": 0,
            "fineTimestamp": None,
            "antenna": 1,
            "frequencyOffset": -10242
        }
    ],
    "adr": True,
    "codingRate": "4/5",
    "delayed": False,
    "classB": True,
    "encodingType": "HEXA"
}


def mock_response_endDevices():
    return {
        "profile": "VEHICLE",
        "name": "DFP-429 FZS BENZ",
        "appEui": "0000000000010203"
    }


class KerlinkHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'kerlink_provider'

    def setUp(self):
        super().setUp()
        self.api_path = self.get_webhook_base_url()
        self.test_data = {'id': '1',
                          'endDevice': {'devEui': '0000000000000000',
                                        'devAddr': '00000000',
                                        'cluster': {'id': -1}},
                          'fPort': 0,
                          'fCntDown': 0,
                          'fCntUp': 0,
                          'adr': True,
                          'confirmed': False,
                          'encrypted': False,
                          'payload': '00',
                          'encodingType': '',
                          'recvTime': 1,
                          'delayed': False,
                          'ulFrequency': 868.1,
                          'modulation': 'LORA',
                          'dataRate': 'SF11BW125',
                          'codingRate': '4/5',
                          'gwCnt': 1,
                          'gwInfo': [{'gwEui': '0000000000000000',
                                      'rfRegion': 'EU868',
                                      'rssi': -100,
                                      'snr': -19.1,
                                      'latitude': 0,
                                      'longitude': 0,
                                      'channel': 1,
                                      'radioId': 1
                                      }]}

    def get_webhook_base_url(self):
        provider_key = self.PROVIDER_KEY
        path = reverse('kerlink-view',
                       kwargs={'provider_key': provider_key})
        return path

    def _post_kerlink_dataup(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = KerlinkHandlerView.as_view()(request, self.PROVIDER_KEY)
        return response

    def test_url_handler(self):
        resolver = resolve(self.api_path)
        assert resolver.func.cls == KerlinkHandlerView

    def test_kerlink_serializer(self):
        serializer = KerlinkPushDataUp(data=self.test_data)
        self.assertIs(serializer.is_valid(), True)
        serializer = KerlinkPushDataUp(data=test_data2)
        self.assertIs(serializer.is_valid(), True)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    @mock.patch.object(KerlinkMixin, 'endDevice_info')
    def _test_kerlink_observation(self, mock_method):
        mock_method.return_value = {
            "profile": "VEHICLE",
            "name": "Trial 001 ",
            "appEui": "0000000000000000"
        }
        response = self._post_kerlink_dataup(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    @mock.patch.object(KerlinkMixin, 'endDevice_info')
    def test_decode_globalsat_payload(self, mock_method):
        mock_method.return_value = {
            "profile": "VEHICLE",
            "name": "DFP-429 FZS BENZ",
            "appEui": "0000000000010203"
        }
        response = self._post_kerlink_dataup(json.dumps(test_data2))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
