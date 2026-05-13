from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from haversine import Unit, haversine

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from activity.models import Event, EventCategory, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import SubjectAnalyzerResult
from analyzers.models.base import OK
from analyzers.models.movement_clustering import MovementClusterAnalyzerConfig
from analyzers.utils import save_analyzer_event

MOVEMENT_CLUSTER_EVENT_TYPE = "movement_cluster"
MAXIMUM_OBSERVATIONS = 1000
MAX_CLUSTER_POINTS_STORED = 200


def _point_within_search_window(point: dict, cutoff: datetime) -> bool:
    """Return True if the stored cluster point's recorded time is at or after *cutoff*.

    Uses :func:`django.utils.dateparse.parse_datetime` so that timestamps with a
    trailing ``Z`` or any UTC-offset suffix are handled correctly.  Naive datetimes
    (no timezone info) are treated as UTC — not the Django TIME_ZONE setting —
    because stored cluster-point timestamps are always written as UTC ISO strings.
    Points that cannot be parsed are treated as aged-out (excluded).
    """
    time_str = point.get("time")
    if not time_str:
        return False
    try:
        dt = parse_datetime(time_str)
        if dt is None:
            return False
        if timezone.is_naive(dt):
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt >= cutoff
    except (ValueError, TypeError):
        return False


def _st_dbscan(points, spatial_eps_m, temporal_eps_s, min_points):
    """Spatio-Temporal DBSCAN (ST-DBSCAN).

    Parameters
    ----------
    points:
        List of ``(lat, lon, timestamp_seconds)`` tuples.
    spatial_eps_m:
        Maximum spatial distance in metres for two points to be neighbours.
    temporal_eps_s:
        Maximum temporal distance in seconds for two points to be neighbours.
    min_points:
        Minimum number of neighbours (including the point itself) required to
        classify a point as a core point.

    Returns
    -------
    list[int]
        A label per input point.  ``-1`` denotes noise; positive integers
        identify individual clusters.
    """
    n = len(points)
    labels = [None] * n  # None = unvisited

    def _neighbors(idx):
        lat1, lon1, t1 = points[idx]
        result = []
        for j, (lat2, lon2, t2) in enumerate(points):
            if abs(t2 - t1) <= temporal_eps_s:
                if haversine((lat1, lon1), (lat2, lon2), unit=Unit.METERS) <= spatial_eps_m:
                    result.append(j)
        return result

    cluster_id = 0
    for i in range(n):
        if labels[i] is not None:
            continue

        neighbors = _neighbors(i)

        if len(neighbors) < min_points:
            labels[i] = -1  # mark as noise for now; may be absorbed later
            continue

        cluster_id += 1
        labels[i] = cluster_id

        seed_set = [j for j in neighbors if j != i]
        k = 0
        while k < len(seed_set):
            j = seed_set[k]
            k += 1

            if labels[j] == -1:
                # Previously marked noise — promote to border point
                labels[j] = cluster_id
            elif labels[j] is None:
                labels[j] = cluster_id
                j_neighbors = _neighbors(j)
                if len(j_neighbors) >= min_points:
                    # Core point — add its unvisited / noise neighbours to queue
                    for jn in j_neighbors:
                        if labels[jn] is None or labels[jn] == -1:
                            seed_set.append(jn)

    return [-1 if lbl is None else lbl for lbl in labels]


