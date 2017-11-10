from django.contrib.gis.db import models
from analyzers.models.base import SubjectAnalyzerConfig


class EnvironmentalSubjectAnalyzerConfig(SubjectAnalyzerConfig):

    """
     Environmental analyzer per Subject.
    """

    threshold_value = models.FloatField(null=False, default=0.0)
    # The scale for the analysis in GEE (meters)
    scale_meters = models.FloatField(null=False, default=500.0)
    GEE_img_name = models.CharField(null=False, max_length=100, default='')
    GEE_img_band_name = models.CharField(
        null=False, max_length=50, default='b1')
    short_description = models.CharField(
        null=False, max_length=50)  # e.g. 'Human Footprint'

    report_friendly_type = 'environmental'
