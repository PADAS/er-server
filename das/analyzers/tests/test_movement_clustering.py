"""Tests for the MovementClusterAnalyzer (ST-DBSCAN based)."""

import json
from datetime import datetime, timedelta

import pytest
import pytz
from django_multitenant.utils import set_current_tenant

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from activity.models import Event
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import SubjectAnalyzerResult
from analyzers.models.base import OK
from analyzers.models.movement_clustering import MovementClusterAnalyzerConfig
from analyzers.movement_clustering import MovementClusterAnalyzer, _st_dbscan
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
        self.now = pytz.utc.localize(datetime.utcnow())

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
        assert len(cluster_points) == result.values["cluster_point_count"]
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
        from analyzers.movement_clustering import MOVEMENT_CLUSTER_EVENT_TYPE

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
        from analyzers.movement_clustering import MOVEMENT_CLUSTER_EVENT_TYPE

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
        from analyzers.movement_clustering import (
            MOVEMENT_CLUSTER_EVENT_TYPE,
            MOVEMENT_CLUSTER_SCHEMA,
        )

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
        from analyzers.movement_clustering import MOVEMENT_CLUSTER_EVENT_TYPE

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

        from analyzers.movement_clustering import (
            MOVEMENT_CLUSTER_EVENT_TYPE,
            save_analyzer_event,
        )

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
        recent_end = timezone.now() - timedelta(minutes=30)
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
            (p["location"]["latitude"], p["location"]["longitude"], p["time"]) for p in existing_points + extra_points
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert ia._find_open_clusters(new_point_set)

    def test_find_open_clusters_returns_empty_when_not_all_points_subset(self):
        config = self._make_saved_config("find_open_not_subset_group")
        recent_end = timezone.now() - timedelta(minutes=30)
        existing_points = self._make_cluster_points(BASE_LAT, BASE_LON, count=5)
        self._save_cluster_result(config, existing_points, recent_end)

        # Completely different points — not a superset of existing
        different_points = self._make_cluster_points(BASE_LAT + 5.0, BASE_LON, count=5)
        diff_point_set = frozenset(
            (p["location"]["latitude"], p["location"]["longitude"], p["time"]) for p in different_points
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert not ia._find_open_clusters(diff_point_set)

    def test_find_open_clusters_returns_empty_when_result_has_expired(self):
        config = self._make_saved_config("find_open_expired_group")
        # Result is 2 hours old — beyond the 1-hour temporal threshold
        old_end = timezone.now() - timedelta(hours=2)
        existing_points = self._make_cluster_points(BASE_LAT, BASE_LON, count=3)
        self._save_cluster_result(config, existing_points, old_end)

        existing_set = frozenset(
            (p["location"]["latitude"], p["location"]["longitude"], p["time"]) for p in existing_points
        )
        ia = MovementClusterAnalyzer(subject=self.subject, config=config)
        assert not ia._find_open_clusters(existing_set)

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
        recent_end = timezone.now() - timedelta(minutes=30)
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
        assert not ia._find_open_clusters(frozenset([("0.0", "36.0", "2024-01-01")]))

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
        recent_end = timezone.now() - timedelta(minutes=30)
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
