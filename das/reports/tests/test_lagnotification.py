import random
from datetime import datetime, timedelta

import pytest
import pytz
from accounts.models import PermissionSet
from activity.models import Event
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
)
from reports.distribution import (
    OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME,
    get_users_for_permission,
)
from reports.observationlagnotification import (
    check_sources_threshold,
    generate_lag_notification_email,
    get_lagging_providers,
)


User = get_user_model()


def generate_random_positions(source, min_lag_mins=10, max_lag_mins=20, x=37.5, y=0.56, time_length=timedelta(minutes=30),
                              intervals=10):

    start_time = - time_length

    created_at = start_time
    cur = 0
    existing_recorded_at = []

    while cur < intervals:
        while True:
            recorded_at = datetime.now(
                tz=pytz.utc) - timedelta(seconds=random.randint(min_lag_mins * 60, max_lag_mins * 60))
            if not any((recorded_at == era for era in existing_recorded_at)):
                break
        yield Observation(source=source, recorded_at=recorded_at, location=Point(x, y), additional={})
        x += (random.random() - 0.5) / 10000
        y += (random.random() - 0.5) / 10000
        cur = cur + 1
        existing_recorded_at.append(recorded_at)


class TestSubjectSourceReport(TestCase):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_groups')

        # Setup Users

        self.u1 = User.objects.create(username='user1', first_name='User 1', last_name='Report User', email='u1@tempuri.org',
                                      password='Sko2901!kd219')
        self.u2 = User.objects.create(username='user2', first_name='User 2', last_name='Report User', email='u2@tempuri.org',
                                      password='Sko2901!kd219')
        self.u3 = User.objects.create(username='user3', first_name='User 3', last_name='Report User', email='u3@tempuri.org',
                                      password='Sko2901!kd219')

        # Add the users to the report recipients permission set.
        pset = PermissionSet.objects.get(
            permissions__codename=OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME)
        for u in (self.u1, self.u2):
            u.permission_sets.add(pset)

        provider1 = SourceProvider.objects.create(
            provider_key='dummy1', display_name='Dummy provider1', additional=dict(lag_notification_threshold="00:30:00"))

        provider2 = SourceProvider.objects.create(
            provider_key='dummy2', display_name='Dummy provider2')  # using default lag threshold

        provider3 = SourceProvider.objects.create(
            provider_key='dummy3', display_name='Dummy provider3',
            additional=dict(lag_notification_threshold="00:10:00"))
        # Add Source
        source1 = Source.objects.create(
            manufacturer_id='source1', provider=provider1)
        source2 = Source.objects.create(
            manufacturer_id='source2', provider=provider2)
        source3 = Source.objects.create(
            manufacturer_id='source3', provider=provider3)

        # Generate some observations for each source
        for observation in generate_random_positions(source1, min_lag_mins=40, max_lag_mins=60):
            observation.save()

        for observation in generate_random_positions(source2, min_lag_mins=0, max_lag_mins=59):
            observation.save()

        for observation in generate_random_positions(source3, min_lag_mins=11, max_lag_mins=11):
            observation.save()

    def create_observation_record(self):
        subject = Subject.objects.create(name='Subject01')
        subject2 = Subject.objects.create(name='Subject02')
        provider = SourceProvider.objects.create(
            provider_key='provider001',
            display_name='Provider001',
            additional=dict(silence_notification_threshold="0:10:0"))
        source = Source.objects.create(manufacturer_id='001',
                                       provider=provider)
        source2 = Source.objects.create(manufacturer_id='002',
                                        provider=provider)
        ASSIGNED_RANGE = list(
            (pytz.utc.localize(datetime.now()),
             pytz.utc.localize(datetime.now() + timedelta(days=20))))
        ss = SubjectSource.objects.create(subject=subject,
                                          source=source,
                                          assigned_range=ASSIGNED_RANGE)

        ss2 = SubjectSource.objects.create(subject=subject2, source=source2)
        recorded_at = datetime.now(tz=pytz.utc)
        x = float(random.randint(3000, 3000)) / 100
        y = float(random.randint(2800, 4000)) / 100

        recorded_late = datetime.now(tz=pytz.utc) - timedelta(days=3)
        location = Point(x, y)

        return source, source2, recorded_at, recorded_late, location

    def test_lag_notify_permission(self):
        ps = Permission.objects.filter(
            codename=OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME)
        self.assertIsNotNone(ps)

        recipients = get_users_for_permission(
            OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME)
        recipients = list(recipients)

        expecting_usernames = (self.u1.username, self.u2.username)
        # Assert the list of recipients is accurate.
        self.assertTrue(self._lists_equal(
            list((x.username for x in recipients)), expecting_usernames))

    def _lists_equal(self, l1, l2):
        return all(x in l1 for x in l2) and all(x in l2 for x in l1)

    def test_get_lagging_providers(self):
        '''
        Make several assertions about the providers.
        '''

        providers = get_lagging_providers()

        for provider, provider_config in providers:
            provider_key = provider['provider_key']
            self.assertNotEqual(provider_key, 'dummy2')

            email_body, message_subject = generate_lag_notification_email(
                provider, provider_config)

            if provider_key == 'dummy1':
                self.assertGreater(
                    int(provider['avg_lag'].total_seconds()), 40 * 60)
                self.assertLess(
                    int(provider['avg_lag'].total_seconds()), 60 * 60)
                self.assertEqual(
                    provider_config['lag_notification_threshold'], '00:30:00')
                self.assertTrue('Dummy provider1' in email_body)

            if provider_key == 'dummy3':
                self.assertEqual(
                    int(provider['avg_lag'].total_seconds()), 11 * 60)
                self.assertEqual(
                    provider_config['lag_notification_threshold'], '00:10:00')
                self.assertTrue('Dummy provider3' in email_body)


