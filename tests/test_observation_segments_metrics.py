import math

import pytest

from django.contrib.gis.geos import Point
from django.utils import timezone

from das.factories import SourceFactory, SubjectFactory, SubjectSourceFactory
from observations.models import Observation, ObservationSegment


@pytest.mark.django_db
def test_create_segment_computes_distance_and_speed():
    subject = SubjectFactory()
    source = SourceFactory()
    SubjectSourceFactory(subject=subject, source=source)

    t0 = timezone.now()
    t1 = t0 + timezone.timedelta(hours=1)

    start_obs = Observation.objects.create(
        source=source,
        location=Point(0.0, 0.0, srid=4326),
        recorded_at=t0,
    )
    end_obs = Observation.objects.create(
        source=source,
        location=Point(0.1, 0.0, srid=4326),  # ~11.1 km east at equator
        recorded_at=t1,
    )

    seg = ObservationSegment.objects.create_segment(start_obs, end_obs, subject)

    assert seg.distance_meters > 0
    # Speed should be roughly distance_km / 1 hour
    expected_speed_kmh = (seg.distance_meters / 1000.0) / 1.0
    assert math.isclose(seg.speed_kmh, expected_speed_kmh, rel_tol=1e-6)
    # time_gap_ms should be exactly 3600_000
    assert math.isclose(seg.time_gap_ms, 3600_000.0, rel_tol=1e-9)


@pytest.mark.django_db
def test_create_segment_zero_time_gap_sets_zero_speed():
    subject = SubjectFactory()
    source = SourceFactory()
    SubjectSourceFactory(subject=subject, source=source)

    t0 = timezone.now()
    start_obs = Observation.objects.create(
        source=source,
        location=Point(0.0, 0.0, srid=4326),
        recorded_at=t0,
    )
    # Same timestamp, different source to satisfy unique (tenant, source, recorded_at)
    other_source = SourceFactory(das_tenant=source.das_tenant)
    end_obs = Observation.objects.create(
        source=other_source,
        location=Point(0.0, 0.1, srid=4326),
        recorded_at=t0,  # same time
    )

    seg = ObservationSegment.objects.create_segment(start_obs, end_obs, subject)

    # Distance computed, but speed must be zero due to zero hours
    assert seg.distance_meters >= 0
    assert math.isclose(seg.time_gap_ms, 0.0, rel_tol=1e-9)
    assert math.isclose(seg.speed_kmh, 0.0, rel_tol=1e-9)
