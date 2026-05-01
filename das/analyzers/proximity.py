import json
import logging
import uuid
from datetime import timedelta

import pymet
from osgeo import ogr
from pymet.proximity import ProximityAnalysis, ProximityAnalysisParams
from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import Point as ShapelyPoint
from shapely.ops import nearest_points
from shapely.wkt import loads as shapely_wkt_loads

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.utils.translation import gettext_lazy as _

from activity.models import Event, EventCategory, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.models import FeatureProximityAnalyzerConfig, SubjectAnalyzerResult
from analyzers.models.base import CRITICAL, EVENT_PRIORITY_MAP, WARNING
from analyzers.utils import save_analyzer_event


class ProximityAnalyzer(SubjectAnalyzer):

    # Number of recent fixes to inspect when checking whether the current
    # proximity streak began inside this analyzer run. Caps the burst-extended
    # fetch so a high-frequency tracker can't blow up the per-fix proximity
    # cost.
    _HISTORY_FIXES = 10

    # Time window used to detect a burst of squashed observations. Set wider
    # than handle_observation's 60s squash period (countdown=60 in tasks.py)
    # so jitter at the boundary doesn't flicker between batched and
    # not-batched. When the most recent 3 fixes fall inside this window
    # ``default_observations`` extends the fetch.
    #
    # The DB-based dedup in ``_existing_streak_result`` already handles the
    # original "transition hidden inside a batch" bug on its own. This
    # extension is kept for one rare edge case: a leave-and-return that
    # happens entirely within the burst window (e.g. high-frequency GPS
    # jitter at a feature boundary). Without it, the brief "out" fix isn't
    # in the trajectory, the streak boundary can't be located, and the
    # return is treated as continuation of the original streak instead of a
    # new event.
    _BURST_DETECT_SECONDS = 120

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def subject_analyzers(cls, subject, analyzer_class):
        subject_groups = subject.get_ancestor_subject_groups()
        for ac in analyzer_class.objects.select_related("feature_group_filter").filter(
            subject_group__in=subject_groups, is_active=True
        ):
            yield cls(subject=subject, config=ac)

    def default_observations(self):
        """
        Default set of observations is fetched from the database based on this
        analyzer's configuration.

        Common case: returns the 3 most recent fixes, which is enough for the
        latest-segment vs prior-segment comparison in ``analyze_trajectory``
        and for ``_existing_streak_result`` to locate a non-proximal fix when
        the streak boundary lies in the recent past.

        Burst case: when those 3 fixes all fall inside
        ``_BURST_DETECT_SECONDS``, the fetch is extended to all observations
        within the burst window plus one fix preceding it (capped at
        ``_HISTORY_FIXES``). This is only needed for the rare case where a
        leave-and-return happens entirely inside the burst window — without
        the extra history, the brief "out" fix isn't visible and the return
        gets treated as continuation of the original streak. DB-based dedup
        handles the simpler "transition hidden inside a batch" case without
        any extension.

        :return: a list of Observations in descending temporal order
        """
        if self.config.search_time_hours <= 0:
            base_qs = self.subject.observations()
        else:
            base_qs = self.subject.observations(last_hours=self.config.search_time_hours)

        recent = list(base_qs[:3])
        if len(recent) < 3:
            return recent

        # ``recent`` is in descending temporal order — newest at index 0.
        burst_span = recent[0].recorded_at - recent[-1].recorded_at
        if burst_span.total_seconds() >= self._BURST_DETECT_SECONDS:
            return recent

        cutoff = recent[0].recorded_at - timedelta(seconds=self._BURST_DETECT_SECONDS)
        within_burst = list(base_qs.filter(recorded_at__gte=cutoff)[: self._HISTORY_FIXES - 1])
        prior = list(base_qs.filter(recorded_at__lt=cutoff)[:1])
        return within_burst + prior

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

    def value_to_display(self, value):
        return " ".join(x.capitalize() or "_" for x in value.split("_"))

    def evaluate_return_value(self, value):
        if not isinstance(value, str):
            value = value[0]

        if isinstance(value, float):
            value = round(value, 2)

        return value

    def verify_event_type(self, this_result):
        from analyzers.subject_proximity import (
            SUBJECT_PROXIMITY_SCHEMA,
            SubjectProximityAnalyzerConfig,
        )

        et_value = this_result.subject_analyzer.analyzer_category
        et_display = self.value_to_display(et_value)
        et_defaults_dict = dict(display=et_display)

        ec, created = EventCategory.objects.get_or_create(
            value="analyzer_event", defaults=dict(display="Analyzer Events")
        )
        et, created = EventType.objects.get_or_create(value=et_value, category=ec, defaults=et_defaults_dict)

        if created and isinstance(this_result.subject_analyzer, SubjectProximityAnalyzerConfig):
            et.schema = json.dumps(SUBJECT_PROXIMITY_SCHEMA, indent=2, default=str)
            et.save()
        return et_value

    def create_analyzer_event(self, last_result=None, this_result=None):

        # no data to create an event so exit
        if not this_result:
            return

        event_data = None

        event_details = {"name": self.subject.name}
        event_details.update(this_result.values)

        # Create a dict() location to satisfy our EventSerializer.
        event_location_value = {
            "longitude": this_result.geometry_collection[0].x,
            "latitude": this_result.geometry_collection[0].y,
        }

        event_type = self.verify_event_type(this_result)
        relate_subjects = [{"id": self.subject.id}]

        if this_result.values.get("subject_2_id"):
            subject_2_id = self.evaluate_return_value(this_result.values.get("subject_2_id"))
            relate_subjects.append({"id": uuid.UUID(subject_2_id)})

        # Notify if result is critical or warning
        if this_result.level in (CRITICAL, WARNING):
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type=event_type,
                priority=EVENT_PRIORITY_MAP.get(this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=event_details,
                related_subjects=relate_subjects,
            )

        if event_data:
            return save_analyzer_event(event_data)


