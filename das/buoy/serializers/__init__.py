import logging

import rest_framework
import rest_framework.serializers

from observations import models
from observations.serializers import CommonNameRelatedField, SubjectSubTypeRelatedField

logger = logging.getLogger(__name__)


class GearSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(
        required=False,
    )
    name = rest_framework.serializers.CharField(max_length=100)
    subject_type = rest_framework.serializers.CharField(max_length=100, required=False, read_only=True)
    subject_subtype = SubjectSubTypeRelatedField()
    common_name = CommonNameRelatedField(required=False)
    additional = rest_framework.serializers.JSONField(label="Additional data", required=False)
    created_at = rest_framework.serializers.DateTimeField(read_only=True)
    updated_at = rest_framework.serializers.DateTimeField(read_only=True)
    is_active = rest_framework.serializers.BooleanField(required=False)

    additional_fields = ("devices", "additional")

    class Meta:
        model = models.Subject
        read_only_fields = (
            "image_url",
            "color",
            "content_type",
            "subject_type",
            "user",
        )
        fields = (
            "id",
            "name",
            "subject_subtype",
            "common_name",
            "additional",
            "is_active",
        ) + read_only_fields

    def to_internal_value(self, data):
        if "id" in data and self.read_only:
            try:
                return models.Subject.objects.get(id=data["id"])
            except models.Subject.DoesNotExist:
                raise rest_framework.serializers.ValidationError(f"Subject: {data} does not exist.")
        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super(GearSerializer, self).to_representation(instance)
        additional = instance.additional
        additional = {k: additional[k] for k in self.additional_fields if k in additional}
        rep.update(additional)

        gear_rep = dict()
        gear_rep["id"] = rep["id"]
        gear_rep["display_id"] = rep["name"]
        gear_rep["state"] = "deployed" if rep["is_active"] else "hauled"
        gear_rep["type"] = "trawl" if len(rep["additional"]["devices"]) > 1 else "single"
        gear_rep["last_updated"] = rep["updated_at"]
        # TODO: add last_change_time
        gear_rep["devices"] = rep["additional"]["devices"]

        return gear_rep
