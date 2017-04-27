from datetime import timedelta, datetime
import pytz
import logging
import pymet.base, pymet.cluster

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point as DjangoPoint
from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point
from django.db import transaction
from django.contrib.postgres.fields import DateTimeRangeField, JSONField
from observations.models import Observation, SubjectTrackSegmentFilter
from activity.models import Event, EventType
from analyzers.models.analyzer import SubjectAnalyzer, SubjectAnalyzerResult, OK, WARNING, CRITICAL

from analyzers.exceptions import InsufficientDataAnalyzerException

from analyzers.models.utils import cluster

logger = logging.getLogger(__name__)


class ImmobilityAnalyzer(SubjectAnalyzer):

    """ Immobility Analyzer for a Track.

    Based on the clustering algorithm described by Jake Wall in RTM_Appendix_A.pdf

    parameters:

    threshold_radius: radius of cluster.  Defaults to 13m as in the Wall document

    threshold_time: time in seconds the track is expected to be stationary.
        Defaults to 18000 seconds (5 hours) as in Wall

    threshold_warning_cluster_ratio: the proportion of observations in a sample which
        must be inside a cluster to generate a CRITICAL.  Default 0.8 as in Wall

     """

    threshold_radius = models.FloatField(null=False, default=13.0)
    threshold_time = models.IntegerField(null=False, default=18000)  # 5 hours
    threshold_probability = models.FloatField(null=False, default=0.8)
    search_time_hours = models.FloatField(null=False, default=24.0)

    @property
    def event_type(self):
        return EventType.objects.get_by_value('analyzer_immobility')

    def _create_trajectory(self, subject):
        """
        Hydrate the trajectory 
        """
        def create_fix(observation):
            gp = pymet.base.GeoPoint(observation.location.x, observation.location.y, 0.0)
            fix = pymet.base.Fix(gp, observation.recorded_at)
            return fix

        fixes = [create_fix(x) for x in subject.observations(last_hours=self.search_time_hours)]
        relocs = pymet.base.Relocations(fixes)
        traj = pymet.base.Trajectory(relocs)

        # Look up the StraightTrackSegmentFilter settings for the given SubjectType
        traj_filter_params = SubjectTrackSegmentFilter.objects.filter(subject_type=subject.subject_subtype).first()
        if traj_filter_params is not None:
            traj_filter = pymet.base.TrajSegFilter(max_speed_kmhr=traj_filter_params.speed_KmHr)
            traj.traj_seg_filter = traj_filter  # Set the trajectory segment filter on the trajectory

        return traj

    def analyze(self, subject, last_result):
        traj = self._create_trajectory(subject)
        return self.analyze_trajectory(subject, last_result, traj)

    def analyze_trajectory(self,subject, last_result, traj):
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

        :param traj:
        :return:

        """

        # Check to see if we have data that spans the threshold time otherwise impossible to calculate
        if timedelta(seconds=traj.relocs.timespan_seconds) < timedelta(seconds=self.threshold_time):
            raise InsufficientDataAnalyzerException

        # Get the relocation fixes in descending order
        fixes = traj.relocs.get_fixes('DESC')

        # Create a blank cluster
        test_cluster = pymet.cluster.Cluster()

        # Create the analyzer result
        result = SubjectAnalyzerResult(subject_analyzer=self,
                                       level=OK,
                                       message=subject.name + ' is mobile',
                                       analyzer_revision=1,subject=subject)

        # Test for immobility
        for i in range(len(fixes)):
            test_cluster.add_fix(fixes[i])

            # Calculate the ratio of points within cluster threshold distance and total points in cluster
            cluster_pvalue = test_cluster.threshold_point_count(self.threshold_radius) / test_cluster.relocs.fix_count

            cluster_timespan_seconds = test_cluster.relocs.timespan_seconds

            result.geometry_collection = DjangoGeoColl([DjangoPoint(test_cluster.centroid.GetX(),
                                                               test_cluster.centroid.GetY())])

            result.estimated_time = test_cluster.relocs.earliest_fix

            result.values = {
                'probability_value': cluster_pvalue,
                'cluster_radius': test_cluster.cluster_radius,
                'cluster_fix_count': test_cluster.threshold_point_count(self.threshold_radius),
                'total_fix_count': test_cluster.relocs.fix_count,
            }

            if (cluster_pvalue >= self.threshold_probability) and (cluster_timespan_seconds >= self.threshold_time):
                # Modify analyzer result
                result.level = CRITICAL
                result.notes = subject.name + ' is immobile'
                break

        logger.info(result.message)
        self.save_analyzer_result(last_result=last_result, this_result=result)
        this_event = self.create_analyzer_event(last_result=last_result, this_result=result)

        return result, this_event

    def create_analyzer_event(self, last_result=None, this_result=None):
        event_data = dict()
        # no data to create an event so exit
        if this_result is not None:

            # Notify if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                event_data = dict(
                    message=this_result.notes,
                    time=this_result.estimated_time,
                    provenance=Event.PC_ANALYZER,
                    event_type=EventType.objects.get_by_value('immobility'),
                    priority=Event.PRI_REFERENCE,
                    location=dict(longitude=this_result.location.x, latitude=this_result.location.y)
                )

            # Notify if there is a state transition from Critical/Warning back to OK
            if last_result is not None:
                if (last_result.level in (CRITICAL, WARNING)) and this_result.level is OK:
                    event_data = dict(
                        message=this_result.notes,
                        time=this_result.estimated_time,
                        provenance=Event.PC_ANALYZER,
                        event_type=EventType.objects.get_by_value('immobility_all_clear'),
                        priority=Event.PRI_REFERENCE,
                        location=dict(longitude=this_result.location.x, latitude=this_result.location.y)
                    )

        return Event.objects.create_event(**event_data)

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()



