import copy
import csv
import json
import logging
import platform
from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Type, Union

import pytz
from psycopg2.errors import InvalidTextRepresentation
from rest_framework_extensions.etag.decorators import etag

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.aggregates import ArrayAgg, StringAgg
from django.db import transaction
from django.db.models import Count, OuterRef, Prefetch, Q, TextField
from django.db.models.functions import JSONObject
from django.db.models.query import QuerySet
from django.db.utils import DataError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

import utils.schema_utils as schema_utils
from accounts.serializers import UserDisplaySerializer
from activity.filters import (
    EventListFilter,
    EventPermissionsFilter,
    EventSubjectsFilter,
)
from activity.models import (
    Event,
    EventCategory,
    EventFactor,
    EventFile,
    EventFilter,
    EventGeometry,
    EventProvider,
    EventRelationship,
)
from activity.permissions import (
    EventCategoryGeographicPermission,
    EventCategoryPermissions,
    IsOwner,
)
from activity.serializers import (
    EventFactorSerializer,
    EventFilterSerializer,
    EventGeoJsonSerializer,
    EventJSONSchema,
    EventProviderSerializer,
    EventSerializer,
    EventStateSerializer,
    PatrolSegmentEventSerializer,
)
from activity.serializers.geometries import EventGeometryRevisionSerializer
from activity.util import get_permitted_event_categories
from activity.views.helpers import (
    calculate_event_etag,
    generate_event_type_cache,
    generate_reported_by_lookup,
)
from activity.views.schemas import EventsViewSchema
from core.permissions import UserCanExportDataPermission
from observations.models import Subject
from utils.db.expresions import ArraySubquery
from utils.drf import (
    CachedCountResultsSetPagination,
    StandardResultsSetGeoJsonPagination,
    StandardResultsSetPagination,
)
from utils.json import ExtendedGEOJSONRenderer, parse_bool

logger = logging.getLogger(__name__)

User = get_user_model()


