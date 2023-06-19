import logging

from django.contrib.auth import get_user_model
from rest_framework import serializers

from observations.models import Subject

logger = logging.getLogger(__name__)
User = get_user_model()


class SensorPostParameters(serializers.Serializer):
    location = serializers.DictField()
    recorded_at = serializers.DateTimeField()
    manufacturer_id = serializers.CharField()
    subject_id = serializers.CharField(default=None)
    subject_name = serializers.CharField(default=None)
    subject_groups = serializers.ListField(
        child=serializers.CharField(allow_blank=True), allow_empty=True, default=list
    )
    subject_type = serializers.CharField(default=None)  # Legacy key
    subject_subtype = serializers.CharField(default=None)
    subject_additional = serializers.DictField(default=None)
    model_name = serializers.CharField(default=None)
    source_type = serializers.CharField(default=None)
    additional = serializers.DictField(default=dict)
    source_additional = serializers.DictField(default=None)
    user_id = serializers.UUIDField(required=False)

    def validate(self, data):
        user_id = data.get("user_id")
        subject_id = data.get("subject_id")
        if user_id and subject_id:
            user = User.objects.get(id=user_id)
            subject = Subject.objects.get(id=subject_id)

            if not hasattr(user, "linked_subject") and subject.linked_user and subject.linked_user != user:
                raise serializers.ValidationError("The subject is linked to another user.")

            if hasattr(user, "linked_subject") and user.linked_subject != subject:
                raise serializers.ValidationError("The subject is not linked to the user.")

        return data

    def validate_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"The user with id {value} does not exists.")
        return value
