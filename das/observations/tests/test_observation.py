from datetime import datetime, timedelta

from pytz import UTC
from django.test import TestCase
from observations.models import Observation, SubjectSource, SubjectStatus
from django.contrib.gis.geos import Point
from observations.serializers import ObservationSerializer
import random
class ObservationTestCase(TestCase):

    fixtures = [
        'test/sourceprovider.yaml',
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
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
