import os
import random
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import pytest
from pytz import UTC

from django.contrib.auth import get_user_model
from django.db.models import F
from django.urls import reverse

from core.tests import BaseAPITest
from observations.models import (STATIONARY_SUBJECT_VALUE, Observation, Source,
                                 SourceProvider, Subject, SubjectSource,
                                 SubjectStatus, SubjectType)
from observations.serializers import ObservationSerializer
from observations.views import (ObservationsView, SubjectStatusView,
                                SubjectsView, TrackingDataCsvView)

User = get_user_model()

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'fixtures')

FIXTURE_FOR_SUBJECT_STATUS_TESTS = 'test/radio-subject-fixtures.json'


class ObservationTestCase(BaseAPITest):

    fixtures = [
        'test/sourceprovider.yaml',
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
        FIXTURE_FOR_SUBJECT_STATUS_TESTS,
    ]

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)

    def test_observation_get_source_range_observations_in_range(self):
        until = datetime(2015, 11, 10, tzinfo=UTC)
        since = until - timedelta(days=2)

        subject_source = SubjectSource.objects.get(
            source="2e47839d-0277-4398-904d-91da8b0698f4"
        )
        observations = Observation.objects.get_subject_observations(
            subject_source.subject, until=until, since=since
        )
        actual = len(observations)
        expected = 1

        self.assertEqual(actual, expected)

    def test_observation_get_source_range_observations_outside_range(self):
        subject_sources = SubjectSource.objects.all()
        until = datetime(3030, 11, 10, tzinfo=UTC)
        since = until - timedelta(days=2)

        observations = Observation.objects.get_subject_observations(
            subject_sources[0].subject,
            until=until,
            since=since
        )
        actual = len(observations)
        expected = 0

        self.assertEqual(actual, expected)

    def test_observation_post_save_subject_status(self):
        '''
        Test saving an observation for an existing source.
        Validate that an associated SubjectStatus is updated appropriately.
        '''

        # These are known IDs for subject and source, from test fixtures.
        subject_id = '269524d5-a434-4377-9ea9-2a7946dbd9c4'
        source_id = '56b1cf14-ef97-4054-8fbd-1342f265b2a9'

        # Generate some random data for the observation.
        observation_time = UTC.localize(datetime.now())
        fixed_latitude = float(random.randint(3000, 3000))/100
        fixed_longitude = float(random.randint(2800, 4000))/100

        fixed_location = dict(longitude=fixed_longitude,
                              latitude=fixed_latitude)

        observation = {
            'location': fixed_location,
            'recorded_at': observation_time,
            'source': source_id,
            'additional': {}
        }

        serializer = ObservationSerializer(data=observation)

        self.assertTrue(serializer.is_valid(), msg='Observation is not valid.')

        observation_instance = None
        if serializer.is_valid():
            observation_instance = serializer.save()

        self.assertTrue(observation_instance is not None)

        subject_statuses = SubjectStatus.objects.filter(
            subject_id=subject_id, delay_hours=0)

        self.assertTrue(subject_statuses is not None)

        subject_status = subject_statuses.first()
        self.assertEqual(subject_status.recorded_at, observation_time)
        self.assertEqual((subject_status.location.x, subject_status.location.y), (fixed_longitude,
                                                                                  fixed_latitude))

    def test_observation_post_delete_subject_status(self):

        # These are known IDs for subject and source, from test fixtures.
        subject_id = '269524d5-a434-4377-9ea9-2a7946dbd9c4'
        source_id = '56b1cf14-ef97-4054-8fbd-1342f265b2a9'

        # Generate some random data for the observation.
        observation_time = UTC.localize(datetime.now())
        fixed_latitude = float(random.randint(3000, 3000))/100
        fixed_longitude = float(random.randint(2800, 4000))/100

        fixed_location = dict(longitude=fixed_longitude,
                              latitude=fixed_latitude)

        observation = {
            'location': fixed_location,
            'recorded_at': observation_time,
            'source': source_id,
            'additional': {}
        }
        serializer = ObservationSerializer(data=observation)
        observation_instance = None
        if serializer.is_valid():
            observation_instance = serializer.save()

        self.assertTrue(observation_instance is not None)

        subject_statuses = SubjectStatus.objects.filter(
            subject_id=subject_id, delay_hours=0)

        self.assertTrue(subject_statuses is not None)

        subject_status = subject_statuses.first()
        self.assertEqual(subject_status.recorded_at, observation_time)
        self.assertEqual((subject_status.location.x, subject_status.location.y), (fixed_longitude,
                                                                                  fixed_latitude))
        observation_time2 = UTC.localize(datetime.now())
        observation = {
            'location': fixed_location,
            'recorded_at': observation_time2,
            'source': source_id,
            'additional': {}
        }
        serializer = ObservationSerializer(data=observation)
        observation_instance = None
        if serializer.is_valid():
            observation_instance = serializer.save()
        self.assertTrue(observation_instance is not None)

        obs = Observation.objects.filter(
            recorded_at=observation_time2, source=source_id)
        self.assertTrue(obs is not None)
        obs.delete()

        subject_status = SubjectStatus.objects.filter(
            subject_id=subject_id, delay_hours=0, recorded_at=observation_time2)
        self.assertTrue(subject_status.first() is None)

    def test_delete_latest_observation(self):
        f'''
        Using fixture data in {FIXTURE_FOR_SUBJECT_STATUS_TESTS} 
        '''
        subject_id = 'd35cb4fe-c15f-404f-bc86-b479f01b6a01'

        SubjectStatus.objects.maintain_subject_status(subject_id)
        initial_subjectstatus = SubjectStatus.objects.get(
            subject_id=subject_id, delay_hours=0)

        print(f'initial radio state: {initial_subjectstatus.radio_state}')
        # Grab the latest two observations -- we'll after deleting the latest, we'll use these
        # to assert proper updates in SubjectStatus.
        last1, last2 = Observation.objects.filter(source__subjectsource__subject_id=subject_id,
                                                  source__subjectsource__assigned_range__contains=F(
                                                      'recorded_at')
                                                  ).order_by('-recorded_at')[:2]

        self.assertEqual(initial_subjectstatus.recorded_at, last1.recorded_at)

        # DELETE the latest observations
        last1.delete()

        # After delete, check consistency.
        next_subjectstatus = SubjectStatus.objects.get(
            subject_id=subject_id, delay_hours=0)

        last2 = Observation.objects.filter(source__subjectsource__subject_id=subject_id,
                                           source__subjectsource__assigned_range__contains=F(
                                               'recorded_at')
                                           ).order_by('-recorded_at').first()

        self.assertEqual(last2.recorded_at, next_subjectstatus.recorded_at)
        self.assertEqual(last2.location, next_subjectstatus.location)

        # Assert our test data is set up to test that during an Observation delete we will
        # forgo updating the radio state in SubjectStatus.
        self.assertNotEqual(
            last1.additional['radio_state'], last2.additional['radio_state'])
        self.assertEqual(initial_subjectstatus.radio_state,
                         next_subjectstatus.radio_state)

    def test_delete_observation_that_is_not_latest(self):
        f'''
        Using fixture data in {FIXTURE_FOR_SUBJECT_STATUS_TESTS} 
        '''
        subject_id = 'd35cb4fe-c15f-404f-bc86-b479f01b6a01'

        SubjectStatus.objects.maintain_subject_status(subject_id)
        initial_subjectstatus = SubjectStatus.objects.get(
            subject_id=subject_id, delay_hours=0)

        # Grab the latest two observations -- we'll after deleting the latest, we'll use these
        # to assert proper updates in SubjectStatus.
        last1, last2 = Observation.objects.filter(source__subjectsource__subject_id=subject_id,
                                                  source__subjectsource__assigned_range__contains=F(
                                                      'recorded_at')
                                                  ).order_by('-recorded_at')[:2]

        self.assertEqual(initial_subjectstatus.recorded_at, last1.recorded_at)

        # DELETE the second latest observations
        last2.delete()

        # Assert that the subject status did not change.
        self.assertEqual(last1.recorded_at, initial_subjectstatus.recorded_at)
        self.assertEqual(last1.location, initial_subjectstatus.location)

    def test_subject_additional_data(self):
        subject_id = '269524d5-a434-4377-9ea9-2a7946dbd9c4'
        source_id = '56b1cf14-ef97-4054-8fbd-1342f265b2a9'

        SourceProvider.objects.filter(source__id=source_id).update(transforms=[{"dest": "voltage",
                                                                               "label": "Voltage",
                                                                                "source": "voltage",
                                                                                "units": "v"},
                                                                               {"dest": "voltage",
                                                                                "label": "Voltage (from sysB)",
                                                                                "source": "volts",
                                                                                "units": "v"
                                                                                },
                                                                               {"dest": "altitude",
                                                                                "label": "Altitude",
                                                                                "source": "Altitude.[0].#text",
                                                                                "units": "feet"
                                                                                },
                                                                               ])

        # Generate some random data for the observation.
        observation_time = UTC.localize(datetime.now())
        fixed_latitude = float(random.randint(3000, 3000))/100
        fixed_longitude = float(random.randint(2800, 4000))/100

        fixed_location = dict(longitude=fixed_longitude,
                              latitude=fixed_latitude)

        observation = {
            'location': fixed_location,
            'recorded_at': observation_time,
            'source': source_id,
            'additional': {"voltage": 12,
                           "volts": "5.9v",
                           "Altitude": [
                               {
                                   "#text": "3241",
                                   "@units": "Feet"
                               },
                               {
                                   "#text": "3000",
                                   "@units": "Feet"
                               }
                           ]
                           }
        }

        serializer = ObservationSerializer(data=observation)

        self.assertTrue(serializer.is_valid(), msg='Observation is not valid.')

        observation_instance = None
        if serializer.is_valid():
            observation_instance = serializer.save()

        self.assertTrue(observation_instance is not None)
        subject_statuses = SubjectStatus.objects.filter(
            subject_id=subject_id, delay_hours=0)
        self.assertTrue(subject_statuses is not None)

        subject_status = subject_statuses.first()
        self.assertEqual(subject_status.recorded_at, observation_time)
        self.assertEqual((subject_status.location.x,
                         subject_status.location.y), (fixed_longitude, fixed_latitude))

        url = reverse('subjects-list-view')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.data[0].get('device_status_properties'),
                         [{'label': 'Voltage', 'units': 'v', 'value': 12},
                          {'label': 'Altitude', 'units': 'feet', 'value': '3241'}])
        self.assertTrue(
            len(response.data[0].get('device_status_properties')), 2)

        # subject-status
        url = reverse('subjectstatus-view',  kwargs={'subject_id': subject_id})
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = SubjectStatusView.as_view()(request, subject_id=subject_id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('device_status_properties'))

        # observations
        url = reverse('observations-list-view')
        request = self.factory.get(url, data=dict(subject_id=subject_id))
        self.force_authenticate(request, self.user)
        response = ObservationsView.as_view()(request, subject_id=subject_id)
        self.assertEqual(response.status_code, 200)
        first_observation = response.data['results'][0]
        self.assertTrue(
            len(first_observation.get('device_status_properties')), 2)
        assert first_observation['location']['latitude'] and first_observation['location']['longitude']

    def test_subject_observations_for_stationary_subject_where_stationary_subject_observations_have_empty_locations(self):
        subject_id = '269524d5-a434-4377-9ea9-2a7946dbd9c4'
        source_id = '56b1cf14-ef97-4054-8fbd-1342f265b2a9'
        subject_type_stationary_object = SubjectType.objects.get(
            value=STATIONARY_SUBJECT_VALUE)

        subject = Subject.objects.get(id=subject_id)
        subject.subject_subtype.subject_type = subject_type_stationary_object
        subject.subject_subtype.save()

        fixed_latitude = float(0)
        fixed_longitude = float(0)
        fixed_location = dict(longitude=fixed_longitude,
                              latitude=fixed_latitude)

        observation_test_count = 5
        observation_time = datetime.now(tz=timezone.utc)
        for i in range(observation_test_count):

            observation = {
                'location': fixed_location,
                'recorded_at': observation_time + timedelta(seconds=i),
                'source': source_id,
                'additional': {}
            }
            serializer = ObservationSerializer(data=observation)
            assert serializer.is_valid()
            serializer.save()

        url = reverse('observations-list-view')
        request = self.factory.get(url, data=dict(subject_id=subject_id))
        self.force_authenticate(request, self.user)
        response = ObservationsView.as_view()(request, subject_id=subject_id)
        assert response.status_code == 200
        assert len(response.data['results']) == observation_test_count

        second_observation_test_count = 5
        observation_time = datetime.now(tz=timezone.utc)
        for i in range(second_observation_test_count):

            observation = {
                'location': fixed_location,
                'recorded_at': observation_time + timedelta(seconds=i),
                'source': source_id,
                'additional': {}
            }
            serializer = ObservationSerializer(data=observation)
            assert serializer.is_valid()
            serializer.save()

        url = reverse('observations-list-view')
        request = self.factory.get(url, data=dict(subject_id=subject_id))
        self.force_authenticate(request, self.user)
        response = ObservationsView.as_view()(request, subject_id=subject_id)
        assert response.status_code == 200
        assert len(
            response.data['results']) == observation_test_count + second_observation_test_count


