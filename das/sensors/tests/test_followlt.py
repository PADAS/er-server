import logging
from django.contrib.auth.models import Permission
import django.contrib.auth

from core.tests import BaseAPITest
from sensors.views import SensorObservation
from observations.models import Subject, Source, SourceProvider, SubjectSource, \
    DEFAULT_ASSIGNED_RANGE

logger = logging.getLogger(__name__)
User = django.contrib.auth.get_user_model()


class RadioObservationTest(BaseAPITest):
    user_const = dict(last_name='Lastname',
                      first_name='Firstname', is_superuser=False)
    sensor_type = 'animal-collar-push'
    provider_key = 'grumeti-followlt'

    def setUp(self):
        super().setUp()

        self.testuser = User.objects.create_user('das_trbonet',
                                                 'das@tempuri.org',
                                                 'somesecret',
                                                 **self.user_const)

        self.henry = Subject.objects.create(name='henry')
        self.test_sourceprovider = SourceProvider.objects.create(
            display_name=self.provider_key, provider_key=self.provider_key)
        self.test_source = Source.objects.create(
            source_type='gps-radio', provider=self.test_sourceprovider,
            manufacturer_id='followlt-1234')

        self.test_subjectsource = SubjectSource.objects.create(
            source=self.test_source, subject=self.henry,
            assigned_range=DEFAULT_ASSIGNED_RANGE)

    def test_post_new_radio_update(self):

        data = [{"lat": 32.01, "lng": 40.05, "date": "12-09-2018", "ttf": "485",
                 "sats": "2", "collarId": "followlt-1234",
                 "positionId": "789adc", "serialId": "12345", "alt": "58",
                 "hdop": "0.23", "temp": "32.9", "name": "Test"},
                {"lat": 32.02, "lng": 40.06, "date": "13-09-2018", "ttf": "386",
                 "sats": "1", "collarId": "followlt-1234",
                 "positionId": "684adc", "serialId": "12345", "alt": "58",
                 "hdop": "0.23", "temp": "32.9", "name": "Test"}]

        path = '/'.join((self.api_base, 'sensors',
                         self.sensor_type, self.provider_key, 'status'))
        request = self.factory.post(path, data=data)

        self.force_authenticate(request, self.testuser)
        response = SensorObservation.as_view()(request,
                                               sensor_type=self.sensor_type,
                                               provider_key=self.provider_key)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(len(self.henry.observations()) == 2)
