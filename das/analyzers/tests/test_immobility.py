import copy
from datetime import datetime, timedelta

from django.test import TestCase
import pytz

from analyzers.models.immobility import ImmobilityAnalyzer
from analyzers.models.analyzer import NOMINAL, WARNING, CRITICAL
from observations.track import Track
import observations.models


class TestImmobilityAnalyzer(TestCase):

    fixtures = ['test/observations_source.json', 'test/observations_subject.json',
                'test/observations_subject_source.json', 'test/observations_observation.json']

    def setUp(self):

        self.n_points = 50

        mobile_points = [
            [200 * i * 10 ** -6, 0]
            for i in range(self.n_points)
        ]

        # dead track
        immobile_points = [
            [0, 0]
            for i in range(self.n_points)
        ]

        immobile_points_with_outliers = copy.deepcopy(immobile_points)

        # insert noise:
        immobile_points_with_outliers[49][0] = immobile_points_with_outliers[49][0] + .0004

        times = [
            datetime(2000,1,1,0,0,0,tzinfo=pytz.utc) + timedelta(hours=i)
            for i in range(self.n_points)
        ]

        self.mobile_track = Track(mobile_points, times)
        self.immobile_track = Track(immobile_points, times)
        self.immobile_track_with_outliers = Track(immobile_points_with_outliers, times)


    def test_generic(self):

        f = observations.models.SubjectTrackSegmentFilter(subject_type='elephant')
        ia = ImmobilityAnalyzer.objects.create(subject_id='9342973f-b369-4d21-9f1f-ae89d523e05a', threshold_time=1000)

        r = ia.analyze()

        print(r)

    def xtest_immobility_analyzer_is_mobile(self):
        """
        Test a mobile Track
        """

        immobility_analyzer = ImmobilityAnalyzer()
        analyzer_result = immobility_analyzer.analyze(self.mobile_track)

        expected = NOMINAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected, 'actual value: {}'.format(analyzer_result.value))

    def xtest_immobility_analyzer_is_critical_immobile(self):
        """
        Test an immobile Track
        """

        analyzer = ImmobilityAnalyzer()
        analyzer_result = analyzer.analyze(self.immobile_track)

        actual = analyzer_result.level
        expected = CRITICAL

        self.assertEqual(actual, expected)

    def xtest_immobility_analyzer_is_warning_immobile(self):
        """
        Test an immobile Track
        """
        analyzer = ImmobilityAnalyzer()
        analyzer_result = analyzer.analyze(self.immobile_track)

        expected = CRITICAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected, "actual value: {}".format(analyzer_result.value))

    def xtest_immobility_analyzer_is_nominal_with_a_few_outliers_but_less_than_threshold_ratio(self):
        """
        Test an immobile Track with a few outliers, but less than the threshold ratio.  Should still
        be classified as immobile.
        """

        analyzer = ImmobilityAnalyzer()
        analyzer_result = analyzer.analyze(self.immobile_track_with_outliers)

        expected = WARNING
        actual = analyzer_result.level

        self.assertEqual(actual, expected, "actual value: {}".format(analyzer_result.value))

    def xtest_immobility_analyzer_is_warning_with_more_outliers_than_the_threshold_ratio(self):
        """
        Test an immobile Track with enough outliers to exceed threshold ratio.
        """

        analyzer = ImmobilityAnalyzer()
        analyzer_result = analyzer.analyze(self.immobile_track_with_outliers)

        expected = NOMINAL
        actual = analyzer_result.level

        self.assertEqual(actual, expected, "actual value: {}".format(analyzer_result.value))