@pytest.mark.django_db
class TestReportByTask:
    def test_two_sources_with_same_provider_reach_the_provider_threshold(
        self, five_subject_sources
    ):
        provider = five_subject_sources[0].source.provider
        provider.additional = {"silence_notification_threshold": "00:30:00"}
        provider.save()
        source_a = five_subject_sources[0].source
        source_a.provider = provider
        source_a.save()
        source_b = five_subject_sources[1].source
        source_b.provider = provider
        source_b.save()

        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(hours=4),
            source=source_a,
            location=Point(0, 0),
        )
        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(hours=3),
            source=source_b,
            location=Point(0, 0),
        )
        check_sources_threshold()

        events = Event.objects.all()
        assert events.count() == 1
        for event in events:
            assert event.event_type.display == "Silent Source Provider"

    def test_one_of_many_sources_with_same_provider_reach_the_provider_threshold(
        self, five_subject_sources
    ):
        provider = five_subject_sources[0].source.provider
        provider.additional = {"silence_notification_threshold": "00:30:00"}
        provider.save()
        source_a = five_subject_sources[0].source
        source_a.provider = provider
        source_a.save()
        source_b = five_subject_sources[1].source
        source_b.provider = provider
        source_b.save()

        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(hours=4),
            source=source_a,
            location=Point(0, 0),
        )
        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(minutes=10),
            source=source_b,
            location=Point(0, 0),
        )
        check_sources_threshold()

        events = Event.objects.all()
        assert events.count() == 0

    def test_neither_sources_with_same_provider_reach_the_provider_threshold(
        self, five_subject_sources
    ):
        provider = five_subject_sources[0].source.provider
        provider.additional = {"silence_notification_threshold": "00:30:00"}
        provider.save()
        source_a = five_subject_sources[0].source
        source_a.provider = provider
        source_a.save()
        source_b = five_subject_sources[1].source
        source_b.provider = provider
        source_b.save()

        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(minutes=10),
            source=source_a,
            location=Point(0, 0),
        )
        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(minutes=15),
            source=source_b,
            location=Point(0, 0),
        )
        check_sources_threshold()

        events = Event.objects.all()
        assert events.count() == 0

    def test_two_source_with_same_provider_reach_the_provider_default_threshold(
        self, five_subject_sources
    ):
        provider = five_subject_sources[0].source.provider
        provider.additional = {
            "default_silent_notification_threshold": "00:30"}
        provider.save()
        source_a = five_subject_sources[0].source
        source_a.provider = provider
        source_a.save()
        source_b = five_subject_sources[1].source
        source_b.provider = provider
        source_b.save()

        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(hours=4),
            source=source_a,
            location=Point(0, 0),
        )
        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(hours=3),
            source=source_b,
            location=Point(0, 0),
        )
        check_sources_threshold()

        events = Event.objects.all()
        assert events.count() == 2
        for event in events:
            assert event.event_type.display == "Silent Source"

    def test_two_source_with_different_providers_reach_the_provider_default_threshold(
        self, five_subject_sources
    ):
        source_a = five_subject_sources[0].source
        source_b = five_subject_sources[1].source
        provider_a = five_subject_sources[0].source.provider
        provider_a.additional = {
            "default_silent_notification_threshold": "00:30"}
        provider_a.save()
        provider_b = five_subject_sources[1].source.provider
        provider_b.additional = {
            "default_silent_notification_threshold": "00:30"}
        provider_b.save()

        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(hours=4),
            source=source_a,
            location=Point(0, 0),
        )
        Observation.objects.create(
            recorded_at=timezone.now() - timedelta(hours=3),
            source=source_b,
            location=Point(0, 0),
        )
        check_sources_threshold()

        events = Event.objects.all()
        assert events.count() == 2
        for event in events:
            assert event.event_type.display == "Silent Source"
