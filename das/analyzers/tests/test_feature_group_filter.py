"""
Tests for the feature_group_filter field on SubjectAnalyzerConfig and the
_is_within_feature_group_filter method on SubjectAnalyzer.
"""

from typing import List
from unittest.mock import MagicMock

import pytest
from django_multitenant.utils import set_current_tenant

from django.contrib.gis.geos import GeometryCollection, Point, Polygon
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from analyzers.immobility import ImmobilityAnalyzer
from analyzers.models import ImmobilityAnalyzerConfig
from core.models import DASTenant
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic, SpatialFeatureType
from observations.models import (
    Observation,
    Source,
    Subject,
    SubjectGroup,
    SubjectSource,
)


def _make_result_at(lon: float, lat: float):
    """Return a minimal result-like object whose geometry_collection is a single point."""
    result = MagicMock()
    result.geometry_collection = GeometryCollection(Point(lon, lat))
    return result


def _create_observations(locations: List[Point], source, date, time_increment_minutes=5):
    for count, location in enumerate(locations, 1):
        Observation.objects.create(
            location=location,
            source=source,
            recorded_at=date - timezone.timedelta(minutes=count * time_increment_minutes),
        )


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFeatureGroupFilterBase(TestCase):
    """Unit tests for SubjectAnalyzer._is_within_feature_group_filter."""

    def setUp(self):
        tenant = DASTenant.objects.first()
        set_current_tenant(tenant)
        call_command("loaddata_with_tenant", "event_data_model")

        geofence_geom = Polygon([(-10, -10.0), (10, -10.0), (10, 10), (-10, 10), (-10, -10.0)])
        self.spatial_feature_type = SpatialFeatureType.objects.get_or_create(name="test_polygon_filter")[0]
        gf = SpatialFeature.objects.create(
            name="Polygon Test Fence",
            feature_geometry=geofence_geom,
            feature_type=self.spatial_feature_type,
        )
        self.spatial_feature_group = SpatialFeatureGroupStatic.objects.create(name="Polygon Filter")
        self.spatial_feature_group.features.add(gf)
        self.spatial_feature_group.save()

        self.subject = Subject.objects.create(name="fgf_subject", subject_subtype_id="elephant")
        self.subject.save()

        self.subject_group = SubjectGroup.objects.create(name="fgf_group")
        self.subject_group.subjects.add(self.subject)
        self.subject_group.save()

        self.source = Source.objects.create(manufacturer_id="001")
        self.source.save()

        self.subject_source = SubjectSource.objects.create(subject=self.subject, source=self.source)
        self.subject_source.save()


class TestFeatureGroupFilter_NoFilter(TestFeatureGroupFilterBase):

    def test_no_filter_returns_true(self):
        """When feature_group_filter is not set the method always returns True."""

        self.immobility_config = ImmobilityAnalyzerConfig.objects.create(
            name="immobility-config",
            subject_group=self.subject_group,
            threshold_radius=100.0,
            threshold_time=600,
        )
        self.immobility_config.save()

        analyzer = ImmobilityAnalyzer(subject=self.subject, config=self.immobility_config)
        assert analyzer._is_within_feature_group_filter(_make_result_at(0, 0)) is True
        assert analyzer._is_within_feature_group_filter(_make_result_at(10, 10)) is True


class TestFeatureGroupFilter_Filter(TestFeatureGroupFilterBase):

    def setUp(self):
        super().setUp()

        self.config = ImmobilityAnalyzerConfig.objects.create(
            name="immobility-config",
            subject_group=self.subject_group,
            threshold_radius=1000.0,
            threshold_time=600,
            search_time_hours=1,
            feature_group_filter=self.spatial_feature_group,
        )

        self.analyzer = ImmobilityAnalyzer(subject=self.subject, config=self.config)

    def test_returns_true_when_inside_polygon(self):
        """Returns True when the result point falls inside a polygon in the filter group."""

        assert self.analyzer._is_within_feature_group_filter(_make_result_at(0, 0)) is True
        assert self.analyzer._is_within_feature_group_filter(_make_result_at(20, 20)) is False

    def test_event_created_when_detection_inside_filter_group(self):
        """analyze() creates an event when the detected location is within the filter group."""

        points = [Point(0, y / 1000.0) for y in range(0, 10, 1)]
        _create_observations(points, self.source, timezone.now())

        results = self.analyzer.analyze()
        assert len(results) == 1
        result, event = results[0]
        assert event is not None

    def test_event_suppressed_when_detection_outside_filter_group(self):
        """analyze() omits results when the detected location is outside the filter group."""

        points = [Point(20, y / 1000.0) for y in range(0, 10, 1)]
        _create_observations(points, self.source, timezone.now())

        results = self.analyzer.analyze()
        assert len(results) == 0
