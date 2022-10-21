from collections import namedtuple
from datetime import datetime
from typing import Dict
import urllib.parse

import json

import jsonschema

from django.conf import settings

from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.dateparse import parse_duration
from django.http.request import HttpRequest
import pytz
from django.utils import timezone


class StaticImageFinder(object):
    image_caches = {}
    IMAGE_TYPES = ('svg', 'png', 'jpg')
    StaticImage = namedtuple('StaticImage', ('exists', 'path'))
    static_paths = ('{0}', 'sprite-src/{0}')
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
                for static_path in self.static_paths:
                    static_file = static_path.format(file)
                    if staticfiles_storage.exists(static_file):
                        path = self.web_path.format(static_file)
                        image_cache[key] = self.StaticImage(True, path)
                        return path
            image_cache[key] = self.StaticImage(False, None)


static_image_finder = StaticImageFinder()


class Schedule:

    def __init__(self, periods: Dict[str, list]):
        self.schedule_definition = periods

    def __contains__(self, value):
        raise NotImplemented('An extending class must implement __contains__.')

    def __repr__(self):
        return json.dumps(self.schedule_definition)


class OneWeekSchedule(Schedule):
    '''
    A OneWeekSchedule is defined by a dictionary whereby each property is the name of a day of the week. Each
    value is a list of tuples where each tuple indicates a range of time of the form ('hh:mm', 'hh:mm').
    An example range is: ('08:30', '14:00') to represent a range from 8:30am to 2:00pm.

    A complete example is:
        {
          "schedule_type": "week",
          "periods":
            {
                "monday": [["08:00", "12:00"], ["13:00", "17:30"]],
                "wednesday": [["08:00", "12:00"], ["13:00", "17:30"]]
            }
        }

    Once initialized you can ask if a datetime is in the Schedule.
    '''

    # List of days compatible with ISO weekday index.
    days_of_week = ['index-0', 'monday', 'tuesday',
                    'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    def __init__(self, schedule_definition: Dict[str, dict] = dict):

        self.schedule_definition = schedule_definition or {}

        if self.schedule_definition:
            self.validate_schedule_document()

        self.schedule_periods = self.schedule_definition.get('periods', {})

        if 'timezone' in self.schedule_definition:
            self.schedule_timezone = pytz.timezone(
                self.schedule_definition['timezone'])
        else:
            self.schedule_timezone = timezone.get_current_timezone()

    def __contains__(self, value):

        if not bool(self.schedule_periods):
            return True

        value = value.astimezone(self.schedule_timezone)

        # Truncate the timestamp to our finest granularity.
        value = value.replace(second=0, microsecond=0)

        relevant_periods = self.schedule_periods.get(
            self.days_of_week[value.isoweekday()])
        if relevant_periods:
            return self.test_timestamp(value, relevant_periods)
        return False

    def test_timestamp(self, sample_ts, periods):

        if not isinstance(sample_ts, datetime):
            return ValueError(f'Type {type(sample_ts)} is not supported.')

        # Calculate sample's total seconds for the day.
        ts_seconds = (sample_ts - sample_ts.replace(hour=0,
                                                    minute=0, second=0, microsecond=0)).total_seconds()

        for x, y in self._generate_ranges(periods):
            if x <= ts_seconds and ts_seconds <= y:  # inclusive
                return True
        return False

    @staticmethod
    def _generate_ranges(periods):
        for period in periods:
            start, end = (parse_duration(f'{x}:00') for x in period)
            yield (start.seconds, end.seconds)

    def validate_schedule_document(self):
        jsonschema.validate(self.schedule_definition, self.json_schema)

    json_schema = {
        "definitions": {
            "dayofweek": {
                "$id": "#/properties/periods/properties/dayofweek_periods",
                "type": "array",
                "title": "Day of week periods Schema",
                "default": None,
                "items": {
                    "$id": "#/properties/periods/properties/dayofweek/items",
                    "type": "array",
                    "title": "Time-based periods Schema",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {
                        "$id": "#/properties/periods/properties/dayofweek/items/items",
                        "type": "string",
                        "title": "Time-range Schema",
                        "default": "",
                        "examples": [
                            "08:00", "17:30",
                        ],
                        "minLength": 5,
                        "maxLength": 5,
                        "pattern": "^[0-2]\\d:[0-5]\\d$"
                    }
                }
            }

        },
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://earthranger.com/schedule.json",
        "type": "object",
        "title": "The Schedule Schema",
        "additionalProperties": False,
        "properties": {
            "schedule_type": {
                "$id": "#/properties/schedule_type",
                "type": "string",
                "default": "week",
                "enum": ["week"],
                "title": "The kind of schedule this document represents. Currently only 'week' is supported."
            },
            "periods": {
                "$id": "#/properties/schedule/periods",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "monday": {"$ref": "#/definitions/dayofweek"},
                    "tuesday": {"$ref": "#/definitions/dayofweek"},
                    "wednesday": {"$ref": "#/definitions/dayofweek"},
                    "thursday": {"$ref": "#/definitions/dayofweek"},
                    "friday": {"$ref": "#/definitions/dayofweek"},
                    "saturday": {"$ref": "#/definitions/dayofweek"},
                    "sunday": {"$ref": "#/definitions/dayofweek"}
                }

            },
            "timezone": {
                "$id": "#/properties/timezone",
                "type": "string",
                "title": "The name of the timezone within which the schedule will be evaluated.",
                "enum": list(pytz.all_timezones_set)
            }
        }
    }


class NonHttpRequest(HttpRequest):
    '''
    This is a simple convenient class with minimal support for satisfying serialization
    outside an actual request.
    '''

    def build_absolute_uri(self, url):
        if hasattr(settings, 'UI_SITE_URL'):
            return f'{settings.UI_SITE_URL}{url}'
        return url


def get_site_name():
    """The sites name as used in google analytics and our ER site metrics
    """
    if hasattr(settings, 'METRICS_SITE_NAME'):
        return settings.METRICS_SITE_NAME

    if hasattr(settings, 'UI_SITE_URL'):
        parts = urllib.parse.urlsplit(settings.UI_SITE_URL)
        sitename = parts.hostname.split('.')[0]
        return sitename
    return "unknown"
