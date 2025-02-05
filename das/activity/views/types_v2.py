from django_filters import rest_framework as filters

from django.db import models
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from activity.filters import EventTypeFilter
from activity.models import Event, EventCategory, EventType
from activity.permissions import EventCategoryPermissions
from activity.serializers.events_v2 import EventCategorySerializer, EventTypeSerializer
from activity.views.events.utils import AllowedCategoriesMixin
from utils.views import EtagListRetrieveModelMixin


class EventCategoryViewSet(ModelViewSet):

    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventCategorySerializer
    queryset = EventCategory.objects.all()
    lookup_field = "value"
    ordering = ("ordernum",)

    def perform_destroy(self, instance: models.Model):
        instance.set_to_inactive()

    def create(self, request, *args, **kwargs):
        raise NotImplementedError("Method not supported")

    def update(self, request: Request, *args, **kwargs):
        super().update(request)
        raise NotImplementedError("Method not supported")


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

    def get_queryset(self):
        queryset = (
            EventType.objects.select_related("category")
            .filter(category__is_active=True)  # Always filter out inactive categories.
            .annotate(in_use=models.Exists(Event.objects.filter(event_type=models.OuterRef("id"))))
        )
        user = self.request.user
        allowed_categories = self._get_allowed_categories_by_user(user)
        if allowed_categories:
            queryset = queryset.filter(category__value__in=allowed_categories)
        return queryset

    def get_list_etag(self, request, queryset):
        queryset = queryset.values("updated_at", "category__updated_at")
        return super().get_list_etag(request, queryset)

    def perform_destroy(self, instance: models.Model):
        # Looks safe to implement this one.
        instance.set_to_inactive()

    def create(self, request, *args, **kwargs):
        # Temporal implementation to avoid creating new event types.
        raise NotImplementedError("Method not supported")

    def update(self, request: Request, *args, **kwargs):
        # Temporal implementation to avoid updating event types.
        raise NotImplementedError("Method not supported")

    @action(methods=["get"], detail=False, url_path="schemas")
    def list_schemas(self, request: Request) -> Response:
        """
        Returns a dictionary of schemas for the EventTypes API.
        Keyed by value field in event_type.
        """
        # Note:
        # Temporal implementation to get all the schemas just to show the idea of having a
        # separate endpoint for schemas.
        # TODO: Implement rendering of the schema for each event type.
        queryset = self.filter_queryset(self.get_queryset())

        schemas = {}
        for event_type in queryset:
            schemas[event_type.value] = event_type.schema
        return Response(schemas)

    @action(methods=["get"], detail=True, url_path="schema.json")
    def retrieve_schema(self, request: Request, value: str) -> Response:
        """
        Returns the rendered schema for the specified event type.
        """
        instance = self.get_object()
        return Response(instance.schema)
