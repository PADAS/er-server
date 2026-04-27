import json
import logging
from collections import OrderedDict, defaultdict
from datetime import datetime
from typing import Dict, List, Type, Union

import pytz
from django_multitenant.utils import get_current_tenant
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
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
from rest_framework.serializers import IntegerField, Serializer
from rest_framework.views import APIView

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
    EventNote,
    EventProvider,
    EventRelationship,
)
from activity.permissions import (
    EventCategoryGeographicPermission,
    EventCategoryPermissions,
    IsOwner,
)
from activity.schemas.schema_adapter import SchemaAdapterFactory
from activity.serializers import (
    EventBulkDeleteSerializer,
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
from utils.date import convert_to_timezone, get_current_time_zone, get_timezone_offset
from utils.db.expresions import ArraySubquery
from utils.drf import StandardResultsSetGeoJsonPagination, StandardResultsSetPagination
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
        queryset = EventGeometry.objects.filter(event__id=self.kwargs.get("event_id")).last()
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

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().partial_update(request, *args, **kwargs)

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
            except (json.JSONDecodeError, ValueError):
                logger.warning("Invalid filter expression %s", event_filter)

        queryset = queryset.annotate(patrol_ids=ArrayAgg("patrol_segments__patrol_id"))
        return queryset


class EventsExportView(APIView):
    permission_classes = (UserCanExportDataPermission, EventCategoryPermissions)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Cache containers are request-scoped via the properties below to avoid
        # leaking data if a view instance is ever reused across requests.

    @property
    def _content_type_cache(self):
        """
        Request-scoped cache for content types.

        The underlying dict is stored on the DRF Request instance so that
        each HTTP request gets an isolated cache, even if the view instance
        is reused.
        """
        request = getattr(self, "request", None)
        if request is not None:
            cache = getattr(request, "_events_export_content_type_cache", None)
            if cache is None:
                cache = {}
                setattr(request, "_events_export_content_type_cache", cache)
            return cache
        # Fallback for code paths where self.request is not yet set
        if not hasattr(self, "__content_type_cache"):
            self.__content_type_cache = {}
        return self.__content_type_cache

    @property
    def _file_model_cache(self):
        """
        Request-scoped cache for file models.

        The underlying dict is stored on the DRF Request instance so that
        each HTTP request gets an isolated cache, even if the view instance
        is reused.
        """
        request = getattr(self, "request", None)
        if request is not None:
            cache = getattr(request, "_events_export_file_model_cache", None)
            if cache is None:
                cache = {}
                setattr(request, "_events_export_file_model_cache", cache)
            return cache
        # Fallback for code paths where self.request is not yet set
        if not hasattr(self, "__file_model_cache"):
            self.__file_model_cache = {}
        return self.__file_model_cache

    def _get_default_headers(self, reported_at_label):
        """Get the default (non-custom) CSV headers."""
        return [
            "Report Type",
            "Report Type Internal Value",
            "Report Id",
            "Title",
            "Priority",
            "Priority Internal Value",
            "Report Status",
            "Reported By",
            reported_at_label,
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

    def _build_custom_headers(self, event_type_map, event_type_ids=None):
        """
        Pre-compute custom headers by scanning event types that appear in the export.

        Only processes event types that have matching events in the queryset,
        preserving the same column set as the original non-streaming implementation.

        Args:
            event_type_map: Dict of all event types keyed by ID.
            event_type_ids: Optional set of event type IDs to include. If None,
                           all event types in event_type_map are processed.
        """
        custom_headers = []

        for event_type_id, event_type in event_type_map.items():
            if event_type_ids is not None and event_type_id not in event_type_ids:
                continue

            try:
                schema_adapter = SchemaAdapterFactory.create_adapter(event_type["schema"], self.request)
                current_schema_order = schema_adapter.get_property_order()

                for key, order in current_schema_order.items():
                    if not isinstance(key, int):
                        if self.value_cols and key not in custom_headers:
                            custom_headers.append(key)

                        if self.display_cols:
                            column_name = schema_adapter.get_column_header_name(key)
                            column_name = self.escape_string(column_name)
                            if column_name not in custom_headers:
                                custom_headers.append(column_name)

            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.warning("Failed to process schema for event type %s: %s", event_type.get("value"), str(e))
                continue

        return custom_headers

    def _get_content_type_cached(self, content_type_id):
        """Get ContentType with caching to avoid N+1 queries."""
        if content_type_id not in self._content_type_cache:
            self._content_type_cache[content_type_id] = ContentType.objects.get(id=content_type_id)
        return self._content_type_cache[content_type_id]

    def _get_file_url(self, file_ref):
        """Get file URL with caching to reduce repeated lookups."""
        file_id = file_ref["usercontent_id"]
        file_content_type = file_ref["usercontent_type"]

        cache_key = (file_content_type, file_id)
        if cache_key in self._file_model_cache:
            return self._file_model_cache[cache_key]

        try:
            usercontent_type = self._get_content_type_cached(file_content_type)
            file_obj = usercontent_type.model_class().objects.get(id=file_id)
            file_url = file_obj.file.url
            self._file_model_cache[cache_key] = file_url
            return file_url
        except (AttributeError, Exception) as e:
            logger.warning(
                "Error getting file url for contenttype %s and file id %s: %s", file_content_type, file_id, e
            )
            return None

    def _preload_file_url_cache(self, events_qs: QuerySet) -> None:
        """Batch-fetch all file URLs for events in the queryset to avoid N+1 queries.

        Groups EventFile records by content type and fetches all file objects for
        each type in a single query, reducing attachment resolution from O(N) DB
        queries to O(content_type_count) queries.
        """
        by_content_type: dict[int, list[str]] = defaultdict(list)

        for usercontent_type_id, usercontent_id in (
            EventFile.objects.filter(event__in=events_qs)
            .values_list("usercontent_type_id", "usercontent_id")
            .iterator()
        ):
            by_content_type[usercontent_type_id].append(str(usercontent_id))

        if not by_content_type:
            return

        for ct_id, file_ids in by_content_type.items():
            content_type = self._get_content_type_cached(ct_id)
            file_model = content_type.model_class()
            if file_model is None:
                logger.warning("ContentType %s has no model_class; caching nulls for %d files", ct_id, len(file_ids))
                for file_id in file_ids:
                    self._file_model_cache[(ct_id, file_id)] = None
                continue

            try:
                file_objs = list(file_model.objects.filter(id__in=file_ids).iterator(chunk_size=2000))
            except Exception:
                logger.exception("Error preloading file urls for contenttype %s", ct_id)
                for file_id in file_ids:
                    self._file_model_cache[(ct_id, file_id)] = None
                continue

            found_ids: set[str] = set()
            for file_obj in file_objs:
                cache_key = (ct_id, str(file_obj.id))
                found_ids.add(str(file_obj.id))
                # Storage backends may raise varied exceptions (S3, filesystem, etc.);
                # degrade to None so the export continues instead of 500-ing.
                try:
                    self._file_model_cache[cache_key] = file_obj.file.url
                except Exception:
                    logger.exception("Error getting URL for file %s", file_obj.id)
                    self._file_model_cache[cache_key] = None

            for file_id in file_ids:
                if file_id not in found_ids:
                    self._file_model_cache[(ct_id, file_id)] = None

    def _get_annotated_queryset(self, queryset: QuerySet) -> QuerySet:
        """Annotate the given queryset with the fields needed for CSV export.

        The caller is responsible for applying permission filters (e.g., related
        subjects) before passing the queryset in.
        """
        file_subquery = EventFile.objects.filter(event=OuterRef("id")).values(
            data=JSONObject(usercontent_type="usercontent_type", usercontent_id="usercontent_id", id="id")
        )

        return (
            queryset.annotate(notes_count=Count("note"))
            .annotate(full_notes=StringAgg("note__text", delimiter="\n", output_field=TextField()))
            .annotate(related_subjects_count=Count("related_subjects"))
            .annotate(file_ids=ArraySubquery(file_subquery))
            .annotate(parent_event_serial_numbers=ArrayAgg("in_relationship__from_event__serial_number", distinct=True))
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
        )

    def _generate_event_rows(
        self, queryset, custom_headers, reported_at_label, event_type_map, reported_by_map, current_tz
    ):
        """
        Generator that yields CSV rows for streaming response.
        """
        current_event_type_data = {"id": None}
        schema_adapter = None
        current_schema_order = {}
        event_type = None

        for event in queryset.iterator(chunk_size=2000):
            # Update schema adapter when event type changes
            if event["event_type_id"] != current_event_type_data["id"]:
                event_type = event_type_map.get(event["event_type_id"], {})

                current_event_type_data = {
                    "id": event["event_type_id"],
                    "display": event_type.get("display", ""),
                    "value": event_type.get("value", ""),
                }

                try:
                    schema_adapter = SchemaAdapterFactory.create_adapter(event_type.get("schema"), self.request)
                    current_schema_order = schema_adapter.get_property_order()
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.warning("Failed to process schema for event type %s: %s", event_type.get("value"), str(e))
                    schema_adapter = None
                    current_schema_order = {}

            # Process event details
            if event["event_details__data"] and schema_adapter:
                details = schema_adapter.get_display_values_for_event_details(
                    event["event_details__data"].get("event_details", {})
                )
            else:
                details = {}

            # Build schema data for custom fields
            schema_data = OrderedDict()
            if schema_adapter:
                for key, order in current_schema_order.items():
                    item_display_name = schema_adapter.get_display_value_header_for_key(key)
                    schema_data[key] = self.escape_string(details.get(key, ""))
                    column_name = schema_adapter.get_column_header_name(key)
                    schema_data[column_name] = self.escape_string(details.get(item_display_name, ""))

            # Get attachments with caching
            attachments = []
            for file_ref in event.get("file_ids") or []:
                file_url = self._get_file_url(file_ref)
                if file_url:
                    attachments.append(file_url)

            # Build the row data
            event_data = {
                "Report_Type": event_type.get("display", ""),
                "Report_Type_Internal_Value": event_type.get("value", ""),
                "Report_Id": event.get("serial_number", ""),
                "Title": self.escape_string(event.get("title", "")),
                "Priority": Event.PRIORITY_LABELS_MAP.get(event.get("priority", ""), ""),
                "Priority_Internal_Value": event.get("priority", ""),
                "Report_Status": "Resolved" if event["state"] == Event.SC_RESOLVED else "Active",
                reported_at_label: convert_to_timezone(event["event_time"], current_tz).strftime("%Y-%m-%d %H:%M"),
                "Latitude": event["location"].y if event["location"] is not None else "",
                "Longitude": event["location"].x if event["location"] is not None else "",
                "Number_of_Notes": event.get("notes_count", ""),
                "Notes": self.escape_string(event.get("full_notes", "")),
                "Number_of_Related_Subjects": event.get("related_subjects_count", ""),
                "Collection_Report_IDs": ";".join(
                    (str(x) for x in event["parent_event_serial_numbers"] if x is not None)
                ),
                "CUSTOM_FIELDS_BEGIN_HERE": "",
                "Area": self._get_polygon_property(event, "area"),
                "Perimeter": self._get_polygon_property(event, "perimeter"),
                "Attachments": " \n".join(str(x) for x in attachments),
            }

            # Add reported_by from cached map
            reported_by_values = reported_by_map.get(str(event.get("reported_by_id", "")), "")
            event_data["Reported_By"] = reported_by_values.get("display", "") if reported_by_values else ""

            # Add custom fields
            for header in custom_headers:
                header_key = header.replace(" ", "_")
                if header.startswith('"') and header.endswith('"'):
                    header = header[1:-1]
                column_data = schema_data.get(header, "")
                event_data[header_key] = column_data if (column_data is not None) else ""

            yield event_data

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
        from utils.csv_streaming import StreamingCSVResponse

        self.value_cols = parse_bool(request.GET.get("value_cols", "false"))
        self.display_cols = parse_bool(request.GET.get("display_cols", "true"))

        # Prepare timezone and headers
        current_tz = get_current_time_zone()
        current_date = datetime.now(tz=current_tz)
        tz_offset = get_timezone_offset(current_date)
        reported_at_label = f"Reported_At_({tz_offset})"

        # Pre-compute caches
        reported_by_map = generate_reported_by_lookup()
        event_type_map = generate_event_type_cache()

        # Apply the related-subjects permission filter once and reuse for header
        # generation, attachment preloading, and row annotation — so we only
        # process events the user is allowed to see and only query user_subjects once.
        user_subjects = list(Subject.objects.by_user_subjects(self.request.user).values_list("id", flat=True))
        filtered_queryset = self.get_queryset().filter(
            Q(related_subjects__isnull=True) | Q(related_subjects__in=user_subjects)
        )

        event_type_ids_in_export = set(filtered_queryset.values_list("event_type_id", flat=True).distinct())
        queryset = self._get_annotated_queryset(filtered_queryset)

        default_headers = self._get_default_headers(f"Reported At ({tz_offset})")
        custom_headers = self._build_custom_headers(event_type_map, event_type_ids_in_export)
        combined_headers = [header.replace(" ", "_") for header in default_headers]
        combined_headers.extend([header.replace(" ", "_") for header in custom_headers])

        # Generate filename
        local_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = local_tz.localize(datetime.utcnow())
        download_filename = f'Event Export {timestamp.strftime("%Y-%m-%d")}.csv'

        # Pre-populate file URL cache to avoid N+1 queries during row generation.
        self._preload_file_url_cache(filtered_queryset)

        # Create streaming response
        row_generator = self._generate_event_rows(
            queryset, custom_headers, reported_at_label, event_type_map, reported_by_map, current_tz
        )

        return StreamingCSVResponse(
            row_generator=row_generator,
            fieldnames=combined_headers,
            filename=download_filename,
        )

    def get_queryset(self):
        # TODO: Update to allow passing last_days constraint.

        queryset = Event.objects.all()

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

        # Only union in child events when collection events are actually present.
        # The unconditional union form is simpler but adds an extra subquery to every
        # export query — revisit if exports of large non-collection result sets ever
        # show measurable regression here.
        collection_qs = queryset.filter(event_type__is_collection=True)
        if collection_qs.exists():
            child_events = Event.objects.filter(
                id__in=EventRelationship.objects.filter(from_event__in=collection_qs).values_list(
                    "to_event_id", flat=True
                )
            )
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

    page_size
    """
    permission_classes = (EventCategoryGeographicPermission,)
    filter_backends = (
        EventPermissionsFilter,
        EventListFilter,
        EventSubjectsFilter,
        OrderingFilter,
    )
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
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

    def _build_revisions_cache(self, events: list) -> dict:
        """Bulk-fetch all EventRevision rows for a page of events in one query."""
        event_ids = [e.pk for e in events]
        if not event_ids:
            return {}
        revision_model = Event.revision.model
        revisions = (
            revision_model.objects.filter(object_id__in=event_ids, das_tenant=get_current_tenant())
            .select_related("user")
            .order_by("sequence")
        )
        cache: dict = {}
        for rev in revisions:
            cache.setdefault(rev.object_id, []).append(rev)
        return cache

    def list(self, request: Request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self.optimize_queryset(queryset)

        try:
            if self.paginator:
                page = self.paginate_queryset(queryset)
                context = self.get_serializer_context()
                if context.get("include_updates"):
                    context["revisions_cache"] = self._build_revisions_cache(page)
                serializer = self.get_serializer(page, many=True, context=context)
                return self.get_paginated_response(serializer.data)

            events = list(queryset)
            context = self.get_serializer_context()
            if context.get("include_updates"):
                context["revisions_cache"] = self._build_revisions_cache(events)
            serializer = self.get_serializer(events, many=True, context=context)
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
            serializer = self.get_serializer(data=new_record, many=True)
            if not serializer.is_valid():
                logger.exception("Invalid Event type(s) provided %s", serializer.errors)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            serializer.save()
            data = serializer.data
            data = data if len(new_record) > 1 else data[0]
            return Response(data, status=status.HTTP_201_CREATED)

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

        queryset = queryset.select_related("event_type__category", "created_by_user", "reported_by_content_type")

        _rel_qs = EventRelationship.objects.select_related(
            "type", "to_event__event_type__category", "from_event__event_type__category"
        )

        prefetches = [
            Prefetch("eventsource_event_refs__eventsource__eventprovider"),
            Prefetch("reported_by"),
            Prefetch("patrol_segments"),
            Prefetch("geometries"),
            Prefetch("related_subjects", to_attr="related_subjects_set"),
            Prefetch(
                "in_relationships",
                to_attr="relationship_in_contains",
                queryset=_rel_qs.filter(type__value="contains").order_by("ordernum", "to_event__created_at"),
            ),
            Prefetch(
                "out_relationships",
                to_attr="relationship_out_contains",
                queryset=_rel_qs.filter(
                    to_event__event_type__category__in=permitted_categories, type__value="contains"
                ).order_by("ordernum", "to_event__created_at"),
            ),
            Prefetch(
                "out_relationships",
                to_attr="relationship_out_is_linked_to",
                queryset=_rel_qs.filter(
                    to_event__event_type__category__in=permitted_categories, type__value="is_linked_to"
                ).order_by("ordernum", "to_event__created_at"),
            ),
        ]

        if serializer_context.get("include_details"):
            prefetches.append(Prefetch("event_details", to_attr="event_details_set"))
        if serializer_context.get("include_notes"):
            prefetches.append(Prefetch("notes", queryset=EventNote.objects.select_related("created_by_user")))
        if serializer_context.get("include_files"):
            prefetches.append(Prefetch("files", queryset=EventFile.objects.select_related("created_by")))

        queryset = queryset.prefetch_related(*prefetches)
        queryset = queryset.annotate(patrol_ids=ArrayAgg("patrol_segments__patrol_id"))
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


class EventBulkDeleteView(APIView):
    http_method_names = ["delete", "options"]
    permission_classes = (EventCategoryPermissions,)

    @extend_schema(
        request=EventBulkDeleteSerializer,
        responses={
            200: inline_serializer("EventBulkDeleteResponse", {"deleted": IntegerField()}),
            400: OpenApiResponse(description="Invalid payload (ids missing, not a list, or not valid UUIDs)."),
            403: OpenApiResponse(
                description="Caller lacks delete permission for one or more events, or an id was not found."
            ),
        },
        summary="Bulk-delete events",
        description=(
            "Delete multiple events atomically. All-or-nothing: if any id is unknown or the caller lacks "
            "`{category}_delete` for any event's category, nothing is deleted."
        ),
    )
    def delete(self, request, *args, **kwargs):
        serializer = EventBulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        if not ids:
            return Response({"deleted": 0})

        with transaction.atomic():
            events_qs = (
                Event.objects.select_for_update(of=("self",))
                .filter(id__in=ids)
                .select_related("event_type__category")
                .prefetch_related("related_subjects")
            )
            events = list(events_qs)

            found_ids = {event.id for event in events}
            requested_ids = set(ids)

            if found_ids != requested_ids:
                # 403 (not 404) on missing IDs so we don't leak the existence
                # of events the caller can't otherwise see.
                return Response(
                    {"detail": "You do not have permission to delete one or more of the requested events."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            for event in events:
                self.check_object_permissions(request, event)

            events_qs.delete()

        return Response({"deleted": len(found_ids)})


class EventsGeoJsonView(EventsView):
    serializer_class = EventGeoJsonSerializer
    pagination_class = StandardResultsSetGeoJsonPagination
    renderer_classes = (ExtendedGEOJSONRenderer,)
