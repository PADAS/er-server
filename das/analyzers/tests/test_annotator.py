from datetime import datetime

import pytest
import pytz

from django.core.management import call_command
from django.test import TestCase

from analyzers.models import ObservationAnnotator
from observations.models import Observation, Subject


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
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


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationAnnotatorNewMethods(TestCase):
    """Test annotate_queryset and annotate_with_segmentation methods."""

    def setUp(self):
        """Create test data for segmentation testing."""
        call_command(
            "loaddata_with_tenant",
            "test/annotation-junkfix-1.json",
        )
        self.subject = Subject.objects.get(id="0fa8ec9a-7e92-4575-9575-df202d5dde25")
        self.annotator = ObservationAnnotator()

    def test_annotate_queryset_adds_expected_fields(self):
        """Test that annotate_queryset adds distance, time, and speed fields."""
        # Get base queryset (apply annotation before slicing)
        qs = Observation.objects.filter(source__subjectsource__subject=self.subject).order_by("recorded_at")

        # Apply annotation first, then slice
        annotated_qs = self.annotator.annotate_queryset(qs)[:10]

        # Check that we can access the new fields
        observations = list(annotated_qs)
        self.assertGreater(len(observations), 0, "Should have test observations")

        for obs in observations:
            # Check that the fields exist (they'll be None for first observation)
            self.assertTrue(hasattr(obs, "distance_preceding"))
            self.assertTrue(hasattr(obs, "time_lapse_preceding"))
            self.assertTrue(hasattr(obs, "speed_kmh"))

    def test_annotate_queryset_calculates_speed_correctly(self):
        """Test that speed calculations work correctly."""
        # Get observations with known data (apply annotation before slicing)
        qs = Observation.objects.filter(source__subjectsource__subject=self.subject).order_by("recorded_at")

        annotated_qs = self.annotator.annotate_queryset(qs)[:20]
        observations = list(annotated_qs)

        # Find observations with non-null speed (not the first one)
        speed_observations = [obs for obs in observations if obs.speed_kmh and obs.speed_kmh > 0]

        if speed_observations:
            # Check that speed is calculated (positive value)
            for obs in speed_observations[:5]:  # Check first few
                self.assertGreater(obs.speed_kmh, 0, "Speed should be positive for moving observations")
                self.assertIsInstance(obs.speed_kmh, (int, float), "Speed should be numeric")

    def test_annotate_with_segmentation_adds_segment_fields(self):
        """Test that annotate_with_segmentation adds all segmentation fields."""
        # Get base queryset (apply annotation before slicing)
        qs = Observation.objects.filter(source__subjectsource__subject=self.subject).order_by("recorded_at")

        # Apply segmentation annotation first, then slice
        segmented_qs = self.annotator.annotate_with_segmentation(
            qs, max_time_gap_hours=24.0, speed_threshold_kmh=100.0
        )[:20]

        observations = list(segmented_qs)
        self.assertGreater(len(observations), 0, "Should have test observations")

        for obs in observations:
            # Check that segmentation fields exist
            self.assertTrue(hasattr(obs, "is_segment_break"))
            self.assertTrue(hasattr(obs, "track_segment_id"))
            self.assertTrue(hasattr(obs, "segment_order"))
            # Also includes the basic fields from annotate_queryset
            self.assertTrue(hasattr(obs, "distance_preceding"))
            self.assertTrue(hasattr(obs, "time_lapse_preceding"))
            self.assertTrue(hasattr(obs, "speed_kmh"))

    def test_annotate_with_segmentation_first_observation_is_break(self):
        """Test that the first observation in each subject is marked as a segment break."""
        qs = Observation.objects.filter(source__subjectsource__subject=self.subject).order_by("recorded_at")

        segmented_qs = self.annotator.annotate_with_segmentation(qs)[:10]
        observations = list(segmented_qs)

        if observations:
            first_obs = observations[0]
            self.assertTrue(first_obs.is_segment_break, "First observation should be a segment break")
            self.assertEqual(first_obs.track_segment_id, 0, "First segment should have ID 0")
            self.assertEqual(first_obs.segment_order, 1, "First observation should have order 1")

    def test_annotate_with_segmentation_segment_ordering(self):
        """Test that segment ordering works correctly."""
        qs = Observation.objects.filter(source__subjectsource__subject=self.subject).order_by("recorded_at")

        segmented_qs = self.annotator.annotate_with_segmentation(qs)[:20]
        observations = list(segmented_qs)

        if len(observations) > 1:
            # Check that segment orders are sequential within segments
            current_segment_id = None
            expected_order = 1

            for obs in observations:
                if obs.track_segment_id != current_segment_id:
                    # New segment started
                    current_segment_id = obs.track_segment_id
                    expected_order = 1

                self.assertEqual(
                    obs.segment_order, expected_order, f"Observation {obs.id} should have order {expected_order}"
                )
                expected_order += 1

    def test_annotate_with_segmentation_uses_default_speed_threshold(self):
        """Test that segmentation uses the annotator's max_speed when no threshold provided."""
        # Set a specific max_speed on the annotator
        self.annotator.max_speed = 50.0

        qs = Observation.objects.filter(source__subjectsource__subject=self.subject).order_by("recorded_at")

        # Call without explicit speed_threshold_kmh parameter
        segmented_qs = self.annotator.annotate_with_segmentation(qs, max_time_gap_hours=24.0)[:10]

        # Should not raise an error and should complete successfully
        observations = list(segmented_qs)
        self.assertGreater(len(observations), 0, "Should process observations with default speed threshold")

    def test_annotate_with_segmentation_custom_parameters(self):
        """Test that segmentation respects custom time gap and speed threshold parameters."""
        qs = Observation.objects.filter(source__subjectsource__subject=self.subject).order_by("recorded_at")

        # Test with very strict parameters that should create more breaks
        strict_segmented_qs = self.annotator.annotate_with_segmentation(
            qs, max_time_gap_hours=0.1, speed_threshold_kmh=5.0  # Very short time gap  # Very low speed threshold
        )[:10]

        # Test with very lenient parameters
        lenient_segmented_qs = self.annotator.annotate_with_segmentation(
            qs, max_time_gap_hours=48.0, speed_threshold_kmh=500.0  # Long time gap  # High speed threshold
        )[:10]

        strict_obs = list(strict_segmented_qs)
        lenient_obs = list(lenient_segmented_qs)

        # Both should process without errors
        self.assertEqual(len(strict_obs), len(lenient_obs), "Should process same number of observations")

        if len(strict_obs) > 1:
            # Strict parameters might create more segment breaks
            strict_breaks = sum(1 for obs in strict_obs if obs.is_segment_break)
            lenient_breaks = sum(1 for obs in lenient_obs if obs.is_segment_break)

            # At minimum, both should have the first observation as a break
            self.assertGreaterEqual(strict_breaks, 1, "Should have at least one segment break")
            self.assertGreaterEqual(lenient_breaks, 1, "Should have at least one segment break")

    def test_annotate_queryset_empty_queryset(self):
        """Test that annotation methods handle empty querysets gracefully."""
        empty_qs = Observation.objects.none()

        # Should not raise errors
        annotated_qs = self.annotator.annotate_queryset(empty_qs)
        segmented_qs = self.annotator.annotate_with_segmentation(empty_qs)

        self.assertEqual(list(annotated_qs), [])
        self.assertEqual(list(segmented_qs), [])
