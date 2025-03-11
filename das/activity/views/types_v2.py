import json
import logging
from typing import Optional

from django_filters import rest_framework as filters

from django.db import models
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from activity.filters import EventTypeFilter, EventTypeSchemaFilter
from activity.models import Event, EventType
from activity.permissions import EventCategoryPermissions
from activity.schemas.schema_rendering import dereference_schema
from activity.schemas.schema_retrieving import build_dynamic_schemas_registry
from activity.serializers.events_v2 import EventTypeSerializer
from activity.views.events.utils import AllowedCategoriesMixin
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer
from utils.views import EtagListRetrieveModelMixin

logger = logging.getLogger(__name__)


class EventTypesViewSet(EtagListRetrieveModelMixin, AllowedCategoriesMixin, ModelViewSet):
    """
    V2 Event Types API. Supports dynamic `schema` generation, which means rendering of references ($ref) in the schemas.
    Features:
        - eTag generation for list and detail views.
        - FUTURE: Cache control for schema rendering.
        - FUTURE: Validation of schemas.
        - Supports filtering with the same query parameters as the other existing EventTypesView.

    Notes:
        - My approach will be:
            - to adopt as much as possible from the existing codebase but implementing what is possible
            with django-filter (DjangoFilterBackend)
            - identify and implement the same exising tests but for the new implementation.
            - implement the missing features in the new implementation.
    """

    permission_classes = (EventCategoryPermissions,)
    filter_backends = [OrderingFilter, filters.DjangoFilterBackend]
    filterset_class = EventTypeFilter
    serializer_class = EventTypeSerializer
    lookup_field = "value"
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
        # Temporary implementation to avoid creating new event types.
        return Response({"detail": "Method not supported"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def update(self, request: Request, *args, **kwargs):
        # Temporary implementation to avoid updating event types.
        return Response({"detail": "Method not supported"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(
        methods=["get"],
        detail=False,
        url_path="schemas",
        filterset_class=EventTypeSchemaFilter,
        renderer_classes=(DirectJSONRenderer, DirectBrowsableAPIRenderer),
    )
    def list_schemas(self, request: Request) -> Response:
        """
        Returns a dictionary of schemas for the EventTypes API.
        Keyed by value field in event_type.
        """
        queryset = self.filter_queryset(self.get_queryset())
        pre_render = request.query_params.get("pre_render", False)

        try:
            schemas = {et.value: json.loads(et.schema) for et in queryset if et.schema}
        except json.JSONDecodeError as e:
            logger.warning(f"Error decoding schema: {e}")
            return Response({"detail": "Error decoding schema"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if pre_render:
            registry = build_dynamic_schemas_registry(request)

            for value, schema in schemas.items():
                if "json" not in schema:
                    logger.warning(f"Schema not found for event type: {value}")
                    continue
                json_schema = schema["json"]
                schemas[value]["json"] = dereference_schema(json_schema, registry)

        return Response(schemas)

    @action(
        methods=["get"],
        detail=True,
        url_path="schema",
        filterset_class=EventTypeSchemaFilter,
        renderer_classes=(DirectJSONRenderer, DirectBrowsableAPIRenderer),
    )
    def retrieve_schema(self, request: Request, value: str, format: Optional[str] = None) -> Response:
        """
        Returns the rendered schema for the specified event type.
        """
        event_type = self.get_object()
        pre_render = request.query_params.get("pre_render", False)

        try:
            schema = json.loads(event_type.schema)
        except json.JSONDecodeError as e:
            logger.warning(f"Error decoding schema: {e}, for event type: {event_type.value}")
            return Response({"detail": "Error decoding schema"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if pre_render:
            registry = build_dynamic_schemas_registry(request.build_absolute_uri("/"))

            if "json" not in schema:
                raise ValueError("Schema not found in event type")
            json_schema = schema["json"]
            schema["json"] = dereference_schema(json_schema, registry)

        return Response(schema)
