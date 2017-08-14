from datetime import timedelta

import logging
import pymet.base
import pymet.eetools

from django.contrib.gis.geos import Point as DjangoPoint
from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.utils.translation import ugettext_lazy as _

from analyzers.utils import save_analyzer_event
from observations.models import SubjectTrackSegmentFilter
from activity.models import Event, EventType
from analyzers.models import EnvironmentalSubjectAnalyzerConfig, SubjectAnalyzerResult, OK, WARNING, CRITICAL

from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.base import SubjectAnalyzer

EVENT_PRIORITY_MAP = {
    CRITICAL: Event.PRI_URGENT,
    WARNING: Event.PRI_IMPORTANT,
    OK: Event.PRI_REFERENCE,
}


class EnvironmentalAnalyzer(SubjectAnalyzer):

    """ 
    Environmental Analyzer is a demonstrator for integration with Google Earth Engine.
    """

    def __init__(self, subject, config):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.subject = subject

    @classmethod
    def get_subject_analyzers(cls, subject):
        for ac in EnvironmentalSubjectAnalyzerConfig.objects.filter(subject_group__subjects=subject):
            yield cls(subject=subject, config=ac)

    def default_observations(self):
        '''
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        '''
        return self.subject.observations(last_hours=self.config.search_time_hours)

    def default_trajectory_filter(self):
        # Get trajectory filter based on subject. Might not exist.
        try:
            return SubjectTrackSegmentFilter.objects.filter(subject_type=self.subject.subject_subtype).first()
        except SubjectTrackSegmentFilter.DoesNotExist:
            pass

    # def analyze(self, observations=None, trajectory_filter=None, last_result=None):
    #
    #     # Get default observations list if one isn't provided
    #     observations = observations or self.default_observations()
    #
    #     # Use default trajectory_filter if one isn't provided
    #     trajectory_filter = trajectory_filter or self.default_trajectory_filter()
    #
    #     # Create Trajectory which is the input to the analysis.
    #     trajectory = self._create_trajectory(observations=observations, trajectory_filter_params=trajectory_filter)
    #     result = self.analyze_trajectory(trajectory)
    #
    #     self.save_analyzer_result(last_result=last_result, this_result=result)
    #     this_event = self.create_analyzer_event(last_result=last_result, this_result=result)
    #
    #     return result, this_event

    def analyze_trajectory(self, traj):
        """
        TODO: Add description.

        """

        # Get the relocation fixes in descending order
        fixes = traj.relocs.get_fixes('DESC')

        # Check to see if we have at least some data within the search time
        if len(fixes) == 0:
            raise InsufficientDataAnalyzerException

        # Create the analyzer result
        result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                       level=OK,
                                       message=self.subject.name + str(_(' is in a low ' +
                                                                         self.config.short_description + ' area.')),
                                       analyzer_revision=1,
                                       subject=self.subject)

        # Define the latest fix as the estimated time
        result.estimated_time = fixes[0].fixtime

        # Define the geometry to be the latest fix geometry
        result.geometry_collection = DjangoGeoColl([DjangoPoint(fixes[0].ogr_geometry.GetX(),
                                                                fixes[0].ogr_geometry.GetY())])

        mean_value = pymet.eetools.extract_point_values_from_image(relocs=traj.relocs,
                                                                   img_name=self.config.GEE_img_name,
                                                                   band_name=self.config.GEE_img_band_name,
                                                                   scale=self.config.scale_meters)

        if mean_value is not None:

            result.values = {
                'environmental_descriptor': self.config.short_description,
                'mean_value': mean_value,
                'img_name': self.config.GEE_img_name,
                'img_band_name': self.config.GEE_img_band_name,
                'total_fix_count': len(fixes),
            }

            if mean_value > self.config.threshold_value:
                # Modify analyzer result
                result.level = CRITICAL
                result.message = self.subject.name + \
                    str(_(' is in a high ' + self.config.short_description + ' area.'))
        return [result, ]

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
                message=this_result.message,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='environmental_value',  # environmental_value
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=this_result.values,
            )

        # Notify if there is a state transition from Critical/Warning back to
        # OK
        elif last_result is not None and (last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
            event_data = dict(
                message=this_result.message,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='environment_all_clear',  # environment_all_clear
                priority=EVENT_PRIORITY_MAP.get(
                    this_result.level, Event.PRI_REFERENCE),
                location=event_location_value,
                event_details=this_result.values,
            )

        if event_data:
            return save_analyzer_event(event_data)

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

            if last_result is not None:
                # Save the result if there was a transition from
                # Critical/Warning to OK
                if (this_result.level is OK) and (last_result.level in (CRITICAL, WARNING)):
                    this_result.save()
