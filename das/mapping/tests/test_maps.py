import logging

from django.test import TestCase
from django.contrib.auth import get_user_model

from core.tests import BaseAPITest
from mapping import views
logger = logging.getLogger(__name__)

User = get_user_model()


class TestMaps(BaseAPITest):
    fixtures = ('initial_dev_map.yaml', './test/mapping_layer.yaml')

    def test_return_two_maps(self):
        request = self.factory.get(
            self.api_base + '/maps')
        self.force_authenticate(request, self.app_user)

        response = views.MapListJsonView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

    def test_return_layers(self):
        request = self.factory.get(
            self.api_base + '/layers')
        self.force_authenticate(request, self.app_user)

        response = views.LayerListJsonView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
