from __future__ import annotations

import logging
from collections import OrderedDict

from drf_extra_fields.geo_fields import PointField

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.encoding import force_str
from rest_framework.exceptions import APIException
from rest_framework.metadata import BaseMetadata
from rest_framework.request import clone_request
from rest_framework.serializers import (
    BooleanField,
    CharField,
    ChoiceField,
    DateField,
    DateTimeField,
    DecimalField,
    DictField,
    EmailField,
    Field,
    FileField,
    FloatField,
    HyperlinkedIdentityField,
    HyperlinkedRelatedField,
    IntegerField,
    ListField,
    ManyRelatedField,
    MultipleChoiceField,
    PrimaryKeyRelatedField,
    RegexField,
    RelatedField,
    Serializer,
    SlugField,
    SlugRelatedField,
    TimeField,
    URLField,
    UUIDField,
)
from rest_framework.utils.field_mapping import ClassLookupDict

from activity.serializers.helpers import get_hidden_event_states
from choices.serializers import ChoiceField

logger = logging.getLogger(__name__)


def filter_blank_choice(choices):
    if isinstance(choices, dict):
        choices = choices.items()
    for value, display in choices:
        try:
            if display.startswith("-----"):
                continue
        except AttributeError:
            pass
        yield value, display


class EventJSONSchema(BaseMetadata):
    label_lookup = ClassLookupDict(
        {
            Field: "object",
            BooleanField: "boolean",
            CharField: "string",
            URLField: "string",
            EmailField: "string",
            RegexField: "string",
            SlugField: "string",
            IntegerField: "integer",
            FloatField: "number",
            DecimalField: "number",
            DateField: "string",
            DateTimeField: "string",
            TimeField: "string",
            FileField: "string",
            MultipleChoiceField: "string",
            ListField: "array",
            DictField: "object",
            Serializer: "object",
            PrimaryKeyRelatedField: "string",
            SlugRelatedField: "enum",
            UUIDField: "string",
            RelatedField: "object",
            HyperlinkedRelatedField: "string",
            HyperlinkedIdentityField: "string",
            PointField: "string",
            ChoiceField: "string",
        }
    )

    ignore_choices_lookup = ClassLookupDict({ManyRelatedField: True})

    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "properties": {},
        "required": [],
        "dependencies": {},
    }

    def determine_metadata(self, request, view):
        metadata = OrderedDict(self.schema)

        if hasattr(view, "get_serializer"):
            properties = self.determine_properties(request, view)
            metadata["properties"] = properties
            self._prune_hidden_event_states(metadata["properties"])
        metadata["description"] = view.get_view_description()
        return metadata

    def _prune_hidden_event_states(self, properties: dict) -> None:
        """Remove hidden event state values from the rendered schema.

        Filters both ``enum`` and ``enum_ext`` entries on the ``state`` field
        so that states controlled by a preview feature (e.g. ``SC_REVIEW``) are
        not exposed to the UI unless the corresponding feature is enabled for
        the current tenant.  Called at request time — never at class-definition
        time — so the tenant context is always valid when this runs.
        """
        state_field = properties.get("state")
        if not state_field:
            return
        hidden = get_hidden_event_states()
        if not hidden:
            return
        if "enum_ext" in state_field:
            state_field["enum_ext"] = [entry for entry in state_field["enum_ext"] if entry.get("value") not in hidden]
        if "enum" in state_field:
            state_field["enum"] = [v for v in state_field["enum"] if v not in hidden]

    def determine_properties(self, request, view):
        """Return the schema properties for a view"""

        actions = {}
        for method in {"PUT", "POST"} & set(view.allowed_methods):
            view.request = clone_request(request, method)
            try:
                # Test global permissions
                if hasattr(view, "check_permissions"):
                    view.check_permissions(view.request)
                # Test object permissions
                if method == "PUT" and hasattr(view, "get_object"):
                    view.get_object()
            except (APIException, PermissionDenied, Http404):
                pass
            else:
                # If user has appropriate permissions for the view, include
                # appropriate metadata about the fields that should be
                # supplied.
                serializer = view.get_serializer()
                return self.get_serializer_info(serializer)
            finally:
                view.request = request

        return actions

    def get_serializer_info(self, serializer):
        """
        Given an instance of a serializer, return a dictionary of metadata
        about its fields.
        """
        if hasattr(serializer, "child"):
            # If this is a `ListSerializer` then we want to examine the
            # underlying child serializer instance instead.
            serializer = serializer.child

        def get_fields():
            for field_name, field in serializer.fields.items():
                value = self.get_field_info(field)
                if value:
                    yield (field_name, value)

        return OrderedDict([(key, value) for key, value in get_fields()])

    def get_field_info(self, field):
        """
        Given an instance of a serializer field, return a dictionary
        of metadata about it.
        """
        field_info = OrderedDict()
        try:
            field_info["type"] = self.label_lookup[field]
        except KeyError:
            logger.debug("Unsupported field {0} type {1} for JSON schema".format(field.field_name, type(field)))
            return None

        ignore_choices = False
        try:
            ignore_choices = self.ignore_choices_lookup[field]
        except KeyError:
            pass

        field_info["required"] = getattr(field, "required", False)

        attr_map = {
            "label": "title",
            "help_text": "description",
            "min_length": "minLength",
            "max_length": "maxLength",
            "min_value": "minimum",
            "max_value": "maximum",
        }

        for key, dest_key in attr_map.items():
            value = getattr(field, key, None)
            if value is not None and value != "":
                field_info[dest_key] = value

        if not field_info.get("read_only") and not ignore_choices:
            try:
                object_choices = field.object_choices
            except AttributeError:
                try:
                    choices = field.choices
                except AttributeError:
                    pass
                else:
                    field_info["enum_ext"] = [
                        {
                            "value": choice_value,
                            "title": force_str(choice_name, strings_only=True),
                        }
                        for choice_value, choice_name in filter_blank_choice(choices)
                    ]
                    field_info["enum"] = [v["value"] for v in field_info["enum_ext"]]
            else:
                if isinstance(object_choices, dict):
                    unassigned = []
                    enum_ext = {}
                    for group, values in filter_blank_choice(object_choices):
                        if isinstance(values, (list, tuple, dict)):
                            if isinstance(values, dict):
                                values_iter = values.items()
                            else:
                                values_iter = iter(values)
                            enum_ext[group] = [
                                {
                                    "value": choice_value,
                                    "title": force_str(choice_name, strings_only=True),
                                }
                                for choice_value, choice_name in filter_blank_choice(values_iter)
                            ]
                        else:
                            unassigned.append(
                                {
                                    "value": group,
                                    "title": force_str(values, strings_only=True),
                                }
                            )
                    if not enum_ext:
                        enum_ext = unassigned
                else:
                    enum_ext = [
                        {
                            "value": choice_value,
                            "title": force_str(choice_name, strings_only=True),
                        }
                        for choice_value, choice_name in filter_blank_choice(object_choices)
                    ]
                    field_info["enum"] = [v["value"] for v in enum_ext]
                field_info["enum_ext"] = enum_ext

        return field_info
