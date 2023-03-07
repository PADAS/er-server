from django.contrib.gis.db import models
from django.utils.translation import gettext as _

from analyzers.models.base import SubjectAnalyzerConfig


class LowSpeedPercentileAnalyzerConfig(SubjectAnalyzerConfig):

    low_threshold_percentile = models.FloatField(null=False, default=0.01)

    # the default value to use when there is no speed_profile available
    # should set this to the global median low speed value for the
    # corresponding percentile
    default_low_speed_value = models.FloatField(
        null=False, default=0.05)  # 0.05 Km/Hr

    analyzer_category = 'low_speed'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _('Low-Speed Analyzer (Percentile method)')
        verbose_name_plural = _('Low-Speed Analyzers (Percentile method)')


class LowSpeedWilcoxAnalyzerConfig(SubjectAnalyzerConfig):

    low_speed_probability_cutoff = models.FloatField(null=False, default=0.001)

    analyzer_category = 'low_speed'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _('Low-Speed Analyzer (Wilcox method)')
        verbose_name_plural = _('Low-Speed Analyzers (Wilcox method)')
