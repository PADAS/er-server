from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import EmailValidator, RegexValidator
from django.urls import reverse
from rest_framework.serializers import (
    CurrentUserDefault,
    DictField,
    HiddenField,
    ModelSerializer,
    ValidationError,
)

import utils
from activity.models import NotificationMethod

PHONE_NUMBER_VALIDATOR = RegexValidator(regex=r"^\+?1?[-\d]{9,15}$", message="Not a valid phone number.")


class NotificationMethodSerializer(ModelSerializer):
    owner = HiddenField(default=CurrentUserDefault())
    contact = DictField()

    class Meta:
        model = NotificationMethod
        read_only_fields = (
            "id",
            "owner",
        )
        fields = (
            "title",
            "contact",
            "is_active",
        ) + read_only_fields

    def to_representation(self, instance):

        instance.contact = {"method": instance.method, "value": instance.value}
        rep = super().to_representation(instance)

        rep["owner"] = {"username": instance.owner.username}

        rep["url"] = utils.add_base_url(
            self.context["request"],
            reverse(
                "notificationmethod-view",
                args=[
                    instance.id,
                ],
            ),
        )
        return rep

    def create(self, validated_data):
        contact = validated_data.pop("contact")
        validated_data["method"] = contact["method"]
        validated_data["value"] = contact["value"]
        return super().create(validated_data)

    def validate_contact(self, value):
        if not value:
            raise ValidationError({"contact": "Must be a valid contact, empty contact is not allowed"})
        if "method" not in value:
            raise ValidationError({"contact": "Must be a valid contact, method is required"})
        if "value" not in value:
            raise ValidationError({"contact": "Must be a valid contact, value is required"})

        if value["method"] == "email":
            try:
                EmailValidator()(value["value"])
            except DjangoValidationError:
                raise ValidationError(
                    {"contact.value": "Must be a valid email address when using contact.method='email'"}
                )

        elif value["method"] == "sms":
            try:
                PHONE_NUMBER_VALIDATOR(value["value"])
            except DjangoValidationError:
                raise ValidationError({"contact.value": "Must be a valid phone number when using contact.method='sms'"})

        return value

    def update(self, instance, validated_data):
        contact = validated_data.pop("contact")
        validated_data["method"] = contact["method"]
        validated_data["value"] = contact["value"]
        return super().update(instance, validated_data)
