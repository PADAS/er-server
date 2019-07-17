import json

import requests
from django.contrib.gis.geos import GEOSGeometry
from functional import seq
from rest_framework import status

from analyzers.models.gfw import GlobalForestWatchSubscription
from analyzers.tests import gfw_test_data
from core.tests import BaseAPITest

GFW_API_ROOT = 'https://production-api.globalforestwatch.org/v1'
SUBSCRIPTION_ENDPOINT = f'{GFW_API_ROOT}/subscriptions'
GEOSTORE_ENDPOINT = f'{GFW_API_ROOT}/geostore'
AUTH_HEADER = {'Authorization': f'Bearer {gfw_test_data.GFW_AUTH_TOKEN}'}


class GFWServiceTest(BaseAPITest):

    def setUp(self):
        super().setUp()

        self.subscription_ids_to_delete = []

    def tearDown(self):
        seq(self.subscription_ids_to_delete).for_each(self._unsubscribe)
        # todo: filter for/delete only those subs that are in the sub_ids_to_delete list
        GlobalForestWatchSubscription.objects.all().delete()

    def test_create_geostore(self):
        rsp = self._post_data(GEOSTORE_ENDPOINT, {'geojson': gfw_test_data.DRC_POLYGON})
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)
        self.assertEqual(json.loads(rsp.text)['data']['id'], gfw_test_data.DRC_GEOSTORE_ID)

    def test_create_subscriptions(self):
        test_models = [x for x in self._generate_model_objects()]

        seq(test_models).for_each(self._verify_subscription)

    def test_get_subscription(self):
        model = self._make_model_object(gfw_test_data.GLAD_ALERT_SUBSCRIPTION_DATA)
        model.save()
        self._verify_subscription(model)

    def test_update_subscription(self):
        model = self._make_model_object(gfw_test_data.GLAD_ALERT_SUBSCRIPTION_DATA)
        model.save()

        self._verify_subscription(model)
        sub_id = model.subscription_id

        model.additional = {'alert_types': gfw_test_data.FIRE_ALERT_SUBSCRIPTION_DATA['datasets'],
                            'gfw_auth_token': gfw_test_data.GFW_AUTH_TOKEN}

        model.save()

        self.assertEqual(model.subscription_id, sub_id)  # shouldn't have created a new subscription_id

        rsp = self._get_data(dest_url=f'{SUBSCRIPTION_ENDPOINT}/{model.subscription_id}',
                             headers=AUTH_HEADER)

        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)
        rsp_payload = json.loads(rsp.text)['data']
        self.assertEqual(gfw_test_data.FIRE_ALERT_SUBSCRIPTION_DATA['datasets'],
                         rsp_payload['attributes']['datasets'])

    def _generate_model_objects(self):
        sub_configs = [gfw_test_data.GLAD_ALERT_SUBSCRIPTION_DATA,
                       gfw_test_data.FIRE_ALERT_SUBSCRIPTION_DATA,
                       gfw_test_data.TERRAI_ALERT_SUBSCRIPTION_DATA,
                       gfw_test_data.ALL_ALERTS_SUBSCRIPTION_DATA,
                       ]
        for cfg in sub_configs:
            model = self._make_model_object(cfg)
            model.save()
            yield model

    def _make_model_object(self, cfg):
        additional = {'alert_types': cfg['datasets'],
                      'gfw_auth_token': gfw_test_data.GFW_AUTH_TOKEN}
        return GlobalForestWatchSubscription(name=cfg['name'],
                                             additional=additional,
                                             subscription_geometry=GEOSGeometry(
                                                 json.dumps(gfw_test_data.DRC_POLYGON)))

    def _verify_subscription(self, model):
        self.assertIsNotNone(model.id)
        self.assertIsNotNone(model.subscription_id)
        self.assertIsNotNone(model.geostore_id)

        self.subscription_ids_to_delete.append(model.subscription_id)

        persisted_instance = GlobalForestWatchSubscription.objects.get(pk=model.id)
        self.assertIsNotNone(persisted_instance)

        rsp = self._get_data(dest_url=f'{SUBSCRIPTION_ENDPOINT}/{persisted_instance.subscription_id}',
                             headers=AUTH_HEADER)

        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)

    def _unsubscribe(self, sub_id):
        rsp = requests.get(url=f'{SUBSCRIPTION_ENDPOINT}/{sub_id}/unsubscribe', headers=AUTH_HEADER)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)

    def _post_data(self, dest_url, payload_dict, headers=None):
        return requests.post(url=dest_url, json=payload_dict, headers=headers)

    def _get_data(self, dest_url, payload_dict=None, headers=None):
        return requests.get(url=dest_url, json=payload_dict, headers=headers)
