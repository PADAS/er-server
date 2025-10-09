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
            "id", "recorded_at", "subject_id", "subject_name",
            "source_id", "source_name", "track_segment_id",
            "segment_order", "speed_kmh", "additional"
        ]
        for field in expected_fields:
            self.assertIn(field, fields)

    def test_presentation_keys_property(self):
        """Test that presentation_keys returns expected styling keys."""
        layer = ObservationVectorLayer()
        keys = layer.presentation_keys
        expected_keys = [
            "stroke", "stroke-width", "stroke-opacity"
        ]
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

    def test_segment_tracks_empty_features(self):
        """Test segmenting tracks with empty features."""
        layer = ObservationVectorLayer()
        result = layer._segment_tracks([])
        self.assertEqual(result, [])

    def test_segment_tracks_none_features(self):
        """Test segmenting tracks with None features."""
        layer = ObservationVectorLayer()
        result = layer._segment_tracks(None)
        self.assertEqual(result, None)

    def test_finalize_segment(self):
        """Test finalizing a track segment."""
        layer = ObservationVectorLayer()
        features = [
            {"properties": {"id": "1"}},
            {"properties": {"id": "2"}}
        ]
        result = layer._finalize_segment(features, 123)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["properties"]["track_segment_id"], 123)
        self.assertEqual(result[0]["properties"]["segment_order"], 1)
        self.assertEqual(result[1]["properties"]["track_segment_id"], 123)
        self.assertEqual(result[1]["properties"]["segment_order"], 2)

    def test_finalize_segment_without_properties(self):
        """Test finalizing a segment where features don't have properties."""
        layer = ObservationVectorLayer()
        features = [{"id": "1"}, {"id": "2"}]
        result = layer._finalize_segment(features, 456)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["properties"]["track_segment_id"], 456)
        self.assertEqual(result[0]["properties"]["segment_order"], 1)
        self.assertEqual(result[1]["properties"]["track_segment_id"], 456)
        self.assertEqual(result[1]["properties"]["segment_order"], 2)

    def test_convert_rgb_to_hex(self):
        """Test RGB to hex color conversion."""
        layer = ObservationVectorLayer()

        # Test valid RGB string
        result = layer._convert_rgb_to_hex("100,150,200")
        self.assertEqual(result, "#6496c8")

        # Test with spaces
        result = layer._convert_rgb_to_hex(" 255 , 0 , 128 ")
        self.assertEqual(result, "#ff0080")
        
        # Test edge cases
        result = layer._convert_rgb_to_hex("0,0,0")
        self.assertEqual(result, "#000000")
        
        result = layer._convert_rgb_to_hex("255,255,255")
        self.assertEqual(result, "#ffffff")
        
        # Test invalid input
        result = layer._convert_rgb_to_hex("invalid")
        self.assertIsNone(result)
        
        result = layer._convert_rgb_to_hex("")
        self.assertIsNone(result)
        
        result = layer._convert_rgb_to_hex(None)
        self.assertIsNone(result)
        
        # Test out of range values (should be clamped)
        result = layer._convert_rgb_to_hex("300,400,500")
        self.assertEqual(result, "#ffffff")  # Clamped to 255
        
        result = layer._convert_rgb_to_hex("-10,-20,-30")
        self.assertEqual(result, "#000000")  # Clamped to 0

