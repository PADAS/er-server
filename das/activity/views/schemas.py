import json
import re
from collections import OrderedDict

from rest_framework_extensions.etag.decorators import etag

from django.template import Context, Template
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.generics import ListCreateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

import utils.schema_utils as schema_utils
from activity.models import Event, EventType, PatrolSegmentManager
from activity.permissions import EventCategoryPermissions
from activity.search import get_event_search_schema
from activity.serializers import EventJSONSchema, EventSerializer, TrackedBySerializer
from choices.models import Choice
from das_server.views import CustomSchema
from utils import add_base_url
from utils.drf import StandardResultsSetPagination
from utils.etags import get_hash_from_queryset
from utils.json import loads

from .helpers import calculate_event_schema_etag
from .response_headers import SUBJECT_FIELDS


class PatrolSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "filter",
                    "in": "query",
                    "required": False,
                    "description": "Advanced filtering using a JSON-encoded object.",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "description": "Filter as a JSON object with various filter criteria",
                                "properties": {
                                    "date_range": {
                                        "type": "object",
                                        "properties": {
                                            "lower": {"type": "string", "format": "date-time"},
                                            "upper": {"type": "string", "format": "date-time"},
                                        },
                                        "description": "Filter on the patrol start/end time range",
                                    },
                                    "patrols_overlap_daterange": {
                                        "type": "boolean",
                                        "default": True,
                                        "description": "When true, include patrols whose time range overlaps with date_range. Defaults to true.",
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Search text across serial number, title, patrol type, notes, and tracked-by subjects/users",
                                    },
                                    "patrol_type": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Filter on patrol type IDs",
                                    },
                                    "tracked_by": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Filter on subject IDs leading the patrol",
                                    },
                                },
                                "example": {"date_range": {"lower": "2020-09-16T00:00:00.000Z"}, "text": "search text"},
                            }
                        }
                    },
                },
                {
                    "name": "exclude_empty_patrols",
                    "in": "query",
                    "required": False,
                    "description": 'Exclude patrols without a patrol segment. Defaults to "false".',
                    "schema": {"type": "boolean", "default": False},
                },
                {
                    "name": "status",
                    "in": "query",
                    "required": False,
                    "description": (
                        "Filter patrols by status. Repeatable — provide multiple times for multiple values. "
                        "Allowed values: scheduled, active, overdue, done, cancelled."
                    ),
                    "schema": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["scheduled", "active", "overdue", "done", "cancelled"],
                        },
                    },
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class EventsViewSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "sort_by",
                    "required": False,
                    "description": "Sort by (use 'event_time', 'updated_at', 'created_at', 'serial_number')"
                    " with optional minus ('-') prefix to reverse order.",
                },
                {
                    "name": "is_collection",
                    "in": "query",
                    "description": "true/false whether to include only events that are a collection/incident",
                },
                {
                    "name": "exclude_contained",
                    "in": "query",
                    "description": "true/false whether to filter out events that are included in a collection/incident",
                },
                {"name": "updated_since", "in": "query", "description": "date-string to limit on updated_at"},
                {
                    "name": "event_ids",
                    "in": "query",
                    "description": "Event IDs, comma-separated",
                    "schema": {"type": "array", "items": {"type": "string"}},
                },
                {
                    "name": "event_category",
                    "in": "query",
                    "description": "Only include this/these categories. can specify one or more",
                },
                {
                    "name": "event_type",
                    "in": "query",
                    "description": "include only events with this event type id",
                },
                {
                    "name": "bbox",
                    "in": "query",
                    "description": "bounding box of the form (west-longitude, south-latitude, east-longitude, north-latitude)."
                    " Ex. bbox=-122.4,48.4,-122.95,49.0 (west, south, east, north).",
                },
                {"name": "include_updates", "in": "query", "description": "Include the event history. Boolean value"},
                {"name": "include_files", "in": "query", "description": "Include the event files list. Boolean value"},
                {
                    "name": "include_details",
                    "in": "query",
                    "description": "Include the event details, the event type specific data. Boolean value",
                },
                {"name": "include_notes", "in": "query", "description": "Include the event notes. Boolean value"},
                {
                    "name": "include_related_events",
                    "in": "query",
                    "description": "Include the related events, which are events that are linked to this event by a relationship. Boolean value",
                },
                {
                    "name": "state",
                    "in": "query",
                    "description": "only include events in this state(s). ex: new, active, resolved",
                },
                {
                    "name": "filter",
                    "in": "query",
                    "required": False,
                    "description": (
                        "Advanced filtering using a JSON-encoded object. "
                        "Supports date ranges, text search, and custom filter values."
                    ),
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "description": "Filter as a JSON object with various filter criteria",
                                "properties": {
                                    "date_range": {
                                        "type": "object",
                                        "properties": {
                                            "lower": {"type": "string", "format": "date-time"},
                                            "upper": {"type": "string", "format": "date-time"},
                                        },
                                        "description": "Filter on the event time",
                                    },
                                    "update_date": {
                                        "type": "object",
                                        "properties": {
                                            "lower": {"type": "string", "format": "date-time"},
                                            "upper": {"type": "string", "format": "date-time"},
                                        },
                                        "description": "Filter on the updated time for the event",
                                    },
                                    "text": {"type": "string", "description": "Search text in the event"},
                                    "duration": {
                                        "type": "string",
                                        "description": "Filter on the duration of the event",
                                    },
                                    "priority": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "enum": ["gray", "green", "amber", "red"],
                                        },
                                        "description": "Filter on the priority of the event",
                                    },
                                    "state": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "enum": ["new", "active", "resolved"],
                                        },
                                        "description": "Filter on the state of the event",
                                    },
                                    "event_category": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Filter on the event category id, an array of EventCategory IDs",
                                    },
                                    "event_type": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Filter on the event type id, an array of EventType IDs",
                                    },
                                    "reported_by": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Filter on the reported by id, an array of ReportedBy IDs",
                                    },
                                    "create_date": {
                                        "type": "object",
                                        "properties": {
                                            "lower": {"type": "string", "format": "date-time"},
                                            "upper": {"type": "string", "format": "date-time"},
                                        },
                                        "description": "Filter on the create time for the event",
                                    },
                                    "event_filter_id": {
                                        "type": "string",
                                        "format": "uuid",
                                        "description": "ID of a saved EventFilter whose filter_spec is applied. When present, all other filter keys are ignored.",
                                    },
                                },
                                "example": {"date_range": {"lower": "2025-09-16T00:00:00.000Z"}, "text": "search text"},
                            }
                        }
                    },
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


