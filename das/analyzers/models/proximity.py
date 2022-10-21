from django.contrib.gis.db import models
from django.utils.translation import gettext as _

from analyzers.models.base import SubjectAnalyzerConfig
from mapping.models import SpatialFeatureGroupStatic
from observations.models import SubjectGroup


class FeatureProximityAnalyzerConfig(SubjectAnalyzerConfig):
    threshold_time = models.IntegerField(null=False, default=86400)  # 24 hours
    threshold_dist_meters = models.FloatField(
        null=False, default=500.0,
        verbose_name='Proximity Distance (meters)',
        help_text="A proximity event occurs when a subject's path passes "
                     "within this distance of a designated spatial feature. "
                     "<br/>A subject's path is drawn using a straight line between "
                     "reported positions.")  # 500 meters

    analyzer_category = 'proximity'
    proximal_features = models.ForeignKey(
        to=SpatialFeatureGroupStatic,
        on_delete=models.CASCADE,
        null=True,
        related_name='proximal_features',
        verbose_name="Feature Groups",
        help_text=_(
            'This analyzer applies to proximity features in this Feature Group.')
    )

    class Meta:
        verbose_name = 'Feature Proximity Analyzer'


class SubjectProximityAnalyzerConfig(SubjectAnalyzerConfig):
    search_time_hours = None
    threshold_time = models.IntegerField(null=False, default=86400)  # 24 hours
    threshold_dist_meters = models.FloatField(
        null=False, default=100.0,
        verbose_name='Proximity Distance (meters)',
        help_text="A proximity event will only occur when either subject's path passes "
                  "within this distance of the other subject. A subject's path "
                  "is drawn using a straight line between reported positions.")
    analyzer_category = 'subject_proximity'
    analysis_search_time_hours = models.FloatField(
        null=False, default=1.0,
        verbose_name='Analysis time frame (hours)',
        help_text=_('Analysis will be performed on recent data within this time frame.'))

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

    proximity_time = models.FloatField(
        null=False, default=1.0,
        verbose_name='Proximity Time',
        help_text=_("A proximity event will only occur when the two subject's position points occur within this time."))

    class Meta:
        verbose_name = 'Subject Proximity Analyzer'
