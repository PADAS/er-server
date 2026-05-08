from zoneinfo import ZoneInfo

import jsonschema

from django.urls import reverse
from django.utils import timezone
from rest_framework.serializers import (
    CurrentUserDefault,
    HiddenField,
    JSONField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    SlugRelatedField,
    ValidationError,
)

import utils
from activity.alerting.conditions import Conditions
from activity.models import AlertRule, EventType, NotificationMethod
from core.utils import OneWeekSchedule


def _default_schedule():
    return {"timezone": timezone.get_current_timezone_name(), "periods": {}}


class AlertRuleSerializer(ModelSerializer):
    """
    Notice that 'notification_methods' and 'notification_method_ids' work together to provide clean read-write
    capabilities in this serializer.

    See: https://stackoverflow.com/questions/29950956/drf-simple-foreign-key-assignment-with-nested-serializers
    """

    reportTypes = SlugRelatedField(
        queryset=EventType.objects.all(),
        many=True,
        write_only=False,
        slug_field="value",
        source="event_types",
    )

    conditions = JSONField(required=False, default=dict)
    schedule = JSONField(required=False, default=_default_schedule)

    owner = HiddenField(default=CurrentUserDefault())

    notification_method_ids = PrimaryKeyRelatedField(
        queryset=NotificationMethod.objects.all(),
        many=True,
        write_only=False,
        source="notification_methods",
    )
    # notification_methods = NotificationMethodSerializer(many=True, read_only=True)

    class Meta:
        exclude = (
            "event_types",
            "notification_methods",
        )
        model = AlertRule
        read_only_fields = (
            "id",
            "owner_username",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notification_method_ids"].child_relation.queryset = NotificationMethod.objects.all()
        self.fields["reportTypes"].child_relation.queryset = EventType.objects.all()

    def validate_schedule(self, value):
        try:
            jsonschema.validate(value, OneWeekSchedule.json_schema)

            if not "timezone" in value:
                value["timezone"] = timezone.get_current_timezone_name()
            else:
                ZoneInfo(value["timezone"])

            return value
        except jsonschema.ValidationError as ve:
            rpath = "/".join([""] + [str(x) for x in ve.relative_path])
            error_message = (
                f"JSON schema validation error at {rpath}. Value {ve.instance} failed {ve.validator} "
                f"validation against {ve.validator_value}"
            )
            raise ValidationError(error_message)

    def validate_conditions(self, value):
        try:
            # Guardrail: If the request includes an empty array for either
            # conditions-list, then delete it.
            for key in ("all", "any"):
                if key in value and len(value[key]) < 1:
                    del value[key]

            Conditions(value).validate()
            return value

        except jsonschema.ValidationError as ve:
            rpath = "/".join([""] + [str(x) for x in ve.relative_path])
            error_message = (
                f"JSON schema validation error at {rpath}. Value {ve.instance} failed {ve.validator} "
                f"validation against {ve.validator_value}"
            )
            raise ValidationError(error_message)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["owner"] = {"username": instance.owner.username}

        rep["conditions"].setdefault("all", [])
        rep["conditions"].setdefault("any", [])

        rep["url"] = utils.add_base_url(
            self.context["request"],
            reverse(
                "alert-view",
                args=[
                    instance.id,
                ],
            ),
        )

        return rep

    def update(self, instance, validated_data):
        notification_method_ids = validated_data.pop("notification_method_ids", None)

        if notification_method_ids:
            instance.notification_methods.clear()
            instance.notification_methods.add(*notification_method_ids)

        return super().update(instance, validated_data)
