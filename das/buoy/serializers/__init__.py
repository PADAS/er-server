import logging

import rest_framework
import rest_framework.serializers

from drf_extra_fields.geo_fields import PointField

from observations import models
from observations.models import Observation
from observations.serializers import SubjectRelatedField, SubjectSubTypeRelatedField, CommonNameRelatedField

logger = logging.getLogger(__name__)

DISPLAY_ID_KEY = "display_id"
DEVICES_KEY = "devices"
ID_KEY = "id"
STATUS_KEY = "status"
GEAR_TYPE_TRAWL = "trawl"
GEAR_TYPE_SINGLE = "single"
SUBJECT_KEY = "subject"


class GearSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(
        required=False,
    )
    name = rest_framework.serializers.CharField(max_length=100)
    subject_type = rest_framework.serializers.CharField(max_length=100, required=False, read_only=True)
    subject_subtype = SubjectSubTypeRelatedField()
    common_name = CommonNameRelatedField(required=False)
    created_at = rest_framework.serializers.DateTimeField(read_only=True)
    updated_at = rest_framework.serializers.DateTimeField(read_only=True)
    is_active = rest_framework.serializers.BooleanField(required=False)
    additional_fields = ("additional")
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
        gear_rep[STATUS_KEY] = "deployed" if rep["is_active"] else "hauled"
        # gear_rep["type"] = "trawl" if len(rep["additional"]["devices"]) > 1 else "single"
        gear_rep["last_updated"] = rep["updated_at"]
        # TODO: add last_change_time
        # gear_rep["devices"] = rep["additional"]["devices"]
        # if rep["additional"]:
        #     gear_rep["type"] = "trawl" if rep["additional"]["devices"] and len(rep["additional"]["devices"]) > 1 else "single"
        #     gear_rep["devices"] = rep["additional"]["devices"]
        # else:
        #     gear_rep["type"] = "single"
        #     gear_rep["devices"] = []

        return gear_rep


class GearsSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(
        required=False,
    )
    location = PointField(required=False)
    subject = SubjectRelatedField()

    additional_fields = ("devices", "additional")

    class Meta:
        model = models.SubjectSource
        fields = (
            "id", 
            "assigned_range", 
            "source", "subject", 
            "additional", 
            "location"
        ) 

    def to_internal_value(self, data):
        if ID_KEY in data and self.read_only:
            try:
                return models.SubjectSource.objects.get(id=data["id"])
            except models.SubjectSource.DoesNotExist:
                raise rest_framework.serializers.ValidationError(f"Subject: {data} does not exist.")
        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super(GearsSerializer, self).to_representation(instance)
        # additional = instance.additional
        # additional = {k: additional[k] for k in self.additional_fields if k in additional}
        # rep.update(additional)

        latest_observation = Observation.objects.filter(source__subjectsource__subject=instance.subject).latest("recorded_at")
        subject = rep["subject"]

        gear_rep = dict()
        gear_rep[ID_KEY] = subject[ID_KEY]
        gear_rep[STATUS_KEY] = "deployed" if subject["is_active"] else "hauled"
        gear_rep["last_updated"] = subject["updated_at"]
        # TODO: add last_change_time
        if latest_observation.additional:
            display_id = subject["name"] if not DISPLAY_ID_KEY in latest_observation.additional else latest_observation.additional[DISPLAY_ID_KEY]
            gear_rep[DISPLAY_ID_KEY] = display_id
            if DEVICES_KEY in latest_observation.additional:
                gear_rep["type"] = GEAR_TYPE_TRAWL if len(latest_observation.additional[DEVICES_KEY]) > 1 else GEAR_TYPE_SINGLE
                gear_rep[DEVICES_KEY] = latest_observation.additional[DEVICES_KEY]
        else:
            gear_rep[DISPLAY_ID_KEY] = subject["name"]
            # TODO: return 500 internal server error with this detail
            gear_rep["type"] = "Error: no device information"
            gear_rep[DEVICES_KEY] = []

        return gear_rep
