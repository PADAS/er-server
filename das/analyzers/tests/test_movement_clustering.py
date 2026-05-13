"""Tests for the MovementClusterAnalyzer (ST-DBSCAN based)."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django_multitenant.utils import set_current_tenant

from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import TestCase

from activity.models import Event
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import SubjectAnalyzerResult
from analyzers.models.base import OK
from analyzers.models.movement_clustering import MovementClusterAnalyzerConfig
from analyzers.movement_clustering import (
    MAX_CLUSTER_POINTS_STORED,
    MOVEMENT_CLUSTER_EVENT_TYPE,
    MOVEMENT_CLUSTER_SCHEMA,
    MovementClusterAnalyzer,
    _st_dbscan,
)
from analyzers.movement_clustering_multi_subject import (
    MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE,
    MULTI_SUBJECT_MOVEMENT_CLUSTER_SCHEMA,
    MultiSubjectMovementClusterAnalyzer,
    _SubjectPoint,
)
from observations import models

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_LAT = 0.0  # equatorial, 1 degree ≈ 111 km
BASE_LON = 36.0


def _make_obs(lat, lon, recorded_at):
    """Unsaved Observation-like object (uses real Observation model instances)."""
    return models.Observation(
        recorded_at=recorded_at,
        location=Point(x=lon, y=lat),
        additional={},
    )


def _clustered_obs(center_lat, center_lon, count, start, interval_s, jitter=0.0005):
    """
    Return `count` observations within ~55 m of *center* (jitter ≈ 0.0005 deg ≈ 55 m).
    Timestamps run backwards from *start* in steps of *interval_s* seconds, so the
    most recent observation is at *start* and the oldest is at
    ``start - (count - 1) * interval_s``.
    """
    offsets = [
        (0.0, 0.0),
        (jitter, 0.0),
        (-jitter, 0.0),
        (0.0, jitter),
        (0.0, -jitter),
        (jitter, jitter),
        (-jitter, -jitter),
        (jitter, -jitter),
        (-jitter, jitter),
        (0.0, jitter * 2),
    ]
    observations = []
    for i in range(count):
        dlat, dlon = offsets[i % len(offsets)]
        t = start - timedelta(seconds=(count - 1 - i) * interval_s)
        observations.append(_make_obs(center_lat + dlat, center_lon + dlon, t))
    return observations


def _scattered_obs(count, start, interval_s):
    """
    Return *count* observations spread 1 degree (~111 km) apart — far outside
    any realistic spatial threshold.
    """
    observations = []
    for i in range(count):
        t = start + timedelta(seconds=i * interval_s)
        observations.append(_make_obs(BASE_LAT + i * 1.0, BASE_LON, t))
    return observations


# ---------------------------------------------------------------------------
# 1. Pure algorithm tests — no database required
# ---------------------------------------------------------------------------


class TestStDbscan:
    _T0 = 0  # epoch seconds reference

    # ---- helpers ----

    def _close_points(self, n, t_start=0, t_step=300):
        """n points at the same location, evenly spaced in time."""
        return [(BASE_LAT, BASE_LON, t_start + i * t_step) for i in range(n)]

    def _far_point(self, t=0):
        """One point 2 degrees away (≈222 km) — outside any spatial epsilon."""
        return (BASE_LAT + 2.0, BASE_LON, t)

    # ---- tests ----

    def test_empty_input_returns_empty(self):
        assert _st_dbscan([], 200, 3600, 3) == []

    def test_single_point_is_noise(self):
        pts = self._close_points(1)
        labels = _st_dbscan(pts, 200, 3600, 2)
        assert labels == [-1]

    def test_all_noise_when_below_min_points(self):
        pts = self._close_points(4)
        labels = _st_dbscan(pts, 200, 3600, 5)
        assert all(lbl == -1 for lbl in labels)

    def test_all_points_form_one_cluster(self):
        pts = self._close_points(6)
        labels = _st_dbscan(pts, 200, 3600, 3)
        assert all(lbl == 1 for lbl in labels)

    def test_two_spatial_clusters(self):
        # 5 points near origin, 5 points far away but close to each other
        pts_a = self._close_points(5, t_start=0, t_step=300)
        pts_b = [(BASE_LAT + 2.0, BASE_LON + 2.0, 300 * i) for i in range(5)]
        labels = _st_dbscan(pts_a + pts_b, 200, 3600, 3)
        labels_a = labels[:5]
        labels_b = labels[5:]
        # Each group should be its own cluster
        assert len(set(labels_a)) == 1
        assert len(set(labels_b)) == 1
        assert labels_a[0] != labels_b[0]
        assert labels_a[0] > 0
        assert labels_b[0] > 0

    def test_isolated_noise_point_among_cluster(self):
        pts = self._close_points(5)
        pts.append(self._far_point(t=0))
        labels = _st_dbscan(pts, 200, 3600, 3)
        assert labels[5] == -1
        assert all(lbl == 1 for lbl in labels[:5])

    def test_temporal_separation_prevents_single_cluster(self):
        # Two groups of points at the same spatial location but separated by
        # more than the temporal threshold.
        temporal_eps = 3600
        # Gap between groups: 2 * temporal_eps + 1 ensures no overlap
        gap = 2 * temporal_eps + 1
        pts_early = self._close_points(5, t_start=0, t_step=300)
        pts_late = self._close_points(5, t_start=gap, t_step=300)
        labels = _st_dbscan(pts_early + pts_late, 200, temporal_eps, 3)
        labels_early = set(labels[:5])
        labels_late = set(labels[5:])
        assert len(labels_early) == 1 and len(labels_late) == 1
        assert labels_early != labels_late

    def test_temporal_chain_merges_cluster(self):
        # Points spaced 30 min apart; adjacent pairs are within temporal_eps (1h),
        # so the full chain is a single cluster even though first and last are far apart.
        pts = self._close_points(8, t_start=0, t_step=1800)
        labels = _st_dbscan(pts, 200, 3600, 3)
        # All points should be in one cluster
        assert len(set(labels)) == 1
        assert labels[0] > 0

    def test_border_point_absorbed_from_noise(self):
        # A border point that would otherwise be noise is absorbed when a
        # neighbouring core point's cluster expands to include it.
        pts = self._close_points(4, t_start=0, t_step=300)
        # 5th point: spatially close but only has 1 neighbour on its own
        pts.append((BASE_LAT + 0.0004, BASE_LON, 0))
        labels = _st_dbscan(pts, 200, 3600, 3)
        # The border point should be assigned to the cluster, not noise
        assert labels[4] > 0

    def test_min_points_exactly_met(self):
        pts = self._close_points(3)
        labels = _st_dbscan(pts, 200, 3600, 3)
        assert all(lbl == 1 for lbl in labels)

    def test_cluster_labels_are_positive_integers(self):
        pts = self._close_points(5)
        labels = _st_dbscan(pts, 200, 3600, 3)
        for lbl in labels:
            assert isinstance(lbl, int)
            assert lbl >= -1


# ---------------------------------------------------------------------------
# 2. Analyzer-level tests — Django database required
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db
class TestMovementClusterAnalyzerTrajectory(TestCase):
    """
    Tests for MovementClusterAnalyzer.analyze_trajectory() and analyze().
    Observations are injected directly so no Source/SubjectSource is needed.
    """

    def setUp(self):
        set_current_tenant(self.das_tenant)
        self.subject = models.Subject.objects.create_subject(name="TestSubject")
        self.config = MovementClusterAnalyzerConfig(
            spatial_threshold_meters=200,
            temporal_threshold_seconds=3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
        )
        self.now = datetime.now(tz=timezone.utc)

    def _analyzer(self):
        return MovementClusterAnalyzer(subject=self.subject, config=self.config)

    # ------------------------------------------------------------------
    # Insufficient data
    # ------------------------------------------------------------------

    def test_too_few_observations_raises_insufficient_data(self):
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=2, start=self.now, interval_s=1800)
        ia = self._analyzer()
        with pytest.raises(InsufficientDataAnalyzerException):
            ia.analyze(observations=obs)

    # ------------------------------------------------------------------
    # No cluster → empty results
    # ------------------------------------------------------------------

    def test_scattered_observations_return_no_results(self):
        obs = _scattered_obs(count=8, start=self.now, interval_s=1800)
        ia = self._analyzer()
        results = ia.analyze(observations=obs)
        assert results == []

    # ------------------------------------------------------------------
    # Cluster present
    # ------------------------------------------------------------------

    def test_clustered_observations_return_results(self):
        # 8 points within 55 m, 30-min intervals → total span 3.5 h > 1 h threshold
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=8, start=self.now, interval_s=1800)
        ia = self._analyzer()
        results = ia.analyze(observations=obs)
        assert results

    def test_cluster_result_has_expected_values_keys(self):
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=8, start=self.now, interval_s=1800)
        ia = self._analyzer()
        results = ia.analyze(observations=obs)
        assert len(results) == 1, "Expected at least one cluster result"
        result, event = results[0]
        assert "cluster_point_count" in result.values
        assert "cluster_duration_hours" in result.values
        assert "cluster_radius_meters" in result.values
        assert "cluster_start_time" in result.values
        assert "cluster_end_time" in result.values
        assert "cluster_points" in result.values
        assert event.location is not None
        cluster_points = result.values["cluster_points"]
        assert isinstance(cluster_points, list)
        assert len(cluster_points) <= result.values["cluster_point_count"]
        for pt in cluster_points:
            assert "location" in pt
            assert "latitude" in pt["location"]
            assert "longitude" in pt["location"]
            assert "time" in pt

    def test_cluster_result_centroid_near_cluster_center(self):
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=6, start=self.now, interval_s=1800)
        ia = self._analyzer()
        results = ia.analyze(observations=obs)
        assert len(results) == 1
        result, event = results[0]
        assert abs(event.location.y - BASE_LAT) < 0.01
        assert abs(event.location.x - BASE_LON) < 0.01
        for pt in result.values["cluster_points"]:
            assert abs(pt["location"]["latitude"] - BASE_LAT) < 0.01
            assert abs(pt["location"]["longitude"] - BASE_LON) < 0.01

    def test_cluster_event_details_include_analyzer_name(self):
        sg = models.SubjectGroup.objects.create(name="cluster_analyzer_name_group")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(
            name="Mara Movement Cluster Analyzer",
            subject_group=sg,
            spatial_threshold_meters=200,
            temporal_threshold_seconds=3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
        )
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=8, start=self.now, interval_s=1800)
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        results = ia.analyze(observations=obs)
        assert len(results) == 1
        _, event = results[0]
        ed = event.event_details.all().first().data["event_details"]
        assert ed["analyzer_name"] == config.name

    # ------------------------------------------------------------------
    # Duration threshold
    # ------------------------------------------------------------------

    def test_cluster_below_duration_threshold_returns_no_results(self):
        # 5 points at 5-minute intervals → total span 20 min = 1200s < 3600s threshold
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=5, start=self.now, interval_s=300)
        ia = self._analyzer()
        results = ia.analyze(observations=obs)
        assert results == []

    # ------------------------------------------------------------------
    # Multiple clusters
    # ------------------------------------------------------------------

    def test_two_distinct_clusters_produce_two_results(self):
        # Cluster A: near origin
        obs_a = _clustered_obs(0.0, 36.0, count=6, start=self.now, interval_s=1800)
        # Cluster B: 5 degrees away, same time window
        obs_b = _clustered_obs(5.0, 36.0, count=6, start=self.now, interval_s=1800)
        obs = obs_a + obs_b
        ia = self._analyzer()
        results = ia.analyze(observations=obs)
        assert len(results) == 2

    # ------------------------------------------------------------------
    # Analyzer discovery
    # ------------------------------------------------------------------

    def test_get_subject_analyzers_finds_analyzer_for_group_member(self):
        sg = models.SubjectGroup.objects.create(name="cluster_test_group")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        analyzers = list(MovementClusterAnalyzer.get_subject_analyzers(self.subject))
        assert any(a.config.pk == config.pk for a in analyzers)

    def test_get_subject_analyzers_empty_for_non_member(self):
        sg = models.SubjectGroup.objects.create(name="cluster_test_group_2")
        MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        # subject is NOT in sg
        analyzers = list(MovementClusterAnalyzer.get_subject_analyzers(self.subject))
        assert analyzers == []

    def test_get_subject_analyzers_excludes_inactive_config(self):
        sg = models.SubjectGroup.objects.create(name="cluster_test_inactive_group")
        sg.subjects.add(self.subject)
        sg.save()
        MovementClusterAnalyzerConfig.objects.create(subject_group=sg, is_active=False)
        analyzers = list(MovementClusterAnalyzer.get_subject_analyzers(self.subject))
        assert analyzers == []

    # ------------------------------------------------------------------
    # save_analyzer_result
    # ------------------------------------------------------------------

    def test_save_cluster_result_persists_to_db(self):
        sg = models.SubjectGroup.objects.create(name="cluster_save_test_group")
        sg.subjects.add(self.subject)
        sg.save()
        saved_config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        ia = MovementClusterAnalyzer(subject=self.subject, config=saved_config)

        result = SubjectAnalyzerResult(
            subject_analyzer=saved_config,
            subject=self.subject,
            level=OK,
            title="cluster detected",
            message="cluster detected",
            analyzer_revision=1,
            estimated_time=self.now,
            geometry_collection=None,
        )
        from django.contrib.gis.geos import GeometryCollection, Point

        result.geometry_collection = GeometryCollection(Point(BASE_LON, BASE_LAT))
        result.values = {}

        before = SubjectAnalyzerResult.objects.filter(subject=self.subject).count()
        ia.save_analyzer_result(last_result=None, this_result=result)
        after = SubjectAnalyzerResult.objects.filter(subject=self.subject).count()
        assert after == before + 1

    # ------------------------------------------------------------------
    # create_analyzer_event
    # ------------------------------------------------------------------

    def test_create_analyzer_event_returns_none_for_none_result(self):
        sg = models.SubjectGroup.objects.create(name="cluster_event_none_group")
        sg.subjects.add(self.subject)
        sg.save()
        saved_config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        ia = MovementClusterAnalyzer(subject=self.subject, config=saved_config)
        event = ia.create_analyzer_event(last_result=None, this_result=None)
        assert event is None

    # ------------------------------------------------------------------
    # Event type bootstrap
    # ------------------------------------------------------------------

    def test_ensure_event_type_creates_event_type_on_first_call(self):
        from activity.models import EventType

        sg = models.SubjectGroup.objects.create(name="ensure_et_group")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)

        assert not EventType.objects.filter(value=MOVEMENT_CLUSTER_EVENT_TYPE).exists()
        ia._ensure_event_type()
        assert EventType.objects.filter(value=MOVEMENT_CLUSTER_EVENT_TYPE).exists()

    def test_ensure_event_type_is_idempotent(self):
        from activity.models import EventType

        sg = models.SubjectGroup.objects.create(name="ensure_et_idempotent_group")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)

        ia._ensure_event_type()
        ia._ensure_event_type()  # second call must not raise or duplicate
        assert EventType.objects.filter(value=MOVEMENT_CLUSTER_EVENT_TYPE).count() == 1

    def test_ensure_event_type_stores_schema(self):
        from activity.models import EventType

        sg = models.SubjectGroup.objects.create(name="ensure_et_schema_group")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)

        ia._ensure_event_type()
        et = EventType.objects.get(value=MOVEMENT_CLUSTER_EVENT_TYPE)
        stored = json.loads(et.schema)
        assert stored == MOVEMENT_CLUSTER_SCHEMA

    def test_ensure_event_type_uses_analyzer_event_category(self):
        from activity.models import EventType

        sg = models.SubjectGroup.objects.create(name="ensure_et_category_group")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)

        ia._ensure_event_type()
        et = EventType.objects.get(value=MOVEMENT_CLUSTER_EVENT_TYPE)
        assert et.category.value == "analyzer_event"

    # ------------------------------------------------------------------
    # Open-cluster deduplication
    # ------------------------------------------------------------------

    def _make_saved_config(self, group_name):
        sg = models.SubjectGroup.objects.create(name=group_name)
        sg.subjects.add(self.subject)
        sg.save()
        return MovementClusterAnalyzerConfig.objects.create(
            name=group_name,
            subject_group=sg,
            spatial_threshold_meters=200,
            temporal_threshold_seconds=3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
        )

    def _make_cluster_points(self, lat, lon, count=5, start_time=None):
        """Return a list of cluster_points dicts (same format as stored in result.values)."""
        start = start_time or self.now
        return [
            {
                "location": {
                    "latitude": round(lat, 7),
                    "longitude": round(lon, 7),
                },
                "time": (start + timedelta(seconds=i * 1800)).isoformat(),
            }
            for i in range(count)
        ]

    def _save_cluster_result(self, config, cluster_points, end_time):
        from django.contrib.gis.geos import GeometryCollection, Point

        from analyzers.movement_clustering import save_analyzer_event

        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        ia._ensure_event_type()

        lats = [p["location"]["latitude"] for p in cluster_points]
        lons = [p["location"]["longitude"] for p in cluster_points]
        centroid_lat = sum(lats) / len(lats)
        centroid_lon = sum(lons) / len(lons)

        event_data = dict(
            title="Cluster detected",
            state=Event.SC_ACTIVE,
            time=end_time,
            provenance=Event.PC_ANALYZER,
            event_type=MOVEMENT_CLUSTER_EVENT_TYPE,
            location={"longitude": centroid_lon, "latitude": centroid_lat},
            related_subjects=[{"id": self.subject.id}],
        )

        event = save_analyzer_event(event_data)

        result = SubjectAnalyzerResult(
            subject_analyzer=config,
            subject=self.subject,
            level=OK,
            title="cluster detected",
            message="cluster detected",
            analyzer_revision=1,
            estimated_time=end_time,
            geometry_collection=GeometryCollection(Point(centroid_lon, centroid_lat)),
            values={
                "cluster_radius_meters": 0.0,
                "cluster_end_time": end_time.isoformat(),
                "cluster_start_time": end_time.isoformat(),
                "cluster_point_count": len(cluster_points),
                "cluster_duration_hours": 2.0,
                "cluster_points": cluster_points,
            },
            event=event,
        )
        result.save()
        return result

    def test_find_open_clusters_returns_result_when_all_points_subset(self):
        config = self._make_saved_config("find_open_subset_group")
        recent_end = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        existing_points = self._make_cluster_points(BASE_LAT, BASE_LON, count=3)
        self._save_cluster_result(config, existing_points, recent_end)

        # New cluster is a superset of the existing points
        extra_points = self._make_cluster_points(
            BASE_LAT + 0.0001,
            BASE_LON,
            count=2,
            start_time=self.now + timedelta(hours=1),
        )
        new_point_set = frozenset(
            (p["location"]["latitude"], p["location"]["longitude"], p["time"], p.get("subject_id"))
            for p in existing_points + extra_points
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert ia._find_open_clusters(new_point_set)

    def test_find_open_clusters_returns_empty_when_not_all_points_subset(self):
        config = self._make_saved_config("find_open_not_subset_group")
        recent_end = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        existing_points = self._make_cluster_points(BASE_LAT, BASE_LON, count=5)
        self._save_cluster_result(config, existing_points, recent_end)

        # Completely different points — not a superset of existing
        different_points = self._make_cluster_points(BASE_LAT + 5.0, BASE_LON, count=5)
        diff_point_set = frozenset(
            (p["location"]["latitude"], p["location"]["longitude"], p["time"], p.get("subject_id"))
            for p in different_points
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert not ia._find_open_clusters(diff_point_set)

    def test_find_open_clusters_returns_empty_when_result_has_expired(self):
        config = self._make_saved_config("find_open_expired_group")
        # Result is 2 hours old — beyond the 1-hour temporal threshold
        old_end = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        existing_points = self._make_cluster_points(BASE_LAT, BASE_LON, count=3)
        self._save_cluster_result(config, existing_points, old_end)

        existing_set = frozenset(
            (p["location"]["latitude"], p["location"]["longitude"], p["time"], p.get("subject_id"))
            for p in existing_points
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert not ia._find_open_clusters(existing_set)

    def test_find_open_clusters_matches_when_old_points_aged_out(self):
        """A stored result whose old points have aged out of search_time_hours still
        matches if its within-window points are a subset of the new cluster."""
        config = self._make_saved_config("find_open_aged_out_group")
        recent_end = datetime.now(timezone.utc) - timedelta(minutes=30)

        # Two points recorded within the search window (< 24 h ago)
        recent_points = self._make_cluster_points(BASE_LAT, BASE_LON, count=2)
        # One point recorded 25 hours ago — outside the 24-hour search window
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        aged_out_point = {
            "location": {"latitude": round(BASE_LAT, 7), "longitude": round(BASE_LON, 7)},
            "time": old_time.isoformat(),
        }
        all_stored_points = recent_points + [aged_out_point]
        self._save_cluster_result(config, all_stored_points, recent_end)

        # The new cluster contains only the recent points (aged-out point not present)
        new_point_set = frozenset(
            (p["location"]["latitude"], p["location"]["longitude"], p["time"], p.get("subject_id"))
            for p in recent_points
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert ia._find_open_clusters(new_point_set)

    def test_find_open_clusters_returns_empty_when_all_points_aged_out(self):
        """A stored result whose every point has aged out of search_time_hours does
        not produce a spurious match via an empty-subset comparison."""
        config = self._make_saved_config("find_open_all_aged_group")
        recent_end = datetime.now(timezone.utc) - timedelta(minutes=30)

        # All points recorded more than 24 hours ago
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        aged_out_points = [
            {
                "location": {"latitude": round(BASE_LAT, 7), "longitude": round(BASE_LON, 7)},
                "time": (old_time + timedelta(seconds=i * 1800)).isoformat(),
            }
            for i in range(3)
        ]
        self._save_cluster_result(config, aged_out_points, recent_end)

        new_point_set = frozenset(
            (p["location"]["latitude"], p["location"]["longitude"], p["time"], p.get("subject_id"))
            for p in self._make_cluster_points(BASE_LAT, BASE_LON, count=3)
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert not ia._find_open_clusters(new_point_set)

    def test_find_open_clusters_returns_empty_for_unsaved_config(self):
        unsaved_config = MovementClusterAnalyzerConfig(
            spatial_threshold_meters=200,
            temporal_threshold_seconds=3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=unsaved_config)
        assert not ia._find_open_clusters(frozenset())

    def test_find_open_clusters_returns_empty_when_no_cluster_points_stored(self):
        config = self._make_saved_config("find_open_no_points_group")
        recent_end = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        # Old-style result without cluster_points key
        from django.contrib.gis.geos import GeometryCollection, Point

        result = SubjectAnalyzerResult(
            subject_analyzer=config,
            subject=self.subject,
            level=OK,
            title="cluster detected",
            message="cluster detected",
            analyzer_revision=1,
            estimated_time=recent_end,
            geometry_collection=GeometryCollection(Point(BASE_LON, BASE_LAT)),
            values={
                "cluster_radius_meters": 0.0,
                "cluster_end_time": recent_end.isoformat(),
                "cluster_start_time": recent_end.isoformat(),
                "cluster_point_count": 5,
                "cluster_duration_hours": 2.0,
            },
        )
        result.save()

        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert not ia._find_open_clusters(frozenset([("0.0", "36.0", "2024-01-01", None)]))

    def test_analyze_updates_existing_cluster_instead_of_creating_new(self):
        config = self._make_saved_config("update_cluster_group")
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=8, start=self.now, interval_s=1800)

        # First run: creates a new cluster result and fires an event
        ia1 = MovementClusterAnalyzer(subject=self.subject, config=config)
        ia1.analyze(observations=obs)

        results = SubjectAnalyzerResult.objects.filter(subject=self.subject)
        assert len(results) == 1, f"Expected 1 cluster Analyzer result, got {len(results)}"

        # Second run with the same observations: should update the existing result
        ia2 = MovementClusterAnalyzer(subject=self.subject, config=config)
        ia2.analyze(observations=obs)

        # Still only one result row in the DB (updated, not inserted)
        total = SubjectAnalyzerResult.objects.filter(subject=self.subject).count()
        assert total == 1

        # Third run: add one point within the 200 m spatial threshold and one outside.
        # 0.001 deg lat ≈ 111 m — within the 200 m threshold
        near_obs = _make_obs(BASE_LAT + 0.001, BASE_LON, self.now)
        # 0.1 deg lat ≈ 11.1 km — outside the 200 m threshold
        far_obs = _make_obs(BASE_LAT + 0.1, BASE_LON, self.now)

        ia3 = MovementClusterAnalyzer(subject=self.subject, config=config)
        ia3.analyze(observations=obs + [near_obs, far_obs])

        # Still only one cluster result in the DB
        total = SubjectAnalyzerResult.objects.filter(subject=self.subject, subject_analyzer_id=config.pk).count()
        assert total == 1

        # The updated cluster should contain the near point but not the far point
        updated = SubjectAnalyzerResult.objects.get(subject=self.subject, subject_analyzer_id=config.pk)
        stored_lats = {p["location"]["latitude"] for p in updated.values["cluster_points"]}
        assert round(BASE_LAT + 0.001, 7) in stored_lats
        assert round(BASE_LAT + 0.1, 7) not in stored_lats

        # Fourth run: add a point that is within the 200 m spatial threshold but
        # 3601 s beyond the most recent cluster point — outside the 3600 s temporal
        # threshold.  It must not be absorbed into the existing cluster.
        # 0.0008 deg lat ≈ 89 m — within 200 m, but its unique lat makes it
        # distinguishable from near_obs in the stored cluster_points.
        temporally_far_obs = _make_obs(BASE_LAT + 0.0008, BASE_LON, self.now + timedelta(seconds=3601))

        ia4 = MovementClusterAnalyzer(subject=self.subject, config=config)
        ia4.analyze(observations=obs + [near_obs, far_obs, temporally_far_obs])

        # Still only one cluster result in the DB
        total = SubjectAnalyzerResult.objects.filter(subject=self.subject, subject_analyzer_id=config.pk).count()
        assert total == 1

        # The temporally-excluded point should not appear in the cluster
        updated = SubjectAnalyzerResult.objects.get(subject=self.subject, subject_analyzer_id=config.pk)
        stored_lats = {p["location"]["latitude"] for p in updated.values["cluster_points"]}
        assert round(BASE_LAT + 0.0008, 7) not in stored_lats

    def test_analyze_creates_new_result_for_distinct_cluster(self):
        config = self._make_saved_config("distinct_cluster_group")
        recent_end = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        # Existing open cluster has points at a different location with different times
        existing_points = self._make_cluster_points(BASE_LAT + 5.0, BASE_LON, count=3)
        self._save_cluster_result(config, existing_points, recent_end)

        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=8, start=self.now, interval_s=1800)
        results = ia.analyze(observations=obs)
        assert results

    def test_two_spatially_distinct_temporally_overlapping_clusters(self):
        """Two clusters at different spatial locations whose observation windows
        fully overlap in time are detected as separate results, and a second
        analyzer run updates both in place without creating new records or
        firing new events.
        """
        # Both clusters span the same time window — 100 % temporal overlap.
        # They are 5 degrees apart spatially (~555 km), well beyond the 200 m threshold.
        obs_a = _clustered_obs(BASE_LAT, BASE_LON, count=6, start=self.now, interval_s=1800)
        obs_b = _clustered_obs(BASE_LAT + 5.0, BASE_LON, count=6, start=self.now, interval_s=1800)

        config = self._make_saved_config("spatial_temporal_overlap_group")

        # First run: both clusters detected as separate results
        ia1 = MovementClusterAnalyzer(subject=self.subject, config=config)
        results_1 = ia1.analyze(observations=obs_a + obs_b)

        assert len(results_1) == 2

        lats = sorted(r[0].event.location.y for r in results_1)
        assert abs(lats[0] - BASE_LAT) < 0.01
        assert abs(lats[1] - (BASE_LAT + 5.0)) < 0.01

        # Second run: both clusters updated in place — no new DB rows, no new events
        ia2 = MovementClusterAnalyzer(subject=self.subject, config=config)
        ia2.analyze(observations=obs_a + obs_b)

        total = SubjectAnalyzerResult.objects.filter(subject=self.subject, subject_analyzer_id=config.pk).count()
        assert total == 2

        # Third run: use two clusters that are ~333 m apart (just outside the 200 m
        # spatial threshold) so that a single bridge observation at their midpoint
        # (~167 m from each centre) causes them to merge into one cluster.
        #
        # A new config is used so the existing two results (obs_a/obs_b at 5 degrees
        # apart) do not interfere with the deduplication lookup.
        bridge_config = self._make_saved_config("bridge_merge_group")

        # 0.003 degrees latitude ≈ 333 m — separate without bridge
        close_obs_a = _clustered_obs(BASE_LAT, BASE_LON, count=6, start=self.now, interval_s=1800)
        close_obs_b = _clustered_obs(BASE_LAT + 0.003, BASE_LON, count=6, start=self.now, interval_s=1800)

        ia_pre = MovementClusterAnalyzer(subject=self.subject, config=bridge_config)
        pre_results = ia_pre.analyze(observations=close_obs_a + close_obs_b)
        assert len(pre_results) == 2

        # Each pre-merge result must have a linked event.
        pre_event_ids = []
        for r in pre_results:
            assert r[0].event.id is not None, "Pre-merge result should have a linked event"
            pre_event_ids.append(r[0].event.id)

        # Bridge observation at the midpoint: ~167 m from each cluster centre,
        # within the 200 m threshold and within temporal threshold of all obs.
        bridge_obs = _make_obs(BASE_LAT + 0.0015, BASE_LON, self.now)

        ia_merge = MovementClusterAnalyzer(subject=self.subject, config=bridge_config)
        merge_results = ia_merge.analyze(observations=close_obs_a + close_obs_b + [bridge_obs])

        assert len(merge_results) == 1
        merged_result = merge_results[0][0]

        # The single merged cluster must contain points from both original clusters.
        stored_lats = {p["location"]["latitude"] for p in merged_result.values["cluster_points"]}
        assert any(abs(lat - BASE_LAT) < 0.001 for lat in stored_lats)
        assert any(abs(lat - (BASE_LAT + 0.003)) < 0.001 for lat in stored_lats)

        # Both pre-merge events must have been resolved.
        resolved_states = list(Event.objects.filter(id__in=pre_event_ids).values_list("state", flat=True))
        assert all(
            s == Event.SC_RESOLVED for s in resolved_states
        ), f"Expected all pre-merge events resolved, got states: {resolved_states}"

        # The merged result must have its own new event (not one of the old ones).
        assert merged_result.event_id is not None, "Merged result should have a linked event"
        assert (
            merged_result.event_id not in pre_event_ids
        ), "Merged result should have a new event, not reuse a pre-merge event"


# ---------------------------------------------------------------------------
# 3. Multi-subject cluster tests
# ---------------------------------------------------------------------------


def _make_subject_points(subject_id, subject_name, center_lat, center_lon, count, start, interval_s, jitter=0.0005):
    """Return _SubjectPoint instances clustered around center, like _clustered_obs but tagged with subject."""
    offsets = [
        (0.0, 0.0),
        (jitter, 0.0),
        (-jitter, 0.0),
        (0.0, jitter),
        (0.0, -jitter),
        (jitter, jitter),
        (-jitter, -jitter),
        (jitter, -jitter),
        (-jitter, jitter),
        (0.0, jitter * 2),
    ]
    points = []
    for i in range(count):
        dlat, dlon = offsets[i % len(offsets)]
        t = start - timedelta(seconds=(count - 1 - i) * interval_s)
        points.append(
            _SubjectPoint(
                lat=center_lat + dlat,
                lon=center_lon + dlon,
                recorded_at=t,
                subject_id=subject_id,
                subject_name=subject_name,
            )
        )
    return points


class TestBuildMultiSubjectClusterResults:
    """Tests for MultiSubjectMovementClusterAnalyzer._build_cluster_results.

    These tests currently rely on Django DB-backed subject creation and tenant
    fixtures for setup, even though the clustering inputs themselves are built
    in memory.
    """

    _now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    def _unsaved_config(self, min_subjects=2):
        return MovementClusterAnalyzerConfig(
            spatial_threshold_meters=200,
            temporal_threshold_seconds=3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
            min_subjects_in_cluster=min_subjects,
        )

    def _analyzer(self, subject, min_subjects=2):
        return MultiSubjectMovementClusterAnalyzer(subject=subject, config=self._unsaved_config(min_subjects))

    def _labeled_points(self, subject_id_a, subject_id_b, label_a=1, label_b=1):
        """Six points from two subjects at the same location, labeled as one cluster."""
        pts_a = _make_subject_points(subject_id_a, "SubjectA", BASE_LAT, BASE_LON, 3, self._now, 1800)
        pts_b = _make_subject_points(subject_id_b, "SubjectB", BASE_LAT, BASE_LON, 3, self._now, 1800)
        all_points = pts_a + pts_b
        labels = [label_a] * 3 + [label_b] * 3
        return all_points, labels

    @pytest.mark.django_db
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_cluster_with_enough_subjects_is_kept(self, das_tenant_monkeypatch):
        from django_multitenant.utils import set_current_tenant

        set_current_tenant(das_tenant_monkeypatch)
        subject = models.Subject.objects.create_subject(name="MSC_kept")
        ia = self._analyzer(subject, min_subjects=2)

        sid_a = subject.id
        sid_b = uuid.uuid4()
        all_points, labels = self._labeled_points(sid_a, sid_b)

        results = ia._build_cluster_results(all_points, labels)
        assert len(results) == 1

    @pytest.mark.django_db
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_cluster_with_too_few_subjects_is_discarded(self, das_tenant_monkeypatch):
        from django_multitenant.utils import set_current_tenant

        set_current_tenant(das_tenant_monkeypatch)
        subject = models.Subject.objects.create_subject(name="MSC_discarded")
        ia = self._analyzer(subject, min_subjects=2)

        sid_a = subject.id
        # All points from the same subject → only 1 distinct subject
        all_points = _make_subject_points(sid_a, "SubjectA", BASE_LAT, BASE_LON, 6, self._now, 1800)
        labels = [1] * 6

        results = ia._build_cluster_results(all_points, labels)
        assert results == []

    @pytest.mark.django_db
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_cluster_values_include_subjects_in_cluster(self, das_tenant_monkeypatch):
        from django_multitenant.utils import set_current_tenant

        set_current_tenant(das_tenant_monkeypatch)
        subject = models.Subject.objects.create_subject(name="MSC_values")
        ia = self._analyzer(subject, min_subjects=2)

        sid_a = subject.id
        sid_b = uuid.uuid4()
        all_points, labels = self._labeled_points(sid_a, sid_b)

        results = ia._build_cluster_results(all_points, labels)
        assert len(results) == 1
        values = results[0].values
        assert values["subjects_in_cluster"] == 2
        assert len(values["subject_ids_in_cluster"]) == 2
        assert str(sid_a) in values["subject_ids_in_cluster"]
        assert str(sid_b) in values["subject_ids_in_cluster"]

    @pytest.mark.django_db
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_cluster_points_include_subject_identity(self, das_tenant_monkeypatch):
        from django_multitenant.utils import set_current_tenant

        set_current_tenant(das_tenant_monkeypatch)
        subject = models.Subject.objects.create_subject(name="MSC_identity")
        ia = self._analyzer(subject, min_subjects=2)

        sid_a = subject.id
        sid_b = uuid.uuid4()
        all_points, labels = self._labeled_points(sid_a, sid_b)

        results = ia._build_cluster_results(all_points, labels)
        cluster_points = results[0].values["cluster_points"]
        subject_ids_in_points = {pt["subject_id"] for pt in cluster_points}
        assert str(sid_a) in subject_ids_in_points
        assert str(sid_b) in subject_ids_in_points

    @pytest.mark.django_db
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_cluster_below_duration_threshold_is_discarded(self, das_tenant_monkeypatch):
        from django_multitenant.utils import set_current_tenant

        set_current_tenant(das_tenant_monkeypatch)
        subject = models.Subject.objects.create_subject(name="MSC_duration")
        ia = self._analyzer(subject, min_subjects=2)

        sid_a = subject.id
        sid_b = uuid.uuid4()
        # 3 points each at 5-minute intervals → total span 10 min < 1 h threshold
        pts_a = _make_subject_points(sid_a, "SubjectA", BASE_LAT, BASE_LON, 3, self._now, 300)
        pts_b = _make_subject_points(sid_b, "SubjectB", BASE_LAT, BASE_LON, 3, self._now, 300)
        all_points = pts_a + pts_b
        labels = [1] * 6

        results = ia._build_cluster_results(all_points, labels)
        assert results == []

    @pytest.mark.django_db
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    def test_noise_points_are_excluded(self, das_tenant_monkeypatch):
        from django_multitenant.utils import set_current_tenant

        set_current_tenant(das_tenant_monkeypatch)
        subject = models.Subject.objects.create_subject(name="MSC_noise")
        ia = self._analyzer(subject, min_subjects=2)

        sid_a = subject.id
        sid_b = uuid.uuid4()
        # First 3 labelled as cluster 1, last 3 labelled as noise (-1)
        pts_a = _make_subject_points(sid_a, "SubjectA", BASE_LAT, BASE_LON, 3, self._now, 1800)
        pts_b = _make_subject_points(sid_b, "SubjectB", BASE_LAT, BASE_LON, 3, self._now, 1800)
        all_points = pts_a + pts_b
        labels = [1, 1, 1, -1, -1, -1]  # pts_b are noise

        # Cluster 1 has only pts_a (1 subject) → below min_subjects=2
        results = ia._build_cluster_results(all_points, labels)
        assert results == []


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db
class TestMultiSubjectAnalyzeRouting(TestCase):
    """Integration tests for MultiSubjectMovementClusterAnalyzer.analyze()."""

    def setUp(self):
        set_current_tenant(self.das_tenant)
        self.subject = models.Subject.objects.create_subject(name="MSC_route_subject")
        self.now = datetime.now(tz=timezone.utc)

    def _make_saved_config(self, group_name, min_subjects=2):
        sg = models.SubjectGroup.objects.create(name=group_name)
        sg.subjects.add(self.subject)
        sg.save()
        return MovementClusterAnalyzerConfig.objects.create(
            name=group_name,
            subject_group=sg,
            spatial_threshold_meters=200,
            temporal_threshold_seconds=3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
            min_subjects_in_cluster=min_subjects,
        )

    def _subject_points_two_subjects(self, center_lat=BASE_LAT, center_lon=BASE_LON):
        """Points from self.subject and a freshly created second subject, clustered together."""
        subject2 = models.Subject.objects.create_subject(name=f"MSC_second_{uuid.uuid4().hex[:8]}")
        pts_a = _make_subject_points(self.subject.id, self.subject.name, center_lat, center_lon, 6, self.now, 1800)
        pts_b = _make_subject_points(subject2.id, subject2.name, center_lat, center_lon, 6, self.now, 1800)
        return pts_a + pts_b

    def test_min_subjects_defaults_to_1(self):
        sg = models.SubjectGroup.objects.create(name="msc_default_sg")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg)
        assert config.min_subjects_in_cluster == 1

    def test_single_subject_path_used_when_min_subjects_is_1(self):
        """When min_subjects_in_cluster=1, analyze() uses the single-subject trajectory path."""
        config = MovementClusterAnalyzerConfig(
            spatial_threshold_meters=200,
            temporal_threshold_seconds=3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
            min_subjects_in_cluster=1,
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=8, start=self.now, interval_s=1800)
        # Observations passed directly — only works via the single-subject path
        results = ia.analyze(observations=obs)
        assert results

    def test_multi_subject_cluster_fires_when_enough_subjects(self):
        config = self._make_saved_config("msc_fires_group")
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        points = self._subject_points_two_subjects()
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze()

        assert len(results) == 1
        result, event = results[0]
        assert result.values["subjects_in_cluster"] == 2
        assert event is not None

    def test_multi_subject_cluster_silent_when_too_few_subjects(self):
        config = self._make_saved_config("msc_silent_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        # All points from one subject only
        points = _make_subject_points(self.subject.id, self.subject.name, BASE_LAT, BASE_LON, 8, self.now, 1800)
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze()

        assert results == []

    def test_analyze_raises_insufficient_data_when_too_few_points(self):
        config = self._make_saved_config("msc_insufficient_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        # Only 2 points — below min_cluster_points=3
        points = _make_subject_points(self.subject.id, self.subject.name, BASE_LAT, BASE_LON, 2, self.now, 1800)
        with patch.object(ia, "_collect_group_points", return_value=points):
            with pytest.raises(InsufficientDataAnalyzerException):
                ia.analyze()

    def test_multi_subject_cluster_two_spatial_locations_only_overlapping_fires(self):
        """Two spatial clusters: one shared by both subjects, one containing only one subject."""
        config = self._make_saved_config("msc_two_locs_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        subject2 = models.Subject.objects.create_subject(name="MSC_two_locs_subject2")
        # Cluster A — both subjects present (≈5 degrees apart from cluster B)
        pts_a_subj1 = _make_subject_points(self.subject.id, self.subject.name, BASE_LAT, BASE_LON, 6, self.now, 1800)
        pts_a_subj2 = _make_subject_points(subject2.id, subject2.name, BASE_LAT, BASE_LON, 6, self.now, 1800)
        # Cluster B — only self.subject is present (5 degrees away)
        pts_b_subj1 = _make_subject_points(
            self.subject.id, self.subject.name, BASE_LAT + 5.0, BASE_LON, 6, self.now, 1800
        )

        points = pts_a_subj1 + pts_a_subj2 + pts_b_subj1
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze()

        # Only cluster A (both subjects) should fire
        assert len(results) == 1
        result, _ = results[0]
        assert result.values["subjects_in_cluster"] == 2

    # ------------------------------------------------------------------
    # Multi-subject event type bootstrap
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Quiet-period / silent-period
    # ------------------------------------------------------------------

    def test_quiet_period_cache_is_set_after_multi_subject_cluster_fires(self):
        """When a multi-subject cluster produces an event and analyzer_key is supplied,
        the quiet-period cache entry must be written so the task loop can skip
        subsequent runs within the quiet window."""
        from datetime import timedelta as td

        config = self._make_saved_config("msc_quiet_group", min_subjects=2)
        config.quiet_period = td(hours=1)
        config.save()

        analyzer_key = f"analyzer_silent__{config.id}__{self.subject.id}"
        cache.delete(analyzer_key)

        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)
        points = self._subject_points_two_subjects()
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze(analyzer_key=analyzer_key)

        assert len(results) == 1
        assert cache.get(analyzer_key) is not None, "quiet-period cache entry should be set after a cluster event fires"

    def test_quiet_period_cache_not_set_when_no_cluster_qualifies(self):
        """When no qualifying cluster is found (e.g. too few subjects), the
        quiet-period cache must remain unset so the next run is not skipped."""
        from datetime import timedelta as td

        config = self._make_saved_config("msc_quiet_no_event_group", min_subjects=2)
        config.quiet_period = td(hours=1)
        config.save()

        analyzer_key = f"analyzer_silent__{config.id}__{self.subject.id}"
        cache.delete(analyzer_key)

        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)
        # All points belong to a single subject — cluster won't meet min_subjects=2
        single_subject_points = _make_subject_points(
            self.subject.id, self.subject.name, BASE_LAT, BASE_LON, 8, self.now, 1800
        )
        with patch.object(ia, "_collect_group_points", return_value=single_subject_points):
            results = ia.analyze(analyzer_key=analyzer_key)

        assert results == []
        assert cache.get(analyzer_key) is None, "quiet-period cache must not be set when no event fires"

    # ------------------------------------------------------------------
    # Multi-subject event type bootstrap
    # ------------------------------------------------------------------

    def test_ensure_event_type_creates_multi_subject_type_when_configured(self):
        from activity.models import EventType

        config = self._make_saved_config("msc_et_create_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        assert not EventType.objects.filter(value=MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE).exists()
        ia._ensure_event_type()
        assert EventType.objects.filter(value=MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE).exists()

    def test_ensure_event_type_stores_multi_subject_schema(self):
        from activity.models import EventType

        config = self._make_saved_config("msc_et_schema_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        ia._ensure_event_type()
        et = EventType.objects.get(value=MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE)
        assert json.loads(et.schema) == MULTI_SUBJECT_MOVEMENT_CLUSTER_SCHEMA

    def test_ensure_event_type_single_subject_type_unchanged(self):
        """min_subjects_in_cluster=1 still creates the original movement_cluster event type."""
        from activity.models import EventType

        sg = models.SubjectGroup.objects.create(name="msc_et_single_group")
        sg.subjects.add(self.subject)
        sg.save()
        config = MovementClusterAnalyzerConfig.objects.create(subject_group=sg, min_subjects_in_cluster=1)
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)

        ia._ensure_event_type()
        assert EventType.objects.filter(value=MOVEMENT_CLUSTER_EVENT_TYPE).exists()
        assert not EventType.objects.filter(value=MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE).exists()

    # ------------------------------------------------------------------
    # Multi-subject event details
    # ------------------------------------------------------------------

    def test_multi_subject_event_uses_multi_subject_event_type(self):
        config = self._make_saved_config("msc_ev_type_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        points = self._subject_points_two_subjects()
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze()

        assert len(results) == 1
        _, event = results[0]
        assert event.event_type.value == MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE

    def test_multi_subject_event_details_contain_subjects_list(self):
        config = self._make_saved_config("msc_ev_subjects_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        points = self._subject_points_two_subjects()
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze()

        _, event = results[0]
        details = event.event_details.latest("updated_at").data["event_details"]
        assert "subjects" in details
        assert isinstance(details["subjects"], list)
        assert len(details["subjects"]) == 2
        for entry in details["subjects"]:
            assert "subject_id" in entry
            assert "subject_name" in entry

    def test_multi_subject_event_details_have_no_singular_subject_name(self):
        """The multi-subject event should not carry the single-subject subject_name key."""
        config = self._make_saved_config("msc_ev_no_sname_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        points = self._subject_points_two_subjects()
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze()

        _, event = results[0]
        details = event.event_details.latest("updated_at").data["event_details"]
        assert "subject_name" not in details

    def test_multi_subject_event_related_subjects_contains_all_cluster_subjects(self):
        config = self._make_saved_config("msc_ev_related_group", min_subjects=2)
        ia = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)

        points = self._subject_points_two_subjects()
        with patch.object(ia, "_collect_group_points", return_value=points):
            results = ia.analyze()

        _, event = results[0]
        related_ids = {str(s.id) for s in event.related_subjects.all()}
        # Both subjects must appear in related_subjects
        assert len(related_ids) == 2

    def test_single_result_created_when_analyzer_runs_for_each_subject_in_group(self):
        """When the task invokes analyze() once per subject in the group (as
        get_subject_analyzers yields one instance per subject), only a single
        SubjectAnalyzerResult should be created for the shared cluster — not
        one per subject."""
        subject2 = models.Subject.objects.create_subject(name="MSC_dedup_subject2")
        config = self._make_saved_config("msc_dedup_group", min_subjects=2)
        config.subject_group.subjects.add(subject2)

        pts_a = _make_subject_points(self.subject.id, self.subject.name, BASE_LAT, BASE_LON, 6, self.now, 1800)
        pts_b = _make_subject_points(subject2.id, subject2.name, BASE_LAT, BASE_LON, 6, self.now, 1800)
        all_points = pts_a + pts_b

        # Simulate the task scheduler invoking analyze() for each subject
        # separately via get_subject_analyzers, using the same config.
        ia1 = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config)
        ia2 = MultiSubjectMovementClusterAnalyzer(subject=subject2, config=config)

        with patch.object(ia1, "_collect_group_points", return_value=all_points):
            ia1.analyze()

        with patch.object(ia2, "_collect_group_points", return_value=all_points):
            ia2.analyze()

        result_count = SubjectAnalyzerResult.objects.filter(subject_analyzer_id=config.pk).count()
        assert result_count == 1, (
            f"Expected 1 SubjectAnalyzerResult for the shared cluster, got {result_count}. "
            "A multi-subject analyzer config should not create duplicate results when "
            "run for each subject in the group."
        )

    # ------------------------------------------------------------------
    # Leader election in get_subject_analyzers
    # ------------------------------------------------------------------

    def test_get_subject_analyzers_yields_only_for_leader_subject(self):
        """The leader is the active group member with the lowest id.  Only the
        leader should yield a multi-subject analyzer instance — the other
        members must be silent so ST-DBSCAN runs once per config per tick."""
        config = self._make_saved_config("msc_leader_yield_group", min_subjects=2)
        # self.subject is already in the group; add a second active subject.
        subject2 = models.Subject.objects.create_subject(name="MSC_leader_subject2")
        config.subject_group.subjects.add(subject2)

        active = list(config.subject_group.subjects.filter(is_active=True).order_by("id"))
        leader, follower = active[0], active[1]

        leader_analyzers = list(MultiSubjectMovementClusterAnalyzer.get_subject_analyzers(leader))
        follower_analyzers = list(MultiSubjectMovementClusterAnalyzer.get_subject_analyzers(follower))

        assert any(a.config.pk == config.pk for a in leader_analyzers), "leader subject should yield"
        assert all(a.config.pk != config.pk for a in follower_analyzers), "follower subject must not yield"

    def test_get_subject_analyzers_excludes_min_subjects_1_configs(self):
        """MultiSubjectMovementClusterAnalyzer must only consider configs with
        min_subjects_in_cluster > 1 — single-subject configs are owned by the
        legacy MovementClusterAnalyzer and would otherwise be picked up twice."""
        sg = models.SubjectGroup.objects.create(name="msc_min1_group")
        sg.subjects.add(self.subject)
        sg.save()
        single_config = MovementClusterAnalyzerConfig.objects.create(
            name="msc_min1_group", subject_group=sg, min_subjects_in_cluster=1
        )

        analyzers = list(MultiSubjectMovementClusterAnalyzer.get_subject_analyzers(self.subject))
        assert all(a.config.pk != single_config.pk for a in analyzers)

    def test_movement_cluster_analyzer_excludes_multi_subject_configs(self):
        """The legacy single-subject analyzer must skip configs with
        min_subjects_in_cluster > 1, mirroring the multi-subject filter so each
        config is owned by exactly one analyzer class."""
        multi_config = self._make_saved_config("msc_excludes_multi_group", min_subjects=2)

        analyzers = list(MovementClusterAnalyzer.get_subject_analyzers(self.subject))
        assert all(a.config.pk != multi_config.pk for a in analyzers)

    # ------------------------------------------------------------------
    # Query count / N+1 guard
    # ------------------------------------------------------------------

    def test_collect_group_points_query_count_scales_linearly_with_subjects(self):
        """_collect_group_points must have a predictable linear query cost.

        The assertions below expect the total query count to be:
          - 1 query to fetch the group's subjects
          - 2 queries per active subject

        In other words, the expected per-subject delta is 2 queries. This test
        intentionally asserts that exact delta rather than merely checking that the
        query count grows linearly, so the intended query budget remains explicit.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def make_config_with_n_subjects(n, group_name):
            sg = models.SubjectGroup.objects.create(name=group_name)
            for i in range(n):
                s = models.Subject.objects.create_subject(name=f"{group_name}_s{i}")
                sg.subjects.add(s)
            sg.save()
            return MovementClusterAnalyzerConfig.objects.create(
                name=group_name,
                subject_group=sg,
                spatial_threshold_meters=200,
                temporal_threshold_seconds=3600,
                min_cluster_points=3,
                min_cluster_duration_seconds=3600,
                min_subjects_in_cluster=2,
            )

        config1 = make_config_with_n_subjects(1, "qc_1subj")
        config2 = make_config_with_n_subjects(2, "qc_2subj")
        config3 = make_config_with_n_subjects(3, "qc_3subj")

        ia1 = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config1)
        ia2 = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config2)
        ia3 = MultiSubjectMovementClusterAnalyzer(subject=self.subject, config=config3)

        with CaptureQueriesContext(connection) as ctx1:
            ia1._collect_group_points()
        with CaptureQueriesContext(connection) as ctx2:
            ia2._collect_group_points()
        with CaptureQueriesContext(connection) as ctx3:
            ia3._collect_group_points()

        count_1 = len(ctx1.captured_queries)
        count_2 = len(ctx2.captured_queries)
        count_3 = len(ctx3.captured_queries)

        # Each additional subject costs exactly two queries in this test environment:
        #   1. SubjectTrackSegmentFilter.objects.filter(subject_subtype=...).first()
        #      (inside default_trajectory_filter — one lookup per subject)
        #   2. SubjectSource.objects.filter(subject=...) evaluated eagerly inside
        #      Subject.observations() / get_subject_observations_partitioned
        # The group subjects fetch (with select_related("subject_subtype")) is a single
        # constant query, so subject_subtype is never re-fetched per subject.
        # Note: in this test subjects have no observations, so the observations queryset
        # itself returns self.none() and is never evaluated — no additional query.
        # In production (with real SubjectSource records) the delta would be 3.
        # A delta > 2 here means an extra per-subject query has been introduced
        # (e.g. subject_subtype reloaded without select_related).
        expected_per_subject_delta = 2
        delta_1_to_2 = count_2 - count_1
        delta_2_to_3 = count_3 - count_2

        extra_query_hint = (
            "A higher delta indicates an extra per-subject query "
            "(e.g. subject_subtype reloaded without select_related)."
        )
        assert delta_1_to_2 == expected_per_subject_delta, (
            f"Adding a 2nd subject increased query count by {delta_1_to_2}, "
            f"expected {expected_per_subject_delta}. "
            f"Counts: 1 subject={count_1}, 2 subjects={count_2}. "
            f"Expected delta is {expected_per_subject_delta} (trajectory-filter lookup + observations). "
            + extra_query_hint
        )
        assert delta_2_to_3 == expected_per_subject_delta, (
            f"Adding a 3rd subject increased query count by {delta_2_to_3}, "
            f"expected {expected_per_subject_delta}. "
            f"Counts: 2 subjects={count_2}, 3 subjects={count_3}. "
            f"Expected delta is {expected_per_subject_delta} (trajectory-filter lookup + observations). "
            + extra_query_hint
        )


