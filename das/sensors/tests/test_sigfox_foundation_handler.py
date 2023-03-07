import copy
import json
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.urls import resolve, reverse
from rest_framework import status

from core.tests import BaseAPITest
from observations.models import Observation, Source, Subject
from sensors.sigfox_foundation_push_handler import (SigfoxPayloadParserV1,
                                                    SigfoxV1Handler)
from sensors.tests.sigfox_foundation_test_data import DATA_PAIRS, V2_DATA_PAIRS
from sensors.views import (SigfoxFoundationHandlerView,
                           SigfoxV2FoundationHandlerView)


def MockUbi(device_id, data, latitude, longitude, time):
    res = {
        "lat": 48.127702668164275,
        "lng": -1.6279502140630846,
        "alt": 110.59460771083832,
        "accuracy": 35.751512683281305
    }
    return res


class SigfoxFoundationHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'sff-provider'

    def setUp(self):
        super().setUp()
        self.api_path = reverse(
            'sigfox-v1-view', kwargs=dict(provider_key=self.PROVIDER_KEY,))
        self.api_path_v2 = reverse(
            'sigfox-v2-view', kwargs=dict(provider_key=self.PROVIDER_KEY, ))

    def test_url_handler(self):
        resolver = resolve(self.api_path)
        assert resolver.func.cls == SigfoxFoundationHandlerView

        resolver = resolve(self.api_path_v2)
        assert resolver.func.cls == SigfoxV2FoundationHandlerView

    def test_that_test_data_is_valid(self):
        for (data_uplink, data_advanced) in DATA_PAIRS:
            self.assertIsNotNone(data_uplink['data'])
            self.assertIsNotNone(data_advanced['computedLocation'])
            self.assertEqual(24, len(data_uplink['data']))
            self.assertEqual(data_uplink['deviceId'],
                             data_advanced['deviceId'])
            self.assertEqual(data_uplink['seqNumber'],
                             data_advanced['seqNumber'])
            self.assertEqual(data_uplink['time'], data_advanced['time'])

    def test_all_data_uplink_msgs(self):
        for (data_uplink, _) in DATA_PAIRS:
            device_id = data_uplink['deviceId']
            rsp = self._post_data(json.dumps(data_uplink))

            self.assertIsNotNone(rsp)
            self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
            source = Source.objects.get(manufacturer_id=device_id)
            self.assertIsNotNone(source)
            self.assertIsNotNone(Subject.objects.get(name=device_id))

            observation = Observation.objects.get(source=source)
            self._verify_data_uplink_rsp(observation, data_uplink)

    @patch('sensors.sigfox_foundation_push_handler.SigfoxV2Handler.get_position_from_ubi', MockUbi)
    def test_sigfox_data_upload_v2_with_gpx_and_ubiscale_payload(self):
        count = 0
        for data_uplink in V2_DATA_PAIRS:
            device_id = data_uplink['deviceId']
            rsp = self._post_data(json.dumps(
                data_uplink), self.api_path_v2, SigfoxV2FoundationHandlerView)
            if count == 0:  # First iteration, ubi payload cached
                self.assertEqual(rsp.status_code, status.HTTP_200_OK)
                self.assertEqual(rsp.data, {
                                 'message': 'Uplink ubi payload, successfully cached for device: 14159EB'})

            elif count == 1:  # second payload, postion returned
                self.assertIsNotNone(rsp)
                self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
                source = Source.objects.get(manufacturer_id=device_id)
                observations = Observation.objects.count()
                self.assertEqual(observations, 1)

            elif count == 2:  # gps payload saved
                self.assertIsNotNone(rsp)
                self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
                source = Source.objects.get(manufacturer_id=device_id)
                observations = Observation.objects.count()
                # one more observation added
                self.assertEqual(observations, 2)

            elif count == 3:  # gps computed location ignored
                self.assertEqual(rsp.status_code, status.HTTP_200_OK)
                self.assertEqual(rsp.data, {})

            count += 1

    def test_sigfox_v2_setup_and_unknown_data_modes_not_processed(self):
        test_data = {
            "deviceId": "1",
            "time": "1461678551",
            "seqNumber": 1,
            "data": "8768"
        }
        rsp = self._post_data(json.dumps(test_data),
                              self.api_path_v2, SigfoxV2FoundationHandlerView)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)
        self.assertEqual(rsp.data, {
                         'message': 'Ignoring Boot/reboot, geolocation, and unknown record types. Data: 8768'})

    def test_sigfox_v2_invalid_records(self):
        test_data = {
            "time": "1461678551",
            "seqNumber": 1,
            "data": "80aed31501e97f8d3470e200"
        }
        rsp = self._post_data(json.dumps(test_data),
                              self.api_path_v2, SigfoxV2FoundationHandlerView)
        self.assertEqual(rsp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_all_data_advanced_msgs_ignored(self):
        for (_, data_advanced) in DATA_PAIRS:
            rsp = self._post_data(json.dumps(data_advanced))

            self.assertIsNotNone(rsp)
            self.assertEqual(rsp.status_code, status.HTTP_200_OK)

    def test_duplicate_uplink(self):
        uplink, _ = DATA_PAIRS[0]
        rsp = self._post_data(json.dumps(uplink))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(
            source__manufacturer_id__exact=uplink['deviceId']).count())

        posted_again = self._post_data(json.dumps(uplink))
        self.assertIsNotNone(posted_again)
        self.assertEqual(posted_again.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Observation.objects.filter(
            source__manufacturer_id__exact=uplink['deviceId']).count())

    def test_bad_msgs(self):
        uplink, advanced = DATA_PAIRS[0]
        bad_msg = copy.deepcopy(uplink)
        bad_msg.pop('deviceId')
        rsp = self._post_data(json.dumps(bad_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_400_BAD_REQUEST)

        bad_msg = copy.deepcopy(uplink)
        bad_msg.pop('time')
        rsp = self._post_data(json.dumps(bad_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_400_BAD_REQUEST)

        bad_msg = copy.deepcopy(uplink)
        bad_msg.pop('seqNumber')
        rsp = self._post_data(json.dumps(bad_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_400_BAD_REQUEST)

        bad_msg = copy.deepcopy(uplink)
        bad_msg['data'] = '8'  # data len < 2
        rsp = self._post_data(json.dumps(bad_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_400_BAD_REQUEST)

        bad_msg = copy.deepcopy(uplink)
        bad_msg['data'] = '80aed31501e97f8d3470e2rt'  # bad hex data
        rsp = self._post_data(json.dumps(bad_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_400_BAD_REQUEST)

        bad_msg = copy.deepcopy(uplink)
        bad_msg.pop('reception')
        rsp = self._post_data(json.dumps(bad_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)

    def test_ignored_msgs(self):
        uplink, _ = DATA_PAIRS[0]

        ignored_msg = copy.deepcopy(uplink)
        ignored_msg.pop('data')
        rsp = self._post_data(json.dumps(ignored_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)

        ignored_msg = copy.deepcopy(uplink)
        ignored_msg['data'] = '80aed31501e97f8d'  # data len != 24
        rsp = self._post_data(json.dumps(ignored_msg))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_200_OK)

    def _verify_data_uplink_rsp(self, observation, test_data, parser=SigfoxPayloadParserV1):
        self.assertIsNotNone(observation)
        components = SigfoxV1Handler.process_sigfoxv1_data(test_data)
        parsed_data = SigfoxPayloadParserV1.parse(components)
        self.assertIsNotNone(parsed_data)
        location = Point(parsed_data['longitude'], parsed_data['latitude'])
        self.assertEqual(observation.source.manufacturer_id,
                         test_data['deviceId'])
        self.assertEqual(observation.location.coords, location.coords)
        self.assertEqual(
            observation.additional['reception'], test_data['reception'])
        self.assertEqual(
            observation.additional['seqNumber'], test_data['seqNumber'])

    def _post_data(self, payload, path=None, view=SigfoxFoundationHandlerView):
        url = path if path else self.api_path
        request = self.factory.post(
            url, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = view.as_view()(request, self.PROVIDER_KEY)
        return response
