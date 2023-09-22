from datetime import datetime

import pytz

from django.core.management import call_command
from django.test import TestCase

from analyzers.models import ObservationAnnotator
from observations.models import Observation, Subject


class TestAnnotator(TestCase):
    def setUp(self):
        call_command(
            "loaddata_with_tenant",
            "test/annotation-junkfix-1.json",
        )

    def test_annotate_junkfix(self):
        sub = Subject.objects.get(id="0fa8ec9a-7e92-4575-9575-df202d5dde25")
        self.assertTrue(sub is not None)

        observations = sub.observations()
        self.assertEqual(len(observations), 184, msg="I got a different number of observations that I expected.")
        # self.assertEqual(actual, expected)

        annotator = ObservationAnnotator.get_for_subject(sub)

        # The test data in the fixture indicated above is for early March 2017.
        annotator.annotate(
            start_date=pytz.utc.localize(datetime(2017, 3, 3)), end_date=pytz.utc.localize(datetime(2017, 3, 10))
        )

        junk_fix = Observation.objects.get(id="e83b863a-b632-4c6c-9cb3-074632510f20")

        self.assertTrue(junk_fix.exclusion_flags > 0)
