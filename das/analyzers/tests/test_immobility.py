import copy
import random
from datetime import datetime, timedelta

import dateutil.parser as dp
import pytz
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.test import TestCase

from analyzers.models import ImmobilityAnalyzer, SubjectAnalyzerResult
from observations import models
from .immobility_test_data import *
from activity.models import EventType, EventCategory

def generate_random_positions(start_time=None, x=37.5, y=1.41):
    recorded_at = start_time or pytz.utc.localize(datetime.utcnow()) - timedelta(hours=24)

    while True:
        yield recorded_at, Point(x=x, y=y)
        x += (random.random()  - 0.5)/10000
        y += (random.random()  - 0.5)/10000
        recorded_at = recorded_at + timedelta(minutes=30)


def time_shift(items, start_time=None, time_key='recorded_at'):
    fake_start = start_time or pytz.utc.localize(datetime.utcnow()) - timedelta(hours=24)
    for i, item in enumerate(items):
        if i == 0:
            actual_start = dp.parse(item[time_key])
            fake_time = fake_start
        else:
            fake_time = (dp.parse(item[time_key]) - actual_start) + fake_start

        new_item = copy.copy(item)
        new_item[time_key] = fake_time
        yield new_item

from analyzers.tasks import handle_subject

class TestImmobilityAnalyzer(TestCase):

    def setUp(self):
        ec = EventCategory.objects.create(value='analyzer', display='analyzer')
        et1 = EventType.objects.create(value='immobility', display='immobility', category=ec)
        et2 = EventType.objects.create(value='immobility_all_clear', display='immobility_all_clear', category=ec)


    def test_ishango_immobile(self):

        # Grab prepared observation list from test data.
        test_observations = ISHANGO_IMMOBILE

        # Create models (Subject, SubjectSource and Source)
        sub = models.Subject.objects.create(name='Ishango', subject_type='wildlife', subject_subtype= 'elephant')
        source = models.Source.objects.create(manufacturer_id='ishango-collar')
        models.SubjectSource.objects.create(subject=sub, source=source, assigned_range=models.DEFAULT_ASSIGNED_RANGE)

        sg = models.SubjectGroup.objects.create(name='immobility_analyzer_group',)
        sg.subjects.add(sub)
        sg.save()

        ia = ImmobilityAnalyzer.objects.create(subject_group=sg)

        # groups = models.SubjectGroup.objects.filter(subjects=sub)
        # self.assertTrue(ImmobilityAnalyzer.should_run(sub, subject_groups=groups))


        # Create observations in database, so the Analyzer will find them.
        for item in time_shift(test_observations):

            recorded_at = item['recorded_at']
            location = Point(x=item['longitude'], y=item['latitude'])
            obs = models.Observation.objects.create(recorded_at=recorded_at,
                                             location=location,
                                                    source=source, additional={})

        handle_subject(str(sub.id))

        self.assertFalse(SubjectAnalyzerResult.objects.filter(subject=sub).exists())
        # # Create the new analyzer with the Subject we're interested in.
        # ia = ImmobilityAnalyzer.objects.create(subject=sub, threshold_time=18000)
        #
        # # Analyze
        # r = ia.analyze()
        #
        # # Assert
        # self.assertAlmostEqual(29.77662635, r.position.x, places=5)
        # self.assertAlmostEqual(-0.2370999999, r.position.y, places=5)
        # self.assertEqual(r.level, 20)

    def xtest_emmanuel_immobile(self):

        test_observations = EMMANUEL_IMMOBILE

        sub = models.Subject.objects.create(name='Emmanuel', subject_type='wildlife', subject_subtype= 'elephant')
        source = models.Source.objects.create(manufacturer_id='emmanuel-collar')
        models.SubjectSource.objects.create(subject=sub, source=source, assigned_range=models.DEFAULT_ASSIGNED_RANGE)

        for item in time_shift(test_observations):

            recorded_at = item['recorded_at']
            location = Point(x=item['longitude'], y=item['latitude'])
            obs = models.Observation.objects.create(recorded_at=recorded_at,
                                             location=location,
                                                    source=source, additional={})


        ia = ImmobilityAnalyzer.objects.create(subject=sub, threshold_time=18000)

        r = ia.analyze()

        print (r.level, r.position.x, r.position.y)
        self.assertAlmostEqual(29.821741, r.position.x, places=5)
        self.assertAlmostEqual(-0.428036, r.position.y, places=5)
        self.assertEqual(r.level, 20)

    def xtest_random(self):
        '''
        This test is just for fun. No assertions take place.
        :return: 
        '''
        sub = models.Subject.objects.create(name='Random Guy', subject_type='wildlife', subject_subtype= 'elephant')
        source = models.Source.objects.create(manufacturer_id='random-guy-collar')
        models.SubjectSource.objects.create(subject=sub, source=source, assigned_range=models.DEFAULT_ASSIGNED_RANGE)

        n = pytz.utc.localize(datetime.utcnow())
        positions = generate_random_positions()
        positions.send(None)
        while True:

            recorded_at, location = positions.send(None)
            obs = models.Observation.objects.create(recorded_at=recorded_at,
                                             location=location,
                                                    source=source, additional={})
            if obs.recorded_at > n:
                break

        ia = ImmobilityAnalyzer.objects.create(subject=sub, threshold_time=18000)

        r = ia.analyze()
        print(r)


