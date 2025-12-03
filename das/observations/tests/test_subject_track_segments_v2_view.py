"""
Tests for SubjectTrackSegmentsV2View / SubjectTrackSegmentsGroupedSerializer

Focus: runtime segmentation thresholds (max_speed_kmh, max_gap_ms) and existing filters.
"""

from datetime import datetime, timedelta, timezone

import pytest

from django.contrib.gis.geos import Point
from rest_framework.test import APIRequestFactory

from core.models import DASTenant
from observations.models import (
    Observation,
    ObservationSegment,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectSubType,
    SubjectType,
)
from observations.serializers.segments import SubjectTrackSegmentsGroupedSerializer
from utils.migrations.columns import default_tenant_id


@pytest.mark.django_db
class TestSubjectTrackSegmentsGroupedSerializer:
    @pytest.fixture
    def setup_subject_with_segments(self, db):
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="buffalo", display="Buffalo", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Test Buffalo", subject_subtype=subject_subtype, das_tenant=tenant)
        factory = APIRequestFactory()
        request = factory.get("/")

        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_provider_grouped", display_name="Test Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="test_collar_grouped", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # Create 3 observations forming 2 contiguous segments
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.0, 0.0), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=15), location=Point(0.05, 0.0), das_tenant=tenant
        )
        obs3 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=30), location=Point(0.10, 0.0), das_tenant=tenant
        )

        seg1 = ObservationSegment.objects.create_segment(obs1, obs2, subject)
        seg2 = ObservationSegment.objects.create_segment(obs2, obs3, subject)

        # Sanity: segments are contiguous by observation IDs
        assert seg1.end_observation_id == seg2.start_observation_id

        return {
            "tenant": tenant,
            "subject": subject,
            "source": source,
            "obs": (obs1, obs2, obs3),
            "segments": (seg1, seg2),
            "base_time": base_time,
            "request": request,
        }

    def test_defaults_merge_contiguous(self, setup_subject_with_segments):
        subject = setup_subject_with_segments["subject"]
        serializer = SubjectTrackSegmentsGroupedSerializer(context={"request": setup_subject_with_segments["request"]})
        feature_collection = serializer.to_representation(subject)
        features = feature_collection.get("features", [])
        # Without thresholds, contiguous segments should merge into one LineString feature
        assert len(features) == 1
        props = features[0]["properties"]
        assert props["segment_count"] == 2

    def test_max_speed_kmh_breaks_group(self, setup_subject_with_segments):
        subject = setup_subject_with_segments["subject"]
        seg1, seg2 = setup_subject_with_segments["segments"]
        # Force a high speed on second segment to exceed threshold
        seg2.speed_kmh = seg2.speed_kmh + 9999
        seg2.save(update_fields=["speed_kmh"])

        serializer = SubjectTrackSegmentsGroupedSerializer(
            context={"max_speed_kmh": 100.0, "request": setup_subject_with_segments["request"]}
        )
        feature_collection = serializer.to_representation(subject)
        features = feature_collection.get("features", [])
        # Expect split into two features because seg2 exceeds max_speed_kmh
        assert len(features) == 2
        assert features[0]["properties"]["segment_count"] == 1
        assert features[1]["properties"]["segment_count"] == 1

    def test_max_gap_ms_breaks_group(self, setup_subject_with_segments):
        subject = setup_subject_with_segments["subject"]
        seg1, seg2 = setup_subject_with_segments["segments"]
        # Increase seg2 time gap beyond threshold
        seg2.time_gap_ms = 60 * 60 * 1000  # 1 hour in ms
        seg2.save(update_fields=["time_gap_ms"])

        serializer = SubjectTrackSegmentsGroupedSerializer(
            context={"max_gap_ms": 10 * 60 * 1000, "request": setup_subject_with_segments["request"]}
        )  # 10 minutes
        feature_collection = serializer.to_representation(subject)
        features = feature_collection.get("features", [])
        # Expect split into two features because seg2 time gap exceeds 10 minutes
        assert len(features) == 2
        assert features[0]["properties"]["segment_count"] == 1
        assert features[1]["properties"]["segment_count"] == 1

    def test_since_until_time_bounding(self, setup_subject_with_segments):
        subject = setup_subject_with_segments["subject"]
        base_time = setup_subject_with_segments["base_time"]

        # Bound to include only the second segment window
        since = base_time + timedelta(minutes=15)
        until = base_time + timedelta(minutes=30)
        serializer = SubjectTrackSegmentsGroupedSerializer(
            context={"since": since, "until": until, "request": setup_subject_with_segments["request"]}
        )
        feature_collection = serializer.to_representation(subject)
        features = feature_collection.get("features", [])
        # Only second segment should be present
        assert len(features) == 1
        assert features[0]["properties"]["segment_count"] == 1

    def test_group_by_flags_splits_on_change(self, setup_subject_with_segments):
        subject = setup_subject_with_segments["subject"]
        seg1, seg2 = setup_subject_with_segments["segments"]
        # Simulate flag change between segments
        # Assign integer masks directly to avoid BitHandler init issues
        seg1.exclusion_flags = 1
        seg2.exclusion_flags = 2
        seg1.save(update_fields=["exclusion_flags"])
        seg2.save(update_fields=["exclusion_flags"])

        serializer = SubjectTrackSegmentsGroupedSerializer(
            context={
                "group_by_flags": True,
                "show_excluded": True,
                "request": setup_subject_with_segments["request"],
            }
        )
        feature_collection = serializer.to_representation(subject)
        features = feature_collection.get("features", [])
        # Expect split into two features due to flag change
        assert len(features) == 2
        assert features[0]["properties"]["segment_count"] == 1
        assert features[1]["properties"]["segment_count"] == 1
