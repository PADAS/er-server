import json
import logging
import uuid

import pymet
from osgeo import ogr
from pymet.proximity import ProximityAnalysis, ProximityAnalysisParams

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.utils.translation import gettext_lazy as _

from activity.models import Event, EventCategory, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.models import (CRITICAL, WARNING,
                              FeatureProximityAnalyzerConfig,
                              SubjectAnalyzerResult)
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.utils import save_analyzer_event


class ProximityAnalyzer(SubjectAnalyzer):

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def subject_analyzers(cls, subject, analyzer_class):
        subject_groups = subject.get_ancestor_subject_groups()
        for ac in analyzer_class.objects.filter(
                subject_group__in=subject_groups, is_active=True):
            yield cls(subject=subject, config=ac)

    def default_observations(self):
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        # observations get passed back in temporally descending order
        if self.config.search_time_hours <= 0:
            return list(self.subject.observations())[:2]
        else:
            return list(self.subject.observations(last_hours=self.config.search_time_hours))[:2]

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

    def value_to_display(self, value):
        return ' '.join(x.capitalize() or '_' for x in value.split('_'))

    def evaluate_return_value(self, value):
        if not isinstance(value, str):
            value = value[0]
        return value

    def verify_event_type(self, this_result):
        from analyzers.subject_proximity import (
            SUBJECT_PROXIMITY_SCHEMA, SubjectProximityAnalyzerConfig)
        et_value = this_result.subject_analyzer.analyzer_category
        et_display = self.value_to_display(et_value)
        et_defaults_dict = dict(display=et_display)

        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))
        et, created = EventType.objects.get_or_create(
            value=et_value, category=ec,
            defaults=et_defaults_dict)

        if created and isinstance(this_result.subject_analyzer, SubjectProximityAnalyzerConfig):
            et.schema = json.dumps(
                SUBJECT_PROXIMITY_SCHEMA, indent=2, default=str)
            et.save()
        return et_value

    def create_analyzer_event(self, last_result=None, this_result=None):

        # no data to create an event so exit
        if not this_result:
            return

        event_data = None

        event_details = {'name': self.subject.name}
        event_details.update(this_result.values)

        # Create a dict() location to satisfy our EventSerializer.
        event_location_value = {
            'longitude': this_result.geometry_collection[0].x,
            'latitude': this_result.geometry_collection[0].y
        }

        event_type = self.verify_event_type(this_result)
        relate_subjects = [{'id': self.subject.id}]

        if this_result.values.get('subject_2_id'):
            subject_2_id = self.evaluate_return_value(
                this_result.values.get('subject_2_id'))
            relate_subjects.append({'id': uuid.UUID(subject_2_id)})

        # Notify if result is critical or warning
        if this_result.level in (CRITICAL, WARNING):
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type=event_type,
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_URGENT),
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

    def _create_proximity_analysis_params(self):
        sfs = []
        for feat in self.config.proximal_features.features.all():
            sfs.append(pymet.base.SpatialFeature(ogr_geometry=ogr.CreateGeometryFromWkt(feat.feature_geometry.wkt),
                                                 name=feat.name, unique_id=feat.id))

        return ProximityAnalysisParams(spatial_features=sfs)

    def analyze_trajectory(self, traj=None):
        """
        A function to analyze the trajectory of a subject in relation to a set of spatial features and regions to
        determine where/when the subject was proximal to the spatial feature
         and what the containment of the individual was before and after any proximal events
        """

        if traj is None:
            return

        analysis_params = self._create_proximity_analysis_params()

        # Subsample trajectory to the last two fixes
        traj = pymet.base.Trajectory(relocs=pymet.base.Relocations(fixes=traj.relocs.get_fixes()[-2:],
                                                                   subject_id=traj.relocs.subject_id))

        proximity_results = ProximityAnalysis.calc_proximity_events(proximity_analysis_params=analysis_params,
                                                                    trajectories=[traj])

        das_analyzer_results = []
        for prox in proximity_results.proximity_events:
            # Create a DAS Analyser result based on each proximity event within
            # the threshold distance
            if prox.proximity_distance_meters <= self.config.threshold_dist_meters:

                # Create the analyzer result
                result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                               title=self.subject.name + str(_(' proximal to ')) +
                                               prox.spatial_feature_name + '.',
                                               level=CRITICAL,
                                               message=self.subject.name + str(_(' proximal to ')) +
                                               prox.spatial_feature_name + '.',
                                               analyzer_revision=1,
                                               subject=self.subject)

                # Define the latest fix as the estimated time
                result.estimated_time = prox.proximal_fix.fixtime

                # Define the geometry to be the latest fix geometry
                result.geometry_collection = DjangoGeoColl(
                    [DjangoPoint(prox.proximal_fix.geopoint.ogr_geometry.GetX(),
                                 prox.proximal_fix.geopoint.ogr_geometry.GetY())])

                result.values = {
                    'spatial_feature_name': prox.spatial_feature_name,
                    'proximity_dist_meters': prox.proximity_distance_meters,
                    'total_fix_count': traj.relocs.fix_count,
                    'subject_speed_kmhr': prox.subject_speed_kmhr,
                    'subject_heading': prox.subject_heading,
                }

                self.logger.info(result.message)

                das_analyzer_results.append(result)
        return das_analyzer_results
