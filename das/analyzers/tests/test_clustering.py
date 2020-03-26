from unittest import TestCase

from analyzers.clustering_utils import cluster_alerts, normalize_alert_object
from analyzers.tests.cluster_test_data import GFW_DEFORESTATION_ALERTS_DATA, \
    GFW_FIRMS_DATA

CLUSTER_RADIUS = 4
MIN_CLUSTER_SIZE = 1


class TestClustering(TestCase):

    def test_cluster_deforestation_alerts(self):
        clustered_alerts = cluster_alerts(GFW_DEFORESTATION_ALERTS_DATA, CLUSTER_RADIUS, MIN_CLUSTER_SIZE)
        self.assertLess(len(clustered_alerts), len(GFW_DEFORESTATION_ALERTS_DATA))

        # a single report contains the number of clustered alerts
        self.assertIn('num_clustered_alerts', clustered_alerts[0].keys())

    def test_cluster_firm_alerts(self):
        clustered_alerts = cluster_alerts(GFW_FIRMS_DATA,
                                          CLUSTER_RADIUS, MIN_CLUSTER_SIZE)
        self.assertLess(len(clustered_alerts),
                        len(GFW_FIRMS_DATA))

        # a single report contains the number of clustered alerts
        self.assertIn('num_clustered_alerts', clustered_alerts[0].keys())

    def test_normalize_lat_long_in_deforestation_alert(self):
        raw_alert = {
            "year": 2020,
            "long": 98.44987500000012,
            "lat": 15.966124999999982,
            "julian_day": 65,
            "confidence": 2
        }

        normalized_alert = {
            "year": 2020,
            "longitude": 98.44987500000012,
            "latitude": 15.966124999999982,
            "julian_day": 65,
            "confidence": 2
        }

        self.assertEqual(normalize_alert_object(raw_alert), normalized_alert)
