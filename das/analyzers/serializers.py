import logging

from core.serializers import ContentTypeField
import rest_framework.serializers

import mapping.models
import analyzers.models
from mapping.serializers import SpatialFeatureGroupStaticSerializer

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

    geofence_group = rest_framework.serializers.HyperlinkedRelatedField(source='geofences',
                                                                        read_only=True, view_name='mapping:spatialfeaturegroup-view', lookup_field='id')

    threshold_seconds = rest_framework.serializers.IntegerField(
        source='threshold_time')

    containment_regions = rest_framework.serializers.HyperlinkedRelatedField(
        read_only=True, view_name='mapping:spatialfeaturegroup-view', lookup_field='id')


class ProximityAnalyzerConfigSerializer(SpatialAnalyzerConfigSerializer):

    proximal_features = rest_framework.serializers.HyperlinkedRelatedField(
        read_only=True, view_name='mapping:spatialfeaturegroup-view', lookup_field='id')
    threshold_seconds = rest_framework.serializers.IntegerField(
        source='threshold_time')
    threshold_dist_meters = rest_framework.serializers.FloatField()


class SubjectAnalyzerResultSerializer(rest_framework.serializers.Serializer):

    content_type = ContentTypeField(read_only=True)

    class Meta:
        model = analyzers.models.SubjectAnalyzerResult
