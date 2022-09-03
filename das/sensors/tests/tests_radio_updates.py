import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

import django.contrib.auth
from django.test import override_settings

from core.tests import BaseAPITest, fake_get_pool
from observations.models import (DEFAULT_ASSIGNED_RANGE, Source,
                                 SourceProvider, Subject, SubjectSource,
                                 SubjectStatus)
from observations.views import SubjectTracksView
from sensors.views import RadioAgentHandlerView

logger = logging.getLogger(__name__)
User = django.contrib.auth.get_user_model()


class RadioObservationTest(BaseAPITest):
    user_const = dict(last_name='Lastname',
                      first_name='Firstname', is_superuser=True)
    sensor_type = 'dasradioagent'

    def setUp(self):
        super().setUp()

        self.testuser = User.objects.create_user('das_trbonet',
                                                 'das@tempuri.org',
                                                 'somesecret',
                                                 **self.user_const)

        self.test_subject_no1 = Subject.objects.create(
            name='No1', subject_subtype_id='ranger')
        self.test_sourceprovider_no1 = SourceProvider.objects.create(
            display_name='No1', provider_key='lewa-trbonet')
        self.test_source_no1 = Source.objects.create(source_type='gps-radio',
                                                     provider=self.test_sourceprovider_no1,
                                                     manufacturer_id='trbonet-000001')

        self.test_subjectsource_no1 = SubjectSource.objects.create(source=self.test_source_no1,
                                                                   subject=self.test_subject_no1,
                                                                   assigned_range=DEFAULT_ASSIGNED_RANGE)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_post_new_radio_update(self):

        next_track = {'recorded_at': datetime.now(tz=timezone.utc),
                      'location': {'lon': -122.4, 'lat': 47.6}}
        provider = 'lewa-trbonet'

        # - timedelta(seconds=30)
        last_voice_call_start_at = next_track['recorded_at']
        location_requested_at = datetime.now(
            tz=timezone.utc) - timedelta(minutes=20)
        data = dict(message_key='observation',
                    manufacturer_id='trbonet-000001',
                    source_type='gps-radio',
                    subject_name='My radio',
                    recorded_at=next_track['recorded_at'],
                    location=next_track['location'],
                    additional={
                        'event_action': 'device_location_changed',
                        'radio_state': 'online-gps',
                        'radio_state_at': datetime.now(tz=timezone.utc).isoformat(),
                        'last_voice_call_start_at': last_voice_call_start_at.isoformat(),
                        'location_requested_at': location_requested_at.isoformat()
                    })

        path = '/'.join((self.api_base, 'sensors',
                         self.sensor_type, provider, 'status'))
        request = self.factory.post(path, data=data)

        self.force_authenticate(request, self.testuser)
        response = RadioAgentHandlerView.as_view()(request, provider)
        self.assertEqual(response.status_code, 201)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_radio_state_change(self):

        st = SubjectStatus.objects.filter(
            subject=self.test_subject_no1, delay_hours=0).values()

        next_track = {'recorded_at': datetime.now(tz=timezone.utc),
                      'location': {'lon': -122.4, 'lat': 47.6}}

        # - timedelta(seconds=30)
        last_voice_call_start_at = next_track['recorded_at']
        location_requested_at = datetime.now(
            tz=timezone.utc) - timedelta(minutes=20)
        radio_state_at = datetime.now(tz=timezone.utc)
        data = dict(message_key='observation',
                    manufacturer_id=self.test_source_no1.manufacturer_id,
                    source_type='gps-radio',
                    subject_name=self.test_subject_no1.name,
                    recorded_at=next_track['recorded_at'],
                    location=next_track['location'],
                    additional={
                        'event_action': 'device_location_changed',
                        'radio_state': 'online-gps',
                        'radio_state_at': (radio_state_at + timedelta(minutes=2)).isoformat(),
                        'last_voice_call_start_at': last_voice_call_start_at.isoformat(),
                        'location_requested_at': location_requested_at.isoformat()
                    })

        path = '/'.join((self.api_base, 'sensors', self.sensor_type,
                         self.test_sourceprovider_no1.provider_key, 'status'))
        request = self.factory.post(path, data=data)

        self.force_authenticate(request, self.testuser)
        response = RadioAgentHandlerView.as_view()(
            request, self.test_sourceprovider_no1.provider_key)

        self.assertEqual(201, response.status_code)

        subjectstatus = SubjectStatus.objects.filter(
            subject=self.test_subject_no1, delay_hours=0)

        self.assertEqual(len(subjectstatus), 1)

        path = '/'.join((self.api_base, 'subject',
                         str(self.test_subject_no1.id), 'tracks'))
        request = self.factory.get(path)

        self.force_authenticate(request, self.testuser)
        response = SubjectTracksView.as_view()(
            request, subject_id=str(self.test_subject_no1.id))

        self.assertEqual(200, response.status_code)

        track_properties = response.data['features'][0]['properties']
        self.assertEqual('online-gps', track_properties['radio_state'])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_post_new_radio_for_inactive_subject(self):
        provider = 'lewa-trbonet'
        recorded_time = datetime.now(tz=timezone.utc)
        subject_name = 'Sierra 12'

        last_voice_call_start_at = recorded_time
        location_requested_at = recorded_time - timedelta(minutes=10)

        data = dict(message_key='observation',
                    manufacturer_id='trbonet-0000012',
                    source_type='gps-radio',
                    subject_name=subject_name,
                    recorded_at=recorded_time,
                    location={'lon': -122.4, 'lat': 47.6},
                    additional={
                        'event_action': 'device_location_changed',
                        'radio_state': 'online-gps',
                        'radio_state_at': datetime.now(tz=timezone.utc).isoformat(),
                        'last_voice_call_start_at': last_voice_call_start_at.isoformat(),
                        'location_requested_at': location_requested_at.isoformat()
                    })

        path = '/'.join([self.api_base, 'sensors',
                        self.sensor_type, provider, 'status'])
        request = self.factory.post(path, data=data)
        self.force_authenticate(request, self.testuser)
        response = RadioAgentHandlerView.as_view()(request, provider)
        self.assertEqual(response.status_code, 201)

        # mark the subject inactive.
        Subject.objects.filter(name=subject_name).update(is_active=False)

        recorded_time = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        data['recorded_at'] = recorded_time
        data['location'] = {'lon': -124.4, 'lat': 49.6}
        data['radio_state_at'] = recorded_time
        data['radio_state_at'] = 'online'
        data['last_voice_call_start_at'] = recorded_time.isoformat()
        data['location_requested_at'] = (
            recorded_time - timedelta(minutes=10)).isoformat()

        request = self.factory.post(path, data=data)
        self.force_authenticate(request, self.testuser)
        response = RadioAgentHandlerView.as_view()(request, provider)
        self.assertEqual(response.status_code, 201)

        # subject-status is created/updated for inactive subject.
        ss = SubjectStatus.objects.get(
            subject__name=subject_name, delay_hours=0)
        self.assertEqual(set(ss.location.coords),
                         set(data['location'].values()))
        self.assertEqual(ss.recorded_at.isoformat(),
                         data['recorded_at'].isoformat())
