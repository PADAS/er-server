import json
import logging
from enum import Enum
from typing import Optional, Tuple

from django_filters import rest_framework as filters

from django.db import models
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from activity.exceptions import SchemaRenderingError
from activity.filters import EventTypeFilter
from activity.models import Event, EventType
from activity.permissions import EventCategoryPermissions
from activity.schemas.schema_rendering import SchemaRenderer
from activity.schemas.schema_retrieving import build_dynamic_schemas_registry
from activity.serializers.events_v2 import EventTypeSerializer
from activity.views.events.utils import AllowedCategoriesMixin
from activity.views.schemas import EventTypeViewSchema
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer, parse_bool
from utils.views import EtagListRetrieveModelMixin

logger = logging.getLogger(__name__)


class StrEnum(str, Enum):
    """Enum that can be used as a string."""


class RenderStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class RenderErrors(StrEnum):
    NO_SCHEMA_DEFINED = "no_schema_defined"
    INVALID_JSON = "invalid_json"
    NO_JSON_KEY = "no_json_key"
    INVALID_SCHEMA = "invalid_schema"
    SCHEMA_RENDERING_ERROR = "rendering_error"


def parse_and_render_schema(event_type: EventType, schema_renderer: Optional[SchemaRenderer]) -> Tuple[bool, dict]:
    """
    Attempts to parse the raw event_type.schema as JSON, check if 'json' key is present,
    and de-reference using schema_renderer if provided.

    :return: (success, data) where
            success = True => data is the fully prepared schema
            success = False => data is an error dict with 'code' and 'message'
    """
    if not event_type.schema:
        return (
            False,
            {
                "code": RenderErrors.NO_SCHEMA_DEFINED,
                "message": f"EventType {event_type.value} has no schema defined.",
            },
        )

    try:
        parsed_schema = json.loads(event_type.schema)
    except json.JSONDecodeError as e:
        logger.warning("Error decoding JSON for event type %s: %s", event_type.value, str(e))
        return (
            False,
            {
                "code": RenderErrors.INVALID_JSON,
                "message": f"Invalid JSON for event type {event_type.value}: {str(e)}",
            },
        )

    if "json" not in parsed_schema:
        return (
            False,
            {
                "code": RenderErrors.NO_JSON_KEY,
                "message": f"Schema for event type {event_type.value} does not contain 'json' key.",
            },
        )

    if not schema_renderer:
        # Return as-is
        return (True, parsed_schema)

    # Attempt render
    try:
        parsed_schema["json"] = schema_renderer.dereference_schema(parsed_schema["json"])
        return (True, parsed_schema)
    except SchemaRenderingError as e:
        logger.warning("Error rendering schema for event type %s: %s", event_type.value, str(e))
        return (
            False,
            {
                "code": RenderErrors.SCHEMA_RENDERING_ERROR,
                "message": f"Error rendering schema for event type {event_type.value}: {str(e)}",
            },
        )


class EventTypesViewSet(EtagListRetrieveModelMixin, AllowedCategoriesMixin, ModelViewSet):

    schema = EventTypeViewSchema()
    permission_classes = (EventCategoryPermissions,)
    filter_backends = [OrderingFilter, filters.DjangoFilterBackend]
    filterset_class = EventTypeFilter
    serializer_class = EventTypeSerializer
    lookup_field = "value"
    lookup_url_kwarg = "eventtype_value"
    ordering = ("ordernum",)

    def get_queryset(self) -> models.QuerySet:
        user = self.request.user
        allowed_categories = self._get_allowed_categories_by_user(user)

        if not allowed_categories:
            return EventType.objects.none()

        queryset = (
            EventType.objects.filter(
                version=EventType.VersionChoices.VERSION_2,
                category__is_active=True,  # Always filter out inactive categories.
                category__value__in=allowed_categories,
            )
            .select_related("category")
            .annotate(
                in_use=models.Exists(Event.objects.filter(event_type=models.OuterRef("id"))),
            )
        )
        return queryset

    def get_list_etag(self, request: Request, queryset: models.QuerySet) -> str:
        queryset = queryset.values("updated_at", "category__updated_at")
        return super().get_list_etag(request, queryset)

    def perform_destroy(self, instance: models.Model):
        # Looks safe to implement this one.
        instance.set_to_inactive()

    def create(self, request, *args, **kwargs):
        res = super().create(request, *args, **kwargs)
        new_object_url = reverse("v2-eventtype-retrieve-schema", kwargs={"eventtype_value": res.data["value"]})

        return Response(
            status=status.HTTP_201_CREATED,
            data={"resource_url": new_object_url},
            headers={"Location": new_object_url},
        )

    def update(self, request: Request, *args, **kwargs):
        # Temporary implementation to avoid updating event types.
        return Response({"detail": "Method not supported"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_schema_renderer(self, request: Request) -> SchemaRenderer:
        # This is where the rendering and retrieval sides are being connected.
        registry = build_dynamic_schemas_registry(request)
        return SchemaRenderer(registry)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        include_schema = parse_bool(self.request.query_params.get("include_schema", "false"))
        context["include_schema"] = include_schema
        return context

    @action(
        methods=["get"],
        detail=False,
        url_path="schemas",
        renderer_classes=(DirectJSONRenderer, DirectBrowsableAPIRenderer),
    )
    def list_schemas(self, request: Request) -> Response:
        """
        Returns a JSON structure with a list of schemas, using a list-based approach.
        Each item indicates 'success' or 'failure' and contains an 'error.code' when failing.
        """
        queryset = self.filter_queryset(self.get_queryset())
        schema_renderer = None
        if parse_bool(request.query_params.get("pre_render", False)):
            schema_renderer = self.get_schema_renderer(request)

        results = []
        for et in queryset:
            schema_item = {"value": et.value}

            success, data = parse_and_render_schema(et, schema_renderer)
            if success:
                schema_item["status"] = RenderStatus.SUCCESS
                schema_item["schema"] = data
            else:
                schema_item["status"] = RenderStatus.FAILURE
                schema_item["error"] = data

            results.append(schema_item)

        # Format designed for easy implementation of pagination
        response_data = {
            "count": len(results),
            "results": results,
        }
        if all(item["status"] == RenderStatus.SUCCESS for item in results):
            response_status = status.HTTP_200_OK
        else:
            response_status = status.HTTP_207_MULTI_STATUS

        return Response(response_data, status=response_status)

    # pylint: disable=unused-argument
    @action(
        methods=["get"],
        detail=True,
        url_path="schema",
        renderer_classes=(DirectJSONRenderer, DirectBrowsableAPIRenderer),
    )
    def retrieve_schema(self, request: Request, **kwargs) -> Response:
        """
        Returns the rendered schema for the specified event type.
        """
        event_type = self.get_object()
        schema_renderer = None
        if parse_bool(request.query_params.get("pre_render", False)):
            schema_renderer = self.get_schema_renderer(request)

        success, data = parse_and_render_schema(event_type, schema_renderer)
        if success:
            return Response(data, status=status.HTTP_200_OK)
        return Response({"error": data}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
