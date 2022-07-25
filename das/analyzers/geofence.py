import logging

import pymet
from osgeo import ogr

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.utils.translation import gettext_lazy as _

from activity.models import Event, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.geofence_crossings_analysis import DasGeofenceAnalysis
from analyzers.models import (CRITICAL, WARNING, GeofenceAnalyzerConfig,
                              SubjectAnalyzerResult)
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.utils import save_analyzer_event
from mapping.models import SpatialFeature

logger = logging.getLogger(__name__)

geofence_eventtype_natural_key = 'geofence_break'


class GeofenceAnalyzer(SubjectAnalyzer):
    """ Geofence analyzer to determine locations and estimated times where a subject's trajectory
     crosses a set of virtual fences.
     Return: a list of GeofenceAnalyzerResult
     """

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject):
        subject_groups = subject.get_ancestor_subject_groups()
        for ac in GeofenceAnalyzerConfig.objects.filter(
                subject_group__in=subject_groups, is_active=True):
            yield cls(subject=subject, config=ac)

    def _create_geofence_analysis_param(self):
        """ Hydrate GeofenceAnalysisParams"""
        gfs, crs = [], []

        # Get the SpatialFeatureGroupStatic containing the fences
        if self.config.critical_geofence_group:
            for feat in self.config.critical_geofence_group.features.all():
                vf = pymet.geofence.Geofence(ogr_geometry=ogr.CreateGeometryFromWkt(feat.feature_geometry.wkt),
                                             fence_name=feat.name,
                                             unique_id=feat.id,
                                             warn_level='CRITICAL')
                gfs.append(vf)

        if self.config.warning_geofence_group:
            for feat in self.config.warning_geofence_group.features.all():
                vf = pymet.geofence.Geofence(ogr_geometry=ogr.CreateGeometryFromWkt(feat.feature_geometry.wkt),
                                             fence_name=feat.name,
                                             unique_id=feat.id,
                                             warn_level='WARNING')
                gfs.append(vf)

        # Get the SpatialFeatureGroupStatic containing the containment regions
        if self.config.containment_regions:
            for feat in self.config.containment_regions.features.all():
                cr = pymet.base.SpatialFeature(ogr_geometry=ogr.CreateGeometryFromWkt(feat.feature_geometry.wkt),
                                               name=feat.name,
                                               unique_id=feat.id)
                crs.append(cr)

        return pymet.geofence.GeofenceAnalysisParams(geofences=gfs, regions=crs)

    def default_observations(self):
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        logger.info('Using default observations for subject %s', self.subject)
        # observations get passed back in temporally descending order
        if self.config.search_time_hours <= 0:
            return list(self.subject.observations()[:2])
        else:
            return list(self.subject.observations(last_hours=self.config.search_time_hours))

    def analyze_trajectory(self, traj=None):
        """
        A function to analyze the trajectory of a subject in relation to a set of virtual fences and regions to
        determine where/when the polylines were crossed and what the containment of the individual was before and
        after any geofence crossings
        """

        if traj is None:
            return

        _analysis_params = self._create_geofence_analysis_param()

        # Generate a list of crossings
        cross_results = DasGeofenceAnalysis.calc_crossings(
            _analysis_params, [traj])

        das_analyzer_results = []
        for cross in cross_results.geofence_crossings:
            # Create a DAS Analyser result based on each crossing event

            # Create the analyzer result
            result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                           title=self.subject.name,
                                           message=self.subject.name,
                                           analyzer_revision=1,
                                           subject=self.subject)

            # Define the latest fix as the estimated time
            result.estimated_time = cross.est_cross_fix.fixtime

            # Define the geometry to be the latest fix geometry
            result.geometry_collection = DjangoGeoColl([DjangoPoint(cross.est_cross_fix.geopoint.ogr_geometry.GetX(),
                                                                    cross.est_cross_fix.geopoint.ogr_geometry.GetY())])

            # Set the event status level
            result.level = WARNING if cross.warn_level == 'WARNING' else CRITICAL

            # Get the geofence name and final containing region names to form
            # the analyzer result message
            vf_name = SpatialFeature.objects.get(pk=cross.geofence_id).name
            result.title = f'{self.subject.name} {_("crossed")} {vf_name}.'

            contain_names = ','.join([SpatialFeature.objects.get(pk=contain_id).name
                                      for contain_id in cross.end_region_ids])
            if not contain_names:
                contain_names = 'Unknown region'

            result.message = result.title + \
                str(_(' Subject now in: ')) + contain_names

            result.values = {
                'geofence_name': vf_name or 'Un-named Feature',
                'contain_regions': contain_names,
                'total_fix_count': traj.relocs.fix_count,
                'subject_speed_kmhr': cross.subject_speed_kmhr,
                'subject_heading': cross.subject_heading,
            }

            self.logger.info(result.message)

            das_analyzer_results.append(result)

        return das_analyzer_results

    def save_analyzer_result(self, last_result=None, this_result=None):

        # Suppress saving a new result if it will duplicate the last result.
        if not this_result or last_result and last_result.estimated_time == this_result.estimated_time:
            logger.info('Calculated a duplicate result, so not saving it.')
            return

        if this_result.level in (CRITICAL, WARNING):
            this_result.save()

    def create_analyzer_event(self, last_result=None, this_result=None):

        if not this_result or this_result.level not in (CRITICAL, WARNING):
            return

        try:
            Event.objects.get(related_subjects=self.subject,
                              event_type=EventType.objects.get(
                                  value=geofence_eventtype_natural_key),
                              event_time=this_result.estimated_time,
                              location=this_result.geometry_collection[0])

            logger.info('This event is already recorded, so skipping it now.')
            return
        except Event.DoesNotExist:

            event_priority = EVENT_PRIORITY_MAP.get(
                this_result.level, Event.PRI_URGENT)

            event_details = {'name': self.subject.name}
            event_details.update(this_result.values)

            # Create a dict() location to satisfy our EventSerializer.
            event_location_value = {
                'longitude': this_result.geometry_collection[0].x,
                'latitude': this_result.geometry_collection[0].y
            }
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type=geofence_eventtype_natural_key,
                priority=event_priority,
                location=event_location_value,
                event_details=event_details,
                related_subjects=[{'id': self.subject.id}, ],
            )

            return save_analyzer_event(event_data)
