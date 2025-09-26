from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from accounts.models.eula import EULA, UserAgreement
from core.serializers import ContentTypeField
from observations.models import Subject
from utils.tenant import get_tenant_settings


class LinkedSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id",)


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="get_role")
    subject = LinkedSubjectSerializer(source="linked_subject", read_only=True)

    class Meta:
        model = get_user_model()
        read_only_fields = (
            "is_staff",
            "is_superuser",
            "date_joined",
            "id",
            "is_active",
            "last_login",
            "accepted_eula",
            "pin",
            "subject",
        )
        fields = ("username", "email", "first_name", "last_name", "role") + read_only_fields

    def to_representation(self, instance):
        ret = super(UserSerializer, self).to_representation(instance)

        if not get_tenant_settings().env_settings.accept_eula:
            del ret["accepted_eula"]

        user_permissions = self.context.get("permissions")
        if user_permissions is not None:
            ret["permissions"] = user_permissions

        return ret


class SimpleUserDisplaySerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name")
        read_only_fields = fields


class UserDisplaySerializer(serializers.ModelSerializer):
    content_type = ContentTypeField()

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "id", "content_type")
        read_only_fields = fields

    def to_internal_value(self, data):
        if not "id" in data:
            raise ValidationError("Missing id in deserializing User object")
        obj = get_user_model().objects.get(id=data["id"])
        return obj


def get_user_display(user):
    if not user:
        return ""
    try:
        if user.get_full_name():
            return user.get_full_name()
    except NotImplementedError:
        pass
    return user.get_username()


class AcceptEulaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAgreement
        read_only_fields = ["id"]
        fields = [
            "user",
            "eula",
            "accept",
            "id",
        ]


class EulaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EULA
        fields = ["id", "version", "eula_url"]
