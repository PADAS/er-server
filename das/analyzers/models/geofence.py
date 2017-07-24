from django.contrib.gis.db import models
from analyzers.models.base import SubjectAnalyzerConfig


class GeofenceAnalyzerConfig(SubjectAnalyzerConfig):

    """ Geofence Analyzer for a Track.

        Based on the algorithm described by Jake Wall in RTM_Appendix_A.pdf

        parameters:

        threshold_time: time in seconds the track is expected to be stationary.
            Defaults to 18000 seconds (5 hours) as in Wall
         """

    threshold_time = models.IntegerField(null=False, default=18000)  # 5 hours