# ---------------------------------------------------------------------------
# cluster_points cap — OOM guard
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db
class TestClusterPointsCap(TestCase):
    """cluster_points stored in new_values must not exceed MAX_CLUSTER_POINTS_STORED
    even when the cluster contains more observations than the cap.  The full count
    is still reflected in cluster_point_count so callers are not misled.
    """

    def setUp(self):
        set_current_tenant(self.das_tenant)
        self.subject = models.Subject.objects.create_subject(name="CapTestSubject")
        self.now = datetime.now(tz=timezone.utc)

    def _config(self, **kwargs):
        defaults = dict(
            spatial_threshold_meters=200,
            temporal_threshold_seconds=7 * 24 * 3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
        )
        defaults.update(kwargs)
        return MovementClusterAnalyzerConfig(**defaults)

    def test_cluster_points_capped_when_cluster_exceeds_limit(self):
        oversized = MAX_CLUSTER_POINTS_STORED + 50
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=oversized, start=self.now, interval_s=300)
        analyzer = MovementClusterAnalyzer(subject=self.subject, config=self._config())
        results = analyzer.analyze(observations=obs)
        assert results, "Expected a cluster to form from the oversized observation set"
        result, _ = results[0]
        stored_points = result.values["cluster_points"]
        total_count = result.values["cluster_point_count"]
        assert len(stored_points) == MAX_CLUSTER_POINTS_STORED
        assert total_count == oversized

    def test_cluster_points_not_truncated_when_under_limit(self):
        count = MAX_CLUSTER_POINTS_STORED - 10
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=count, start=self.now, interval_s=300)
        analyzer = MovementClusterAnalyzer(subject=self.subject, config=self._config())
        results = analyzer.analyze(observations=obs)
        assert results
        result, _ = results[0]
        stored_points = result.values["cluster_points"]
        total_count = result.values["cluster_point_count"]
        assert len(stored_points) == total_count

    def test_cluster_points_stores_most_recent_when_capped(self):
        # The cap must retain the NEWEST points so that _find_open_clusters can still
        # match them on the next run (old points age out of the search window).
        oversized = MAX_CLUSTER_POINTS_STORED + 50
        obs = _clustered_obs(BASE_LAT, BASE_LON, count=oversized, start=self.now, interval_s=300)
        analyzer = MovementClusterAnalyzer(subject=self.subject, config=self._config())
        results = analyzer.analyze(observations=obs)
        assert results
        result, _ = results[0]
        stored_points = result.values["cluster_points"]
        # All stored points should be the newest (largest timestamps)
        all_times = sorted(pt["time"] for pt in stored_points)
        # The oldest stored point must be newer than ANY point from the dropped prefix.
        # The full obs list is ASC-ordered; the dropped prefix is obs[0..oversized-cap-1].
        dropped_cutoff = obs[oversized - MAX_CLUSTER_POINTS_STORED - 1].recorded_at.isoformat()
        assert all_times[0] > dropped_cutoff


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db
class TestMultiSubjectClusterPointsCap(TestCase):
    """Same cap guarantee for MultiSubjectMovementClusterAnalyzer."""

    def setUp(self):
        set_current_tenant(self.das_tenant)
        self.now = datetime.now(tz=timezone.utc)

    def _make_subject_points(self, n, subject_id, subject_name):
        points = []
        for i in range(n):
            t = self.now - timedelta(seconds=(n - 1 - i) * 300)
            points.append(
                _SubjectPoint(
                    lat=BASE_LAT + (i % 10) * 0.0005,
                    lon=BASE_LON + (i % 10) * 0.0005,
                    recorded_at=t,
                    subject_id=subject_id,
                    subject_name=subject_name,
                )
            )
        return points

    def _make_config(self, subject_group):
        return MovementClusterAnalyzerConfig(
            pk=uuid.uuid4(),
            spatial_threshold_meters=200,
            temporal_threshold_seconds=7 * 24 * 3600,
            min_cluster_points=3,
            min_cluster_duration_seconds=3600,
            min_subjects_in_cluster=2,
            subject_group=subject_group,
        )

    def test_multi_subject_cluster_points_capped(self):
        sg = models.SubjectGroup.objects.create(name="cap_test_group_ms")
        sid_a = uuid.uuid4()
        sid_b = uuid.uuid4()
        oversized = MAX_CLUSTER_POINTS_STORED + 50
        points_a = self._make_subject_points(oversized // 2, sid_a, "SubjectA")
        points_b = self._make_subject_points(oversized - oversized // 2, sid_b, "SubjectB")
        all_points = points_a + points_b
        labels = [1] * len(all_points)

        config = self._make_config(sg)
        subject = models.Subject.objects.create_subject(name="MSCapLeader")
        analyzer = MultiSubjectMovementClusterAnalyzer(subject=subject, config=config)
        results = analyzer._build_cluster_results(all_points, labels)
        assert results, "Expected a cluster result from oversized point set"
        stored = results[0].values["cluster_points"]
        total = results[0].values["cluster_point_count"]
        assert len(stored) == MAX_CLUSTER_POINTS_STORED
        assert total == len(all_points)
