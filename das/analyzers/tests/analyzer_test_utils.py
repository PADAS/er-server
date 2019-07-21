import dateutil.parser as dp
import pytz
from datetime import datetime, timedelta
from functools import reduce, partial
import copy
import random
from analyzers.utils import typify
from django.contrib.gis.geos import Point
from observations import models

# Function to apply to plain/JSON observations to convert recorded_at to datetime.
parse_recorded_at = partial(typify, dict(recorded_at=dp.parse))


def time_shift(items, time_key='recorded_at', start_time=None):
    """
    Time-shift the items in the list using each item's 'time_key' key.
    Anchor the new list at start_time or a time calculated based on the item data.

    :param items: A list of dict items where each item has a time in item[time_key]
    :param time_key: The key to use for getting a datetime from each item.
    :param start_time: Anchor the new list at this datetime if it's provided.
    :return: generator which yields a new 'time-shifted' list of the items.
    """

    if not items:
        return

    # Determine timespan of 'items'.
    minimum_time = min([ x[time_key] for x in items])
    maximum_time = max([ x[time_key] for x in items])
    actual_start = minimum_time

    fake_start = start_time or pytz.utc.localize(datetime.utcnow()) - (maximum_time - minimum_time)
    for i, item in enumerate(items):
        fake_time = (item[time_key] - actual_start) + fake_start
        new_item = copy.copy(item)
        new_item[time_key] = fake_time
        yield new_item


def generate_random_positions(start_time=None, x=37.5, y=0.56, ts_days=1):  # Samburu
    recorded_at = start_time or pytz.utc.localize(datetime.utcnow())

    while (pytz.utc.localize(datetime.utcnow()) - recorded_at).days < ts_days:
        yield recorded_at, Point(x=x, y=y)
        x += (random.random() - 0.5) / 10000
        y += (random.random() - 0.5) / 10000
        recorded_at = recorded_at - timedelta(minutes=30)


def generate_observations(observations, timeshift=True):
    if timeshift:
        observations = time_shift(observations)

    for item in observations:
        recorded_at = item['recorded_at']
        location = Point(x=item['longitude'], y=item['latitude'])
        obs = models.Observation(recorded_at=recorded_at, location=location)
        yield obs


def store_observations(observations, timeshift=True, source=None):
    if timeshift:
        observations = time_shift(observations)

    for item in observations:
        recorded_at = item['recorded_at']
        location = Point(x=item['longitude'], y=item['latitude'])
        models.Observation.objects.create(recorded_at=recorded_at, location=location,
                                                source=source, additional={})


