from datetime import timedelta
import logging
import pymet

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point as DjangoPoint

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

    immobility_probability = models.FloatField()
    radius = models.FloatField(default=13.0)
    threshold_time = models.IntegerField(default=18000) #5 hours
    threshold_probability = models.FloatField(default=0.8)

    # these should go away...
    threshold_warning_cluster_ratio = models.FloatField(default=.8)
    threshold_critical_cluster_ratio = models.FloatField(default=1.0)

    def analyze(self, track):
        """ analyze track for immobile state. Only the 24 hours before the most
        recent observation are considered """

        super().analyze(track)

        if len(track) < 5:
            raise InsufficientDataAnalyzerException

        result = AnalyzerResult(self)
        result.analyzer_type = self.__class__.__name__

        # assume immobile until detected otherwise
        result.level = NOMINAL

        # truncate track to recent observations
        t_last_observation, p_last_observation = track.last_observation
        t_cutoff = t_last_observation - timedelta(seconds=self.threshold_time)
        track = track.truncate(before=t_cutoff)

        cluster_probability = cluster(track, self.radius)

        if cluster_probability >= self.threshold_warning_cluster_ratio:
            result.value = cluster_probability
            point = track.geo_series[-1]
            result.location = DjangoPoint(point.x, point.y)

            if cluster_probability >= self.threshold_critical_cluster_ratio:
                result.level = CRITICAL
                result.title = 'Subject is immobile'
                logger.info(result.title)

            else:
                result.level = WARNING
                result.title = 'Subject is almost immobile'
                logger.info(result.title)

        else:
            result.location = DjangoPoint(p_last_observation.x, p_last_observation.y)
            result.title = 'Subject is mobile'
            logger.info(result.title)

        return result


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
        if len(traj.getRelocations().getTimespanSeconds()) < self.threshold_time:
            raise InsufficientDataAnalyzerException

        # Get the relocation fixes in descending order
        fixes = traj.getRelocations().getFixes('DESC')

        # Create a blank cluster
        test_cluster = pymet.cluster.Cluster()

        # Create the analyzer result
        result = AnalyzerResult(self)
        result.analyzer_type = self.__class__.__name__
        result.level = NOMINAL
        result.title = 'Subject is mobile'
        #TODO: Do we need to assign a position to a Null result?

        #Test for immobility
        for i in range(len(fixes)):
            test_cluster.addFix(fixes[i])

            # Calculate the ratio of points within cluster threshold distance and total points in cluster
            cluster_pvalue = test_cluster.NumPointsWithinThreshold(self.radius) / \
                             test_cluster.getRelocations().getFixCount()

            cluster_timespan_seconds = test_cluster.getRelocations().getTimespanSeconds()

            if (cluster_pvalue >= self.threshold_probability) and (cluster_timespan_seconds >= self.threshold_time):
                # Create and analyzer result
                result = AnalyzerResult(self)
                result.analyzer_type = self.__class__.__name__
                result.level = CRITICAL
                result.position = DjangoPoint(test_cluster.getCentroidOGRPoint().GetX(),
                                              test_cluster.getCentroidOGRPoint().GetY())

                result.title = 'Subject is immobile'
                logger.info(result.title)

        return result









