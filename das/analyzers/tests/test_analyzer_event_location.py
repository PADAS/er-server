from typing import List

import pytest

from django.contrib.gis.geos import MultiPoint, Point
from django.utils import timezone

from analyzers.models import (FeatureProximityAnalyzerConfig,
                              SubjectProximityAnalyzerConfig)
from analyzers.proximity import FeatureProximityAnalyzer
from analyzers.subject_proximity import SubjectProximityAnalyzer
from conftest import subject_group_without_permissions, subject_source
from mapping.models import SpatialFeature
from observations.models import Observation, SubjectSource
from utils.gis import convert_to_point

subject_source_2 = subject_source
subject_group_without_permissions_2 = subject_group_without_permissions


@pytest.mark.django_db
class TestAnalyzerEventLocation:
    def test_feature_proximity_analyzer_confirm_event_location(
        self,
        subject_source,
        spatial_feature_type,
        subject_group_without_permissions,
        spatial_feature_group_static,
    ):
        subject = subject_source.subject
        subject_group_without_permissions.subjects.add(subject)
        source = subject_source.source

        spatial_feature = SpatialFeature.objects.create(
            feature_type=spatial_feature_type,
            feature_geometry=MultiPoint(Point(-103, 20)),
        )
        spatial_feature_group_static.features.add(spatial_feature)

        FeatureProximityAnalyzerConfig.objects.create(
            name="Test feature proximity analyzer",
            subject_group=subject.groups.first(),
            threshold_dist_meters=150.0,
            is_active=True,
            proximal_features=spatial_feature_group_static,
        )

        locations = ["-103, 20.001155774646055", "-103, 20.001798483879462"]
        self._create_observations(locations, source, timezone.now())

        for analyzer in FeatureProximityAnalyzer.get_subject_analyzers(subject):
            result, event = analyzer.analyze()[0]
            assert event.location == convert_to_point(locations[0])

    def test_subject_proximity_analyzer_confirm_event_location(
            self,
            subject_source,
            subject_source_2,
            subject_group_without_permissions,
            subject_group_without_permissions_2,
    ):
        subject_1 = subject_source.subject
        subject_2 = subject_source_2.subject

        source_1 = subject_source.source
        source_2 = subject_source_2.source

        date_sub_1 = timezone.now()
        date_sub_2 = date_sub_1

        locations_sub_1 = [
            "-103.28294277191162, 20.67029657811917",
            "-103.28260615468025, 20.66972189063414",
        ]
        self._create_observations(locations_sub_1, source_1, date_sub_1)

        locations_sub_2 = [
            "-103.28276574611664, 20.6711548409691",
            "-103.28153729438782, 20.67181735634294",
        ]
        self._create_observations(locations_sub_2, source_2, date_sub_2)

        subject_group_without_permissions.subjects.add(subject_1)
        subject_group_without_permissions_2.subjects.add(subject_2)

        SubjectProximityAnalyzerConfig.objects.create(
            subject_group=subject_group_without_permissions,
            second_subject_group=subject_group_without_permissions_2,
            threshold_dist_meters=200,
        )

        for analyzer in SubjectProximityAnalyzer.get_subject_analyzers(subject_1):
            result, event = analyzer.analyze()[0]
            assert event.location == convert_to_point(locations_sub_1[0])

    def _create_observations(
        self, locations: List[str], source: SubjectSource, date: timezone.datetime
    ):
        # Locations list should be ordered from the newest to the oldest
        for count, location in enumerate(locations, 1):
            Observation.objects.create(
                location=convert_to_point(location),
                source=source,
                recorded_at=date - timezone.timedelta(minutes=count * 5),
            )
    # new comments
