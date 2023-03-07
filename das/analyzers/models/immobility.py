from django.contrib.gis.db import models
from django.utils.translation import gettext as _

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
        null=False, default=13.0, verbose_name='Threshold Radius (meters)',
        help_text=_('This determines the circle within which a Subject\'s points will be considered stationary.'))
    threshold_time = models.IntegerField(
        # 5 hours
        null=False, default=18000, verbose_name='Threshold Time (seconds)',
        help_text=_(
            'This is the maximum time frame a Subject is expected to be stationary.')
    )

    threshold_probability_helptext = '''
    This indicates a ratio threshold for (number of stationary points) / (total points). If the data indicates
    a higher ratio, the analyzer will produce an event.
    '''
    threshold_probability = models.FloatField(null=False, default=0.8,
                                              verbose_name='Threshold ratio',
                                              help_text=_(threshold_probability_helptext))

    analyzer_category = 'immobility'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _('Immobility Analyzer')
        verbose_name_plural = _('Immobility Analyzers')
