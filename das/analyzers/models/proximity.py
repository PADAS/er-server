from django.contrib.gis.db import models
from django.utils.translation import ugettext as _
from analyzers.models.base import SubjectAnalyzerConfig
from mapping.models import SpatialFeatureGroupStatic
from observations.models import SubjectGroup


class ProximityAnalyzerConfig(SubjectAnalyzerConfig):

    threshold_time = models.IntegerField(null=False, default=86400)  # 24 hours

    threshold_dist_meters = models.FloatField(
        null=False, default=500.0,
        verbose_name='Proximity Distance (meters)',
        help_text="A proximity event occurs when a subject's path passes "
                     "within this distance of a designated spatial feature. "
                     "<br/>A subject's path is drawn using a straight line between "
                     "reported positions.")  # 500 meters

    analyzer_category = 'proximity'

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = True


class FeatureProximityAnalyzerConfig(ProximityAnalyzerConfig):
    proximal_features = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='proximal_features',
        verbose_name="Feature Groups",
        help_text=_(
            'This analyzer applies to proximity features in this Feature Group.')
    )


class SubjectProximityAnalyzerConfig(ProximityAnalyzerConfig):
    subject_group = models.ForeignKey(
        to=SubjectGroup, on_delete=models.CASCADE,
        verbose_name=_('Subject Group 1'),
        related_name='subject_group_1',
        help_text=_('This analyzer applies to subjects in this Subject Group.'))

    second_subject_group = models.ForeignKey(
        to=SubjectGroup,
        on_delete=models.CASCADE,
        verbose_name=_('Subject Group 2'),
        related_name='subject_group_2',
        help_text=_('This analyzer applies to subjects in this Subject Group.'))

    proximal_time_frame = models.FloatField(
        null=False, default=24.0,
        verbose_name='Proximal time frame (hours)',
        help_text=_('Report will be created only if the subjects are of close proximity distance within this time frame'))
