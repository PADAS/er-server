import datetime
import logging
import uuid
from unittest import mock

from oauth2_provider.models import AccessToken

from django.urls import resolve
from django.utils import timezone
from rest_framework.test import force_authenticate

from core.tests import BaseAPITest, User, fake_get_pool
from observations.models import (DEFAULT_ASSIGNED_RANGE, Source,
                                 SourceProvider, Subject, SubjectSource)
from sensors.views import FollowltHandlerView

logger = logging.getLogger(__name__)


class FollowltObservationTest(BaseAPITest):
    # Set sensor_key of FollowltHandler and sourceprovider key
    user_const = dict(last_name='Lastname',
                      first_name='Firstname', is_superuser=False)
    sensor_type = 'animal-collar-push'
    provider_key = 'followlt'

    def setUp(self):
        # Create a user, subject linked with source via subjectsource,
        # and source linked with source provider
        super().setUp()
        self.testuser = User.objects.create_user('das_trbonet',
                                                 'das@tempuri.org',
                                                 'somesecret',
                                                 **self.user_const)

        self.henry = Subject.objects.create(name='henry')
        self.test_sourceprovider = SourceProvider.objects.create(
            display_name=self.provider_key, provider_key=self.provider_key)
        self.test_source = Source.objects.create(
            source_type='tracking-device', provider=self.test_sourceprovider,
            manufacturer_id='followlt-1234')

        self.test_subjectsource = SubjectSource.objects.create(
            source=self.test_source, subject=self.henry,
            assigned_range=DEFAULT_ASSIGNED_RANGE)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_post_new_radio_update(self):
        # Post sample data in api, and check subject's observations
        data = [{"lat": 32.01, "lng": 40.05, "date": "13-09-2018", "ttf": "485",
                 "sats": "2", "collarId": "followlt-1234",
                 "positionId": "789adc", "serialId": "12345", "alt": "58",
                 "hdop": "0.23", "temp": "32.9", "name": "Test", "power": "3.5"},
                {"lat": 32.02, "lng": 40.06, "date": "14-09-2018", "ttf": "386",
                 "sats": "1", "collarId": "followlt-1234",
                 "positionId": "684adc", "serialId": "12345", "alt": "58",
                 "hdop": "0.23", "temp": "32.9", "name": "Test"}]

        path = '/'.join((self.api_base, 'sensors',
                         self.sensor_type, self.provider_key, 'status'))

        resolver = resolve(path + "/")
        assert resolver.func.cls == FollowltHandlerView

        # This is what BaseAPITest class's force_authenticate do
        tok = AccessToken.objects.create(
            user=self.testuser, token=str(uuid.uuid4()),
            application=self.application, scope='read write',
            expires=timezone.now() + datetime.timedelta(days=1)
        )
        # appending token in url
        path = path + '?auth={}'.format(tok.token)
        request = self.factory.post(path, data=data)
        request.user = self.testuser
        force_authenticate(request, user=request.user, token=tok)

        response = FollowltHandlerView.as_view()(request, self.provider_key)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(len(self.henry.observations()) == 2)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_post_new_minimal_radio_update(self):
        # Post sample data in api, and check subject's observations
        # ttf, sats, alt, hdop, temp
        data = [{"lat": 32.01, "lng": 40.05, "date": "13-09-2018", "collarId": "followlt-12345",
                 },
                {"lat": 32.02, "lng": 40.06, "date": "14-09-2018", "ttf": None,
                 "sats": None, "collarId": "followlt-12345",
                 "positionId": "684adc", "serialId": "12345", "alt": None,
                 "hdop": None, "temp": None, "name": "Test"}]

        path = '/'.join((self.api_base, 'sensors',
                         self.sensor_type, self.provider_key, 'status'))

        # This is what BaseAPITest class's force_authenticate do
        tok = AccessToken.objects.create(
            user=self.testuser, token=str(uuid.uuid4()),
            application=self.application, scope='read write',
            expires=timezone.now() + datetime.timedelta(days=1)
        )
        # appending token in url
        path = path + '?auth={}'.format(tok.token)
        request = self.factory.post(path, data=data)
        request.user = self.testuser
        force_authenticate(request, user=request.user, token=tok)

        response = FollowltHandlerView.as_view()(request, self.provider_key)
        self.assertEqual(response.status_code, 201)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_post_null_island_radio_update(self):
        # Post sample data in api, and check subject's observations
        # ttf, sats, alt, hdop, temp
        data = [{"lat": 0, "lng": 0, "date": "13-09-2018", "collarId": "followlt-123456",
                 },
                {"lat": -1, "lng": -1, "date": "14-09-2018", "ttf": None,
                 "sats": None, "collarId": "followlt-123456",
                 "positionId": "684adc", "serialId": "12345", "alt": None,
                 "hdop": None, "temp": None, "name": "Test"}]

        path = '/'.join((self.api_base, 'sensors',
                         self.sensor_type, self.provider_key, 'status'))

        # This is what BaseAPITest class's force_authenticate do
        tok = AccessToken.objects.create(
            user=self.testuser, token=str(uuid.uuid4()),
            application=self.application, scope='read write',
            expires=timezone.now() + datetime.timedelta(days=1)
        )
        # appending token in url
        path = path + '?auth={}'.format(tok.token)
        request = self.factory.post(path, data=data)
        request.user = self.testuser
        force_authenticate(request, user=request.user, token=tok)

        response = FollowltHandlerView.as_view()(request, self.provider_key)
        self.assertEqual(response.status_code, 201)
