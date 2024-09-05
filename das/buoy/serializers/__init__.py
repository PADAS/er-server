import logging

import rest_framework
import rest_framework.serializers

from observations import models
from observations.models import Observation
from observations.serializers import CommonNameRelatedField, SubjectSubTypeRelatedField

logger = logging.getLogger(__name__)

DISPLAY_ID_KEY = "display_id"
DEVICES_KEY = "devices"
ID_KEY = "id"
GEAR_TYPE_TRAWL = "trawl"
GEAR_TYPE_SINGLE = "single"



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
        if ID_KEY in data and self.read_only:
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

        latest_observation = Observation.objects.filter(source__subjectsource__subject=instance).latest("recorded_at")

        gear_rep = dict()
        gear_rep[ID_KEY] = rep[ID_KEY]
        gear_rep["state"] = "deployed" if rep["is_active"] else "hauled"
        gear_rep["last_updated"] = rep["updated_at"]
        # TODO: add last_change_time
        if latest_observation.additional:
            if DISPLAY_ID_KEY in latest_observation.additional:
                gear_rep[DISPLAY_ID_KEY] = latest_observation.additional.display_id if latest_observation.additional[DISPLAY_ID_KEY] else rep["name"]
            if DEVICES_KEY in latest_observation.additional:
                gear_rep["type"] = GEAR_TYPE_TRAWL if len(latest_observation.additional[DEVICES_KEY]) > 1 else GEAR_TYPE_SINGLE
                gear_rep[DEVICES_KEY] = latest_observation.additional[DEVICES_KEY]
        else:
            gear_rep[DISPLAY_ID_KEY] = rep["name"]
            gear_rep["type"] = "Error: no device information"
            gear_rep[DEVICES_KEY] = []

        return gear_rep
