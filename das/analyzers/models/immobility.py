from django.contrib.gis.db import models
from django.utils.translation import ugettext as _
from analyzers.models.base import SubjectAnalyzerConfig


class ImmobilityAnalyzerConfig(SubjectAnalyzerConfig):

    """ Immobility Analyzer for a Track.

    Based on the clustering algorithm described by Jake Wall in RTM_Appendix_A.pdf

    parameters:

    threshold_radius: radius of cluster.  Defaults to 13m as in the Wall document

    threshold_time: time in seconds the track is expected to be stationary.
        Defaults to 18000 seconds (5 hours) as in Wall

    threshold_warning_cluster_ratio: the proportion of observations in a sample which
        must be inside a cluster to generate a CRITICAL.  Default 0.8 as in Wall

     """

    threshold_radius = models.FloatField(
        null=False, default=13.0, verbose_name='Threshold Radius (meters)')
    threshold_time = models.IntegerField(
        null=False, default=18000, verbose_name='Threshold Time (seconds)')  # 5 hours
    threshold_probability = models.FloatField(null=False, default=0.8)

    analyzer_category = 'immobility'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _('Immobility Analyzer')
        verbose_name_plural = _('Immobility Analyzers')
