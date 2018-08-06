import logging

from core.serializers import ContentTypeField
import rest_framework.serializers

import analyzers.models


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
    pass


class ProximityAnalyzerConfigSerializer(SpatialAnalyzerConfigSerializer):
    pass


class SubjectAnalyzerResultSerializer(rest_framework.serializers.Serializer):

    content_type = ContentTypeField(read_only=True)

    class Meta:
        model = analyzers.models.SubjectAnalyzerResult
