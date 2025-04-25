import logging

from drf_extra_fields.geo_fields import PointField

from rest_framework import serializers

from observations import models
from observations.models import LatestObservationSource
from observations.serializers import (
    CommonNameRelatedField,
    SubjectRelatedField,
    SubjectSubTypeRelatedField,
)

logger = logging.getLogger(__name__)

DISPLAY_ID_KEY = "display_id"
DEVICES_KEY = "devices"
ID_KEY = "id"
STATUS_KEY = "status"
GEAR_TYPE_TRAWL = "trawl"
GEAR_TYPE_SINGLE = "single"
SUBJECT_KEY = "subject"


class GearSerializer(serializers.Serializer):
    id = serializers.UUIDField(
        required=False,
    )
    name = serializers.CharField(max_length=100)
    subject_type = serializers.CharField(max_length=100, required=False, read_only=True)
    subject_subtype = SubjectSubTypeRelatedField()
    common_name = CommonNameRelatedField(required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    is_active = serializers.BooleanField(required=False)
    additional_fields = "additional"

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
                raise serializers.ValidationError(f"Subject: {data} does not exist.")
        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super(GearSerializer, self).to_representation(instance)

        gear_rep = dict()
        gear_rep["id"] = rep["id"]
        gear_rep["display_id"] = rep["name"]
        gear_rep[STATUS_KEY] = "deployed" if rep["is_active"] else "hauled"
        gear_rep["last_updated"] = rep["updated_at"]
        # TODO: add last_change_time

        return gear_rep


class GearsSerializer(serializers.Serializer):
    id = serializers.UUIDField(
        required=False,
    )
    location = PointField(required=False)
    subject = SubjectRelatedField()

    additional_fields = ("devices", "additional")

    class Meta:
        model = models.SubjectSource
        fields = ("id", "assigned_range", "source", "subject", "additional", "location")

    def get_type(self, latest_observation):
        return GEAR_TYPE_TRAWL if len(latest_observation.additional[DEVICES_KEY]) > 1 else GEAR_TYPE_SINGLE

    def get_display_id(self, subject, latest_observation):
        return (
            subject["name"]
            if DISPLAY_ID_KEY not in latest_observation.additional
            else latest_observation.additional[DISPLAY_ID_KEY]
        )

    def to_internal_value(self, data):
        if ID_KEY in data and self.read_only:
            try:
                return models.SubjectSource.objects.get(id=data["id"])
            except models.SubjectSource.DoesNotExist:
                raise serializers.ValidationError(f"Subject: {data} does not exist.")
        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super(GearsSerializer, self).to_representation(instance)
        latest_observation = LatestObservationSource.objects.filter(source_id=instance.source_id).first().observation
        subject = rep["subject"]

        gear_rep = dict()
        gear_rep[ID_KEY] = subject[ID_KEY]
        gear_rep[STATUS_KEY] = "deployed" if subject["is_active"] else "hauled"
        gear_rep["last_updated"] = subject["updated_at"]
        # TODO: add last_change_time
        if latest_observation.additional:
            gear_rep[DISPLAY_ID_KEY] = self.get_display_id(subject, latest_observation)
            if DEVICES_KEY in latest_observation.additional:
                gear_rep["type"] = self.get_type(latest_observation)
                gear_rep[DEVICES_KEY] = latest_observation.additional[DEVICES_KEY]
        else:
            gear_rep[DISPLAY_ID_KEY] = subject["name"]
            # TODO: return 500 internal server error with this detail
            gear_rep["type"] = "Error: no device information"
            gear_rep[DEVICES_KEY] = []

        return gear_rep
