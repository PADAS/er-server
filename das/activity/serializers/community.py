from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer

from activity.models import Community
from core.serializers import ContentTypeField


class CommunitySerializer(ModelSerializer):
    content_type = ContentTypeField()

    class Meta:
        model = Community
        fields = ("name", "id", "content_type")

    def to_internal_value(self, data):
        if not "id" in data:
            raise ValidationError("Missing id in deserializing User object")
        obj = Community.objects.get(id=data["id"])
        return obj
