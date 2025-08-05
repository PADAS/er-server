import logging

from django_filters import rest_framework as filters

from django.db import models
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from activity.filters import EventTypeFilterSet
from activity.models import Event, EventType
from activity.permissions import EventCategoryPermissions
from activity.schemas.schema_rendering import SchemaRenderer
from activity.schemas.schema_retrieving import build_dynamic_schemas_registry
from activity.serializers.events_v2 import EventTypeV2Serializer
from activity.schemas.eventtype_service import EventTypeSchemaService
from activity.serializers.events_v2 import EventTypeSerializer
from activity.views.events.utils import AllowedCategoriesMixin
from activity.views.schemas import EventTypeViewSchema
from core.utils import is_uuid
from schemas.view_mixins import DynamicSchemaDataMixin
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer, parse_bool
from utils.views import EtagListRetrieveModelMixin

logger = logging.getLogger(__name__)


class EventTypesViewSet(EtagListRetrieveModelMixin, AllowedCategoriesMixin, DynamicSchemaDataMixin, ModelViewSet):

    schema = EventTypeViewSchema()
    permission_classes = (EventCategoryPermissions,)
    filter_backends = [OrderingFilter, filters.DjangoFilterBackend]
    filterset_class = EventTypeFilterSet
    serializer_class = EventTypeV2Serializer
    lookup_field = "value"
    lookup_url_kwarg = "eventtype_value"
    ordering = ("ordernum",)

    def get_base_queryset(self) -> models.QuerySet:
        user = self.request.user
        allowed_categories = self._get_allowed_categories_by_user(user)

        if not allowed_categories:
            return EventType.objects.none()

        queryset = (
            EventType.objects.filter(
                category__is_active=True,  # Always filter out inactive categories.
                category__value__in=allowed_categories,
            )
            .select_related("category")
            .annotate(
                in_use=models.Exists(Event.objects.filter(event_type=models.OuterRef("id"))),
            )
        )
        return queryset

    def get_queryset(self) -> models.QuerySet:
        """Normal queryset for viewset"""
        return self.get_base_queryset().filter(version=EventType.VersionChoices.VERSION_2)

    def get_schema_queryset(self) -> models.QuerySet:
        """Queryset used for our dynamic schemas"""
        return self.get_base_queryset()

    def get_list_etag(self, request: Request, queryset: models.QuerySet) -> str:
        queryset = queryset.values("updated_at", "category__updated_at")
        return super().get_list_etag(request, queryset)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event_type = serializer.save()
        reverse_url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": event_type.value})

        return Response(
            status=status.HTTP_201_CREATED,
            data={"resource_url": reverse_url},
            headers={"Location": reverse_url},
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(status=status.HTTP_200_OK)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        if hasattr(instance, "in_use"):
            has_events = instance.in_use
        else:
            has_events = instance.event_set.exists()
        has_alerts = instance.alert_rules.exists()

        if has_events or has_alerts:
            reasons = []
            if has_events:
                reasons.append("it is associated with existing Events")
            if has_alerts:
                reasons.append("it is associated with existing Alert Rules")
            error_message = f"Cannot delete Event Type '{instance.display}' because {', and '.join(reasons)}."
            return Response({"detail": error_message}, status=status.HTTP_409_CONFLICT)

        # If no dependencies, proceed with standard deletion which returns 204
        return super().destroy(request, *args, **kwargs)

    def get_schema_renderer(self, request: Request) -> SchemaRenderer:
        # This is where the rendering and retrieval sides are being connected.
        registry = build_dynamic_schemas_registry(request)
        return SchemaRenderer(registry)

    def get_serializer_context(self) -> dict:
        """Add include_schema to serializer context"""
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
        schema_service = EventTypeSchemaService()
        pre_render = parse_bool(request.query_params.get("pre_render", False))

        if pre_render:
            schema_results = [schema_service.get_rendered_schema(event_type, request) for event_type in queryset]
        else:
            schema_results = [schema_service.get_raw_schema(event_type) for event_type in queryset]

        # Format designed for easy implementation of pagination later
        response_data = {
            "count": len(schema_results),
            "results": [sr.to_api_dict() for sr in schema_results],
        }
        if all(sr.status == "success" for sr in schema_results):
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
        schema_service = EventTypeSchemaService()
        pre_render = parse_bool(request.query_params.get("pre_render", False))

        if pre_render:
            schema_result = schema_service.get_rendered_schema(event_type, request)
        else:
            schema_result = schema_service.get_raw_schema(event_type)

        # TODO: Propose a change to the shape of the response, to be more in line with the list_schemas response
        if schema_result.status != "failure":
            return Response(schema_result.schema, status=status.HTTP_200_OK)
        return Response(
            {"errors": [err.to_dict() for err in schema_result.errors]}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
        )
