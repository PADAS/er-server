import copy
import random
from datetime import datetime, timedelta
from functools import reduce, partial
import dateutil.parser as dp
import pytz
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.test import TestCase

from analyzers.models import ImmobilityAnalyzerConfig, SubjectAnalyzerResult, OK, WARNING, CRITICAL
from observations import models
from activity.models import Event
from .immobility_test_data import *
from analyzers.tasks import analyze_subject
import analyzers.exceptions

from analyzers.utils import typify

from analyzers.immobility import ImmobilityAnalyzer

# Function to apply to plain/JSON observations to convert recorded_at to datetime.
parse_recorded_at = partial(typify, dict(recorded_at=dp.parse))

def generate_random_positions(start_time=None, x=37.5, y=1.41):
    recorded_at = start_time or pytz.utc.localize(datetime.utcnow()) - timedelta(hours=24)

    while True:
        yield recorded_at, Point(x=x, y=y)
        x += (random.random()  - 0.5)/10000
        y += (random.random()  - 0.5)/10000
        recorded_at = recorded_at + timedelta(minutes=30)


def time_shift(items, time_key='recorded_at', start_time=None):
    '''
    Time-shift the items in the list using each item's 'time_key' key.
    Anchor the new list at start_time or a time calculated based on the item data.
    
    :param items: A list of dict items where each item has a time in item[time_key]
    :param time_key: The key to use for getting a datetime from each item.
    :param start_time: Anchor the new list at this datetime if it's provided.
    :return: generator which yields a new 'time-shifted' list of the items.
    '''

    if not items:
        return

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

    def test_immobility_with_moving_observations_list(self):

        test_subject = models.Subject(name='Sample')

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in ISHANGO_IMMOBILE]

        def generate_observations(observations):
            for item in time_shift(observations):

                recorded_at = item['recorded_at']
                location = Point(x=item['longitude'], y=item['latitude'])
                obs = models.Observation(recorded_at=recorded_at, location=location)
                yield obs

        test_observations = list(generate_observations(test_observations))

        for count in range(21, 10, -1):
            try:
                config = ImmobilityAnalyzerConfig() # default values
                last_result = SubjectAnalyzerResult(level=OK)

                ia = ImmobilityAnalyzer(config=config, subject=test_subject)
                result, event = ia.analyze(observations=test_observations[:count], last_result=last_result)

                # Break when we get to an OK result
                if result.level == OK:
                    break
            except analyzers.exceptions.InsufficientDataAnalyzerException:
                break

        # Assert we've broken from this for-loop at level=>OK and count=>17
        self.assertEqual(result.level, OK)
        self.assertEqual(count, 17) # Magic number, based on Ishango test dataset

    def test_integration_ishango_immobile(self):

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

    def test_ishango_immobile(self):
        print('Analyzing: ', 'Ishango')
        test_subject = models.Subject(name='Ishango')

        # parse recorded_at (from string to datetime)
        test_observations = [parse_recorded_at(x) for x in ISHANGO_IMMOBILE2]

        def generate_observations(observations):
            for item in observations:
                recorded_at = item['recorded_at']
                location = Point(x=item['longitude'], y=item['latitude'])
                obs = models.Observation(recorded_at=recorded_at, location=location)
                yield obs

        # Grab prepared observation list from test data.
        test_observations = list(generate_observations(test_observations))

        last_result = None
        for i in range(1, len(test_observations)):
            try:
                print('Current data-point: ', test_observations[i-1])

                ia_config = ImmobilityAnalyzerConfig()
                ia_config.threshold_time = 18000 # 5 hours

                ia = ImmobilityAnalyzer(config=ia_config, subject=test_subject)
                result, event = ia.analyze(observations=test_observations[:i+1], last_result=last_result)
                last_result = result

                print('Analyzer result: ', last_result)
                print('Analyzer event: ', event)
            except analyzers.exceptions.InsufficientDataAnalyzerException:
                print('Insufficient data warning')
                pass

        self.assertTrue(True)

    def test_immobility_event(self):
        '''
        Test creating an Immobility Event, along with EventDetails reflecting an ImmobilityAnalyzer result.
        :return: 
        '''
        from analyzers.utils import save_analyzer_event

        event_location_value = {
            'longitude': 36.5,
            'latitude': 1.5
        }

        analyzer_result_values = {
            'probability_value': .80,
            'cluster_radius': 13,
            'cluster_fix_count': 6,
            'total_fix_count': 26,
        }

        event_data = dict(
            message='Woody is immobile',
            event_time=pytz.utc.localize(datetime.utcnow()),
            provenance=Event.PC_ANALYZER,
            event_type='immobility',
            priority=Event.PRI_URGENT,
            location=event_location_value,
            event_details=analyzer_result_values,
        )

        e = save_analyzer_event(event_data)

        self.assertTrue(e.event_details.count() == 1)