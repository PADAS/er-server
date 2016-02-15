from datetime import datetime, timedelta

from django.contrib.gis.geos import Point
from django.test import TestCase
from observations.models import Subject, Observation


class SubjectTestCase(TestCase):

    fixtures = [
        'observations_source.json',
        'observations_subject.json',
        'observations_subject_source.json',
        'observations_observation.json',
    ]

    def setUp(self):
        pass

    def test_subject_observations(self):
        subject = Subject.objects.get(name='Topsy')
        actual = len(subject.observations())
        expected = 1

        self.assertEqual(actual, expected)

    def test_subject_observations_last_days(self):
        subject = Subject.objects.get(name='Topsy')
        point = Point((0.000001, 0.000001))  # really close to Null Island
        t1 = datetime.now() - timedelta(days=2)
        t2 = datetime.now() - timedelta(days=20)

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


        actual = len(subject.observations(last_days=3))
        expected = 1

        self.assertEqual(actual, expected)
