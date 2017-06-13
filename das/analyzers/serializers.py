import logging

from core.serializers import ContentTypeField
import rest_framework.serializers

import analyzers.models


logger = logging.getLogger(__name__)

class SubjectAnalyzerResultSerializer(rest_framework.serializers.Serializer):

    content_type = ContentTypeField(read_only=True)

    class Meta:
        model = analyzers.models.SubjectAnalyzerResult