def etag_tracked_by_schema_hash(request, *args, **kwargs):
    subjects_available = PatrolSegmentManager.get_subjects(user=request.user)
    return get_hash_from_queryset(queryset=subjects_available.values(*SUBJECT_FIELDS), request=request)


class TrackedBySchema(ListCreateAPIView):
    serializer_class = TrackedBySerializer
    metadata_class = EventJSONSchema

    @etag(etag_tracked_by_schema_hash)
    def get(self, request, *args, **kwargs):
        meta = self.metadata_class()
        data = meta.determine_metadata(request, self)
        return Response(data)

    def post(self, request, *args, **kwargs):
        raise MethodNotAllowed("For Schema")


class EventCategoriesViewSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {"name": "include_inactive", "in": "query", "description": "include inactive event-categories"},
                {
                    "name": "include_event_types",
                    "in": "query",
                    "required": False,
                    "description": "include event types related to each category",
                },
                {
                    "name": "include_permission_set_changed",
                    "in": "query",
                    "required": False,
                    "description": "adds the property `permission_set_changed` which indicates whether permission sets are default.",
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class EventCategoryViewSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        operation["parameters"] = operation.get("parameters", [])
        if self.method == "GET":
            query_params = [
                {
                    "name": "include_event_types",
                    "in": "query",
                    "required": False,
                    "description": "include event types related to each category",
                },
                {
                    "name": "include_permission_set_changed",
                    "in": "query",
                    "required": False,
                    "description": "include `permission_set_changed` if its permission sets are non-default.",
                },
            ]
            operation["parameters"].extend(query_params)
        elif self.method == "DELETE":
            query_params = [
                {
                    "name": "keep_permission_sets",
                    "in": "query",
                    "required": False,
                    "description": "to not trigger the auto-deletion of that category's linked permission sets.",
                },
            ]
            operation["parameters"].extend(query_params)
        elif self.method == "PATCH":
            query_params = [
                {
                    "name": "update_permission_sets",
                    "in": "query",
                    "required": False,
                    "description": "to update permission sets and permissions explicitly",
                },
            ]
            operation["parameters"].extend(query_params)
        return operation


class EventFilterSchemaView(APIView):
    def get(self, request, *args, **kwargs):
        schema = get_event_search_schema()
        schema["schema"]["id"] = add_base_url(
            request,
            reverse(
                "eventfilter-schema-view",
            ),
        )

        return Response(schema)


class EventSchemaView(ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema

    def get_queryset(self):
        return Event.objects.all()

    choices = Choice.objects.order_by("is_active", "ordernum")

    @etag(etag_func=calculate_event_schema_etag)
    def get(self, request, *args, **kwargs):
        meta = self.metadata_class()
        data = meta.determine_metadata(request, self)
        return Response(data)

    def post(self, request, *args, **kwargs):
        raise MethodNotAllowed("For Schema")


class EventTypeSchemaView(ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema

    def get_queryset(self):
        return Event.objects.all()

    def get(self, request, *args, **kwargs):
        eventtype = get_object_or_404(EventType.objects.all(), value__iexact=self.kwargs["eventtype"])
        event_id = self.request.query_params.get("event_id")

        if not eventtype.schema:
            return Response(None)

        definition_format = self.request.query_params.get("definition", None)

        schema_fields = schema_utils.get_replacement_fields_in_schema(eventtype.schema)

        if event_id:
            json_schema = self._get_json_schema(eventtype)

            properties = json_schema.get("schema", {}).get("properties", {})
            for schema_field in schema_fields:
                for key, value in properties.items():
                    enum = value.get("enum")
                    enum_names = value.get("enumNames")
                    if (
                        enum
                        and enum_names
                        and schema_field.get("tag")
                        in [
                            self._clean_curly_brackets(enum),
                            self._clean_curly_brackets(enum_names),
                        ]
                    ):
                        schema_field["event_detail"] = key

        choices = Choice.objects.filter(is_active=True) if definition_format == "flat" else Choice.objects.all()

        parameters = {}
        enumImages_vals = {}
        for schema_field in schema_fields:
            if schema_field["lookup"] == "enum":
                icon_vals = schema_utils.get_enumImage_values(schema_field, queryset=choices)
                if icon_vals:
                    enumImages_vals[schema_field["field"]] = icon_vals
                parameters[schema_field["tag"]] = schema_utils.get_enum_choices(schema_field, queryset=choices)
            elif schema_field["lookup"] == "query":
                parameters[schema_field["tag"]] = schema_utils.get_dynamic_choices(schema_field, event=event_id)
            elif schema_field["lookup"] == "table":
                parameters[schema_field["tag"]] = schema_utils.get_table_choices(schema_field)

        if len(parameters) > 0:
            template = Template(eventtype.schema)
            rendered_template = template.render(Context(parameters, autoescape=False))
            schema = loads(rendered_template, object_pairs_hook=OrderedDict)
        else:
            schema = loads(eventtype.schema, object_pairs_hook=OrderedDict)

        if "schema" not in schema:
            return Response(None)

        schema["schema"]["id"] = add_base_url(
            request,
            reverse(
                "event-schema-eventtype",
                args=[
                    eventtype.value,
                ],
            ),
        )
        schema["schema"]["icon_id"] = eventtype.icon_id
        schema["schema"]["image_url"] = add_base_url(request, eventtype.image_url)

        field_schema = list(schema_utils.schema_property_choices(eventtype.schema, schema))

        if definition_format != "flat":
            for choice_property in field_schema:
                inactive_choices = []
                objs = Choice.objects.get_choices(
                    model=Choice.EVENT_MODEL, field=choice_property.field_name
                ).filter_inactive_choices()
                for o in objs:
                    inactive_choices.append(o.value)
                if inactive_choices:
                    choice_property.properties[f"inactive_{choice_property.lookup}"] = inactive_choices

            for value in schema_utils.get_values_titlemap(eventtype.schema):
                inactive_choices = []
                objs = Choice.objects.get_choices(model=Choice.EVENT_MODEL, field=value).filter_inactive_choices()
                for o in objs:
                    inactive_choices.append(o.value)
                if inactive_choices:
                    for key in schema["definition"]:
                        if isinstance(key, OrderedDict):
                            items = key.get("items")

                            tmap_values = (
                                [(i, i["titleMap"]) for i in items if isinstance(i, OrderedDict) and i.get("titleMap")]
                                if items
                                else None
                            )

                            # TODO: Consider the truthiness of tmap_values here,
                            # for the case where it is set to [].
                            if tmap_values:
                                for item, tmap in tmap_values:
                                    for tm in tmap:
                                        if tm.get("value") in inactive_choices:
                                            item["inactive_titleMap"] = inactive_choices

                            elif key.get("titleMap"):
                                for title_map_elem in key.get("titleMap"):
                                    if title_map_elem.get("value") in inactive_choices:
                                        key["inactive_titleMap"] = inactive_choices

        for choice_property in field_schema:
            for o, vals in enumImages_vals.items():
                if choice_property.field_name == o:
                    choice_property.properties["enumImages"] = vals

        # Apply definition filter
        try:
            schema = schema_utils.filter_schema_definition(schema, definition_format)
        except ValueError as ex:
            return Response(str(ex), status=status.HTTP_400_BAD_REQUEST)

        return Response(schema)

    def post(self, request, *args, **kwargs):
        raise MethodNotAllowed("For Schema")

    def _get_json_schema(self, event_type):
        schema = event_type.schema
        for expression in set(re.findall("{{.*?}}", event_type.schema)):
            schema = schema.replace(expression, '"{}"'.format(expression))
        return json.loads(schema)

    def _clean_curly_brackets(self, value):
        # This is used to remove the curly brackets from a tag property enum or enumNames
        # something like {{enum___field_name___values}}. But some users have been
        # directly adding full enum lists and enum dicts directly in the schema.
        # if we detect that here, turn None.
        if not isinstance(value, str):
            return None
        return value.replace("{{", "").replace("}}", "")


class EventTypeViewSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            parameters = operation.get("parameters", [])
            parameters.append(
                {
                    "name": "include_schema",
                    "in": "query",
                    "description": "include eventtype schema in the payload",
                    "schema": {"type": "boolean", "default": False},
                }
            )

            path = getattr(self, "path", None)

            if path and "v2" not in path:
                parameters.append(
                    {
                        "name": "include_inactive",
                        "in": "query",
                        "description": "Include inactive event types in the list.",
                    }
                )
                parameters.append(
                    {
                        "name": "updated_since",
                        "in": "query",
                        "description": "Only include event types that have changed since this date, expressed as an ISO date/time. Example: 2024-08-01 12:00:00Z",
                    }
                )

            operation["parameters"] = parameters
        return operation
