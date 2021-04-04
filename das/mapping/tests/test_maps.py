import logging

from django.contrib.auth.models import Permission
from django.contrib.auth import get_user_model

from accounts.models import PermissionSet
from core.tests import BaseAPITest
from mapping import views

logger = logging.getLogger(__name__)

User = get_user_model()

TILELAYER_CUD_PERMISSIONS = ('change_tilelayer', 'delete_tilelayer', 'add_tilelayer')

class TestMaps(BaseAPITest):
    fixtures = ('initial_dev_map.yaml', './test/mapping_layer.yaml',
                'initial_tilelayers.json')
       
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

    def test_layers_api_crud_operations(self):
        ps = PermissionSet.objects.create(name='TILELAYER CUD Permissions')
        for p in Permission.objects.filter(codename__in=TILELAYER_CUD_PERMISSIONS):
            ps.permissions.add(p)
        self.app_user.permission_sets.add(ps)

        layers_url = self.api_base + '/mapping/layers'
        layer_data = dict(name="Esri Satellite", attributes={})

        # Create and view layer
        request = self.factory.post(layers_url, layer_data)
        self.force_authenticate(request, self.app_user)
        response = views.LayerListJsonView.as_view()(request)
        assert response.status_code == 201

        # Update layer
        layer_id = response.data.get('id')
        layer_url = self.api_base + f'/mapping/layer{layer_id}'
        update_data = dict(
            attributes={
                "type": "google_map",
                "title": "Google Satellite",
                "configuration": {
                    "accessToken": "testaccesstoken"
                }
            }
        )
        request = self.factory.patch(layer_url, update_data)
        self.force_authenticate(request, self.app_user)
        response = views.LayerJsonView.as_view()(request, id=layer_id)
        assert response.status_code == 200

        data = response.data
        assert data.get('name') == layer_data.get('name')
        assert data.get('attributes') == update_data.get("attributes")

        # Delete layer
        request = self.factory.delete(layer_url)
        self.force_authenticate(request, self.app_user)
        response = views.LayerJsonView.as_view()(request, id=layer_id)
        assert response.status_code == 204