def generate_observation(source, recorded_at=None):
    observation_time = recorded_at if recorded_at else datetime.now(
        tz=timezone.utc)
    fixed_latitude = float(random.randint(3000, 3000))/100
    fixed_longitude = float(random.randint(2800, 4000))/100
    fixed_location = dict(longitude=fixed_longitude, latitude=fixed_latitude)
    observation = {
        'location': fixed_location,
        'recorded_at': observation_time,
        'source': str(source.id),
        'additional': {}
    }
    serializer = ObservationSerializer(data=observation)
    serializer.is_valid(raise_exception=True)
    observation_instance = serializer.save()
    return observation_instance


class TwoSubjectsOneSource(NamedTuple):
    bobo: Subject
    ivy: Subject
    source: Source
    bobo_observations: list
    ivy_observations: list


@pytest.fixture
def two_subjects_one_source(db):
    bobo = Subject.objects.create_subject(
        name="Bobo", subject_subtype_id='elephant')
    ivy = Subject.objects.create_subject(
        name="Ivy", subject_subtype_id='elephant')

    source = Source.objects.ensure_source(
        manufacturer_id="1125496", provider="bobo_provider")

    time_start = datetime(year=2019, month=1, day=1,
                          hour=2, tzinfo=timezone.utc)

    bobo_observations = [generate_observation(
        source, recorded_at=time_start + timedelta(days=i)).recorded_at for i in range(1, 5)]
    SubjectSource.objects.ensure(
        source, bobo, (bobo_observations[0], bobo_observations[3]+timedelta(seconds=1)))

    ivy_observations = [generate_observation(
        source, recorded_at=time_start + timedelta(days=i)).recorded_at for i in range(5, 9)]
    SubjectSource.objects.ensure(
        source, ivy, (ivy_observations[0], ivy_observations[3]+timedelta(seconds=1)))

    bobo_observations += [generate_observation(
        source, recorded_at=time_start + timedelta(days=i)).recorded_at for i in range(9, 13)]
    SubjectSource.objects.ensure(
        source, bobo, (bobo_observations[4], bobo_observations[7]+timedelta(seconds=1)))

    ivy_observations += [generate_observation(
        source, recorded_at=time_start + timedelta(days=i)).recorded_at for i in range(13, 17)]
    SubjectSource.objects.ensure(
        source, ivy, (ivy_observations[4], ivy_observations[7]+timedelta(seconds=1)))

    return TwoSubjectsOneSource(bobo, ivy, source, bobo_observations, ivy_observations)