class FeatureProximityAnalyzer(ProximityAnalyzer):

    @classmethod
    def get_subject_analyzers(cls, subject):
        return cls.subject_analyzers(subject, FeatureProximityAnalyzerConfig)

    def _create_proximity_analysis_params(self, features):
        sfs = [
            pymet.base.SpatialFeature(
                ogr_geometry=ogr.CreateGeometryFromWkt(feat.feature_geometry.wkt),
                name=feat.name,
                unique_id=feat.id,
            )
            for feat in features
        ]
        return ProximityAnalysisParams(spatial_features=sfs)

    @staticmethod
    def _proximal_feature_ids(geom, threshold_m, analysis_params, restrict_to=None):
        """Return the set of spatial-feature ids whose distance to ``geom`` is
        within ``threshold_m`` meters. When ``restrict_to`` is given, features
        whose ``unique_id`` is not in the set are skipped — used to avoid
        wasted distance work on features that aren't candidates to fire.
        """
        proximal_ids = set()
        for sf in analysis_params.spatial_features:
            if restrict_to is not None and sf.unique_id not in restrict_to:
                continue
            dist_m = pymet.utils.degrees_to_km(geom.Distance(sf.ogr_geometry)) * 1000.0
            if dist_m <= threshold_m:
                proximal_ids.add(sf.unique_id)
        return proximal_ids

    @staticmethod
    def _streak_start_time(feat_id, older_fixes, per_fix_proximal_ids):
        """Time of the most recent fix in ``older_fixes`` (newest to oldest)
        where ``feat_id`` was NOT individually proximal — the start of the
        current streak — or None if every older fix was proximal (or
        ``older_fixes`` is empty).
        """
        for i in range(len(older_fixes) - 1, -1, -1):
            if feat_id not in per_fix_proximal_ids[i]:
                return older_fixes[i].fixtime
        return None

    def _refresh_streak_result(self, existing_result, loc_x, loc_y, values):
        """Update an existing streak's ``SubjectAnalyzerResult`` and its linked
        ``Event`` with the latest fix's location and metadata. Used while the
        streak is ongoing so the recorded event tracks the subject's current
        position rather than firing duplicates.

        The event's ``event_time`` (and the result's ``estimated_time``) is
        left at the streak's original time so the event records when the
        proximity began rather than the most recent fix.
        """
        existing_result.geometry_collection = DjangoGeoColl([DjangoPoint(loc_x, loc_y)])
        existing_result.values = values
        existing_result.save()

        event = existing_result.event
        if event is None:
            return

        event.location = DjangoPoint(loc_x, loc_y)
        event.save()

        details = event.event_details.first()
        if details is not None:
            details.data = {"event_details": {"name": self.subject.name, **values}}
            details.save()

    def analyze_trajectory(self, traj=None):
        """
        A function to analyze the trajectory of a subject in relation to a set of spatial features and regions to
        determine where/when the subject was proximal to the spatial feature
         and what the containment of the individual was before and after any proximal events
        """

        if traj is None:
            return []

        # Fetch features once — used for both pymet params and the Shapely geometry map.
        features = list(self.config.proximal_features.features.all())
        analysis_params = self._create_proximity_analysis_params(features)
        threshold_m = self.config.threshold_dist_meters

        # Look at up to ``_HISTORY_FIXES`` recent fixes. The per-fix walk-back
        # in ``_existing_streak_result`` uses them to locate the streak's
        # not-proximal → proximal boundary so the DB-dedup query can be
        # time-bounded; the wider window also lets us catch a leave-and-return
        # that happened entirely inside the burst window
        # (see ``default_observations`` for the burst extension).
        #
        # Caveat: `traj` has already been run through the SubjectTrackSegmentFilter,
        # so a high-speed (or otherwise out-of-bounds) fix between two proximal fixes
        # may have been dropped. In that case the prior history won't reflect the
        # true prior state and a duplicate event can still slip through. This is a
        # pre-existing limitation of the upstream filter, not something this analyzer
        # can fix on its own — track via the analyzer's quiet_period if it becomes a problem.
        all_fixes = traj.relocs.get_fixes()[-self._HISTORY_FIXES :]
        if not all_fixes:
            return []

        latest_two = all_fixes[-2:]

        if len(latest_two) >= 2:
            current_traj = pymet.base.Trajectory(
                relocs=pymet.base.Relocations(fixes=latest_two, subject_id=traj.relocs.subject_id)
            )
            current_proximity_events = list(
                ProximityAnalysis.calc_proximity_events(
                    proximity_analysis_params=analysis_params, trajectories=[current_traj]
                ).proximity_events
            )
        else:
            # A single-fix trajectory has no segment for pymet's segment-based
            # iteration, so build point-vs-feature proximity events directly.
            fix = latest_two[0]
            fix_geom = fix.geopoint.ogr_geometry
            current_proximity_events = []
            for sf in analysis_params.spatial_features:
                dist_m = pymet.utils.degrees_to_km(fix_geom.Distance(sf.ogr_geometry)) * 1000.0
                if dist_m <= threshold_m:
                    current_proximity_events.append(
                        pymet.proximity.ProximityEvent(
                            subject_id=traj.relocs.subject_id,
                            subject_speed=None,
                            subject_travel_heading=None,
                            proximity_distance_meters=dist_m,
                            proximal_fix=fix,
                            spatial_feature_id=sf.unique_id,
                            spatial_feature_name=sf.name,
                        )
                    )

        # Filter pymet's events to those within threshold (the 1-fix branch
        # already filters at construction). Most analyzer runs end here — the
        # subject is rarely near any feature in the group, so we skip all of
        # the per-fix and prior-segment work below.
        proximal_events = [p for p in current_proximity_events if p.proximity_distance_meters <= threshold_m]
        if not proximal_events:
            return []

        proximal_feat_ids = {p.spatial_feature_id for p in proximal_events}

        # Single-fix proximity per older fix, restricted to features that are
        # actually candidates to fire — others can't shift the streak boundary.
        # Distances are computed directly via OGR rather than by routing each
        # fix through pymet, since pymet's calc_proximity_events iterates over
        # trajectory segments and returns no events for a single-fix trajectory.
        older_fixes = all_fixes[:-1]
        per_fix_proximal_ids = [
            self._proximal_feature_ids(
                fix.geopoint.ogr_geometry,
                threshold_m,
                analysis_params,
                restrict_to=proximal_feat_ids,
            )
            for fix in older_fixes
        ]

        # Build an id→Shapely-geometry map for closest-point-on-trajectory projection.
        # For polygons, use the boundary ring so the event lands on the perimeter, not the interior.
        # Lines and points are used as-is (a line's boundary is only its endpoints, which gives
        # wrong results when approaching the middle of a line).
        # Only the proximal features need a Shapely geom — others are never projected.
        def _feature_ref_geom(geom):
            if geom.geom_type in ("Polygon", "MultiPolygon"):
                return geom.boundary
            return geom

        feature_geom_by_id = {
            feat.id: _feature_ref_geom(shapely_wkt_loads(feat.feature_geometry.wkt))
            for feat in features
            if feat.id in proximal_feat_ids
        }

        # Trajectory geometry for closest-point projection: a line segment when
        # two fixes are available, a single point when only one fix exists.
        if len(latest_two) == 1:
            fix = latest_two[0]
            trajectory_geom = ShapelyPoint(fix.geopoint.ogr_geometry.GetX(), fix.geopoint.ogr_geometry.GetY())
        else:
            trajectory_geom = ShapelyLineString(
                [(fix.geopoint.ogr_geometry.GetX(), fix.geopoint.ogr_geometry.GetY()) for fix in latest_two]
            )

        # Pre-fetch existing results for every proximal feature in a single
        # query, ordered newest-first; the loop walks the per-feature lists
        # in Python instead of issuing one DB query per feature.
        proximal_feat_names = list({p.spatial_feature_name for p in proximal_events})
        candidates_by_feat_name: dict = {}
        candidate_qs = (
            SubjectAnalyzerResult.objects.select_related("event")
            .filter(
                subject=self.subject,
                subject_analyzer_id=self.config.id,
                values__spatial_feature_name__in=proximal_feat_names,
            )
            .order_by("-estimated_time")
        )
        for r in candidate_qs:
            candidates_by_feat_name.setdefault(r.values.get("spatial_feature_name"), []).append(r)

        # Cache attrs accessed once per loop iteration.
        subject_name = self.subject.name
        feature_group_name = self.config.proximal_features.name
        total_fix_count = len(latest_two)
        has_filter = bool(self.config.feature_group_filter)

        das_analyzer_results = []
        for prox in proximal_events:
            feat_id = prox.spatial_feature_id
            feat_name = prox.spatial_feature_name

            # Place the event at the closest point on the trajectory to the matched feature.
            feat_geom = feature_geom_by_id.get(feat_id)
            if feat_geom is not None:
                pt_on_trajectory, _pt_on_feature = nearest_points(trajectory_geom, feat_geom)
                loc_x, loc_y = pt_on_trajectory.x, pt_on_trajectory.y
            else:
                loc_x = prox.proximal_fix.geopoint.ogr_geometry.GetX()
                loc_y = prox.proximal_fix.geopoint.ogr_geometry.GetY()

            values = {
                "spatial_feature_name": feat_name,
                "proximity_dist_meters": round(prox.proximity_distance_meters, 2),
                "total_fix_count": total_fix_count,
                "subject_speed_kmhr": (
                    round(prox.subject_speed_kmhr, 2) if prox.subject_speed_kmhr is not None else None
                ),
                "subject_heading": round(prox.subject_heading, 2) if prox.subject_heading is not None else None,
                "feature_group_name": feature_group_name,
            }

            # Look up the existing streak's result (if any) in the pre-fetched
            # candidates. ``streak_start_time`` is the boundary inside the
            # window — when set, only later results count.
            streak_start_time = self._streak_start_time(feat_id, older_fixes, per_fix_proximal_ids)
            candidates = candidates_by_feat_name.get(feat_name, [])
            if streak_start_time is not None:
                existing = next((r for r in candidates if r.estimated_time > streak_start_time), None)
            else:
                existing = candidates[0] if candidates else None

            if existing is not None:
                # Streak hasn't ended — refresh the existing event in place
                # rather than firing a duplicate. If the analyzer has a
                # feature_group_filter and the latest projected location
                # falls outside it, leave the existing event untouched
                # (matches the create path's behavior in the base class).
                if has_filter and not self._is_location_in_cached_features(DjangoPoint(loc_x, loc_y)):
                    continue
                self._refresh_streak_result(existing, loc_x, loc_y, values)
                continue

            result = SubjectAnalyzerResult(
                subject_analyzer=self.config,
                title=subject_name + str(_(" proximal to ")) + feat_name,
                level=CRITICAL,
                message=subject_name + str(_(" proximal to ")) + feat_name,
                analyzer_revision=1,
                subject=self.subject,
            )
            result.estimated_time = prox.proximal_fix.fixtime
            result.geometry_collection = DjangoGeoColl([DjangoPoint(loc_x, loc_y)])
            result.values = values

            self.logger.info(result.message)
            das_analyzer_results.append(result)

        return das_analyzer_results