class EventAlertTargetsListView(ListAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = UserDisplaySerializer

    def get_queryset(self):
        return User.objects.none()


class EventCountView(APIView):
    __doc__ = """
    Returns the count of New Events.
    """
    permission_classes = (EventCategoryPermissions,)

    def get_queryset(self):
        return Event.objects.all()

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.new()

        event_categories = self.request.query_params.getlist("event_category", None)

        if not event_categories:
            event_categories = EventCategory.get_category_keys()

        allowed_event_categories = [ec for ec in event_categories if self.request.user.has_perm(f"activity.{ec}_read")]

        if allowed_event_categories:
            queryset = queryset.by_category(allowed_event_categories)
        else:
            queryset = queryset.none()

        data = {"count": queryset.count()}
        return Response(data)


class EventFactorsView(ListAPIView):
    serializer_class = EventFactorSerializer

    def get_queryset(self):
        return EventFactor.objects.all().order_by("ordernum")


class EventFiltersView(ListCreateAPIView):
    serializer_class = EventFilterSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return EventFilter.objects.order_by("ordernum")


class EventGeometryView(ListAPIView):
    serializer_class = EventGeometryRevisionSerializer

    def get_queryset(self):
        queryset = EventGeometry.objects.filter(event__id=self.kwargs["event_id"]).last()
        if queryset:
            return queryset.revision.all().order_by("sequence")
        return []


class EventProvidersView(ListCreateAPIView):
    serializer_class = EventProviderSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = (IsOwner,)

    def get_queryset(self):
        return EventProvider.objects.filter(owner=self.request.user, is_active=True).order_by("display")


class EventStateView(RetrieveUpdateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventStateSerializer

    lookup_field = "id"

    def get_queryset(self):
        return Event.objects.all()


class EventView(RetrieveUpdateDestroyAPIView):
    permission_classes = (EventCategoryGeographicPermission,)
    serializer_class = EventSerializer

    lookup_field = "id"

    @etag(etag_func=calculate_event_etag)
    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj:
            self.check_object_permissions(self.request, obj)
        return super().get(request, *args, **kwargs)

    def get_serializer_context(self):
        query_params = self.request.query_params if self.request and hasattr(self.request, "query_params") else {}

        context = super().get_serializer_context()

        context["include_updates"] = parse_bool(query_params.get("include_updates", True))
        context["include_notes"] = parse_bool(query_params.get("include_notes", True))
        context["include_files"] = parse_bool(query_params.get("include_files", True))
        context["include_related_events"] = parse_bool(query_params.get("include_related_events", True))
        context["request"] = self.request
        return context

    def get_queryset(self):
        queryset = Event.objects.all()
        queryset = queryset.select_related("das_tenant", "event_type", "event_type__category").prefetch_related(
            "geometries"
        )

        event_filter = self.request.query_params.get("filter", None)
        if event_filter:
            try:
                event_filter = json.loads(event_filter)
                return queryset.by_event_filter(event_filter)
            except:
                logger.warning("Invalid filter expression %s", event_filter)

        queryset = queryset.annotate(patrol_ids=ArrayAgg("patrol_segments__patrol_id"))
        return queryset


class EventsExportView(APIView):
    permission_classes = (UserCanExportDataPermission, EventCategoryPermissions)

    def get_event_export_list(self):
        event_export_data = []

        renderer = schema_utils.get_schema_renderer_method()

        current_event_type_data = {"id": None}
        current_tz_name = timezone.get_current_timezone_name()
        current_tz = pytz.timezone(current_tz_name)
        current_date = datetime.utcnow().astimezone(current_tz)
        tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
        tz_offset = (
            "GMT"
            + ("+" if tz_difference >= 0 else "")
            + str(int(tz_difference))
            + ":"
            + str(int((tz_difference - int(tz_difference)) * 60))
        )
        reported_at = f"Reported At ({tz_offset})"
        default_headers = [
            "Report Type",
            "Report Type Internal Value",
            "Report Id",
            "Title",
            "Priority",
            "Priority Internal Value",
            "Report Status",
            "Reported By",
            reported_at,
            "Latitude",
            "Longitude",
            "Number of Notes",
            "Notes",
            "Number of Related Subjects",
            "Collection Report IDs",
            "Area",
            "Perimeter",
            "Attachments",
            "CUSTOM FIELDS BEGIN HERE",
        ]
        custom_headers = []
        combined_headers = []

        reported_by_map = generate_reported_by_lookup()
        event_type_map = generate_event_type_cache()

        queryset = self.get_queryset()
        user_subjects = list(Subject.objects.by_user_subjects(self.request.user).values_list("id", flat=True))
        queryset = queryset.filter(Q(related_subjects__isnull=True) | Q(related_subjects__in=user_subjects))

        file_subquery = EventFile.objects.filter(event=OuterRef("id")).values(
            data=JSONObject(usercontent_type="usercontent_type", usercontent_id="usercontent_id", id="id")
        )

        for event in (
            queryset.annotate(notes_count=Count("note"))
            .annotate(full_notes=StringAgg("note__text", delimiter="\n", output_field=TextField()))
            .annotate(related_subjects_count=Count("related_subjects"))
            .annotate(file_ids=ArraySubquery(file_subquery))
            .annotate(parent_event_serial_numbers=ArrayAgg("in_relationship__from_event__serial_number", distinct=True))
            .prefetch_related("geometries")
            .prefetch_related("files")
            .values(
                "id",
                "serial_number",
                "priority",
                "state",
                "title",
                "event_type_id",
                "event_details__data",
                "notes_count",
                "full_notes",
                "parent_event_serial_numbers",
                "location",
                "event_time",
                "reported_by_id",
                "related_subjects_count",
                "geometries__properties",
                "file_ids",
            )
        ):
            if event["event_type_id"] != current_event_type_data["id"]:
                event_type = event_type_map[event["event_type_id"]]

                current_event_type_data = {
                    "id": event["event_type_id"],
                    "display": event_type["display"],
                    "value": event_type["value"],
                    "events": [],
                    "headers": copy.deepcopy(default_headers),
                }

                try:
                    current_schema = renderer(event_type["schema"])
                    current_schema_order = schema_utils.property_keys_order_as_dict(current_schema)

                    for key, order in current_schema_order.items():
                        if not isinstance(key, int):
                            display_value = schema_utils.get_display_value_header_for_key(current_schema, key)
                            current_event_type_data["headers"].append(self.escape_string(key))
                            current_event_type_data["headers"].append(self.escape_string(display_value))

                            if self.value_cols and key not in custom_headers:
                                custom_headers.append(key)

                            if self.display_cols:
                                column_name = schema_utils.get_column_header_name(current_schema, key)
                                column_name = self.escape_string(column_name)
                                if column_name not in custom_headers:
                                    custom_headers.append(column_name)

                except json.JSONDecodeError:
                    # Event type does not have schema, which is weird but not
                    # _technically_ invalid
                    current_schema = None
                    current_schema_order = {}

                event_export_data.append(current_event_type_data)
            # First, get the event details (schema data) in the correct order
            # for the headers above
            if event["event_details__data"]:
                details = schema_utils.get_display_values_for_event_details(
                    event["event_details__data"].get("event_details", {}), current_schema
                )
            else:
                details = {}

            schema_data = OrderedDict()
            for key, order in current_schema_order.items():
                item_display_name = schema_utils.get_display_value_header_for_key(current_schema, key)
                schema_data[key] = self.escape_string(details.get(key, ""))
                column_name = schema_utils.get_column_header_name(current_schema, key)
                schema_data[column_name] = self.escape_string(details.get(item_display_name, ""))

            attachments = []
            for file_ref in event.get("file_ids"):
                file_id = file_ref["usercontent_id"]
                file_content_type = file_ref["usercontent_type"]
                usercontent_type = ContentType.objects.get(id=file_content_type)
                try:
                    file_url = usercontent_type.model_class().objects.get(id=file_id).file.url
                except AttributeError:
                    self.logger.exception(
                        "Error getting file url for contenttype %s and file id %s", file_content_type, file_id
                    )
                    break
                else:
                    attachments.append(file_url)

            # Now assemble the data we want to write to the csv
            event_data = {
                "Report_Type": event_type.get("display", ""),
                "Report_Type_Internal_Value": event_type.get("value", ""),
                "Report_Id": event.get("serial_number", ""),
                "Title": self.escape_string(event.get("title", "")),
                "Priority": Event.PRIORITY_LABELS_MAP.get(event.get("priority", ""), ""),
                "Priority_Internal_Value": event.get("priority", ""),
                "Report_Status": "Resolved" if event["state"] == Event.SC_RESOLVED else "Active",
                reported_at.replace(" ", "_"): event["event_time"].astimezone(current_tz).strftime("%Y-%m-%d %H:%M"),
                "Latitude": event["location"].y if event["location"] is not None else "",
                "Longitude": event["location"].x if event["location"] is not None else "",
                "Number_of_Notes": event.get("notes_count", ""),
                "Notes": self.escape_string(event.get("full_notes", "")),
                "Number_of_Related_Subjects": event.get("", ""),
                "Collection_Report_IDs": ";".join(
                    (str(x) for x in event["parent_event_serial_numbers"] if x is not None)
                ),
                "CUSTOM_FIELDS_BEGIN_HERE": "",
                "Area": self._get_polygon_property(event, "area"),
                "Perimeter": self._get_polygon_property(event, "perimeter"),
                "Attachments": " \n".join(str(x) for x in attachments),
            }

            # Use cached reported_by map
            reported_by_values = reported_by_map.get(str(event.get("reported_by_id", "")), "")
            event_data["Reported_By"] = reported_by_values.get("display", "") if reported_by_values else ""

            for header in custom_headers:
                header_key = header.replace(" ", "_")
                # if header has been escaped
                if header.startswith('"') and header.endswith('"'):
                    header = header[1:-1]
                column_data = schema_data.get(header, "")
                event_data[header_key] = column_data if (column_data is not None) else ""

            current_event_type_data["events"].append(event_data)

        if not combined_headers:
            combined_headers.extend(default_headers)
            combined_headers.extend(custom_headers)

        return {
            "event_export_data": event_export_data,
            "combined_headers": [header.replace(" ", "_") for header in combined_headers],
            "custom_headers": custom_headers,
        }

    def _get_polygon_property(self, event: dict, key: str) -> Union[float, str]:
        properties = event.get("geometries__properties", {})
        if properties:
            result = properties.get(key, 0)
            if result:
                return round(float(result), 2)
        return ""

    def escape_string(self, string):
        if not isinstance(string, str) or not string:
            return string
        strings = string.splitlines()
        string = " ".join(strings)
        return string

    def get(self, request, *args, **kwargs):
        self.value_cols = request.GET.get("value_cols", False)
        self.display_cols = request.GET.get("display_cols", True)

        csv_data = self.prepare_csv_data()

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename={csv_data["report_filename"]}'
        response["x-das-download-filename"] = csv_data["report_filename"]

        writer = csv.DictWriter(response, fieldnames=csv_data["event_types"].get("combined_headers"))
        writer.writeheader()
        event_types = csv_data["event_types"]
        for event_type in event_types.get("event_export_data", []):
            for event in event_type.get("events", {}):
                writer.writerow(event)
        return response

    def prepare_csv_data(self, **kwargs):
        REPORT_TIME_FORMAT = "%-d %B %Y %Z" if platform.system().lower() != "windows" else "%#d %B %Y %Z"
        current_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = current_tz.localize(datetime.utcnow())
        csv_data = {
            "report_filename": f'Event Export {timestamp.strftime("%Y-%m-%d")}.csv',
            "report_time": timestamp.strftime(REPORT_TIME_FORMAT),
            "event_types": self.get_event_export_list(),
        }

        return csv_data

    def get_queryset(self):
        # TODO: Update to allow passing last_days constraint.

        queryset = Event.objects.all().prefetch_related("event_type")

        permitted_event_categories = get_permitted_event_categories(self.request)

        if len(permitted_event_categories) > 0:
            queryset = queryset.filter(event_type__category__in=permitted_event_categories)
        else:
            return queryset.none()

        query_params = self.request.query_params
        bbox = query_params.get("bbox", None)
        if bbox:
            bbox = bbox.split(",")
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")

            queryset = queryset.by_bbox(bbox)

        event_filter = self.request.query_params.get("filter", None)
        if event_filter:
            try:
                event_filter = json.loads(event_filter)
                queryset = queryset.by_event_filter(event_filter)
            except json.JSONDecodeError:
                logger.exception("Invalid filter expression. filter=%s", event_filter)
                raise

        state = query_params.getlist("state", None)
        if state:
            queryset = queryset.by_state(state)

        contained_event_ids = (
            queryset.filter(event_type__is_collection=True)
            .aggregate(child_event_ids=ArrayAgg("out_relationship__to_event"))
            .get("child_event_ids")
        )

        if contained_event_ids:
            child_events = Event.objects.filter(id__in=contained_event_ids)
            queryset = queryset.distinct() | child_events.distinct()

        return queryset.order_by("event_type_id")


class EventsView(ListCreateAPIView):
    __doc__ = """
    Returns all events.
    Optional query-params:
    bbox, where bbox is the (west, south, east, north) lon,lat pairs.
        example: bbox=14.24, .41, 15.45, 1.66
    event_type
    state
    include_updates, true to include event updates
    include_notes, true to include notes

    sort_by, valid values are event_time, updated_at, created_at, serial_number (prefix with '-' for reverse order)
    * default is by '-sort_at' which is a special value representing reverse by updated_at.

    page, page number

    page_size, (default is {page_size}, max is {max_page_size})
    """.format(
        page_size=CachedCountResultsSetPagination.page_size, max_page_size=CachedCountResultsSetPagination.max_page_size
    )
    permission_classes = (EventCategoryGeographicPermission,)
    filter_backends = (
        EventPermissionsFilter,
        EventListFilter,
        EventSubjectsFilter,
        OrderingFilter,
    )
    serializer_class = EventSerializer
    pagination_class = CachedCountResultsSetPagination
    metadata_class = EventJSONSchema
    ordering_fields = ("event_time", "updated_at", "serial_number", "created_at", "sort_at")
    ordering = ("-sort_at",)

    page_count_ignored_query_parameters = (
        "format",
        "sort_by",
        "include_updates",
        "include_details",
        "include_files",
        "include_related_events",
        "include_notes",
    )

    schema = EventsViewSchema()

    def list(self, request: Request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self.optimize_queryset(queryset)

        try:
            if self.paginator:
                queryset = self.paginate_queryset(queryset)
                serializer = self.get_serializer(queryset, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        except InvalidTextRepresentation as error:
            logger.exception(f"Possible SQL injection detected, returning empty results: {error}")
            data = {"count": 0, "next": None, "previous": None, "results": []}

            return Response(data=data, status=status.HTTP_200_OK)
        except DataError:
            data = {"count": 0, "next": None, "previous": None, "results": []}

            return Response(data=data, status=status.HTTP_200_OK)

    def post(self, request: Request, *args, **kwargs) -> Response:
        request.POST._mutable = True
        new_record = request.data
        if isinstance(new_record, dict):
            new_record = [new_record]

        patrol_segment = self.kwargs.get("patrol_segment")
        if patrol_segment:
            new_record = self.add_segment_to_record(patrol_segment, new_record)

        with transaction.atomic():
            errors = []
            serializer = self.get_serializer(data=new_record, many=True)
            if serializer.is_valid():
                serializer.save()
                data = serializer.data
                data = data if len(new_record) > 1 else data[0]
                return Response(data, status=status.HTTP_201_CREATED)
            else:
                errors.append(serializer.errors)
                for error in errors:
                    logger.exception("Invalid Event type(s) provided {}".format(error))
                    return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    def get_serializer_class(self) -> Type[Serializer]:
        if self.kwargs.get("patrol_segment") and self.request.method == "GET":
            return PatrolSegmentEventSerializer
        return super().get_serializer_class()

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        query_params = self.request.query_params
        context["include_updates"] = parse_bool(query_params.get("include_updates", True))
        context["include_details"] = parse_bool(query_params.get("include_details", True))
        context["include_files"] = parse_bool(query_params.get("include_files", True))

        # if this is a POST, returned any contained events
        include_for_posts = self.request._request.method == "POST"

        context["include_related_events"] = parse_bool(query_params.get("include_related_events", include_for_posts))
        context["include_notes"] = parse_bool(query_params.get("include_notes", include_for_posts))

        return context

    def get_queryset(self) -> QuerySet:
        queryset = Event.objects.all()

        patrol_segment_id = self.kwargs.get("patrol_segment")
        if patrol_segment_id:
            logger.debug("Filtering on patrol segment id: %s", patrol_segment_id)
            queryset = queryset.filter(patrol_segments__id=patrol_segment_id)

        return queryset

    def optimize_queryset(self, queryset: QuerySet) -> QuerySet:
        serializer_context = self.get_serializer_context()
        permitted_categories = get_permitted_event_categories(self.request)

        queryset = queryset.select_related("event_type__category", "created_by_user")

        queryset = queryset.prefetch_related(
            Prefetch("eventsource_event_refs__eventsource__eventprovider"),
            Prefetch("reported_by"),
            Prefetch("patrol_segments"),
            Prefetch("geometries"),
            Prefetch("event_details", to_attr="event_details_set"),
            Prefetch("related_subjects", to_attr="related_subjects_set"),
            Prefetch(
                "in_relationships",
                to_attr="relationship_in_contains",
                queryset=EventRelationship.objects.filter(type__value="contains")
                .order_by("ordernum", "to_event__created_at")
                .all(),
            ),
            Prefetch(
                "out_relationships",
                to_attr="relationship_out_contains",
                queryset=EventRelationship.objects.filter(
                    to_event__event_type__category__in=permitted_categories, type__value="contains"
                )
                .order_by("ordernum", "to_event__created_at")
                .all(),
            ),
            Prefetch(
                "out_relationships",
                to_attr="relationship_out_is_linked_to",
                queryset=EventRelationship.objects.filter(
                    to_event__event_type__category__in=permitted_categories, type__value="is_linked_to"
                )
                .order_by("ordernum", "to_event__created_at")
                .all(),
            ),
        )

        queryset = queryset.annotate(patrol_ids=ArrayAgg("patrol_segments__patrol_id"))

        if serializer_context.get("include_notes"):
            queryset = queryset.prefetch_related("notes")
        if serializer_context.get("include_files"):
            queryset = queryset.prefetch_related("files")
        return queryset

    def add_segment_to_record(self, patrol_segment_id: Union[List[str], str], new_record: List[Dict]) -> List[Dict]:
        for record in new_record:
            if not record.get("patrol_segments"):
                record["patrol_segments"] = (
                    patrol_segment_id if isinstance(patrol_segment_id, list) else [patrol_segment_id]
                )
            else:
                record["patrol_segments"].append(patrol_segment_id)
        return new_record


class EventsGeoJsonView(EventsView):
    serializer_class = EventGeoJsonSerializer
    pagination_class = StandardResultsSetGeoJsonPagination
    renderer_classes = (ExtendedGEOJSONRenderer,)
