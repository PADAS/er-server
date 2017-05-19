import copy
import random
from datetime import datetime, timedelta
from functools import reduce, partial
import dateutil.parser as dp
import pytz
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.test import TestCase

from analyzers.models import ImmobilityAnalyzerConfig, SubjectAnalyzerResult
from observations import models
from activity.models import Event
from .immobility_test_data import *
from analyzers.tasks import analyze_subject


def generate_random_positions(start_time=None, x=37.5, y=1.41):
    recorded_at = start_time or pytz.utc.localize(datetime.utcnow()) - timedelta(hours=24)

    while True:
        yield recorded_at, Point(x=x, y=y)
        x += (random.random()  - 0.5)/10000
        y += (random.random()  - 0.5)/10000
        recorded_at = recorded_at + timedelta(minutes=30)

def typify(fmap, item):
    r = copy.copy(item)
    for k,f in fmap.items():
        r[k] = f(r[k])
    return r

parse_recorded_at = partial(typify, dict(recorded_at=dp.parse))


def time_shift(items, time_key='recorded_at', start_time=None):

    # Determine timespan of 'items'.
    minimum_time = reduce((lambda x, y: x if x < y else y), [_[time_key] for _ in items])
    maximum_time = reduce((lambda x, y: x if x > y else y), [_[time_key] for _ in items])
    actual_start = minimum_time

    fake_start = start_time or pytz.utc.localize(datetime.utcnow()) - (maximum_time - minimum_time)
    for i, item in enumerate(items):
        fake_time = (item[time_key] - actual_start) + fake_start
        new_item = copy.copy(item)
        new_item[time_key] = fake_time
        yield new_item


class TestImmobilityAnalyzer(TestCase):

    # fixtures = ['initial_eventtype.yaml', 'analyzer_eventtype.yaml']

    def setUp(self):
        pass

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

        ia = ImmobilityAnalyzerConfig.objects.create(subject_group=sg)

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in test_observations]

        # Create observations in database, so the Analyzer will find them.
        for item in time_shift(test_observations):

            recorded_at = item['recorded_at']
            location = Point(x=item['longitude'], y=item['latitude'])
            obs = models.Observation.objects.create(recorded_at=recorded_at,
                                             location=location,
                                                    source=source, additional={})

        analyze_subject(str(sub.id))

        self.assertTrue(SubjectAnalyzerResult.objects.filter(subject=sub).exists())

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)

    def test_wasiwasi_immobile(self):
        # Grab prepared observation list from test data.
        test_observations = WASIWASI_IMMOBILE

        # Create models (Subject, SubjectSource and Source)
        sub = models.Subject.objects.create(name='Wasiwasi', subject_type='wildlife', subject_subtype='elephant')
        source = models.Source.objects.create(manufacturer_id='wasiwasi-collar')
        models.SubjectSource.objects.create(subject=sub, source=source, assigned_range=models.DEFAULT_ASSIGNED_RANGE)

        sg = models.SubjectGroup.objects.create(name='immobility_analyzer_group', )
        sg.subjects.add(sub)
        sg.save()

        ia = ImmobilityAnalyzerConfig.objects.create(subject_group=sg)

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in test_observations]

        print('test_observations length: ', str(len(test_observations)))

        for i in range(0, len(test_observations)):
            tmp_obs = test_observations[0:i]

            # Create observations in database, so the Analyzer will find them.
            for item in time_shift(tmp_obs):
                recorded_at = item['recorded_at']
                location = Point(x=item['longitude'], y=item['latitude'])
                obs = models.Observation.objects.create(recorded_at=recorded_at,
                                                        location=location,
                                                          source=source, additional={})
            analyze_subject(str(sub.id))

            models.Observation.objects.all().delete()

            #self.assertTrue(SubjectAnalyzerResult.objects.filter(subject=sub).exists())

            #for e in Event.objects.all():
            #    self.assertTrue(e.event_details.all().exists())

        #Want to have a look at which results are created
        for result in SubjectAnalyzerResult.objects.filter(subject=sub).all():
            print(result)

        #Want to have a look at which events are created
        for event in Event.objects.all():
            print(event)

        assert(True)

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

        ia = ImmobilityAnalyzerConfig.objects.create(subject=sub, threshold_time=18000)

        r = ia.analyze()
        print(r)


