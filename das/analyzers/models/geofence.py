from django.contrib.gis.db import models
from django.utils.translation import gettext as _

from analyzers.models.base import SubjectAnalyzerConfig
from mapping.models import SpatialFeatureGroupStatic


class GeofenceAnalyzerConfig(SubjectAnalyzerConfig):

    """ Geofence Analyzer for a Track.

        Based on the algorithm described by Jake Wall in RTM_Appendix_A.pdf

    """

    threshold_time = models.IntegerField(
        # 12 hours
        null=False, default=43200, verbose_name='Threshold time (seconds)',
        help_text=_('This does not apply to geofence analysis.')
    )

    critical_geofence_group = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_('Critical geo-fences'),
        help_text=_('A <span style="color:#fff;padding:2px 10px; background-color: #c00; border-radius:3px;">red</span> alert will be recorded when a subject breaks a geo-fence in this Spatial Feature Group.')
    )

    warning_geofence_group = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_('Warning geo-fences'),
        help_text=_('An <span style="color:#000;padding:2px 10px; background-color: #fead38; border-radius:3px;">amber</span> alert will be recorded when a subject breaks a geo-fence in this Spatial Feature Group.')
    )

    containment_regions = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_('Containment Regions'),
        help_text=_(
            'A geo-fence break report will indicate a subject\'s latest location within one of these containment areas.')
    )

    analyzer_category = 'geofence'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _('Geofence Analyzer')
        verbose_name_plural = _('Geofence Analyzers')
