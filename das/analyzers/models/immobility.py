from datetime import timedelta
import logging

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

    radius = models.FloatField(default=13.0)
    threshold_time = models.IntegerField(default=18000)
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
