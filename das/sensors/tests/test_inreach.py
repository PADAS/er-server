import json

from rest_framework import status

from core.tests import BaseAPITest
from sensors.handlers import InreachPushHandler
from sensors.views import SensorObservation


class InreachPushHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'inreach-provider'

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  InreachPushHandler.SENSOR_TYPE,
                                  self.PROVIDER_KEY, 'status'))
        self.test_data = {
            "Version": "2.0",
            "Events": [
                {
                    "imei": "100000000000001",
                    "messageCode":  3,
                    "freeText":  "On my way.",
                    "timeStamp":  1323784607377,
                    "addresses":
                        [
                            {"  address": "2075752244"},
                            {"  address": "product.support@garmin.com"}
                        ],
                    "point":
                        {
                            "latitude":  43.8078653812408,
                            "longitude": -70.1636695861816,
                            "altitude":  45,
                            "gpsFix":  2,
                            "course":  45,
                            "speed":  50
                        },
                    "status":
                        {
                            "autonomous":  0,
                            "lowBattery":  1,
                            "intervalChange":  0,
                            "resetDetected":  0
                        }
                }
            ]
        }

    def _post_inreach_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(
            request, sensor_type=InreachPushHandler.SENSOR_TYPE, provider_key=self.PROVIDER_KEY)
        return response

    def test_inreach_observations(self):
        response = self._post_inreach_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_duplicate_observations(self):
        self._post_inreach_data(json.dumps(self.test_data))
        response = self._post_inreach_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})

    def test_invalid_inreach_payload(self):
        invalid_data = {"Events": [{"imei": "100000000000001"}]}
        response = self._post_inreach_data(json.dumps(invalid_data))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
