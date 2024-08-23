import logging

import rest_framework
import rest_framework.serializers
from django.contrib.auth import get_user_model

from observations import models

logger = logging.getLogger(__name__)

SET_TYPE_CHOICES = [
    ("SETTYPE_SINGLE", "single"),
    ("SETTYPE_TRAWL", "trawl"),
]

STATUS_CHOICES = [
    ("STATUS_DEPLOYED", "deployed"),
    ("STATUS_HAULED", "hauled"),
]


class SubjectSubTypeRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        return models.SubjectSubType.objects.all()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return models.SubjectSubType.objects.get(value=data)
            except models.SubjectSubType.DoesNotExist:
                raise rest_framework.serializers.ValidationError(f"subject_subtype : {data} does not exist")


class CommonNameRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        return models.CommonName.objects.all()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return models.CommonName.objects.get(value=data)
            except models.CommonName.DoesNotExist:
                raise rest_framework.serializers.ValidationError(f"common_name : {data} does not exist")


# TODO: Do I need a permission for viewing buoys?


class LinkedUserserializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id",)


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
    user = LinkedUserserializer(source="linked_user", read_only=True)

    additional_fields = ("region", "country", "sex", "species", "additional")

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
        additional = instance.additional  # TODO: debug additional not populated
        additional = {k: additional[k] for k in self.additional_fields if k in additional}
        rep.update(additional)

        gear_rep = dict()
        gear_rep["id"] = rep["id"]
        gear_rep["display_id"] = rep["name"]
        gear_rep["state"] = "deployed" if rep["is_active"] else "hauled"
        # TODO: debug additional, then configure set_type based on # of devices in additional
        # gear_rep["type"] = rep["subject_subtype"]
        gear_rep["last_updated"] = rep["updated_at"]
        # TODO: add last_change_time
        # TODO: implement devices
        # gear_rep["devices"] = DeviceSerializer(rep["additional"]["devices"], many=True).data

        return gear_rep
