import json

import requests
from django.contrib.gis.geos import GEOSGeometry
from django.test import tag
from django.test.utils import skipIf
from rest_framework import status

from analyzers import gfw_outbound
from analyzers.tests import gfw_test_data
from core.tests import BaseAPITest

GFW_API_ROOT = 'https://production-api.globalforestwatch.org/v1'
SUBSCRIPTION_ENDPOINT = f'{GFW_API_ROOT}/subscriptions'
GEOSTORE_ENDPOINT = f'{GFW_API_ROOT}/geostore'
AUTH_HEADER = {'Authorization': f'Bearer {gfw_outbound.get_gfw_auth_token()}'}


@tag('gwf_outbound')
@skipIf(True, 'Skipping GFWServiceTest tests as they require GFW api calls')
class GFWServiceTest(BaseAPITest):

    def setUp(self):
        super().setUp()

        self.subscription_ids_to_delete = []

    def tearDown(self):
        [self._unsubscribe(sub_id)
         for sub_id in self.subscription_ids_to_delete]

    def test_create_geostore(self):
        id = gfw_outbound._get_geostore_id(
            {'subscription_geometry': GEOSGeometry(json.dumps(gfw_test_data.DRC_POLYGON))})
        self.assertIsNotNone(id)
        self.assertEqual(id, gfw_test_data.DRC_GEOSTORE_ID)

    def test_create_subscriptions(self):
        test_models = [x for x in self._generate_gfw_info_objects()]

        [self._create_and_verify_subscription(info) for info in test_models]

    def test_get_subscription(self):
        gfw_info = self._get_gfw_info(
            gfw_test_data.GLAD_ALERT_SUBSCRIPTION_DATA)
        self._create_and_verify_subscription(gfw_info)

    def test_update_subscription(self):
        gfw_info = self._get_gfw_info(
            gfw_test_data.GLAD_ALERT_SUBSCRIPTION_DATA)
        original_sub_id = self._create_and_verify_subscription(gfw_info)

        gfw_info = self._get_gfw_info(
            gfw_test_data.FIRE_ALERT_SUBSCRIPTION_DATA)
        gfw_info['subscription_id'] = original_sub_id
        rsp = gfw_outbound.update_subscription(gfw_info, False)

        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.get('status_code'), 200)
        self.assertEqual(rsp.get('text'), 'Success')

        data = rsp.get('data')
        self.assertIsNotNone(data)
        updated_sub_id = data.get('subscription_id')
        self.assertIsNotNone(updated_sub_id)
        self.assertIsNotNone(data.get('geostore_id'))

        # shouldn't have created a new subscription_id
        self.assertEqual(updated_sub_id, original_sub_id)

        rsp = self._get_data(dest_url=f'{SUBSCRIPTION_ENDPOINT}/{updated_sub_id}',
                             headers=AUTH_HEADER)

        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)
        rsp_payload = json.loads(rsp.text)['data']
        # datasets should have been updated
        self.assertEqual(gfw_test_data.FIRE_ALERT_SUBSCRIPTION_DATA['datasets'],
                         rsp_payload['attributes']['datasets'])

    def _generate_gfw_info_objects(self):
        subscription_configs = [gfw_test_data.GLAD_ALERT_SUBSCRIPTION_DATA,
                                gfw_test_data.FIRE_ALERT_SUBSCRIPTION_DATA,
                                gfw_test_data.TERRAI_ALERT_SUBSCRIPTION_DATA,
                                gfw_test_data.ALL_ALERTS_SUBSCRIPTION_DATA,
                                ]
        for cfg in subscription_configs:
            gfw_info = self._get_gfw_info(cfg)
            yield gfw_info

    def _get_gfw_info(self, cfg):
        return {
            'name': cfg.get('name'),
            'geostore_id': gfw_test_data.DRC_GEOSTORE_ID,
            'gfw_auth_token': gfw_test_data.GFW_AUTH_TOKEN,
            'alert_types': cfg['datasets'],
            'subscription_geometry': GEOSGeometry(
                json.dumps(gfw_test_data.DRC_POLYGON)),
        }

    def _create_and_verify_subscription(self, gfw_info):
        rsp = gfw_outbound.create_subscription(gfw_info)

        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.get('status_code'), 200)
        self.assertEqual(rsp.get('text'), 'Success')

        data = rsp.get('data')
        self.assertIsNotNone(data)
        sub_id = data.get('subscription_id')
        self.assertIsNotNone(sub_id)
        self.assertIsNotNone(data.get('geostore_id'))

        self.subscription_ids_to_delete.append(sub_id)

        rsp = self._get_data(dest_url=f'{SUBSCRIPTION_ENDPOINT}/{sub_id}',
                             headers=AUTH_HEADER)

        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)
        return sub_id

    def _unsubscribe(self, sub_id):
        rsp = requests.get(
            url=f'{SUBSCRIPTION_ENDPOINT}/{sub_id}/unsubscribe', headers=AUTH_HEADER)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)

    def _post_data(self, dest_url, payload_dict, headers=None):
        return requests.post(url=dest_url, json=payload_dict, headers=headers)

    def _get_data(self, dest_url, payload_dict=None, headers=None):
        return requests.get(url=dest_url, json=payload_dict, headers=headers)
