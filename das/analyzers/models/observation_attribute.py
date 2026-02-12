from django.contrib.gis.db import models
from django.utils.translation import gettext as _

from analyzers.models.base import SubjectAnalyzerConfig
from core.fields import CompoundTenantForeignKey
from observations.models import SubjectGroup


class ObservationAttributeAnalyzerConfig(SubjectAnalyzerConfig):

    AGGREGATION_METHOD_CHOICES = (
        ("all", _("All")),
        ("any", _("Any")),
        ("mean", _("Mean")),
        ("median", _("Median")),
        ("min", _("Minimum")),
        ("max", _("Maximum")),
        ("range", _("Range")),
        ("stdev", _("Standard Deviation")),
    )

    COMPARATOR_CHOICES = (
        ("<", "<"),
        (">", ">"),
        ("=", "="),
        ("<=", "<="),
        (">=", ">="),
        ("<>", "<>"),
    )

    subject_group = CompoundTenantForeignKey(
        to=SubjectGroup,
        on_delete=models.CASCADE,
        verbose_name=_("Subject Group"),
        help_text=_("This analyzer applies to subjects in this Subject Group."),
    )

    analyzer_category = "observation_attribute"

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _("Observation Attribute Analyzer")
        verbose_name_plural = _("Observation Attribute Analyzers")

    attribute_name = models.CharField(
        null=False,
        max_length=100,
        verbose_name=_("Attribute Name"),
        help_text=_("Name of the observation attribute to analyze."),
    )

    aggregation = models.CharField(default="all", max_length=20, choices=AGGREGATION_METHOD_CHOICES)

    comparator = models.CharField(
        null=False,
        max_length=10,
        verbose_name=_("Comparator"),
        help_text=_("Comparison operator to apply between the aggregated attribute value and the target value."),
        choices=COMPARATOR_CHOICES,
    )

    warning_value = models.FloatField(
        null=False,
        verbose_name=_("Warning Value"),
        help_text=_("Value to compare the aggregated attribute value against to trigger a warning."),
    )

    critical_value = models.FloatField(
        null=False,
        verbose_name=_("Critical Value"),
        help_text=_("Value to compare the aggregated attribute value against to trigger a critical event."),
    )

    adjust_to_order_of_magnitude = models.IntegerField(
        null=True,
        blank=True,
        help_text=_(
            _(
                "If present, non-zero attribute values are multiplied by successive powers of 10 until "
                "they are above this threshold before evaluating their values."
            )
        ),
    )
