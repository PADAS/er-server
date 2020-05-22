import json
from datetime import datetime, timedelta
from unittest.mock import patch

import django.contrib.auth
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.conf import settings
from django.test import override_settings
import dateutil.parser as dateparser
from pytz import UTC

from core.tests import BaseAPITest
from observations.models import Subject, Observation
from observations.views import SubjectsView

User = django.contrib.auth.get_user_model()


class SubjectTestCase(BaseAPITest):
    fixtures = [
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
    ]

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)

    def test_subject_observations(self):
        subject = Subject.objects.get(name='Topsy')
        actual = len(subject.observations())
        expected = 1

        self.assertEqual(actual, expected)

    def test_subject_observations_last_days(self):
        subject = Subject.objects.get(name='Topsy')
        point = Point((0.000001, 0.000001))  # really close to Null Island
        t1 = datetime.now(tz=UTC) - timedelta(days=2)
        t2 = datetime.now(tz=UTC) - timedelta(days=20)

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
            )

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t2,
            additional={}
            )


        actual = len(subject.observations(last_hours=3*24))
        expected = 1

        self.assertEqual(actual, expected)

        actual = len(subject.observations(last_hours=30*24))
        expected = 2

        self.assertEqual(actual, expected)

    def test_call_subject_api(self):
        url = reverse('subjects-list-view')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_filter_subject_api_updated_since(self):
        url = reverse('subjects-list-view')
        url += '?updated_since=2019-02-03'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_filter_subject_api_using_updated_until_param(self):
        url = reverse('subjects-list-view')
        url += '?updated_since=2019-04-02'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_filter_subject_api_using_updated_since_and_updated_until_param(self):
        url = reverse('subjects-list-view')
        url += '?updated_since=2019-04-02&updated_until=2019-03-02'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(SHOW_STATIONARY_SUBJECTS_ON_MAP=True)
    @override_settings(SHOW_TRACK_DAYS=16)
    def test_date_range_filter_works(self):
        url = reverse('subjects-list-view')

        subject = Subject.objects.get(name='Topsy')
        subject2 = Subject.objects.get(name='Turvey')

        point = Point((-122.334, 47.598))
        t2 = datetime.now(tz=UTC)
        t1 = datetime.now(tz=UTC) - timedelta(days=3)

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
            )

        Observation.objects.create(
            source=subject2.source,
            location=point,
            recorded_at=t2,
            additional={}
        )

        updated_since = t1.date().isoformat()
        updated_until = t2.date().isoformat()
        url += f'?updated_since={updated_since}&updated_until={updated_until}'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        actual = len(response.data)
        expected = 2
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actual, expected)

        last_positon_date_subject = json.loads(response.render().content.decode())['data'][0]['last_position_date']
        last_positon_date_subject2 = json.loads(response.render().content.decode())['data'][1]['last_position_date']

        last_positon_date_subject = dateparser.parse(last_positon_date_subject).date().isoformat()
        last_positon_date_subject2 = dateparser.parse(last_positon_date_subject2).date().isoformat()

        t1 = updated_since
        t2 = updated_until

        self.assertEqual({t1, t2}, {last_positon_date_subject, last_positon_date_subject2})

        # Use url above together with bbox param
        # the 'point' lies within this bbox.
        bbox = '-122.49866134971379, 47.40051600277377, -122.225591570732, 47.67666096382156'
        url += '&bbox={}'.format(bbox)
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        actual_size = len(response.data)
        expected_size = 2
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actual_size, expected_size)

    def test_date_range_filter_works_with_bbox(self):
        url = reverse('subjects-list-view')

        subject = Subject.objects.get(name='Topsy')
        subject2 = Subject.objects.get(name='Turvey')

        point = Point((-122.334, 47.598))
        t1 = datetime.now(tz=UTC)
        t2 = datetime.now(tz=UTC) + timedelta(days=3)

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
            )

        Observation.objects.create(
            source=subject2.source,
            location=point,
            recorded_at=t2,
            additional={}
        )

        day = timedelta(days=1)
        updated_since = (t1.date() - day).isoformat()
        updated_until = (t2.date() + day).isoformat()
        url += f'?updated_since={updated_since}&updated_until={updated_until}'

        bbox = '-122.49866134971379, 47.40051600277377, -122.225591570732, 47.67666096382156'
        url += '&bbox={}'.format(bbox)
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        actual_size = len(response.data)
        expected_size = 2
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actual_size, expected_size)

    @property
    def additional_data_for_user(self):
        expiry_date = (datetime.now(tz=UTC) + timedelta(days=5)).date().isoformat()
        mou_datesigned = datetime.now(tz=UTC).date().isoformat()
        additional_data = {
            'notes': 'Testing Notes',
            'expiry': expiry_date,
            'moudatesigned': mou_datesigned,
            'moutype': 'Sample MoU Type',
            'tech': ['iOS'],
            'organization': 'KWS',
        }
        return additional_data

    def test_subject_api_returning_last_position_per_MOU_expiry(self):
        url = reverse('subjects-list-view')

        password = User.objects.make_random_password()
        extra_fields = dict(additional=self.additional_data_for_user)
        user = User.objects.create_user(username='Capt.America',
                                        email='Capt.American@avenger.com',
                                        password=password,
                                        is_superuser=True,
                                        is_staff=True,
                                        **extra_fields)

        subject = Subject.objects.get(name='Topsy')
        subject2 = Subject.objects.get(name='Turvey')
        subject3 = Subject.objects.get(name='StatusGuy')


        point = Point((-122.334, 47.598))
        t1 = datetime.now(tz=UTC)
        t2 = datetime.now(tz=UTC) + timedelta(days=3)
        t3 = datetime.now(tz=UTC) + timedelta(days=5)


        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
            )

        Observation.objects.create(
            source=subject2.source,
            location=point,
            recorded_at=t2,
            additional={}
        )

        Observation.objects.create(
            source=subject3.source,
            location=point,
            recorded_at=t3,
            additional={}
        )
        request = self.factory.get(url)

        self.force_authenticate(request, user)
        response = SubjectsView.as_view()(request)

        response_data = json.loads(response.render().content.decode())['data']
        extracted_data = {}
        for o in response_data:
            if o['id'] == str(subject.id):
                extracted_data['subject_last_position'] = o['last_position_date']
            elif o['id'] == str(subject2.id):
                extracted_data['subject2_last_position'] = o['last_position_date']
            elif o['id'] == str(subject3.id):
                extracted_data['subject3_last_position'] = o['last_position_date']

        # subject1 and subject2 are within MOU expiry date.
        subject_last_position = dateparser.parse(extracted_data.get('subject_last_position')).date().isoformat()
        subject2_last_postion = dateparser.parse(extracted_data.get('subject2_last_position')).date().isoformat()
        self.assertEqual(t1.date().isoformat(), subject_last_position)
        self.assertEqual(t2.date().isoformat(), subject2_last_postion)

        # Past MOU expiry date, should not retrieve observation past mou expiry date.
        subject3_last_position = extracted_data.get('subject3_last_position')  # return None
        self.assertNotEqual(t3.date().isoformat(), subject3_last_position)
        self.assertEqual(response.status_code, 200)




