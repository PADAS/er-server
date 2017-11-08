from django.contrib.gis.db import models
from analyzers.models.base import SubjectAnalyzerConfig
from mapping.models import SpatialFeatureGroupStatic


class GeofenceAnalyzerConfig(SubjectAnalyzerConfig):

    """ Geofence Analyzer for a Track.

        Based on the algorithm described by Jake Wall in RTM_Appendix_A.pdf

    """

    threshold_time = models.IntegerField(null=False, default=43200, verbose_name='Threshold time (seconds)')  # 12 hours

    geofences = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='geofences',
        verbose_name='This analyzer applies to geofences in this SpatialFeatureGroupStatic.'
    )

    containment_regions = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='containmentregions',
        verbose_name='This analyzer applies to containment polygons in this SpatialFeatureGroupStatic.'
    )
