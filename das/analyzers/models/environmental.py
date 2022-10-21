from django.contrib.gis.db import models
from django.utils.translation import gettext as _

from analyzers.models.base import SubjectAnalyzerConfig


class EnvironmentalSubjectAnalyzerConfig(SubjectAnalyzerConfig):

    """
     Environmental analyzer per Subject.
    """

    threshold_value = models.FloatField(null=False, default=0.0)
    # The scale for the analysis in GEE (meters)
    scale_meters = models.FloatField(null=False, default=500.0)
    GEE_img_name = models.CharField(
        null=False, max_length=100, default='', verbose_name='Google Earth Engine Image Name')
    GEE_img_band_name = models.CharField(
        null=False, max_length=50, default='b1', verbose_name='Google Earth Engine Image Band Name',)
    short_description = models.CharField(
        null=False, max_length=50)  # e.g. 'Human Footprint'

    analyzer_category = 'environmental'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _('Google Earth Engine Analyzer')
        verbose_name_plural = _('Google Earth Engine Analyzers')
