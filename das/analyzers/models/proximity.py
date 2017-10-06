from django.contrib.gis.db import models
from analyzers.models.base import SubjectAnalyzerConfig
from mapping.models import SpatialFeatureGroupStatic


class ProximityAnalyzerConfig(SubjectAnalyzerConfig):

    threshold_time = models.IntegerField(null=False, default=86400)  # 24 hours

    threshold_dist_meters = models.FloatField(null=False, default=500.0)  # 500 meters

    proximal_features = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='proximal_features',
        verbose_name='This analyzer applies to proximity features in this SpatialFeatureGroupStatic.'
    )

