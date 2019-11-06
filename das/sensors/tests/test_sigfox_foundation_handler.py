import json

from rest_framework import status
from django.contrib.gis.geos import Point

from core.tests import BaseAPITest
from observations.models import Observation, Source, Subject
from sensors.sigfox_foundation_push_handler import SigfoxFoundationPushHandler, SigfoxPayloadParser
from sensors.tests.sigfox_foundation_test_data import DATA_PAIRS
from sensors.views import SensorObservation


class SigfoxFoundationHandlerTest(BaseAPITest):

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  SigfoxFoundationPushHandler.SENSOR_TYPE,
                                  SigfoxFoundationPushHandler.PROVIDER_KEY, 'status'))

    def test_that_test_data_is_valid(self):
        for (data_uplink, data_advanced) in DATA_PAIRS:
            self.assertIsNotNone(data_uplink['data'])
            self.assertIsNotNone(data_advanced['computedLocation'])
            self.assertEqual(24, len(data_uplink['data']))
            self.assertEqual(data_uplink['deviceId'], data_advanced['deviceId'])
            self.assertEqual(data_uplink['seqNumber'], data_advanced['seqNumber'])
            self.assertEqual(data_uplink['time'], data_advanced['time'])

    def test_all_data_uplink_msgs(self):
        for (data_uplink, _) in DATA_PAIRS:
            rsp = self._post_data(json.dumps(data_uplink))
            self.assertIsNotNone(rsp)
            self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
            # TODO

    def test_all_data_advanced_msgs(self):
        for (_, data_advanced) in DATA_PAIRS:
            device_id = data_advanced['deviceId']
            rsp = self._post_data(json.dumps(data_advanced))

            self.assertIsNotNone(rsp)
            self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
            source = Source.objects.get(manufacturer_id=device_id)
            self.assertIsNotNone(source)
            self.assertIsNotNone(Subject.objects.get(name=device_id))
            self.assertEqual(1, Observation.objects.filter(source=source).count())

    def test_uplink_then_advanced(self):
        (uplink, advanced) = DATA_PAIRS[0]
        device_id = uplink['deviceId']
        uplink_rsp = self._post_data(json.dumps(uplink))
        self.assertIsNotNone(uplink_rsp)
        self.assertEqual(uplink_rsp.status_code, status.HTTP_201_CREATED)
        source = Source.objects.get(manufacturer_id=device_id)

        observation = Observation.objects.get(source=source)
        self._verify_data_uplink_rsp(observation, uplink)

        advanced_rsp = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(advanced_rsp)
        self.assertEqual(advanced_rsp.status_code, status.HTTP_200_OK)

        updated_observation = Observation.objects.get(source=source)
        self.assertEqual(observation.id, updated_observation.id)
        self._verify_data_advanced_rsp(updated_observation, advanced)

    def _verify_data_advanced_rsp(self, observation, test_data):
        location = Point(test_data['computedLocation']['lng'], test_data['computedLocation']['lat'])
        self.assertEqual(observation.source.manufacturer_id, test_data['deviceId'])
        self.assertEqual(observation.location.coords, location.coords)
        self.assertEqual(observation.additional['radius'], test_data['computedLocation']['radius'])
        self.assertEqual(observation.additional['source'], test_data['computedLocation']['source'])
        self.assertEqual(observation.additional['status'], test_data['computedLocation']['status'])
        self.assertEqual(observation.additional['seqNumber'], test_data['seqNumber'])

    def _verify_data_uplink_rsp(self, observation, test_data):
        parsed_data = SigfoxPayloadParser.parse(test_data['data'])
        self.assertIsNotNone(parsed_data)
        location = Point(parsed_data['longitude'], parsed_data['latitude'])
        self.assertEqual(observation.source.manufacturer_id, test_data['deviceId'])
        self.assertEqual(observation.location.coords, location.coords)
        self.assertEqual(observation.additional['seqNumber'], test_data['seqNumber'])

    def _post_data(self, payload):
        request = self.factory.post(self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(request,
                                               sensor_type = SigfoxFoundationPushHandler.SENSOR_TYPE,
                                               provider_key = SigfoxFoundationPushHandler.PROVIDER_KEY)
        return response
