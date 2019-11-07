import json

from rest_framework import status
from django.contrib.gis.geos import Point

from core.tests import BaseAPITest
from observations.models import Observation, Source, Subject
from sensors.sigfox_foundation_push_handler import SigfoxFoundationPushHandler, SigfoxPayloadParser
from sensors.tests.sigfox_foundation_test_data import DATA_PAIRS
from sensors.views import SensorObservation


class SigfoxFoundationHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'sff-provider'

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  SigfoxFoundationPushHandler.SENSOR_TYPE,
                                  self.PROVIDER_KEY, 'status'))

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
            device_id = data_uplink['deviceId']
            rsp = self._post_data(json.dumps(data_uplink))

            self.assertIsNotNone(rsp)
            self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
            source = Source.objects.get(manufacturer_id=device_id)
            self.assertIsNotNone(source)
            self.assertIsNotNone(Subject.objects.get(name=device_id))

            observation = Observation.objects.get(source=source)
            self._verify_data_uplink_rsp(observation, data_uplink)

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
            observation = Observation.objects.get(source=source)
            self._verify_data_advanced_rsp(observation, data_advanced)

    def test_uplink_then_advanced(self):

        for (uplink, advanced) in DATA_PAIRS:
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
            self.assertEqual(1, Observation.objects.filter(source=source).count())

            updated_observation = Observation.objects.get(source=source)
            self.assertEqual(observation.id, updated_observation.id)
            self._verify_data_advanced_rsp(updated_observation, advanced)

    def test_duplicate_uplink(self):
        uplink, _ = DATA_PAIRS[0]
        rsp = self._post_data(json.dumps(uplink))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source__manufacturer_id__exact=uplink['deviceId']).count())

        posted_again = self._post_data(json.dumps(uplink))
        self.assertIsNotNone(posted_again)
        self.assertEqual(posted_again.status_code, status.HTTP_200_OK)
        self.assertEqual(1, Observation.objects.filter(source__manufacturer_id__exact=uplink['deviceId']).count())

    def test_dupllicate_advanced(self):
        _, advanced = DATA_PAIRS[0]
        rsp = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(1, Observation.objects.filter(source__provider__provider_key=self.PROVIDER_KEY).count())

        posted_again = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(posted_again)
        self.assertEqual(1, Observation.objects.filter(source__provider__provider_key=self.PROVIDER_KEY).count())

    def test_advanced_updated_location(self):
        _, advanced = DATA_PAIRS[2]
        rsp = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
        obs = Observation.objects.get(source__manufacturer_id=advanced['deviceId'])
        self._verify_data_advanced_rsp(obs, advanced)

        advanced['computedLocation']['lat'] = 0
        advanced['computedLocation']['lng'] = 0
        posted_again = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(posted_again)
        self.assertEqual(posted_again.status_code, status.HTTP_200_OK)
        updated_obs = Observation.objects.get(source__manufacturer_id=advanced['deviceId'])
        self._verify_data_advanced_rsp(updated_obs, advanced)

    def test_advanced_updated_additional(self):
        _, advanced = DATA_PAIRS[2]
        rsp = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
        obs = Observation.objects.get(source__manufacturer_id=advanced['deviceId'])
        self._verify_data_advanced_rsp(obs, advanced)

        advanced['computedLocation']['lat'] = 0
        advanced['computedLocation']['lng'] = 0
        advanced['computedLocation']['radius'] = 0
        advanced['computedLocation']['source'] = 0
        posted_again = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(posted_again)
        self.assertEqual(posted_again.status_code, status.HTTP_200_OK)
        updated_obs = Observation.objects.get(source__manufacturer_id=advanced['deviceId'])
        self._verify_data_advanced_rsp(updated_obs, advanced)

    def test_advanced_updated_location_additional(self):
        _, advanced = DATA_PAIRS[2]
        rsp = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(rsp)
        self.assertEqual(rsp.status_code, status.HTTP_201_CREATED)
        obs = Observation.objects.get(source__manufacturer_id=advanced['deviceId'])
        self._verify_data_advanced_rsp(obs, advanced)

        advanced['computedLocation']['radius'] = 0
        advanced['computedLocation']['source'] = 0
        posted_again = self._post_data(json.dumps(advanced))
        self.assertIsNotNone(posted_again)
        self.assertEqual(posted_again.status_code, status.HTTP_200_OK)
        updated_obs = Observation.objects.get(source__manufacturer_id=advanced['deviceId'])
        self._verify_data_advanced_rsp(updated_obs, advanced)

    def _verify_data_advanced_rsp(self, observation, test_data):
        self.assertIsNotNone(observation)
        location = Point(test_data['computedLocation']['lng'], test_data['computedLocation']['lat'])
        self.assertEqual(observation.source.manufacturer_id, test_data['deviceId'])
        self.assertEqual(observation.location.coords, location.coords)
        self.assertEqual(observation.additional['radius'], test_data['computedLocation']['radius'])
        self.assertEqual(observation.additional['source'], test_data['computedLocation']['source'])
        self.assertEqual(observation.additional['status'], test_data['computedLocation']['status'])
        self.assertEqual(observation.additional['seqNumber'], test_data['seqNumber'])

    def _verify_data_uplink_rsp(self, observation, test_data):
        self.assertIsNotNone(observation)
        parsed_data = SigfoxPayloadParser.parse(test_data['data'])
        self.assertIsNotNone(parsed_data)
        location = Point(parsed_data['longitude'], parsed_data['latitude'])
        self.assertEqual(observation.source.manufacturer_id, test_data['deviceId'])
        self.assertEqual(observation.location.coords, location.coords)
        self.assertEqual(observation.additional['reception'], test_data['reception'])
        self.assertEqual(observation.additional['seqNumber'], test_data['seqNumber'])

    def _post_data(self, payload):
        request = self.factory.post(self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = SensorObservation.as_view()(request,
                                               sensor_type=SigfoxFoundationPushHandler.SENSOR_TYPE,
                                               provider_key=self.PROVIDER_KEY)
        return response
