import random
from datetime import datetime, timedelta

from django.test import TestCase
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.contrib.gis.geos import Point
from django.contrib.auth import get_user_model
import pytz

from accounts.models import PermissionSet
from observations.models import Observation, Subject, SourceProvider, Source, SubjectGroup, SubjectSource
from reports.observationlagnotification import get_lagging_providers, generate_lag_notification_email
from reports.distribution import OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME, get_users_for_permission,\
    create_lag_notify_permissionset


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
