import logging

from django.urls import reverse
from rest_framework import serializers

import utils
from analyzers.models import SubjectAnalyzerResult
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


class GeofenceAnalyzerConfigSerializer(SpatialAnalyzerConfigSerializer):

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


class FeatureProximityAnalyzerSerializer(SpatialAnalyzerConfigSerializer):

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


class SubjectProximityAnalyzerSerializer(SpatialAnalyzerConfigSerializer):
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
