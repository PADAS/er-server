import logging

from django_filters import rest_framework as filters
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)

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
from activity.schemas.eventtype_service import EventTypeSchemaService
from activity.schemas.migration.service import MigrationService
from activity.serializers.event_types_v2 import (
    EventTypeRevisionSerializer,
    EventTypeV2Serializer,
    MigrationRequestSerializer,
    MigrationResultSerializer,
)
from activity.views.events.utils import AllowedCategoriesMixin
from core.utils import is_uuid
from schemas.view_mixins import DynamicSchemaDataMixin
from utils.drf import StandardResultsSetPagination
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer, parse_bool
from utils.views import EtagListRetrieveModelMixin

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="include_schema",
                description="Include eventtype schema in the payload",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
        ]
    )
)
class EventTypesViewSet(EtagListRetrieveModelMixin, AllowedCategoriesMixin, DynamicSchemaDataMixin, ModelViewSet):
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

    def get_object(self) -> EventType:
        # Temporary implementation to allow to retrieve by uuid.
        if is_uuid(self.kwargs.get("eventtype_value")):
            self.lookup_field = "id"
            obj = super().get_object()
            self.lookup_field = "value"
            return obj
        return super().get_object()

    def get_serializer_context(self) -> dict:
        """
        Sets `include_schema` as context for serializer.
        """
        context = super().get_serializer_context()
        context.update({"include_schema": parse_bool(self.request.query_params.get("include_schema", False))})
        return context

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

        if schema_result.status != "failure":
            return Response(schema_result.schema, status=status.HTTP_200_OK)
        return Response(
            {"errors": [err.to_dict() for err in schema_result.errors]}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    @action(
        methods=["get"],
        detail=True,
        url_path="updates",
        serializer_class=EventTypeRevisionSerializer,
        pagination_class=StandardResultsSetPagination,
    )
    def retrieve_updates(self, request: Request, **kwargs) -> Response:
        """
        Returns the updates for the specified event type.
        """
        event_type = self.get_object()
        revisions = event_type.revision.all().order_by("-sequence")
        page = self.paginate_queryset(revisions)
        serializer = EventTypeRevisionSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=MigrationRequestSerializer,
        responses={200: MigrationResultSerializer(many=True)},
    )
    @action(
        methods=["post"],
        detail=False,
        url_path="migrate",
        serializer_class=MigrationRequestSerializer,
    )
    def migrate(self, request: Request) -> Response:
        """
        Migrate V1 EventType schemas to V2.

        Request body:
        - dry_run: if true, preview migration without persisting (default: true)
        - event_types: array of event type values to migrate

        Response:
        - data: array of migration results, one per event type
        """
        serializer = MigrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dry_run = serializer.validated_data["dry_run"]
        event_types = serializer.validated_data["event_types"]

        migration_service = MigrationService(request=request, dry_run=dry_run)
        results = migration_service.migrate(event_types)

        response_data = {"data": [MigrationResultSerializer(r.to_dict()).data for r in results]}

        return Response(response_data, status=status.HTTP_200_OK)
