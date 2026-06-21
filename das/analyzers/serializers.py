from __future__ import annotations

import logging

from django.urls import reverse
from rest_framework import serializers

import utils
from analyzers.models import (
    EnvironmentalSubjectAnalyzerConfig,
    FeatureProximityAnalyzerConfig,
    GeofenceAnalyzerConfig,
    ImmobilityAnalyzerConfig,
    LowSpeedPercentileAnalyzerConfig,
    LowSpeedWilcoxAnalyzerConfig,
    MovementClusterAnalyzerConfig,
    ObservationAttributeAnalyzerConfig,
    SubjectAnalyzerResult,
    SubjectProximityAnalyzerConfig,
)
from core.serializers import ContentTypeField

logger = logging.getLogger(__name__)


class SubjectGroupSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, required=False)
    name = serializers.CharField(required=True)


class SpatialAnalyzerConfigSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, required=False)
    name = serializers.CharField(required=True)
    notes = serializers.CharField(required=False)
    schedule = serializers.ListField(child=serializers.CharField(required=False, max_length=50), required=False)
    is_active = serializers.BooleanField(required=False)
    subject_group = SubjectGroupSerializer()
    analyzer_category = serializers.CharField(read_only=True)
    search_time_hours = serializers.FloatField()


class GeofenceAnalyzerConfigListSerializer(SpatialAnalyzerConfigSerializer):

    critical_geofence_group = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="mapping:spatialfeaturegroup-detail", lookup_field="id"
    )

    warning_geofence_group = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="mapping:spatialfeaturegroup-detail", lookup_field="id"
    )

    threshold_seconds = serializers.IntegerField(source="threshold_time")

    containment_regions = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="mapping:spatialfeaturegroup-detail", lookup_field="id"
    )

    trigger_on_corner_clip = serializers.BooleanField(required=False, default=True)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        critical_group = rep.pop("critical_geofence_group")
        warning_group = rep.pop("warning_geofence_group")
        containment_regions = rep.pop("containment_regions")

        rep["spatial_groups"] = {
            "warning_group": warning_group,
            "critical_group": critical_group,
            "containment_regions_group": containment_regions,
        }

        if "request" in self.context:
            rep["admin_href"] = utils.add_base_url(
                self.context["request"], reverse("admin:analyzers_geofenceanalyzerconfig_change", args=(instance.pk,))
            )

        return rep


class FeatureProximityAnalyzerConfigListSerializer(SpatialAnalyzerConfigSerializer):

    proximal_features = serializers.HyperlinkedRelatedField(
        read_only=True, view_name="mapping:spatialfeaturegroup-detail", lookup_field="id"
    )
    threshold_seconds = serializers.IntegerField(source="threshold_time")
    threshold_dist_meters = serializers.FloatField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        proximal_group = rep.pop("proximal_features")
        rep["spatial_groups"] = {"proximity_group": proximal_group}

        if "request" in self.context:
            rep["admin_href"] = utils.add_base_url(
                self.context["request"],
                reverse("admin:analyzers_featureproximityanalyzerconfig_change", args=(instance.pk,)),
            )

        return rep


class SubjectProximityAnalyzerConfigListSerializer(SpatialAnalyzerConfigSerializer):
    second_subject_group = SubjectGroupSerializer()
    threshold_seconds = serializers.IntegerField(source="threshold_time")
    threshold_dist_meters = serializers.FloatField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["second_subject_group"] = rep.pop("second_subject_group")

        if "request" in self.context:
            rep["admin_href"] = utils.add_base_url(
                self.context["request"],
                reverse("admin:analyzers_subjectproximityanalyzerconfig_change", args=(instance.pk,)),
            )

        return rep


class SubjectAnalyzerResultSerializer(serializers.Serializer):
    content_type = ContentTypeField(read_only=True)

    class Meta:
        model = SubjectAnalyzerResult


class _AnalyzerConfigMixin(serializers.Serializer):
    # Inherits serializers.Serializer so SerializerMetaclass collects these into
    # _declared_fields; a plain mixin's fields are silently ignored by DRF.
    # analyzer_category is a class attribute on the model, not a DB field, so ModelSerializer
    # cannot auto-discover it. schedule overrides the auto-generated ArrayField representation
    # to add allow_null and a callable default.
    analyzer_category = serializers.CharField(read_only=True)
    schedule = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_null=True,
        default=list,
    )

    def validate_name(self, value: str) -> str:
        # CommonTenantManager scopes this query to the current tenant automatically,
        # so we only need to check by name within that scope.
        qs = self.Meta.model.objects.filter(name=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An analyzer config with this name already exists.")
        return value


class GeofenceAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = GeofenceAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "threshold_time",
            "critical_geofence_group",
            "warning_geofence_group",
            "containment_regions",
            "trigger_on_corner_clip",
        ]
        read_only_fields = ["id", "analyzer_category"]


class FeatureProximityAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = FeatureProximityAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "threshold_time",
            "threshold_dist_meters",
            "proximal_features",
        ]
        read_only_fields = ["id", "analyzer_category"]


class SubjectProximityAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = SubjectProximityAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "second_subject_group",
            "is_active",
            "analysis_search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "threshold_time",
            "threshold_dist_meters",
            "proximity_time",
        ]
        read_only_fields = ["id", "analyzer_category"]


class ImmobilityAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = ImmobilityAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "threshold_radius",
            "threshold_time",
            "threshold_probability",
        ]
        read_only_fields = ["id", "analyzer_category"]


class EnvironmentalAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = EnvironmentalSubjectAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "threshold_value",
            "scale_meters",
            "GEE_img_name",
            "GEE_img_band_name",
            "short_description",
        ]
        read_only_fields = ["id", "analyzer_category"]


class LowSpeedPercentileAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = LowSpeedPercentileAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "low_threshold_percentile",
            "default_low_speed_value",
        ]
        read_only_fields = ["id", "analyzer_category"]


class LowSpeedWilcoxAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = LowSpeedWilcoxAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "low_speed_probability_cutoff",
        ]
        read_only_fields = ["id", "analyzer_category"]


class MovementClusterAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = MovementClusterAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "spatial_threshold_meters",
            "temporal_threshold_seconds",
            "min_cluster_points",
            "min_cluster_duration_seconds",
            "min_subjects_in_cluster",
        ]
        read_only_fields = ["id", "analyzer_category"]


class ObservationAttributeAnalyzerConfigSerializer(_AnalyzerConfigMixin, serializers.ModelSerializer):
    class Meta:
        model = ObservationAttributeAnalyzerConfig
        fields = [
            "id",
            "name",
            "notes",
            "schedule",
            "subject_group",
            "is_active",
            "search_time_hours",
            "additional",
            "quiet_period",
            "feature_group_filter",
            "analyzer_category",
            "attribute_name",
            "aggregation",
            "comparator",
            "warning_value",
            "critical_value",
            "adjust_to_order_of_magnitude",
        ]
        read_only_fields = ["id", "analyzer_category"]