class MovementClusterAnalyzer(SubjectAnalyzer):
    """Detects spatio-temporal clusters in a subject's movement track.

    Uses the ST-DBSCAN algorithm to identify locations where a subject
    concentrates activity within configurable spatial and temporal bounds.
    A cluster is reported when it contains at least ``min_cluster_points``
    observations **and** spans at least ``min_cluster_duration_seconds``.
    """

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject, config)
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Analyzer discovery
    # ------------------------------------------------------------------

    @classmethod
    def get_subject_analyzers(cls, subject=None):
        if subject:
            subject_groups = subject.get_ancestor_subject_groups()
            for ac in MovementClusterAnalyzerConfig.objects.select_related("feature_group_filter").filter(
                subject_group__in=subject_groups,
                is_active=True,
                min_subjects_in_cluster=1,
            ):
                yield cls(subject=subject, config=ac)

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def default_observations(self):
        if self.config.search_time_hours <= 0:
            return self.subject.observations()[:MAXIMUM_OBSERVATIONS]
        return self.subject.observations(last_hours=self.config.search_time_hours)[:MAXIMUM_OBSERVATIONS]

    # ------------------------------------------------------------------
    # Open-cluster check
    # ------------------------------------------------------------------

    def _find_open_clusters(self, cluster_point_set: frozenset) -> list:
        """Return all existing open results whose stored points are all
        contained in *cluster_point_set*.

        A result is considered *open* when its ``estimated_time`` falls within
        ``temporal_threshold_seconds`` of now.  Containment is checked by
        comparing the frozenset of ``(lat, lon, time, subject_id)`` tuples stored
        in the result's ``cluster_points`` value against *cluster_point_set*.
        The ``subject_id`` element is ``None`` for single-subject results.

        If the config has not yet been persisted (no PK) the check is skipped
        and an empty list is returned.
        """
        if not self.config.pk:
            return []

        cutoff = timezone.now() - timedelta(seconds=self.config.temporal_threshold_seconds)

        recent_results = SubjectAnalyzerResult.objects.filter(
            subject=self.subject,
            subject_analyzer_id=self.config.pk,
            estimated_time__gte=cutoff,
            event__state=Event.SC_ACTIVE,
        ).select_related("event")

        # Points older than search_time_hours would not appear in the current
        # cluster_point_set because they are no longer fetched as observations.
        # Strip them from the stored set before comparing so that naturally
        # aged-out points don't prevent a valid open-cluster match.
        search_cutoff: datetime | None = (
            timezone.now() - timedelta(hours=self.config.search_time_hours)
            if self.config.search_time_hours > 0
            else None
        )

        matches = []
        for result in recent_results:
            prev_points = result.values.get("cluster_points")
            if not prev_points:
                continue

            if search_cutoff is not None:
                prev_points = [p for p in prev_points if _point_within_search_window(p, search_cutoff)]

            # If every stored point has aged out there is nothing to compare.
            if not prev_points:
                continue

            prev_point_set = frozenset(
                (
                    p.get("location", {}).get("latitude"),
                    p.get("location", {}).get("longitude"),
                    p.get("time"),
                    p.get("subject_id"),
                )
                for p in prev_points
            )
            if prev_point_set.issubset(cluster_point_set):
                matches.append(result)

        return matches

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze_trajectory(self, traj=None):
        if traj is None:
            return []

        fixes = traj.relocs.get_fixes("ASC")

        if len(fixes) < self.config.min_cluster_points:
            raise InsufficientDataAnalyzerException

        # Build the point list expected by _st_dbscan
        points = []
        for fix in fixes:
            lat = fix.ogr_geometry.GetY()
            lon = fix.ogr_geometry.GetX()
            t = fix.fixtime.timestamp()
            points.append((lat, lon, t))

        labels = _st_dbscan(
            points,
            spatial_eps_m=self.config.spatial_threshold_meters,
            temporal_eps_s=self.config.temporal_threshold_seconds,
            min_points=self.config.min_cluster_points,
        )

        # Group fixes by cluster label
        clusters: dict[int, list] = {}
        for fix, label in zip(fixes, labels):
            if label < 1:
                continue  # noise
            clusters.setdefault(label, []).append(fix)

        results = []

        # One result per qualifying cluster
        for cluster_fixes in clusters.values():
            times = [f.fixtime for f in cluster_fixes]
            duration_s = (max(times) - min(times)).total_seconds()

            if duration_s < self.config.min_cluster_duration_seconds:
                continue

            lats = [f.ogr_geometry.GetY() for f in cluster_fixes]
            lons = [f.ogr_geometry.GetX() for f in cluster_fixes]
            centroid_lat = sum(lats) / len(lats)
            centroid_lon = sum(lons) / len(lons)
            cluster_radius_m = (
                0
                if len(lats) < 2
                else max(
                    haversine((centroid_lat, centroid_lon), (lat, lon), unit=Unit.METERS)
                    for lat, lon in zip(lats, lons)
                )
            )

            cluster_points = [
                {
                    "location": {
                        "latitude": round(f.ogr_geometry.GetY(), 7),
                        "longitude": round(f.ogr_geometry.GetX(), 7),
                    },
                    "time": f.fixtime.isoformat(),
                }
                for f in cluster_fixes
            ]
            cluster_point_set = frozenset(
                (p["location"]["latitude"], p["location"]["longitude"], p["time"], p.get("subject_id"))
                for p in cluster_points
            )

            new_values = {
                "cluster_point_count": len(cluster_fixes),
                "cluster_duration_hours": round(duration_s / 3600, 2),
                "cluster_radius_meters": round(cluster_radius_m, 2),
                "cluster_start_time": min(times).isoformat(),
                "cluster_end_time": max(times).isoformat(),
                "cluster_points": cluster_points[:MAX_CLUSTER_POINTS_STORED],
            }

            open_clusters = self._find_open_clusters(cluster_point_set)
            if len(open_clusters) == 1:
                existing = open_clusters[0]
                self.logger.debug(
                    "MovementClusterAnalyzer: updating open cluster at (%.5f, %.5f) for subject=%s",
                    centroid_lat,
                    centroid_lon,
                    self.subject.name,
                )
                existing.estimated_time = max(times)
                existing.geometry_collection = DjangoGeoColl([DjangoPoint(centroid_lon, centroid_lat)])
                existing.values = new_values
                existing._is_cluster_update = True
                results.append(existing)
                continue
            elif len(open_clusters) > 1:
                self.logger.debug(
                    "MovementClusterAnalyzer: merging %d open clusters at (%.5f, %.5f) for subject=%s",
                    len(open_clusters),
                    centroid_lat,
                    centroid_lon,
                    self.subject.name,
                )
                for prev_result in open_clusters:
                    if prev_result.event is not None:
                        prev_result.event.state = Event.SC_RESOLVED
                        prev_result.event.save()

            title = _("%(subject_name)s movement cluster detected") % {"subject_name": self.subject.name}

            result = SubjectAnalyzerResult(
                subject_analyzer=self.config,
                level=OK,
                title=str(title),
                message=str(title),
                analyzer_revision=1,
                subject=self.subject,
                estimated_time=max(times),
                geometry_collection=DjangoGeoColl([DjangoPoint(centroid_lon, centroid_lat)]),
            )
            result.values = new_values
            results.append(result)

        self.logger.info(
            "MovementClusterAnalyzer: subject=%s clusters=%d",
            self.subject.name,
            len(results),
        )
        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_analyzer_result(self, last_result=None, this_result=None):  # noqa: ARG002
        """
        Persist the current analyzer result.

        This method overrides :meth:`SubjectAnalyzer.save_analyzer_result` but
        deliberately ignores ``last_result`` and performs no comparison or
        update logic. It accepts ``last_result`` only to maintain a compatible
        signature with the base class and simply saves ``this_result`` if
        provided.
        """
        if this_result is not None:
            this_result.save()

    # ------------------------------------------------------------------
    # Event creation
    # ------------------------------------------------------------------

    def _ensure_event_type(self) -> None:
        ec, _ = EventCategory.objects.get_or_create(
            value="analyzer_event",
            defaults={"display": "Analyzer Events"},
        )
        et, created = EventType.objects.get_or_create(
            value=MOVEMENT_CLUSTER_EVENT_TYPE,
            category=ec,
            defaults={"display": "Movement Cluster", "version": EventType.VersionChoices.VERSION_2},
        )
        if created:
            et.schema = json.dumps(MOVEMENT_CLUSTER_SCHEMA, indent=2, default=str)
            et.save()

    def create_analyzer_event(self, last_result=None, this_result=None):  # noqa: ARG002
        if not this_result:
            return None

        if getattr(this_result, "_is_cluster_update", False):
            return None

        self._ensure_event_type()
        centroid = this_result.geometry_collection[0]
        event_details = {"analyzer_name": self.config.name, "subject_name": self.subject.name}
        event_details.update(this_result.values)

        event_data = dict(
            title=this_result.title,
            state=Event.SC_ACTIVE,
            time=this_result.estimated_time,
            provenance=Event.PC_ANALYZER,
            event_type=MOVEMENT_CLUSTER_EVENT_TYPE,
            location={"longitude": centroid.x, "latitude": centroid.y},
            event_details=event_details,
            related_subjects=[{"id": self.subject.id}],
        )
        return save_analyzer_event(event_data)


