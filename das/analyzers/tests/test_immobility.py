import copy
from datetime import datetime, timedelta
import dateutil.parser as dp
from django.test import TestCase
import pytz

from analyzers.models.immobility import ImmobilityAnalyzer
from .immobility_test_data import ISHANGO_IMMOBILE
from observations.track import Track
import observations.models
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon
import random
import copy

from observations import models


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

class TestImmobilityAnalyzer(TestCase):

    fixtures = ['test/observations_source.json', 'test/observations_subject.json',
                'test/observations_subject_source.json', 'test/observations_observation.json']

    def setUp(self):
        pass


    def test_ishango_immobile(self):

        source = models.Source.objects.get(id='a91e0366-898c-475b-830f-e0fae46e6efe')
        end = pytz.utc.localize(datetime.utcnow())

        for item in time_shift(ISHANGO_IMMOBILE):

            recorded_at = item['recorded_at']
            location = Point(x=item['longitude'], y=item['latitude'])
            obs = models.Observation.objects.create(recorded_at=recorded_at,
                                             location=location,
                                                    source=source, additional={})
            if obs.recorded_at > end:
                break

        ia = ImmobilityAnalyzer.objects.create(subject_id='9342973f-b369-4d21-9f1f-ae89d523e05a', threshold_time=1000)

        test_subject = models.Subject.objects.get(id='9342973f-b369-4d21-9f1f-ae89d523e05a')
        print (test_subject)

        r = ia.analyze()

        print(r)

    def test_random(self):

        n = pytz.utc.localize(datetime.utcnow())
        source = models.Source.objects.get(id='a91e0366-898c-475b-830f-e0fae46e6efe')
        positions = generate_random_positions()
        positions.send(None)
        while True:

            recorded_at, location = positions.send(None)
            obs = models.Observation.objects.create(recorded_at=recorded_at,
                                             location=location,
                                                    source=source, additional={})
            if obs.recorded_at > n:
                break

        ia = ImmobilityAnalyzer.objects.create(subject_id='9342973f-b369-4d21-9f1f-ae89d523e05a', threshold_time=1000)

        test_subject = models.Subject.objects.get(id='9342973f-b369-4d21-9f1f-ae89d523e05a')
        print (test_subject)

        r = ia.analyze()

        print(r)


