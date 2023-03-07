import json
from unittest import mock

from django.urls import resolve, reverse
from rest_framework import status

from core.tests import BaseAPITest, fake_get_pool
from sensors.views import EzyTrackHandlerView


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
        return path

    def _post_ezytrack_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = EzyTrackHandlerView.as_view()(request, self.PROVIDER_KEY)
        return response

    def test_url_handler(self):
        resolver = resolve(self.api_path)
        assert resolver.func.cls == EzyTrackHandlerView

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_ezytrack_observations(self):
        response = self._post_ezytrack_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_duplicate_observation(self):
        self._post_ezytrack_data(json.dumps(self.test_data))
        response = self._post_ezytrack_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})
