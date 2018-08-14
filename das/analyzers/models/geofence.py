from django.contrib.gis.db import models
from analyzers.models.base import SubjectAnalyzerConfig
from mapping.models import SpatialFeatureGroupStatic


class GeofenceAnalyzerConfig(SubjectAnalyzerConfig):

    """ Geofence Analyzer for a Track.

        Based on the algorithm described by Jake Wall in RTM_Appendix_A.pdf

    """

    threshold_time = models.IntegerField(
        null=False, default=43200, verbose_name='Threshold time (seconds)')  # 12 hours

    critical_geofence_group = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='+',
        verbose_name='Critical geo-fences for this analyzer'
    )

    warning_geofence_group = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='+',
        verbose_name='Warning geo-fences for this analyzer'
    )

    containment_regions = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='+',
        verbose_name='This analyzer applies to containment polygons in this SpatialFeatureGroupStatic.'
    )

    @property
    def warning_geofences(self):
        return self.geofences.features.filter(feature_type__name='Geofence_Warning')

    @property
    def primary_geofences(self):
        return self.geofences.features.filter(feature_type__name='Geofence_Primary')

    analyzer_category = 'geofence'
