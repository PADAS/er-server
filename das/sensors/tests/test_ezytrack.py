import json

from django.urls import reverse
from rest_framework import status

from sensors.handlers import EzyTrackHandler
from sensors.views import EzyTrackHandlerView
from core.tests import BaseAPITest


class EzytrackHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'ezytrack_provider'

    def setUp(self):
        super().setUp()
        self.api_path = self.get_webhook_base_url()
        self.test_data = {"device": "114719", "device_type": "Oyster 2 - 2G/LTE(4G)",
                          "dateReceived": "2017-04-23T09:31:14Z", "latitude": "-26.0444252", "longitude": "28.0111314",
                          "speed": "0"}

    def get_webhook_base_url(self):
        provider_key = self.PROVIDER_KEY
        path = reverse('ezytrack-view',
                       kwargs={'provider_key': provider_key})

        return ''.join([self.api_base, path])

    def _post_ezytrack_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = EzyTrackHandlerView.as_view()(request, self.PROVIDER_KEY)
        return response

    def test_ezytrack_observations(self):
        response = self._post_ezytrack_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_duplicate_observation(self):
        self._post_ezytrack_data(json.dumps(self.test_data))
        response = self._post_ezytrack_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})
