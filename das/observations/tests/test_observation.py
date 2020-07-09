import os
import random
from datetime import datetime, timedelta

from django.db.models import F
from django.test import TestCase
from pytz import UTC

from observations.models import Observation, SubjectSource, SubjectStatus
from observations.serializers import ObservationSerializer

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'fixtures')

FIXTURE_FOR_SUBJECT_STATUS_TESTS = 'test/radio-subject-fixtures.json'
class ObservationTestCase(TestCase):

    fixtures = [
        'test/sourceprovider.yaml',
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
        FIXTURE_FOR_SUBJECT_STATUS_TESTS,
    ]

    def setUp(self):
        pass

    def test_observation_get_source_range_observations_in_range(self):
        source_id = '04859b48-5665-4895-b7b1-64319f9812b0'

        subject_sources = SubjectSource.objects.all()
        until = datetime(2015,11,10, tzinfo=UTC)
        since = until - timedelta(days=2)

        observations = Observation.objects.get_subject_observations(
            subject_sources[1].subject,
            until=until,
            since=since
        )
        actual = len(observations)
        expected = 1

        self.assertEqual(actual, expected)

    def test_observation_get_source_range_observations_outside_range(self):
        source_id = '04859b48-5665-4895-b7b1-64319f9812b0'

        subject_sources = SubjectSource.objects.all()
        until = datetime(3030,11,10, tzinfo=UTC)
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

        fixed_location = dict(longitude=fixed_longitude, latitude=fixed_latitude)

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

        subject_statuses = SubjectStatus.objects.filter(subject_id=subject_id, delay_hours=0)

        self.assertTrue(subject_statuses is not None)

        subject_status = subject_statuses.first()
        self.assertEqual(subject_status.recorded_at, observation_time)
        self.assertEqual((subject_status.location.x, subject_status.location.y), (fixed_longitude, \
                                                                                    fixed_latitude))

    def test_observation_post_delete_subject_status(self):

        # These are known IDs for subject and source, from test fixtures.
        subject_id = '269524d5-a434-4377-9ea9-2a7946dbd9c4'
        source_id = '56b1cf14-ef97-4054-8fbd-1342f265b2a9'

        # Generate some random data for the observation.
        observation_time = UTC.localize(datetime.now())
        fixed_latitude = float(random.randint(3000, 3000))/100
        fixed_longitude = float(random.randint(2800, 4000))/100

        fixed_location = dict(longitude=fixed_longitude, latitude=fixed_latitude)

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

        subject_statuses = SubjectStatus.objects.filter(subject_id=subject_id, delay_hours=0)

        self.assertTrue(subject_statuses is not None)

        subject_status = subject_statuses.first()
        self.assertEqual(subject_status.recorded_at, observation_time)
        self.assertEqual((subject_status.location.x, subject_status.location.y), (fixed_longitude, \
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

        obs = Observation.objects.filter(recorded_at=observation_time2, source=source_id)
        self.assertTrue(obs is not None)
        obs.delete()

        subject_status = SubjectStatus.objects.filter(subject_id=subject_id, delay_hours=0, recorded_at=observation_time2)
        self.assertTrue(subject_status.first() is None)


    def test_delete_latest_observation(self):
        f'''
        Using fixture data in {FIXTURE_FOR_SUBJECT_STATUS_TESTS} 
        '''
        subject_id = 'd35cb4fe-c15f-404f-bc86-b479f01b6a01'

        initial_subjectstatus = SubjectStatus.objects.get(subject_id=subject_id, delay_hours=0)

        print(f'initial radio state: {initial_subjectstatus.radio_state}')
        # Grab the latest two observations -- we'll after deleting the latest, we'll use these
        # to assert proper updates in SubjectStatus.
        last1, last2 = Observation.objects.filter(source__subjectsource__subject_id=subject_id,
                                                        source__subjectsource__assigned_range__contains=F('recorded_at')
                                                        ).order_by('-recorded_at')[:2]

        self.assertEqual(initial_subjectstatus.recorded_at, last1.recorded_at)

        # DELETE the latest observations
        last1.delete()

        # After delete, check consistency.
        next_subjectstatus = SubjectStatus.objects.get(subject_id=subject_id, delay_hours=0)

        last2 = Observation.objects.filter(source__subjectsource__subject_id=subject_id,
                                                        source__subjectsource__assigned_range__contains=F('recorded_at')
                                                        ).order_by('-recorded_at').first()

        self.assertEqual(last2.recorded_at, next_subjectstatus.recorded_at)
        self.assertEqual(last2.location, next_subjectstatus.location)

        # Assert our test data is set up to test that during an Observation delete we will
        # forgo updating the radio state in SubjectStatus.
        self.assertNotEqual(last1.additional['radio_state'], last2.additional['radio_state'])
        self.assertEqual(initial_subjectstatus.radio_state, next_subjectstatus.radio_state)

    def test_delete_observation_that_is_not_latest(self):
        f'''
        Using fixture data in {FIXTURE_FOR_SUBJECT_STATUS_TESTS} 
        '''
        subject_id = 'd35cb4fe-c15f-404f-bc86-b479f01b6a01'

        initial_subjectstatus = SubjectStatus.objects.get(subject_id=subject_id, delay_hours=0)

        # Grab the latest two observations -- we'll after deleting the latest, we'll use these
        # to assert proper updates in SubjectStatus.
        last1, last2 = Observation.objects.filter(source__subjectsource__subject_id=subject_id,
                                                        source__subjectsource__assigned_range__contains=F('recorded_at')
                                                        ).order_by('-recorded_at')[:2]

        self.assertEqual(initial_subjectstatus.recorded_at, last1.recorded_at)

        # DELETE the second latest observations
        last2.delete()

        # Assert that the subject status did not change.
        self.assertEqual(last1.recorded_at, initial_subjectstatus.recorded_at)
        self.assertEqual(last1.location, initial_subjectstatus.location)


