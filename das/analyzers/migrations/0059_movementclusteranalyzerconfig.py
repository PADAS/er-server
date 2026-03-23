import uuid

import django_multitenant.mixins

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models

import core.fields
import utils.migrations.columns
import utils.models


class Migration(migrations.Migration):

    dependencies = [
        ("observations", "0200_deer"),
        ("core", "0030_token"),
        ("analyzers", "0058_geofenceanalyzerconfig_trigger_on_corner_clip"),
    ]

    operations = [
        migrations.CreateModel(
            name="MovementClusterAnalyzerConfig",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                (
                    "name",
                    models.CharField(
                        help_text="A friendly, <b>unique</b> name for the analyzer.",
                        max_length=100,
                        verbose_name="Analyzer Name",
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "schedule",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=50),
                        blank=True,
                        default=list,
                        null=True,
                        size=None,
                        verbose_name="Array of crontab schedule patterns that an analyzer can use to determine whether to run.",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this analyzer is active. Set this False instead of deleting this record.",
                        verbose_name="active",
                    ),
                ),
                (
                    "search_time_hours",
                    models.FloatField(
                        default=24.0,
                        help_text="Analysis will be performed on recent data within this time frame.",
                        verbose_name="Analysis time frame (hours)",
                    ),
                ),
                ("additional", models.JSONField(blank=True, default=dict)),
                (
                    "quiet_period",
                    models.DurationField(
                        blank=True,
                        help_text="This will be used to override the configured quiet period.",
                        null=True,
                        verbose_name="Quiet period (HH:MM:SS)",
                    ),
                ),
                (
                    "spatial_threshold_meters",
                    models.FloatField(
                        default=200.0,
                        help_text="Maximum distance between two observations for them to be considered part of the same cluster.",
                        verbose_name="Spatial Threshold (meters)",
                    ),
                ),
                (
                    "temporal_threshold_seconds",
                    models.IntegerField(
                        default=3600,
                        help_text="Maximum time difference between two observations for them to be considered part of the same cluster.",
                        verbose_name="Temporal Threshold (seconds)",
                    ),
                ),
                (
                    "min_cluster_points",
                    models.IntegerField(
                        default=5,
                        help_text="Minimum number of observations required to form a cluster.",
                        verbose_name="Minimum Points per Cluster",
                    ),
                ),
                (
                    "min_cluster_duration_seconds",
                    models.IntegerField(
                        default=3600,
                        help_text="Minimum time span a cluster must cover before it is reported as a significant event. Clusters with a shorter duration are ignored.",
                        verbose_name="Minimum Cluster Duration (seconds)",
                    ),
                ),
                (
                    "das_tenant",
                    models.ForeignKey(
                        default=utils.migrations.columns.default_tenant_id,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.dastenant",
                    ),
                ),
                (
                    "subject_group",
                    core.fields.CompoundTenantForeignKey(
                        help_text="This analyzer applies to subjects in this Subject Group.",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="observations.subjectgroup",
                        verbose_name="Subject Group",
                    ),
                ),
            ],
            options={
                "verbose_name": "Movement Cluster Analyzer",
                "verbose_name_plural": "Movement Cluster Analyzers",
                "abstract": False,
                "base_manager_name": "objects",
                "default_manager_name": "objects",
            },
            bases=(django_multitenant.mixins.TenantModelMixin, models.Model),
            managers=[
                ("objects", utils.models.CommonTenantManager()),
            ],
        ),
        migrations.AddIndex(
            model_name="movementclusteranalyzerconfig",
            index=models.Index(
                fields=["das_tenant", "name"],
                name="analyzers_m_das_ten_mvclst_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="movementclusteranalyzerconfig",
            constraint=models.UniqueConstraint(
                fields=("das_tenant", "name"),
                name="analyzers_movementclusteranalyzerconfig_unique_name_across_tenants",
            ),
        ),
    ]
