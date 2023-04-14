import json
import logging
from collections import OrderedDict

from django.template.defaultfilters import truncatechars
from rest_framework.serializers import ModelSerializer

from accounts.serializers import UserDisplaySerializer, get_user_display
from activity.models import EventDetails, EventType
from revision.manager import ACTION_UPDATED
from utils.schema_utils import (
    generate_event_type_schema_from_doc,
    get_all_fields,
    get_display_value_header_for_key,
    get_display_values_for_event_details,
    get_dynamic_choices,
    get_enum_choices,
    get_replacement_fields_in_schema,
    get_schema_renderer_method,
    get_table_choices,
    should_auto_generate,
)

from .helpers import get_update_type, get_user_display

logger = logging.getLogger(__name__)

MAX_UPDATES_STR_LENGTH = 10


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

        # Get the current details object
        current_details = self.get_attribute(instance)

        if not current_details:
            current_details = EventDetails.objects.create(
                event=instance, data=validated_data, update_parent_event=False
            )
            logger.info(f"Event Details created successfully for event id: {instance.id}")

        elif current_details.data != validated_data:
            current_details.data = validated_data
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

        all_schema_fields = get_all_fields(schema)
        return all_schema_fields, parameters

    def _to_internal_value_inner(self, instance, data):
        if instance is None:
            data["_internal_validated"] = False
            return data

        event_type = self.get_event_type(instance)

        schema = event_type.schema

        if not schema:
            return super().to_internal_value(data)

        # Auto-generate a schema if appropriate.
        if should_auto_generate(schema):
            schema = generate_event_type_schema_from_doc(data)
            # Downstream code is expecting a template (as a string).
            schema = json.dumps(schema, indent=2)
            EventType.objects.filter(id=event_type.id).update(schema=schema)

        all_schema_fields, parameters = self.get_schema_fields_possible_values(schema)

        # Append field information to the data we're getting so we know how to
        # get back to the source
        ret = {}
        for k, v in data.items():
            if k not in all_schema_fields:
                continue
            if type(v) == dict and k in parameters and v["value"] in parameters[k]:
                ret[k] = {"name": parameters[k][v["value"]], "value": v["value"]}
            elif type(v) == list and k in parameters:
                all_values = []
                for value in v:
                    matches = []
                    for d in parameters[k]:
                        if isinstance(d, dict) and d["value"] == value:
                            matches.append(d)
                        elif value == d:
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
            details = get_display_values_for_event_details(revision_details, rendered_schema)

            if revision.action == ACTION_UPDATED:
                for k, v in revision_details.items():
                    if k not in details:
                        continue
                    if last_details and last_details.get(k) == v:
                        continue

                    title = get_display_value_header_for_key(rendered_schema, k)
                    display = details.get(title, "")
                    display = truncatechars(display, MAX_UPDATES_STR_LENGTH)
                    fieldnames.append(f"{title}")

                result = "{0} fields: {1}".format(revision.get_action_display(), ", ".join(fieldnames))

            last_details = revision_details
            return result

        updates = []
        for revision in event_details.revision.all_user():
            update_action = get_action(revision)
            if update_action:
                updates.append(
                    dict(
                        message="{action}".format(action=update_action, user=get_user_display(revision.user)),
                        time=revision.revision_at.isoformat(),
                        text=revision.data.get("text", ""),
                        user=UserDisplaySerializer().to_representation(revision.user),
                        type=get_update_type(revision),
                    )
                )
        return updates

    def is_valid(self, raise_exception=False):
        return super().is_valid(raise_exception=raise_exception)

    def get_attribute(self, instance):
        return EventDetails.objects.filter(event=instance).order_by("created_at").last()
