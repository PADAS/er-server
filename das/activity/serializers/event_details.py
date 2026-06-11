from __future__ import annotations

import json
import logging
import uuid
from collections import OrderedDict
from typing import Any

from django.template.defaultfilters import truncatechars
from rest_framework import exceptions as drf_exceptions
from rest_framework.serializers import ModelSerializer

from accounts.serializers import UserDisplaySerializer
from activity.models import EventDetails, EventType
from activity.schemas.auto_generate import (
    V2SchemaAutoBuilder,
    should_auto_generate_schema,
)
from activity.schemas.eventtype_service import (
    AttachmentSlot,
    EventTypeSchemaService,
)
from activity.serializers.helpers import get_update_type
from revision.manager import ACTION_ADDED, ACTION_UPDATED
from utils.schema_utils import (
    flatten_definition_items,
    get_all_fields_and_definitions,
    get_display_value_header_for_key,
    get_display_values_for_event_details,
    get_dynamic_choices,
    get_enum_choices,
    get_enum_names_for_field,
    get_replacement_fields_in_schema,
    get_schema_renderer_method,
    get_table_choices,
)

logger = logging.getLogger(__name__)

MAX_UPDATES_STR_LENGTH = 10


def _is_valid_uuid(value: str) -> bool:
    """Return True if *value* is a valid UUID string."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _collect_attachment_uuids(event_type: Any, event_details_data: dict[str, Any]) -> set[str]:
    """Return the set of UUID strings stored in attachment fields of *event_details_data*.

    Only applies to V2 event types.  Returns an empty set for V1 event types, event
    types with unparseable schemas, and schemas with no attachment slots.
    """
    if event_type.version != EventType.VersionChoices.VERSION_2:
        return set()

    schema_result = EventTypeSchemaService().get_raw_schema(event_type)
    if not schema_result.schema:
        return set()

    attachment_slots = schema_result.extract_attachment_slots()
    if not attachment_slots:
        return set()

    uuids: set[str] = set()
    for field_name, slot in attachment_slots.items():
        for container in slot.value_containers(event_details_data):
            value = container.get(field_name)
            if isinstance(value, str) and value and _is_valid_uuid(value):
                uuids.add(value)
    return uuids


class EventDetailsSerializer(ModelSerializer):
    class Meta:
        model = EventDetails
        read_only_fields = ("created_at", "updated_at")
        fields = ("id", "event", "data") + read_only_fields

    def create(self, validated_data):
        return EventDetails.objects.create_event_details(**validated_data)

    def update(self, instance, validated_data):
        # it's possibile that we weren't able to validate event data earlier,
        # so do it now
        if (
            "_internal_validated" in validated_data["event_details"]
            and not validated_data["event_details"]["_internal_validated"]
        ):
            del validated_data["event_details"]["_internal_validated"]
            validated_data = {"event_details": self._to_internal_value_inner(instance, validated_data["event_details"])}

        # Collect attachment UUIDs from the event_details and persist a metadata sidecar.
        # This is recomputed on every write so removing an attachment field drops its placeholder.
        uuids = _collect_attachment_uuids(self.get_event_type(instance), validated_data["event_details"])
        if uuids:
            validated_data["metadata"] = {"attachments": {u: {} for u in uuids}}

        # Get the current details object
        current_details = self.get_attribute(instance)

        if not current_details:
            current_details = EventDetails.objects.create(
                event=instance, data=validated_data, update_parent_event=False
            )
            logger.info(f"Event Details created successfully for event id: {instance.id}")

        elif current_details.data != validated_data:
            current_details.data = validated_data
            # Reuse the caller's Event so dependent_table_updated runs on the
            # same Python object as a follow-up Event save in the parent
            # serializer. Otherwise both saves diff against their own stale
            # revision_original snapshot and duplicate the state-change row.
            current_details.event = instance
            current_details.save()
            logger.info(f"Event Details updated for event id: {instance.id}")

        return current_details

    def get_event_type(self, event):
        event_type = event.event_type
        if "request" in self.context and "event_type" in getattr(self.context["request"], "data", {}):
            new_event_type = self.context["request"].data["event_type"]
            if new_event_type and new_event_type != event_type.value:
                event_type = EventType.objects.get(value=new_event_type)

        return event_type

    def _handle_auto_generate(self, event_type, data):
        """
        Handle auto-generation of schema from event data.

        If the event type has the auto-generate marker in its schema,
        generate a new V2 schema based on the incoming event data and
        update the event type. This works for both v1 and v2 event types.

        For v1 event types, this also upgrades them to v2.

        Args:
            event_type: The EventType instance.
            data: The event data dictionary to generate schema from.

        Returns:
            True if auto-generation was triggered, False otherwise.
        """
        if not should_auto_generate_schema(event_type.schema):
            return False

        new_schema = V2SchemaAutoBuilder.from_document(data)

        event_type.schema = json.dumps(new_schema, indent=2)

        # Upgrade v1 event types to v2
        if event_type.version == EventType.VersionChoices.VERSION_1:
            event_type.version = EventType.VersionChoices.VERSION_2
            logger.info(f"Upgrading EventType {event_type.value} from v1 to v2")

        event_type.save(update_fields=["schema", "version", "updated_at"])
        logger.info(f"Auto-generated V2 schema for EventType: {event_type.value}")
        return True

    def get_schema_fields_possible_values(self, schema):
        replacement_fields = get_replacement_fields_in_schema(schema)

        parameters = {}
        for replacement_field in replacement_fields:
            # No need to get values, only need value to name mapping
            if replacement_field["type"] not in ["names", "map"]:
                continue

            if replacement_field["lookup"] == "enum":
                parameters[replacement_field["field"]] = get_enum_choices(replacement_field, as_string=False)
            elif replacement_field["lookup"] == "query":
                parameters[replacement_field["field"]] = get_dynamic_choices(replacement_field, as_string=False)
            elif replacement_field["lookup"] == "table":
                parameters[replacement_field["field"]] = get_table_choices(replacement_field, as_string=False)

        all_schema_fields, all_definitions = get_all_fields_and_definitions(schema)
        return all_schema_fields, all_definitions, parameters

    def _validate_v2_attachment_fields(self, attachment_slots: dict[str, AttachmentSlot], data: dict[str, Any]) -> None:
        """Validate attachment field values against the provided attachment slots.

        For each ATTACHMENT slot:
        - Skip null / absent / empty values.
        - Reject non-string values and strings that are not valid UUIDs.

        Ownership and file-type checks are NOT performed here; any well-formed
        UUID is accepted at write time.  The resolved status is exposed at read
        time via the ``metadata.attachments`` sidecar.

        Raises:
            rest_framework.exceptions.ValidationError: mapping of
            ``{field_name: [error_message]}`` when any slot has a malformed value.
        """
        errors: dict[str, list[str]] = {}

        for field_name, slot in attachment_slots.items():
            for container in slot.value_containers(data):
                field_errors = self._validate_single_attachment_value(
                    value=container.get(field_name),
                )
                if field_errors:
                    errors.setdefault(field_name, []).extend(field_errors)

        if errors:
            raise drf_exceptions.ValidationError(errors)

    def _validate_single_attachment_value(
        self,
        value: Any,
    ) -> list[str]:
        """Validate a single attachment field value (format check only).

        Null / absent / empty values are accepted.  Non-string values and strings
        that are not valid UUIDs are rejected.  No ownership or file-type
        resolution is performed.

        Returns a list of error strings (empty means valid).
        """
        # Null / absent / empty: allowed (field is optional unless schema marks it required)
        if value is None or value == "":
            return []

        if not isinstance(value, str):
            return ["Not a valid UUID."]

        if not _is_valid_uuid(value):
            return ["Not a valid UUID."]

        return []

    def _to_internal_value_inner(self, instance, data):
        if instance is None:
            data["_internal_validated"] = False
            return data

        event_type = self.get_event_type(instance)

        # Handle auto-generate for both v1 and v2 event types.
        # If triggered, this generates a v2 schema and upgrades v1 event types to v2.
        if self._handle_auto_generate(event_type, data):
            # Auto-generation happened, event type is now v2
            return data

        # V2 schemas don't need the v1-style field processing below
        if event_type.version == EventType.VersionChoices.VERSION_2:
            schema_result = EventTypeSchemaService().get_raw_schema(event_type)
            if not schema_result.schema:
                raise drf_exceptions.ValidationError(
                    f"Event type '{event_type.value}' has an unparseable V2 schema; "
                    "cannot validate event_details. Contact an administrator."
                )
            attachment_slots = schema_result.extract_attachment_slots()
            if attachment_slots:
                self._validate_v2_attachment_fields(attachment_slots, data)
            return data

        schema = event_type.schema
        if not schema:
            return super().to_internal_value(data)

        all_schema_fields, all_schema_definitions, parameters = self.get_schema_fields_possible_values(schema)
        flattened_definitions = list(flatten_definition_items(all_schema_definitions))
        # Append field information to the data we're getting so we know how to
        # get back to the source. Needed by the export to CSV feature
        # This code does not understand arrays and does not visit and annotate
        # fields in an array.
        ret = {}
        for k, v in data.items():
            if k not in all_schema_fields or all_schema_fields[k].get("type", "unset") in ["array"]:
                ret[k] = v
                continue

            schema_field = all_schema_fields[k]
            enum_names = get_enum_names_for_field(k, schema_field, flattened_definitions)
            if isinstance(v, dict) and enum_names and "value" in v and v["value"] in enum_names:
                ret[k] = {"name": enum_names[v["value"]], "value": v["value"]}
            elif isinstance(v, list) and enum_names:
                all_values = []
                for value in v:
                    matches = []
                    for choice in enum_names:
                        if isinstance(choice, dict) and choice["value"] == value:
                            matches.append(choice)
                        elif value == choice:
                            matches.append(value)
                    if len(matches) > 0:
                        all_values.append(matches[0])
                if len(all_values) > 0:
                    ret[k] = all_values
            else:
                ret[k] = v
        return ret

    def to_internal_value(self, data):
        return self._to_internal_value_inner(self.root.instance, data)

    def sanitize_event_details_for_api(self, event_details):
        """
        The select properties are still stored as a dictionary but returned to
        the API caller as a single value.
        Properties are stored as dictionaries for the report csv export to work
        properly

        :param event_details:
        :return:
        """
        for k, v in event_details.items():
            if k == "updates":
                continue
            elif isinstance(v, dict) and "value" in v.keys():
                event_details[k] = v["value"]
            # This is not meant for property type=array, but here we are attempting a cleanup up of enums
            # for the property type=array
            elif isinstance(v, list):
                values = [x["value"] if isinstance(x, dict) and "value" in x.keys() else x for x in v]
                event_details[k] = values
        return event_details

    def to_representation(self, event_details):
        if not event_details:
            return OrderedDict()
        rep = OrderedDict(event_details.data["event_details"])
        event_type = self.get_event_type(event_details.event)
        rep["updates"] = self.render_updates(event_details, event_type)
        rep = self.sanitize_event_details_for_api(rep)
        return rep

    def render_updates(self, event_details, event_type):
        if not self.context.get("include_updates", True):
            return []

        schema = event_type.schema
        rendered_schema = get_schema_renderer_method()(schema)
        last_details = None

        def get_action(revision):
            nonlocal last_details
            result = None
            fieldnames = []
            revision_details = revision.data.get("data", {}).get("event_details", {})
            details = get_display_values_for_event_details(revision_details, rendered_schema, event=event_details.event)

            def get_display_fieldnames():
                for k, v in revision_details.items():
                    if k not in details:
                        continue
                    if last_details and last_details.get(k) == v:
                        continue

                    title = get_display_value_header_for_key(rendered_schema, k)
                    display = details.get(title, "")
                    display = truncatechars(display, MAX_UPDATES_STR_LENGTH)
                    fieldnames.append(f"{title}")

            if revision.action == ACTION_ADDED:
                get_display_fieldnames()
                result = f"Created with fields: {', '.join(fieldnames)}"
            elif revision.action == ACTION_UPDATED:
                get_display_fieldnames()
                result = f"{revision.get_action_display()} fields: {', '.join(fieldnames)}"

            last_details = revision_details
            return result

        updates = []
        for revision in event_details.revision.all_user():
            update_action = get_action(revision)
            if update_action:
                updates.append(
                    {
                        "message": update_action,
                        "time": revision.revision_at.isoformat(),
                        "text": revision.data.get("text", ""),
                        "user": UserDisplaySerializer().to_representation(revision.user),
                        "type": get_update_type(revision),
                    }
                )
        return updates

    def is_valid(self, raise_exception=False):
        return super().is_valid(raise_exception=raise_exception)

    def get_attribute(self, instance):
        return EventDetails.objects.filter(event=instance).order_by("created_at").last()