MOVEMENT_CLUSTER_SCHEMA = {
    "json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {
            "analyzer_name": {
                "deprecated": False,
                "title": "Analyzer Name",
                "default": "",
                "description": "",
                "type": "string",
            },
            "subject_name": {
                "deprecated": False,
                "title": "Subject Name",
                "default": "",
                "description": "",
                "type": "string",
            },
            "cluster_start_time": {
                "deprecated": False,
                "title": "Cluster Start Time",
                "description": "",
                "format": "date-time",
                "type": "string",
            },
            "cluster_end_time": {
                "deprecated": False,
                "title": "Cluster End Time",
                "description": "",
                "format": "date-time",
                "type": "string",
            },
            "cluster_duration_hours": {
                "deprecated": False,
                "title": "Cluster Duration Hours",
                "description": "",
                "minimum": 0,
                "type": "number",
            },
            "cluster_point_count": {
                "deprecated": False,
                "title": "Cluster Point Count",
                "description": "",
                "minimum": 0,
                "type": "number",
            },
            "cluster_radius_meters": {
                "deprecated": False,
                "title": "Cluster Radius Meters",
                "description": "",
                "minimum": 0,
                "type": "number",
            },
            "cluster_points": {
                "deprecated": False,
                "title": "Cluster Points",
                "description": "",
                "items": {
                    "properties": {
                        "time": {
                            "deprecated": False,
                            "title": "Time",
                            "description": "",
                            "format": "date-time",
                            "type": "string",
                        },
                        "location": {
                            "deprecated": False,
                            "title": "Location",
                            "description": "",
                            "properties": {
                                "latitude": {"maximum": 90, "minimum": -90, "type": "number"},
                                "longitude": {"maximum": 180, "minimum": -180, "type": "number"},
                            },
                            "required": ["latitude", "longitude"],
                            "type": "object",
                            "unevaluatedProperties": False,
                        },
                    },
                    "required": [],
                    "type": "object",
                    "unevaluatedProperties": False,
                },
                "type": "array",
                "unevaluatedItems": False,
            },
        },
        "required": [],
        "type": "object",
        "unevaluatedProperties": False,
    },
    "ui": {
        "fields": {
            "analyzer_name": {
                "conditionalDependents": [],
                "parent": "section-2",
                "type": "TEXT",
                "inputType": "SHORT_TEXT",
                "placeholder": "",
            },
            "subject_name": {
                "conditionalDependents": [],
                "parent": "section-2",
                "type": "TEXT",
                "inputType": "SHORT_TEXT",
                "placeholder": "",
            },
            "cluster_start_time": {"conditionalDependents": [], "parent": "section-1", "type": "DATE_TIME"},
            "cluster_end_time": {"conditionalDependents": [], "parent": "section-1", "type": "DATE_TIME"},
            "cluster_duration_hours": {
                "conditionalDependents": [],
                "parent": "section-1",
                "type": "NUMERIC",
                "placeholder": "",
            },
            "cluster_point_count": {
                "conditionalDependents": [],
                "parent": "section-1",
                "type": "NUMERIC",
                "placeholder": "",
            },
            "cluster_radius_meters": {
                "conditionalDependents": [],
                "parent": "section-1",
                "type": "NUMERIC",
                "placeholder": "",
            },
            "cluster_points": {
                "conditionalDependents": [],
                "parent": "section-3",
                "type": "COLLECTION",
                "buttonText": "",
                "columns": 1,
                "itemIdentifier": "",
                "itemName": "Point",
                "leftColumn": ["time", "location"],
                "rightColumn": [],
            },
            "time": {"conditionalDependents": [], "parent": "cluster_points", "type": "DATE_TIME"},
            "location": {"conditionalDependents": [], "parent": "cluster_points", "type": "LOCATION"},
        },
        "headers": {},
        "order": ["section-2", "section-1", "section-3"],
        "sections": {
            "section-2": {
                "columns": 1,
                "conditions": [],
                "isActive": True,
                "label": "",
                "leftColumn": [
                    {"name": "analyzer_name", "type": "field"},
                    {"name": "subject_name", "type": "field"},
                ],
                "rightColumn": [],
            },
            "section-1": {
                "columns": 2,
                "conditions": [],
                "isActive": True,
                "label": "",
                "leftColumn": [
                    {"name": "cluster_start_time", "type": "field"},
                    {"name": "cluster_end_time", "type": "field"},
                    {"name": "cluster_duration_hours", "type": "field"},
                ],
                "rightColumn": [
                    {"name": "cluster_point_count", "type": "field"},
                    {"name": "cluster_radius_meters", "type": "field"},
                ],
            },
            "section-3": {
                "columns": 1,
                "conditions": [],
                "isActive": True,
                "label": "",
                "leftColumn": [{"name": "cluster_points", "type": "field"}],
                "rightColumn": [],
            },
        },
    },
}
