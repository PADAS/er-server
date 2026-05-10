from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import NamedTuple

from haversine import Unit, haversine

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.core.cache import cache
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from activity.models import Event, EventCategory, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import SubjectAnalyzerResult
from analyzers.models.base import OK
from analyzers.models.movement_clustering import MovementClusterAnalyzerConfig
from analyzers.movement_clustering import _point_within_search_window, _st_dbscan
from analyzers.utils import save_analyzer_event
from observations.models import Subject

MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE = "multi_subject_movement_cluster"
MAXIMUM_OBSERVATIONS_MULTIPLE_SUBJECTS = 5000


class _SubjectPoint(NamedTuple):
    """A single observation tagged with its originating subject."""

    lat: float
    lon: float
    recorded_at: datetime
    subject_id: uuid.UUID
    subject_name: str


class MultiSubjectMovementClusterAnalyzer(SubjectAnalyzer):
    """Detects spatio-temporal clusters that span multiple subjects.

    Collects observations from every active subject in the configured subject
    group, runs ST-DBSCAN over the combined point set, and reports a cluster
    only when it contains at least ``min_subjects_in_cluster`` distinct
    subjects.
    """

    def __init__(self, subject: Subject | None = None, config: MovementClusterAnalyzerConfig | None = None) -> None:
        SubjectAnalyzer.__init__(self, subject, config)
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Analyzer discovery
    # ------------------------------------------------------------------

    @classmethod
    def get_subject_analyzers(cls, subject: Subject | None = None) -> Iterator[MultiSubjectMovementClusterAnalyzer]:
        if subject:
            subject_groups = subject.get_ancestor_subject_groups()
            # Prefetch active group members ordered by id so leader election does not
            # issue an extra query per config.
            active_subjects_qs = Subject.objects.filter(is_active=True).order_by("id")
            for ac in (
                MovementClusterAnalyzerConfig.objects.select_related("feature_group_filter")
                .prefetch_related(
                    Prefetch("subject_group__subjects", queryset=active_subjects_qs, to_attr="_active_subjects")
                )
                .filter(
                    subject_group__in=subject_groups,
                    is_active=True,
                    min_subjects_in_cluster__gt=1,
                )
            ):
                # Only yield for the leader subject (lowest ID among active group members)
                # so the expensive group-wide collection and ST-DBSCAN run exactly once
                # per config per schedule tick rather than once per subject in the group.
                active = ac.subject_group._active_subjects
                if active and active[0].id == subject.id:
                    yield cls(subject=subject, config=ac)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        observations: object | None = None,  # noqa: ARG002 — accepted for base-class signature parity
        trajectory_filter: object | None = None,  # noqa: ARG002 — accepted for base-class signature parity
        analyzer_key: str | None = None,
    ) -> list[tuple[SubjectAnalyzerResult, Event | None]]:
        """Run ST-DBSCAN over all subjects in the group and return qualifying clusters.

        A cluster qualifies when it spans at least ``min_subjects_in_cluster``
        distinct subjects.  Post-processing (feature-group filtering, result
        persistence, event creation) mirrors :meth:`SubjectAnalyzer.analyze`.
        """
        all_points = self._collect_group_points()

        if len(all_points) < self.config.min_cluster_points:
            raise InsufficientDataAnalyzerException

        geo_points = [(p.lat, p.lon, p.recorded_at.timestamp()) for p in all_points]
        labels = _st_dbscan(
            geo_points,
            spatial_eps_m=self.config.spatial_threshold_meters,
            temporal_eps_s=self.config.temporal_threshold_seconds,
            min_points=self.config.min_cluster_points,
        )

        results = self._build_cluster_results(all_points, labels)

        analyze_results = []
        for this_result in results:
            if not self._is_within_feature_group_filter(this_result):
                continue
            self.save_analyzer_result(last_result=None, this_result=this_result)
            this_event = self.create_analyzer_event(last_result=None, this_result=this_result)
            if analyzer_key and this_event and self.config.quiet_period:
                self.logger.info("Pausing analyzer with id=%s", self.config.id)
                cache.set(analyzer_key, analyzer_key, self.config.quiet_period.total_seconds())
            if this_event is not None and this_result.pk:
                SubjectAnalyzerResult.objects.filter(pk=this_result.pk).update(event=this_event)
                this_result.event = this_event
            analyze_results.append((this_result, this_event))

        return analyze_results

    def _collect_group_points(self) -> list[_SubjectPoint]:
        """Return filtered observations for every active subject in the subject group.

        Each observation is represented as a :class:`_SubjectPoint` carrying the
        subject identity alongside the spatial and temporal coordinates.

        Observations are passed through each subject's trajectory filter (coordinate
        sanity check and optional speed filter) so that the same junk-point removal
        applied by the single-subject path is also applied here.
        """
        all_points: list[_SubjectPoint] = []
        # Chain through subject_subtype__subject_type so that both
        # default_trajectory_filter (reads subject_subtype.value) and
        # is_stationary_subject (reads subject_subtype.subject_type.value, evaluated
        # eagerly inside get_subject_observations_partitioned) are satisfied without
        # firing an extra query per subject.
        group_subjects = list(
            self.config.subject_group.subjects.filter(is_active=True).select_related("subject_subtype__subject_type")
        )
        if not group_subjects:
            return all_points

        # Divide the budget evenly so every subject gets the same allocation and
        # the total fed into ST-DBSCAN is strictly bounded:
        #   per_subject_limit * N  <=  MAXIMUM_OBSERVATIONS_MULTIPLE_SUBJECTS
        # Integer division guarantees this without any post-collection truncation,
        # so no subject is starved in favour of earlier subjects in the list.
        # For extremely large groups (N > MAXIMUM_OBSERVATIONS_MULTIPLE_SUBJECTS)
        # each subject gets 1 observation at minimum.
        per_subject_limit = max(1, MAXIMUM_OBSERVATIONS_MULTIPLE_SUBJECTS // len(group_subjects))

        for subject in group_subjects:
            if self.config.search_time_hours <= 0:
                obs_qs = subject.observations()[:per_subject_limit]
            else:
                obs_qs = subject.observations(last_hours=self.config.search_time_hours)[:per_subject_limit]

            trajectory_filter = subject.default_trajectory_filter()
            traj = subject.create_trajectory(obs=obs_qs, trajectory_filter_params=trajectory_filter)
            for fix in traj.relocs.get_fixes("ASC"):
                all_points.append(
                    _SubjectPoint(
                        lat=fix.ogr_geometry.GetY(),
                        lon=fix.ogr_geometry.GetX(),
                        recorded_at=fix.fixtime,
                        subject_id=subject.id,
                        subject_name=subject.name,
                    )
                )

        return all_points

    def _build_cluster_results(
        self,
        all_points: list[_SubjectPoint],
        labels: list[int],
    ) -> list[SubjectAnalyzerResult]:
        """Convert labeled multi-subject points into :class:`SubjectAnalyzerResult` objects.

        A cluster is only retained when the number of distinct subjects that
        contributed points to it is at least ``min_subjects_in_cluster``, and
        when its duration meets ``min_cluster_duration_seconds``.
        """
        clusters: dict[int, list[_SubjectPoint]] = {}
        for point, label in zip(all_points, labels):
            if label < 1:
                continue
            clusters.setdefault(label, []).append(point)

        results = []
        for cluster_data in clusters.values():
            times = [p.recorded_at for p in cluster_data]
            subject_ids = {p.subject_id for p in cluster_data}

            if len(subject_ids) < self.config.min_subjects_in_cluster:
                continue

            duration_s = (max(times) - min(times)).total_seconds()
            if duration_s < self.config.min_cluster_duration_seconds:
                continue

            lats = [p.lat for p in cluster_data]
            lons = [p.lon for p in cluster_data]
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
                        "latitude": round(p.lat, 7),
                        "longitude": round(p.lon, 7),
                    },
                    "time": p.recorded_at.isoformat(),
                    "subject_id": str(p.subject_id),
                    "cluster_point_subject_name": p.subject_name,
                }
                for p in cluster_data
            ]
            cluster_point_set = frozenset(
                (pt["location"]["latitude"], pt["location"]["longitude"], pt["time"], pt.get("subject_id"))
                for pt in cluster_points
            )

            new_values = {
                "cluster_point_count": len(cluster_data),
                "cluster_duration_hours": round(duration_s / 3600, 2),
                "cluster_radius_meters": round(cluster_radius_m, 2),
                "cluster_start_time": min(times).isoformat(),
                "cluster_end_time": max(times).isoformat(),
                "cluster_points": cluster_points,
                "subjects_in_cluster": len(subject_ids),
                "subject_ids_in_cluster": [str(sid) for sid in sorted(subject_ids, key=str)],
            }

            open_clusters = self._find_open_clusters(cluster_point_set)
            if len(open_clusters) == 1:
                existing = open_clusters[0]
                self.logger.debug(
                    "MultiSubjectMovementClusterAnalyzer: updating open cluster at (%.5f, %.5f) for subject=%s",
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
                    "MultiSubjectMovementClusterAnalyzer: merging %d open clusters at (%.5f, %.5f) for subject=%s",
                    len(open_clusters),
                    centroid_lat,
                    centroid_lon,
                    self.subject.name,
                )
                # Resolve all merged events atomically so a mid-loop failure cannot
                # leave the cluster in a half-resolved state.
                with transaction.atomic():
                    for prev_result in open_clusters:
                        if prev_result.event is not None:
                            prev_result.event.state = Event.SC_RESOLVED
                            prev_result.event.save()

            group_name = self.config.subject_group.name if self.config.subject_group_id else "Multi-subject"
            title = _("%(group_name)s movement cluster detected") % {"group_name": group_name}
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
            "MultiSubjectMovementClusterAnalyzer: subject=%s clusters=%d (min_subjects=%d)",
            self.subject.name,
            len(results),
            self.config.min_subjects_in_cluster,
        )
        return results

    # ------------------------------------------------------------------
    # Open-cluster check
    # ------------------------------------------------------------------

    def _find_open_clusters(
        self, cluster_point_set: frozenset[tuple[float | None, float | None, str | None, str | None]]
    ) -> list[SubjectAnalyzerResult]:
        """Return all existing open results whose stored points are all
        contained in *cluster_point_set*.

        A result is considered *open* when its ``estimated_time`` falls within
        ``temporal_threshold_seconds`` of now.  Containment is checked by
        comparing the frozenset of ``(lat, lon, time, subject_id)`` tuples stored
        in the result's ``cluster_points`` value against *cluster_point_set*.

        The subject filter is intentionally omitted so that results saved under
        any subject in the group are found.  This prevents duplicate results when
        the same config is run once per subject by the task scheduler.

        If the config has not yet been persisted (no PK) the check is skipped
        and an empty list is returned.
        """
        if not self.config.pk:
            return []

        cutoff = timezone.now() - timedelta(seconds=self.config.temporal_threshold_seconds)

        recent_results = SubjectAnalyzerResult.objects.filter(
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
    # Persistence
    # ------------------------------------------------------------------

    def save_analyzer_result(
        self,
        last_result: SubjectAnalyzerResult | None = None,  # noqa: ARG002 — accepted for base-class signature parity
        this_result: SubjectAnalyzerResult | None = None,
    ) -> None:
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
            value=MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE,
            category=ec,
            defaults={"display": "Multi-Subject Movement Cluster", "version": EventType.VersionChoices.VERSION_2},
        )
        if created:
            et.schema = json.dumps(MULTI_SUBJECT_MOVEMENT_CLUSTER_SCHEMA, indent=2, default=str)
            et.save()

    def create_analyzer_event(
        self,
        last_result: SubjectAnalyzerResult | None = None,  # noqa: ARG002 — accepted for base-class signature parity
        this_result: SubjectAnalyzerResult | None = None,
    ) -> Event | None:
        if not this_result:
            return None

        if getattr(this_result, "_is_cluster_update", False):
            return None

        self._ensure_event_type()
        centroid = this_result.geometry_collection[0]

        seen_ids: set[str] = set()
        subjects = []
        for pt in this_result.values.get("cluster_points", []):
            sid = pt.get("subject_id")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                subjects.append({"subject_id": sid, "subject_name": pt.get("cluster_point_subject_name", "")})

        event_details = dict(this_result.values)
        event_details.pop("subject_ids_in_cluster", None)
        event_details["subjects"] = subjects

        related_subjects = [
            {"id": sid} for sid in this_result.values.get("subject_ids_in_cluster", [str(self.subject.id)])
        ]

        event_data = dict(
            title=this_result.title,
            state=Event.SC_ACTIVE,
            time=this_result.estimated_time,
            provenance=Event.PC_ANALYZER,
            event_type=MULTI_SUBJECT_MOVEMENT_CLUSTER_EVENT_TYPE,
            location={"longitude": centroid.x, "latitude": centroid.y},
            event_details=event_details,
            related_subjects=related_subjects,
        )
        return save_analyzer_event(event_data)


