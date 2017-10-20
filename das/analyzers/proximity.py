import pymet
from django.utils.translation import ugettext_lazy as _
from django.contrib.gis.geos import Point as DjangoPoint
from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from activity.models import Event
from analyzers.utils import save_analyzer_event
from analyzers.models import SubjectAnalyzerResult, ProximityAnalyzerConfig, WARNING, CRITICAL
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.base import SubjectAnalyzer
from pymet.proximity import ProximityAnalysisParams, ProximityAnalysis
import logging

from osgeo import ogr


class ProximityAnalyzer(SubjectAnalyzer):

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject):
        for ac in ProximityAnalyzerConfig.objects.filter(subject_group__subjects=subject, is_active=True):
            yield cls(subject=subject, config=ac)

    def _create_proximity_analysis_params(self):
        sfs = []
        for feat in self.config.proximal_features.features.all():
            sfs.append(pymet.base.SpatialFeature(ogr_geometry=ogr.CreateGeometryFromWkt(feat.feature_geometry.wkt),
                                                 name=feat.name, unique_id=feat.id))

        return ProximityAnalysisParams(spatial_features=sfs)

    def default_observations(self):
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        return list(self.subject.observations(last_hours=self.config.search_time_hours))[-2:]

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
                    'proximal_distance': prox.proximity_distance_meters,
                    'total_fix_count': traj.relocs.fix_count,
                    'subject_speed_kmhr': prox.subject_speed_kmhr,
                    'subject_heading': prox.subject_heading,
                }

                self.logger.info(result.message)

                das_analyzer_results.append(result)

        return das_analyzer_results

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

    def create_analyzer_event(self, last_result=None, this_result=None):

        # no data to create an event so exit
        if not this_result:
            return

        event_data = None

        # Create a dict() location to satisfy our EventSerializer.
        event_location_value = {
            'longitude': this_result.geometry_collection[0].x,
            'latitude': this_result.geometry_collection[0].y
        }

        # Notify if result is critical or warning
        if this_result.level in (CRITICAL, WARNING):
            event_data = dict(
                title=this_result.title,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='analyzer_proximity',
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=this_result.values,
            )

        if event_data:
            return save_analyzer_event(event_data)
