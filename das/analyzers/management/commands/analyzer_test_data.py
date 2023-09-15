import json
from datetime import datetime, timedelta

import pytz

from django.db.models import F

from observations.models import Observation
from utils.tenant.commands import TenantBaseCommand


def print_immobility_test_set():
    # This is a hand-curated list with a subject name, and end-time and a window size in hours.
    IMMOBILITY_TEST_SUBJECTS = [  # (name, window-end-time, window hours)
        ("Jolie", pytz.utc.localize(datetime(2017, 11, 2, 15, 00)), 36)
    ]

    def das_observations(subject_name, start_date, end_date):
        """
        Generate a list of fixes for the given subject_name, between the start and end dates.
        """
        dasobservations = Observation.objects.filter(
            source__subjectsource__subject__name=subject_name,
            recorded_at__gte=start_date,
            recorded_at__lte=end_date,
            source__subjectsource__assigned_range__contains=F("recorded_at"),
        ).order_by("recorded_at")
        for item in dasobservations:
            yield {
                "recorded_at": item.recorded_at,
                "latitude": item.location.y,
                "longitude": item.location.x,
            }

    # Iterate over my list of subjects and print out a dictionary for each one -- I can paste these dictionaries
    # into a python module and use them as test data.
    for name, end, window_size in IMMOBILITY_TEST_SUBJECTS:
        start = end - timedelta(hours=window_size)
        l = [x for x in das_observations(name, start, end)]
        print(
            "{}_IMMOBILE = {}".format(
                name.upper(),
                json.dumps(l, default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x), indent=2),
            )
        )


TEST_SETS = {"immobility": print_immobility_test_set}
DEFAULT_TEST_SET = "immobility"


class Command(TenantBaseCommand):
    help = "Generate and print a test dataset for the given test set name.\n One of %s" % (TEST_SETS.keys(),)

    def handle(self, *args, **options):
        f = TEST_SETS.get(options["n"], None)

        if f:
            f()
        else:
            print("That test set is not available. Choose from %s" % (TEST_SETS.keys(),))

    def add_arguments(self, parser):
        parser.add_argument("-n", type=str, help="Test set name.", default=DEFAULT_TEST_SET)