MULTI_SUBJECT_MOVEMENT_CLUSTER_SCHEMA = {
    "json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {
            "subjects": {
                "deprecated": False,
                "title": "Subjects",
                "description": "Subjects whose observations contributed to this cluster.",
                "items": {
                    "properties": {
                        "subject_id": {
                            "deprecated": False,
                            "title": "Subject ID",
                            "description": "",
                            "type": "string",
                        },
                        "subject_name": {
                            "deprecated": False,
                            "title": "Subject Name",
                            "description": "",
                            "type": "string",
                        },
                    },
                    "required": [],
                    "type": "object",
                    "unevaluatedProperties": False,
                },
                "type": "array",
                "unevaluatedItems": False,
            },
            "subjects_in_cluster": {
                "deprecated": False,
                "title": "Subjects in Cluster",
                "description": "Number of distinct subjects that contributed observations to this cluster.",
                "minimum": 0,
                "type": "number",
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
                        "subject_id": {
                            "deprecated": False,
                            "title": "Subject ID",
                            "description": "",
                            "type": "string",
                        },
                        "cluster_point_subject_name": {
                            "deprecated": False,
                            "title": "Subject Name",
                            "description": "",
                            "type": "string",
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
            "subjects": {
                "conditionalDependents": [],
                "parent": "section-1",
                "type": "COLLECTION",
                "buttonText": "",
                "columns": 2,
                "itemIdentifier": "subject_id",
                "itemName": "Subject",
                "leftColumn": ["subject_name"],
                "rightColumn": [],
            },
            "subject_name": {
                "conditionalDependents": [],
                "parent": "subjects",
                "type": "TEXT",
                "inputType": "SHORT_TEXT",
                "placeholder": "",
            },
            "subjects_in_cluster": {
                "conditionalDependents": [],
                "parent": "section-2",
                "type": "NUMERIC",
                "placeholder": "",
            },
            "cluster_start_time": {"conditionalDependents": [], "parent": "section-2", "type": "DATE_TIME"},
            "cluster_end_time": {"conditionalDependents": [], "parent": "section-2", "type": "DATE_TIME"},
            "cluster_duration_hours": {
                "conditionalDependents": [],
                "parent": "section-2",
                "type": "NUMERIC",
                "placeholder": "",
            },
            "cluster_point_count": {
                "conditionalDependents": [],
                "parent": "section-2",
                "type": "NUMERIC",
                "placeholder": "",
            },
            "cluster_radius_meters": {
                "conditionalDependents": [],
                "parent": "section-2",
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
                "leftColumn": ["time", "location", "cluster_point_subject_name"],
                "rightColumn": [],
            },
            "time": {"conditionalDependents": [], "parent": "cluster_points", "type": "DATE_TIME"},
            "location": {"conditionalDependents": [], "parent": "cluster_points", "type": "LOCATION"},
            "cluster_point_subject_name": {
                "conditionalDependents": [],
                "parent": "cluster_points",
                "type": "TEXT",
                "inputType": "SHORT_TEXT",
                "placeholder": "",
            },
        },
        "headers": {},
        "order": ["section-1", "section-2", "section-3"],
        "sections": {
            "section-1": {
                "columns": 1,
                "conditions": [],
                "isActive": True,
                "label": "Subjects",
                "leftColumn": [{"name": "subjects", "type": "field"}],
                "rightColumn": [],
            },
            "section-2": {
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
                    {"name": "subjects_in_cluster", "type": "field"},
                    {"name": "cluster_point_count", "type": "field"},
                    {"name": "cluster_radius_meters", "type": "field"},
                ],
            },
            "section-3": {
                "columns": 1,
                "conditions": [],
                "isActive": True,
                "label": "Observations",
                "leftColumn": [{"name": "cluster_points", "type": "field"}],
                "rightColumn": [],
            },
        },
    },
}
