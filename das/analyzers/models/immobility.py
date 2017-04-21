from datetime import timedelta
import logging
import pymet.base, pymet.cluster

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point as DjangoPoint
from django.contrib.gis.geos import Point
from django.db import transaction
from django.contrib.postgres.fields import DateTimeRangeField, JSONField
from observations.models import Observation, SubjectTrackSegmentFilter
from activity.models import EventType
from .analyzer import Analyzer, AnalyzerResult, NOMINAL, WARNING, CRITICAL
from ..exceptions import InsufficientDataAnalyzerException

from .utils import cluster

logger = logging.getLogger(__name__)


class ImmobilityAnalyzer(Analyzer):

    """ Immobility Analyzer for a Track.

    Based on the clustering algorithm described by Jake Wall in RTM_Appendix_A.pdf

    parameters:

    radius: radius of cluster.  Defaults to 13m as in the Wall document

    threshold_time: time in seconds the track is expected to be stationary.
        Defaults to 18000 (5 hours) as in Wall

    threshold_warning_cluster_ratio: the proportion of observations in a sample which
        must be inside a cluster to generate a WARNING.  Default 0.8 as in Wall

    threshold_critical_cluster_ratio: the proportion of observations in a sample which
        must be inside a cluster to generate a CRITICAL.  Default 1.0

     """

    @property
    def event_type(self):
        return EventType.objects.get_by_value('analyzer_immobility')

    radius = models.FloatField(null=False, default=13.0)
    threshold_time = models.IntegerField(null=False, default=18000)  # 5 hours
    threshold_probability = models.FloatField(null=False, default=0.8)
    search_time_hours = models.FloatField(null=False, default=24.0)

    """ Hydrate the trajectory """
    def create_trajectory(self):

        def create_fix(observation):

            gp = pymet.base.GeoPoint(observation.location.x, observation.location.y, 0.0)
            fix = pymet.base.Fix(gp, observation.recorded_at)
            return fix

        fixes = [create_fix(x) for x in self.subject.observations(last_hours=self.search_time_hours)]
        relocs = pymet.base.Relocations(fixes)
        traj = pymet.base.Trajectory(relocs)

        # Look up the StraightTrackSegmentFilter settings for the given SubjectType
        traj_filter_params = SubjectTrackSegmentFilter.objects.filter(subject_type=self.subject.subject_subtype).first()
        if traj_filter_params is not None:
            traj_filter = pymet.base.TrajSegFilter(max_speed_kmhr=traj_filter_params.speed_KmHr)
            traj.traj_seg_filter = traj_filter  # Set the trajectory segment filter on the trajectory

        return traj

    def analyze(self, track=None):
        super().analyze()
        traj = self.create_trajectory()
        return self.analyze_jake(traj)

    def analyze_jake(self, traj):
        """

        A function to search for immobility within a movement trajectory. Assumes we start with a filtered
        trajectory spanning some period of time. The algorithm will work backwards through the trajectory's
        relocations and build a cluster. Looks to see if the cluster characteristics match immobility criteria
        (ie., timespan is gte than the threshold_time, and the cluster probability is gte to the threshold_probability)

        Note that this is a simplified version of the full clustering algorithm since it's only looking at data within
        threshold time and will not figure out the true start of an immobility without looking backwards through all

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
        result = AnalyzerResult(self)
        result.analyzer_type = self.__class__.__name__
        result.level = NOMINAL
        result.title = 'Subject is mobile'

        # Test for immobility
        for i in range(len(fixes)):
            test_cluster.add_fix(fixes[i])

            # Calculate the ratio of points within cluster threshold distance and total points in cluster
            cluster_pvalue = test_cluster.threshold_point_count(self.radius) / test_cluster.relocs.fix_count

            cluster_timespan_seconds = test_cluster.relocs.timespan_seconds

            result.position = DjangoPoint(test_cluster.centroid.GetX(), test_cluster.centroid.GetY())

            if (cluster_pvalue >= self.threshold_probability) and (cluster_timespan_seconds >= self.threshold_time):
                # Modify analyzer result
                result.level = CRITICAL
                result.title = 'Subject is immobile'
                break

        logger.info(result.title)
        return result


class ImmobilityAnalyzerResult(AnalyzerResult):
    location = models.PointField()
    analyzer = models.ForeignKey('ImmobilityAnalyzer', on_delete=models.CASCADE)
    probability_value = models.FloatField()
    additional = JSONField()
    cluster_radius = models.FloatField()
    cluster_fix_count = models.IntegerField()
    time_threshold_hours = models.FloatField()
    probability_threshold = models.FloatField()
    cluster_timespan = DateTimeRangeField()
    total_fix_count = models.IntegerField()
    observations = models.ManyToManyField(Observation, related_name='+')
