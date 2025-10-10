from django.test import TestCase
from rest_framework.test import APIClient

from observations.models import Observation
from observations.vector_layers import ObservationVectorLayer


class TestObservationVectorTiles(TestCase):
    """Test cases for observation vector tiles."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        # Create test data here if needed

    def test_observation_vector_layer_creation(self):
        """Test that ObservationVectorLayer can be instantiated."""
        layer = ObservationVectorLayer()
        self.assertEqual(layer.id, "observations")
        self.assertEqual(layer.model, Observation)
        self.assertEqual(layer.min_zoom, 3)
        self.assertEqual(layer.max_zoom, 24)

    def test_tile_fields_property(self):
        """Test that tile_fields returns expected fields."""
        layer = ObservationVectorLayer()
        fields = layer.tile_fields
        expected_fields = [
            "id",
            "recorded_at",
            "subject_id",
            "subject_name",
            "source_id",
            "source_name",
            "track_segment_id",
            "segment_order",
            "speed_kmh",
            "additional",
        ]
        for field in expected_fields:
            self.assertIn(field, fields)

    def test_presentation_keys_property(self):
        """Test that presentation_keys returns expected styling keys."""
        layer = ObservationVectorLayer()
        keys = layer.presentation_keys
        expected_keys = ["stroke", "stroke-width", "stroke-opacity"]
        for key in expected_keys:
            self.assertIn(key, keys)

    def test_default_thresholds(self):
        """Test default threshold values."""
        layer = ObservationVectorLayer()
        self.assertEqual(layer.DEFAULT_MAX_TIME_GAP_HOURS, 24)
        self.assertEqual(layer.DEFAULT_SPEED_THRESHOLD_KMH, 200.0)

    def test_get_max_time_gap_hours_without_request(self):
        """Test getting max time gap hours without request."""
        layer = ObservationVectorLayer()
        result = layer._get_max_time_gap_hours()
        self.assertEqual(result, 24.0)

    def test_get_speed_threshold_kmh_without_request(self):
        """Test getting speed threshold without request."""
        layer = ObservationVectorLayer()
        result = layer._get_speed_threshold_kmh()
        self.assertEqual(result, 200.0)
