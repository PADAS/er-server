from django.contrib.gis.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext as _

from analyzers.models.base import SubjectAnalyzerConfig


class MovementClusterAnalyzerConfig(SubjectAnalyzerConfig):
    """ST-DBSCAN Movement Cluster Analyzer configuration.

    Uses the Spatio-Temporal DBSCAN algorithm to identify clusters in a
    subject's movement data — locations where the subject spends repeated or
    concentrated time within a bounded area.

    Parameters
    ----------
    spatial_threshold_meters:
        Maximum distance between two observations (in metres) for them to be
        considered neighbours in the same cluster.  Acts as the spatial epsilon
        (eps1) of ST-DBSCAN.

    temporal_threshold_seconds:
        Maximum time difference between two observations (in seconds) for them
        to be considered neighbours in the same cluster.  Acts as the temporal
        epsilon (eps2) of ST-DBSCAN.

    min_cluster_points:
        Minimum number of observations that must fall within both thresholds of
        a point for that point to be classified as a core point.  Clusters must
        contain at least this many observations.

    min_cluster_duration_seconds:
        Minimum elapsed time (in seconds) between the earliest and latest
        observation in a cluster for the cluster to be reported as a
        significant event.  Clusters with a shorter duration are discarded.
    """

    spatial_threshold_meters = models.FloatField(
        null=False,
        default=200.0,
        verbose_name=_("Spatial Threshold (meters)"),
        help_text=_("Maximum distance between two observations for them to be considered part of the same cluster."),
    )

    temporal_threshold_seconds = models.IntegerField(
        null=False,
        default=3600,  # 1 hour
        verbose_name=_("Temporal Threshold (seconds)"),
        help_text=_(
            "Maximum time difference between two observations for them to be considered part of the same cluster."
        ),
    )

    min_cluster_points = models.IntegerField(
        null=False,
        default=5,
        verbose_name=_("Minimum Points per Cluster"),
        help_text=_("Minimum number of observations required to form a cluster."),
    )

    min_cluster_duration_seconds = models.IntegerField(
        null=False,
        default=3600,  # 1 hour
        verbose_name=_("Minimum Cluster Duration (seconds)"),
        help_text=_(
            "Minimum time span a cluster must cover before it is reported as "
            "a significant event.  Clusters with a shorter duration are ignored."
        ),
    )

    min_subjects_in_cluster = models.IntegerField(
        null=False,
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("Minimum Subjects per Cluster"),
        help_text=_(
            "Minimum number of distinct subjects required in a cluster before it is "
            "reported as a significant event.  When greater than 1, observations from "
            "all subjects in the subject group are combined before clustering."
        ),
    )

    analyzer_category = "movement_cluster"

    class Meta(SubjectAnalyzerConfig.Meta):
        abstract = False
        verbose_name = _("Movement Cluster Analyzer")
        verbose_name_plural = _("Movement Cluster Analyzers")
