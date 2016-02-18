from datetime import datetime

from django.test import TestCase
import pytz

from observations.track import Track


class TestTrack(TestCase):

    def setUp(self):

        # 1 degree/s sprint along the equator
        points = [
            (i, 0)
            for i in range(5)
        ]

        times = [
            datetime(2000,1,1,0,0,i,tzinfo=pytz.utc)
            for i in range(5)
        ]

        self.track = Track(points, times)

    def test_track_speed_series(self):
        """
        Test a speed calculations of Track
        """

        meters_per_degree_longitude_wgs84 = 111319

        expected = meters_per_degree_longitude_wgs84 / 1
        actual = int(self.track.speed_series[1])

        self.assertEqual(actual, expected)
