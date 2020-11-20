import logging
import urllib

from django.urls import reverse

from core.serializers import ContentTypeField
import rest_framework.serializers

import mapping.models
import analyzers.models
from mapping.serializers import SpatialFeatureGroupStaticSerializer

import utils

logger = logging.getLogger(__name__)


class SubjectGroupSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(read_only=True, required=False)
    name = rest_framework.serializers.CharField(required=True)


class SpatialAnalyzerConfigSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(read_only=True, required=False)
    name = rest_framework.serializers.CharField(required=True)
    notes = rest_framework.serializers.CharField(required=False)
    schedule = rest_framework.serializers.ListField(child=rest_framework.serializers.CharField(required=False,
                                                                                               max_length=50),
                                                    required=False)
    is_active = rest_framework.serializers.BooleanField(required=False)
    subject_group = SubjectGroupSerializer()
    analyzer_category = rest_framework.serializers.CharField(read_only=True)
    search_time_hours = rest_framework.serializers.FloatField()


class GeofenceAnalyzerConfigSerializer(SpatialAnalyzerConfigSerializer):

    critical_geofence_group = rest_framework.serializers.HyperlinkedRelatedField(
        read_only=True, view_name='mapping:spatialfeaturegroup-view',
        lookup_field='id')

    warning_geofence_group = rest_framework.serializers.HyperlinkedRelatedField(
        read_only=True, view_name='mapping:spatialfeaturegroup-view',
        lookup_field='id')

    threshold_seconds = rest_framework.serializers.IntegerField(
        source='threshold_time')

    containment_regions = rest_framework.serializers.HyperlinkedRelatedField(
        read_only=True, view_name='mapping:spatialfeaturegroup-view', lookup_field='id')

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        critical_group = rep.pop('critical_geofence_group')
        warning_group = rep.pop('warning_geofence_group')
        containment_regions = rep.pop('containment_regions')

        rep['spatial_groups'] = {
            'warning_group': warning_group,
            'critical_group': critical_group,
            'containment_regions_group': containment_regions,
        }

        if 'request' in self.context:
            rep['admin_href'] = utils.add_base_url(self.context['request'],
                                                   reverse("admin:analyzers_geofenceanalyzerconfig_change",
                                                           args=(instance.pk,)))

        return rep


class FeatureProximityAnalyzerSerializer(SpatialAnalyzerConfigSerializer):

    proximal_features = rest_framework.serializers.HyperlinkedRelatedField(
        read_only=True, view_name='mapping:spatialfeaturegroup-view', lookup_field='id')
    threshold_seconds = rest_framework.serializers.IntegerField(
        source='threshold_time')
    threshold_dist_meters = rest_framework.serializers.FloatField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        proximal_group = rep.pop('proximal_features')
        rep['spatial_groups'] = {
            'proximity_group': proximal_group
        }

        if 'request' in self.context:
            rep['admin_href'] = utils.add_base_url(self.context['request'],
                                                   reverse("admin:analyzers_featureproximityanalyzerconfig_change",
                                                           args=(instance.pk,)))

        return rep


class SubjectProximityAnalyzerSerializer(SpatialAnalyzerConfigSerializer):
    second_subject_group = SubjectGroupSerializer()
    threshold_seconds = rest_framework.serializers.IntegerField(
        source='threshold_time')
    threshold_dist_meters = rest_framework.serializers.FloatField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['second_subject_group'] = rep.pop('second_subject_group')

        if 'request' in self.context:
            rep['admin_href'] = utils.add_base_url(self.context['request'],
                                                   reverse("admin:analyzers_subjectproximityanalyzerconfig_change",
                                                           args=(instance.pk,)))

        return rep


class SubjectAnalyzerResultSerializer(rest_framework.serializers.Serializer):

    content_type = ContentTypeField(read_only=True)

    class Meta:
        model = analyzers.models.SubjectAnalyzerResult
