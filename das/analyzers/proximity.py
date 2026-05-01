import json
import logging
import uuid

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
        Default set of observations is fetched from the database, limited to
        the three most recent, based on this analyzer's configuration.

        :return: a list of at most 3 Observations in descending temporal order
        """
        if self.config.search_time_hours <= 0:
            return list(self.subject.observations()[:3])
        return list(self.subject.observations(last_hours=self.config.search_time_hours)[:3])

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
                state=Event.SC_ACTIVE,
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

    def analyze_trajectory(self, traj=None):
        """
        A function to analyze the trajectory of a subject in relation to a set of spatial features and regions to
        determine where/when the subject was proximal to the spatial feature
         and what the containment of the individual was before and after any proximal events.
        """

        if traj is None:
            return []

        features = list(self.config.proximal_features.features.all())
        analysis_params = self._create_proximity_analysis_params(features)
        threshold_m = self.config.threshold_dist_meters

        all_fixes = traj.relocs.get_fixes()[-3:]
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
        # the projection and result-building work below.
        proximal_events = [p for p in current_proximity_events if p.proximity_distance_meters <= threshold_m]
        if not proximal_events:
            return []

        proximal_feat_ids = {p.spatial_feature_id for p in proximal_events}

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

        subject_name = self.subject.name
        feature_group_name = self.config.proximal_features.name
        total_fix_count = len(latest_two)

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
            result.values = {
                "spatial_feature_name": feat_name,
                "proximity_dist_meters": round(prox.proximity_distance_meters, 2),
                "total_fix_count": total_fix_count,
                "subject_speed_kmhr": (
                    round(prox.subject_speed_kmhr, 2) if prox.subject_speed_kmhr is not None else None
                ),
                "subject_heading": round(prox.subject_heading, 2) if prox.subject_heading is not None else None,
                "feature_group_name": feature_group_name,
            }

            self.logger.info(result.message)
            das_analyzer_results.append(result)

        return das_analyzer_results
