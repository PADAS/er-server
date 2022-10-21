from django.test import TestCase
from observations.models import Subject
from observations.models import DEFAULT_ASSIGNED_RANGE
from observations.models import Source
from observations.models import SubjectSource
from observations.models import SubjectTrackSegmentFilter
from analyzers.models import SubjectSpeedProfile
from analyzers.models import SpeedDistro
from .analyzer_test_utils import *
from .low_speed_test_data import *
import numpy as np
import logging
logger = logging.getLogger(__name__)


class TestSpeedProfile(TestCase):

    def setUp(self):
        pass

    def test_build_speed_profile(self):

        # Define the subject
        sub = Subject.objects.create(
            name='Heritage', subject_subtype_id='elephant')

        # create a dummy source
        source = Source.objects.create(manufacturer_id='007')

        # Assign the source to the subject
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(
            subject_subtype_id='elephant', speed_KmHr=7.0)

        # Store observations in the database
        test_observations = [parse_recorded_at(x) for x in HERITAGE_Track]
        store_observations(test_observations, timeshift=True, source=source)

        # Create a subject speed profile
        sp = SubjectSpeedProfile.objects.create(subject=sub)

        # Create a speed distribution for the speed profile
        distro = SpeedDistro.objects.create(subject_speed_profile=sp)

        # Update percentile values
        percentiles = [0.25, 0.5, 0.75]
        distro.update_percentiles(percentiles)

        # Update speeds array
        distro.update_speeds_array()

        # Test whether the percentiles were calculated correctly
        for p in percentiles:
            speed_val = distro.percentiles[p]
            logger.info('PercentileSpeedVal: %s' % str(speed_val))
            self.assertTrue(speed_val > 0)

        # Test whether the speeds array was calculated correctly
        speed_vals = distro.speeds_kmhr
        logger.info('Length of distro.speeds_kmhr: %s' % str(len(speed_vals)))
        logger.info('MaxSpeed: %s' % str(np.max(speed_vals)))
        logger.info('MinSpeed: %s' % str(np.min(speed_vals)))
        assert(len(speed_vals) == 3147)
        assert(round(np.min(speed_vals), 6) == 0.000926)
        assert(round(np.max(speed_vals), 6) == 3.181680)
