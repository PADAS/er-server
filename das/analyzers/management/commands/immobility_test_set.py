from datetime import datetime, timedelta
import pytz
import json

from django.core.management.base import BaseCommand
from django.db.models import F

from observations.models import Observation

# This is a hand-curated list with a subject name, and end-time and a window size in hours.
TEST_SUBJECTS = [  # (name, window-end-time, window hours)
    ('Ishango', pytz.utc.localize(datetime(2017, 4, 5, 14, 58)), 24),
    ('Courtney', pytz.utc.localize(datetime(2017, 4, 30, 2, 10)), 48),
    ('Wasiwasi', pytz.utc.localize(datetime(2017, 5, 13, 2, 10)), 25),
]


def das_observations(subject_name, start_date, end_date):
    '''
    Generate a list of fixes for the given subject_name, between the start and end dates.
    '''
    dasobservations = Observation.objects.filter(source__subjectsource__subject__name=subject_name,
                                                 recorded_at__gte=start_date, recorded_at__lte=end_date,
                                                 source__subjectsource__assigned_range__contains=F(
                                                     'recorded_at')).order_by('recorded_at')
    for item in dasobservations:
        yield {'recorded_at': item.recorded_at,
               'latitude': item.location.y,
               'longitude': item.location.x,
               }


class Command(BaseCommand):

    help = 'Print test data for immobility analyzer tests.'

    def handle(self, *args, **options):
        # Iterate over my list of subjects and print out a dictionary for each one -- I can paste these dictionaries
        # into a python module and use them as test data.
        for name, end, window_size in TEST_SUBJECTS:
            start = end - timedelta(hours=window_size)
            l = [x for x in das_observations(name, start, end)]
            print("{}_IMMOBILE = {}".format(name.upper(),
                                            json.dumps(l,
                                                       default=lambda x: x.isoformat() if isinstance(x, datetime)
                                                       else str(x),
                                                       indent=2))
                  )

