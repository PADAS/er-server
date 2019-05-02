from collections import namedtuple
from datetime import datetime
from typing import Dict

import json

from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.dateparse import parse_duration
from django.http.request import HttpRequest


class StaticImageFinder(object):
    image_caches = {}
    IMAGE_TYPES = ('svg', 'png', 'jpg')
    StaticImage = namedtuple('StaticImage', ('exists', 'path'))
    web_path = '/static/{0}'
    file_format = '{key}.{type}'

    def get_marker_icon(self, keys, image_types=IMAGE_TYPES):

        image_cache = self.image_caches.setdefault(image_types, {})

        for key in keys:
            static_image = image_cache.get(key, None)
            if static_image:
                if static_image.exists:
                    return static_image.path
                continue
            for t in image_types:
                file = self.file_format.format(**dict(key=key, type=t))
                if staticfiles_storage.exists(file):
                    path = self.web_path.format(file)
                    image_cache[key] = self.StaticImage(True, path)
                    return path
            image_cache[key] = self.StaticImage(False, None)


static_image_finder = StaticImageFinder()


class Schedule:

    def __init__(self, periods: Dict[str, list]):
        self.periods = periods

    def __contains__(self, value):
        raise NotImplemented('An extending class must implement __contains__.')

    def __repr__(self):
        return json.dumps(self.periods)


class OneWeekSchedule(Schedule):
    '''
    A OneWeekSchedule is defined by a dictionary whereby each property is the name of a day of the week. Each
    value is a list of tuples where each tuple indicates a range of time of the form ('hh:mm', 'hh:mm').
    An example range is: ('08:30', '14:00') to represent a range from 8:30am to 2:00pm.

    A complete example is:

        {
            "monday": [("08:00", "12:00"), ("13:00", "17:30")],
            "wednesday": [("08:00", "12:00"), ("13:00", "17:30")]
        }

    Once initialized you can ask if a datetime is in the Schedule.
    '''

    # List of days compatible with ISO weekday index.
    days_of_week = ['index-0', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    def __init__(self, periods: Dict[str, list] = dict):
        self.periods = periods

    def __contains__(self, value):

        if not bool(self.periods):
            return True

        # Truncate the timestamp to our finest granularity.
        value = value.replace(second=0, microsecond=0)

        relevant_periods = self.periods.get(self.days_of_week[value.isoweekday()])
        if relevant_periods:
            return self.test_timestamp(value, relevant_periods)
        return False

    def test_timestamp(self, sample_ts, periods):

        if not isinstance(sample_ts, datetime):
            return ValueError(f'Type {type(sample_ts)} is not supported.')

        # Calculate sample's total seconds for the day.
        ts_seconds = (sample_ts - sample_ts.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()

        for x, y in self._generate_ranges(periods):
            if x <= ts_seconds and ts_seconds <= y:  # inclusive
                return True
        return False

    @staticmethod
    def _generate_ranges(periods):
        for period in periods:
            start, end = (parse_duration(f'{x}:00') for x in period)
            yield (start.seconds, end.seconds)


class NonHttpRequest(HttpRequest):
    '''
    This is a simple convenient class with minimal support for satisfying serialization
    outside an actual request.
    '''
    def build_absolute_uri(self, url):
        return url

