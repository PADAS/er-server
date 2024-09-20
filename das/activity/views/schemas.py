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
from utils.etags import HashByModelBuilder
from utils.json import loads

from .helpers import calculate_event_schema_etag


class PatrolSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
            query_params = [
                {
                    "name": "filter",
                    "in": "query",
                    "required": False,
                    "description": 'example: {"date_range":{"lower":"2020-09-16T00:00:00.000Z"}}',
                },
                {
                    "name": "exclude_empty_patrols",
                    "in": "query",
                    "required": False,
                    "description": 'Exclude the patrols without a patrol segment, defaults to "false"',
                    "schema": {"type": "bool"},
                },
            ]
            operation["parameters"].extend(query_params)
        return operation


class EventsViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
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
                    "description": "true/false whether to include only events that are a collection",
                },
                {
                    "name": "exclude_contained",
                    "in": "query",
                    "description": "true/false whether to filter out events that are included in a collection",
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
                    "description": "filter to only events with this event type id",
                },
                {
                    "name": "bbox",
                    "in": "query",
                    "description": "bounding box including four coordinate values, comma-separated."
                    " Ex. bbox=-122.4,48.4,-122.95,49.0 (west, south, east, north).",
                },
                {"name": "include_updates", "in": "query", "description": "Boolean value"},
                {"name": "include_files", "in": "query", "description": "Boolean value"},
                {"name": "include_details", "in": "query", "description": "Boolean value"},
                {"name": "include_notes", "in": "query", "description": "Boolean value"},
                {"name": "include_related_events", "in": "query", "description": "Boolean value"},
                {"name": "eventsource_id", "in": "query", "description": "id of related subject->sources"},
                {"name": "state", "in": "query", "description": "event states to filter on, ex: new, active, resolved"},
            ]
            operation["parameters"].extend(query_params)
        return operation


def etag_tracked_by_schema_hash(request, *args, **kwargs):
    subjects_available = PatrolSegmentManager.get_subjects(user=request.user)

    return HashByModelBuilder.build_from_queryset(subjects_available.values())


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
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
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
            operation["parameters"].extend(query_params)
        return operation


class EventCategoryViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
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
        elif method == "DELETE":
            query_params = [
                {
                    "name": "keep_permission_sets",
                    "in": "query",
                    "required": False,
                    "description": "to not trigger the auto-deletion of that category's linked permission sets.",
                },
            ]
            operation["parameters"].extend(query_params)
        elif method == "PATCH":
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
                    model=Choice.Field_Reports, field=choice_property.field_name
                ).filter_inactive_choices()
                for o in objs:
                    inactive_choices.append(o.value)
                if inactive_choices:
                    choice_property.properties[f"inactive_{choice_property.lookup}"] = inactive_choices

            for value in schema_utils.get_values_titlemap(eventtype.schema):
                inactive_choices = []
                objs = Choice.objects.get_choices(model=Choice.Field_Reports, field=value).filter_inactive_choices()
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
        return value.replace("{{", "").replace("}}", "")


class EventTypeViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
            query_params = [
                {"name": "include_inactive", "in": "query", "description": "include inactive eventtypes"},
                {"name": "include_schema", "in": "query", "description": "include eventtype schema in the payload"},
                {
                    "name": "updated_since",
                    "in": "query",
                    "description": "Only include event types that have changed since this date, expressed as an ISO date/time. Example: 2024-08-01 12:00:00Z",
                },
            ]
            operation["parameters"].extend(query_params)
        return operation
