from datetime import timedelta

import logging
import pymet.base, pymet.cluster

from django.contrib.gis.geos import Point as DjangoPoint
from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.utils.translation import ugettext_lazy as _

from analyzers.utils import save_analyzer_event
from observations.models import SubjectTrackSegmentFilter
from activity.models import Event, EventType
from analyzers.models import ImmobilityAnalyzerConfig, SubjectAnalyzerResult, OK, WARNING, CRITICAL

from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers import SubjectAnalyzer

EVENT_PRIORITY_MAP = {
    CRITICAL: Event.PRI_URGENT,
    WARNING: Event.PRI_IMPORTANT,
    OK: Event.PRI_REFERENCE,
}

class ImmobilityAnalyzer(SubjectAnalyzer):

    """ Immobility Analyzer for a Track.

    Based on the clustering algorithm described by Jake Wall in RTM_Appendix_A.pdf

    configuration parameters:

    threshold_radius: radius of cluster.  Defaults to 13m as in the Wall document

    threshold_time: time in seconds the track is expected to be stationary.
        Defaults to 18000 seconds (5 hours) as in Wall

    threshold_warning_cluster_ratio: the proportion of observations in a sample which
        must be inside a cluster to generate a CRITICAL.  Default 0.8 as in Wall

     """
    def __init__(self, subject, config):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.subject = subject

    @classmethod
    def get_subject_analyzers(cls, subject):
        for ac in ImmobilityAnalyzerConfig.objects.filter(subject_group__subjects=subject):
            yield cls(subject=subject, config=ac)

    def _create_trajectory(self, observations, trajectory_filter_params=None):
        """
        Hydrate the trajectory
        """
        def create_fix(observation):
            gp = pymet.base.GeoPoint(observation.location.x, observation.location.y, 0.0)
            fix = pymet.base.Fix(gp, observation.recorded_at)
            return fix

        # Create a relocations object
        fixes = [create_fix(x) for x in observations]
        relocs = pymet.base.Relocations(fixes)

        # Filter the relocations for junk coordinates
        coord_filter = pymet.base.RelocsCoordinateFilter()
        relocs.apply_fix_filter(coord_filter)

        # Filter the relocations based on speed
        speed_threshold = float('Inf')

        if trajectory_filter_params is not None:
            speed_threshold = trajectory_filter_params.speed_KmHr
        speed_filter = pymet.base.RelocsSpeedFilter(max_speed_kmhr=speed_threshold)
        relocs.apply_fix_filter(speed_filter)

        # Create a trajectory from the relocations
        traj = pymet.base.Trajectory(relocs)

        return traj

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

    def analyze(self, observations=None, trajectory_filter=None, last_result=None):

        # Get default observations list if one isn't provided
        observations = observations or self.default_observations()

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.default_trajectory_filter()

        # Create Trajectory which is the input to the analysis.
        trajectory = self._create_trajectory(observations=observations, trajectory_filter_params=trajectory_filter)
        result = self.analyze_trajectory(trajectory)

        self.save_analyzer_result(last_result=last_result, this_result=result)
        this_event = self.create_analyzer_event(last_result=last_result, this_result=result)

        return result, this_event

    def analyze_trajectory(self, traj):
        """

        A function to search for immobility within a movement trajectory. Assumes we start with a filtered
        trajectory spanning some period of time. The algorithm will work backwards through the trajectory's
        relocations and build a cluster. Looks to see if the cluster characteristics match immobility criteria
        (ie., timespan is gte than the threshold_time, and the cluster probability is gte to the threshold_probability)

        Note that this is a simplified version of the full clustering algorithm since it's only looking at data within
        threshold time and will not figure out the true start of an immobility without looking backwards through all
        possible points

        TODO: Update the analyzer_immobility model to include more info about the immobility result:

            1) immobility start time
            2) immobility probability
            3) immobility cluster fix count
            4) algorithm provenance

        """

        # Check to see if we have data that spans the threshold time otherwise impossible to calculate
        if timedelta(seconds=traj.relocs.timespan_seconds) < timedelta(seconds=self.config.threshold_time):
            raise InsufficientDataAnalyzerException

        # Get the relocation fixes in descending order
        fixes = traj.relocs.get_fixes('DESC')

        # Create a blank cluster
        test_cluster = pymet.cluster.Cluster()

        # Create the analyzer result
        result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                       level=OK,
                                       message=self.subject.name + str(_(' is moving')),
                                       analyzer_revision=1,
                                       subject=self.subject)

        # Define the latest fix as the estimated time
        result.estimated_time = fixes[0].fixtime

        # Define the geometry to be the latest fix geometry
        result.geometry_collection = DjangoGeoColl([DjangoPoint(fixes[0].ogr_geometry.GetX(),
                                                                fixes[0].ogr_geometry.GetY())])

        # Test for immobility
        for f in fixes:
            test_cluster.add_fix(f)

            # Calculate the ratio of points within cluster threshold distance and total points in cluster
            cluster_pvalue = test_cluster.threshold_point_count(self.config.threshold_radius) / \
                             test_cluster.relocs.fix_count

            cluster_timespan_seconds = test_cluster.relocs.timespan_seconds


            if (cluster_pvalue >= self.config.threshold_probability) and \
                    (cluster_timespan_seconds > self.config.threshold_time):
                # Todo: gte comparison  on the timespan but switched to achieve parity with STE system
                # Modify analyzer result
                result.level = CRITICAL
                result.message = self.subject.name + str(_(' is immobile'))
                result.geometry_collection = DjangoGeoColl([DjangoPoint(test_cluster.centroid.GetX(),
                                                                        test_cluster.centroid.GetY())])
                result.values = {
                    'probability_value': cluster_pvalue,
                    'cluster_radius': test_cluster.cluster_radius,
                    'cluster_fix_count': test_cluster.threshold_point_count(self.config.threshold_radius),
                    'total_fix_count': test_cluster.relocs.fix_count,
                }
                #break

        self.logger.info(result.message)

        return result

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
                event_type='immobility',
                priority=EVENT_PRIORITY_MAP.get(this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=this_result.values,
            )

        # Notify if there is a state transition from Critical/Warning back to OK
        elif last_result is not None and (last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
            event_data = dict(
                message= this_result.message,
                event_time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type='immobility_all_clear',
                priority=EVENT_PRIORITY_MAP.get(this_result.level, Event.PRI_REFERENCE),
                location=event_location_value,
                event_details = this_result.values,
            )

        if event_data:
            return save_analyzer_event(event_data)

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

            if last_result is not None:
                # Save the result if there was a transition from Critical/Warning to OK
                if (this_result.level is OK) and (last_result.level in (CRITICAL, WARNING)):
                    this_result.save()



