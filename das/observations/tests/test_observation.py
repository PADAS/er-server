from datetime import datetime, timedelta

from django.test import TestCase
from observations.models import Observation, SubjectSource


class ObservationTestCase(TestCase):

    fixtures = [
        'observations_source.json',
        'observations_subject.json',
        'observations_subject_source.json',
        'observations_observation.json',
    ]

    def setUp(self):
        pass

    def test_observation_get_source_range_observations_in_range(self):
        source_id = '04859b48-5665-4895-b7b1-64319f9812b0'

        subject_sources = SubjectSource.objects.all()
        until = datetime(2015,11,10)
        since = until - timedelta(days=2)

        observations = Observation.objects.get_source_range_observations(
            subject_sources,
            until=until,
            since=since
        )
        actual = len(observations)
        expected = 1

        self.assertEqual(actual, expected)

    def test_observation_get_source_range_observations_outside_range(self):
        source_id = '04859b48-5665-4895-b7b1-64319f9812b0'

        subject_sources = SubjectSource.objects.all()
        until = datetime(3030,11,10)
        since = until - timedelta(days=2)

        observations = Observation.objects.get_source_range_observations(
            subject_sources,
            until=until,
            since=since
        )
        actual = len(observations)
        expected = 0

        self.assertEqual(actual, expected)
