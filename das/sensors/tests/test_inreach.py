import json

from django.urls import resolve
from rest_framework import status

from core.tests import BaseAPITest
from observations.models import Observation
from sensors.handlers import InreachPushHandler
from sensors.views import InreachHandlerView


class InreachPushHandlerTest(BaseAPITest):
    PROVIDER_KEY = 'inreach-provider'

    def setUp(self):
        super().setUp()
        self.api_path = '/'.join((self.api_base, 'sensors',
                                  InreachPushHandler.SENSOR_TYPE,
                                  self.PROVIDER_KEY, 'status'))

        self.test_data = {
            'Version': '2.0', 'Events': [
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 0, 'timeStamp': 1592067510000,
                    'point': {'latitude': 47.72327899932861, 'longitude': -122.34231233596802, 'altitude': 122.42968, 'gpsFix': 2, 'course': 270.0, 'speed': 58.665},
                    'status': {'autonomous': 0, 'lowBattery': 2, 'intervalChange': 0, 'resetDetected': 0}},
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 11, 'timeStamp': 1592092215000,
                    'point': {'latitude': 47.93302774429321, 'longitude': -122.168869972229, 'altitude': 2.34594035, 'gpsFix': 2, 'course': 22.5, 'speed': 15.325},
                    'status': {'autonomous': 0, 'lowBattery': 2, 'intervalChange': 600, 'resetDetected': 0}},
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 0, 'timeStamp': 1592094630000,
                    'point': {'latitude': 47.701016664505005, 'longitude': -122.29115724563599, 'altitude': 71.4391556, 'gpsFix': 2, 'course': 0.0, 'speed': 0.0},
                    'status': {'autonomous': 0, 'lowBattery': 2, 'intervalChange': 0, 'resetDetected': 0}},
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 0, 'timeStamp': 1592094030000,
                    'point': {'latitude': 47.73379325866699, 'longitude': -122.30250835418701, 'altitude': 93.854454, 'gpsFix': 2, 'course': 90.0, 'speed': 46.172},
                    'status': {'autonomous': 0, 'lowBattery': 2, 'intervalChange': 0, 'resetDetected': 0}},
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 0, 'timeStamp': 1592093415000,
                    'point': {'latitude': 47.83799171447754, 'longitude': -122.26075172424316, 'altitude': 118.34, 'gpsFix': 2, 'course': 180.0, 'speed': 110.514},
                    'status': {'autonomous': 0, 'lowBattery': 0, 'intervalChange': 0, 'resetDetected': 0}},
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 0, 'timeStamp': 1592092815000,
                    'point': {'latitude': 47.978453636169434, 'longitude': -122.1903920173645, 'altitude': 22.64, 'gpsFix': 2, 'course': 180.0, 'speed': 80.83},
                    'status': {'autonomous': 0, 'lowBattery': 0, 'intervalChange': 0, 'resetDetected': 0}},
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 11, 'timeStamp': 1592146155000,
                    'point': {'latitude': 47.70206809043884, 'longitude': -122.29008436203003, 'altitude': 245.543549, 'gpsFix': 2, 'course': 45.0, 'speed': 1.0},
                    'status': {'autonomous': 0, 'lowBattery': 2, 'intervalChange': 600, 'resetDetected': 0}},
                {
                    'addresses': [], 'imei': '300434060291470', 'messageCode': 0, 'timeStamp': 1592146755000,
                    'point': {'latitude': 47.701295614242554, 'longitude': -122.29079246520996, 'altitude': 116.30191, 'gpsFix': 2, 'course': 45.0, 'speed': 1.0},
                    'status': {'autonomous': 0, 'lowBattery': 2, 'intervalChange': 0, 'resetDetected': 0}},
                {
                    "addresses": [{"  address": "2075752244"}, {"  address": "product.support@garmin.com"}], "imei": "100000000000001", "messageCode":  3, "freeText":  "On my way.", "timeStamp":  1323784607377,
                    "point": {"latitude":  43.8078653812408, "longitude": -70.1636695861816, "altitude":  45, "gpsFix":  2, "course":  45, "speed":  50},
                    "status": {"autonomous":  0, "lowBattery":  1, "intervalChange":  0, "resetDetected":  0}}]}

    def _post_inreach_data(self, payload):
        request = self.factory.post(
            self.api_path, data=payload, content_type='application/json')
        self.force_authenticate(request, self.app_user)
        response = InreachHandlerView.as_view()(request, provider_key=self.PROVIDER_KEY)
        return response

    def test_url_handler(self):
        resolver = resolve(self.api_path + "/")
        assert resolver.func.cls == InreachHandlerView

    def test_inreach_observations(self):
        self.assertEqual(Observation.objects.count(), 0)
        response = self._post_inreach_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Observation.objects.count(), 9)

    def test_duplicate_observations(self):
        self._post_inreach_data(json.dumps(self.test_data))
        response = self._post_inreach_data(json.dumps(self.test_data))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})

    def test_invalid_inreach_payload(self):
        invalid_data = {"Events": [{"imei": "100000000000001"}]}
        response = self._post_inreach_data(json.dumps(invalid_data))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