def test_subject_observations_for_multiple_source_assignments(two_subjects_one_source):
    bobo_get_observations = [x.recorded_at for x in Observation.objects.get_subject_observations(
        str(two_subjects_one_source.bobo.id))]

    assert set(bobo_get_observations) == set(
        two_subjects_one_source.bobo_observations)
    assert set(bobo_get_observations).difference(
        set(two_subjects_one_source.ivy_observations))


def test_trackingdata_view_for_multiple_source_assignments(two_subjects_one_source):
    view = TrackingDataCsvView()
    lower = datetime.min.replace(tzinfo=timezone.utc)
    upper = datetime.now(tz=timezone.utc)
    max_records = -1
    filter_flag = None
    qs = view.get_subject_trackdata_queryset(
        filter_flag, lower, two_subjects_one_source.bobo, upper, max_records)
    values = list(qs)
    bobo_get_observations = [x.recorded_at for x in values]

    assert set(bobo_get_observations) == set(
        two_subjects_one_source.bobo_observations)
    assert set(bobo_get_observations).difference(
        set(two_subjects_one_source.ivy_observations))


def test_trackingdata_view_for_max_records(two_subjects_one_source):
    # Verify we don't see: AssertionError: Cannot reorder a query once a slice has been taken.
    view = TrackingDataCsvView()
    lower = datetime.min.replace(tzinfo=timezone.utc)
    upper = datetime.now(tz=timezone.utc)
    max_records = 1
    filter_flag = None
    qs = view.get_subject_trackdata_queryset(
        filter_flag, lower, two_subjects_one_source.bobo, upper, max_records)
    values = list(qs)

    assert len(values) >= 1

# # TODO: client requests using pytest
# def test_trackingdata_view_for_subjectstatus(two_subjects_one_source):
#     view = TrackingDataCsvView()
#     result = view.get_subject_status_queryset(two_subjects_one_source.bobo.id)
#     status = result.first()
#     assert status.recorded_at == two_subjects_one_source.bobo_observations[-1].recorded_at
