from django.contrib.gis.db import models
from django.utils.translation import ugettext as _
from analyzers.models.base import SubjectAnalyzerConfig
from mapping.models import SpatialFeatureGroupStatic


class ProximityAnalyzerConfig(SubjectAnalyzerConfig):

    threshold_time = models.IntegerField(null=False, default=86400)  # 24 hours

    threshold_dist_meters = models.FloatField(
        null=False, default=500.0,
        verbose_name="A proximity event occurs when a subject's path passes "
                     "within this distance of a designated spatial feature."
                     "A subject's path is drawn using a straight line between "
                     "reported positions.")  # 500 meters

    proximal_features = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='proximal_features',
        verbose_name='This analyzer applies to proximity features in this SpatialFeatureGroupStatic.'
    )

    analyzer_category = 'proximity'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        permissions = (('view_proximityanalyzerconfig',
                        'Can view Proximity Analyzer Configurations'), )
        verbose_name = _('Proximity Analyzer')
        verbose_name_plural = _('Proximity Analyzers')
