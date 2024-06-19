from django.db import IntegrityError
from rest_framework import status
from rest_framework.generics import (
    GenericAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.response import Response

from activity.models import EventCategory
from activity.permissions import EventCategoryObjectPermissions
from activity.serializers import EventCategorySerializer
from activity.util import return_409_response
from activity.views.schemas import EventCategoriesViewSchema, EventCategoryViewSchema
from utils.categories import EventCategoryRelatedPermissionSetActions
from utils.json import parse_bool
from utils.rank import RankSerializer, RankView


class EventCategoriesView(ListCreateAPIView):
    permission_classes = (EventCategoryObjectPermissions,)
    serializer_class = EventCategorySerializer
    schema = EventCategoriesViewSchema()

    def get_serializer_context(self):
        query_params = self.request.query_params if self.request and hasattr(self.request, "query_params") else {}

        context = super().get_serializer_context()
        context["include_event_types"] = parse_bool(query_params.get("include_event_types", False))
        context["include_permission_set_changed"] = parse_bool(
            query_params.get("include_permission_set_changed", False)
        )

        return context

    def get_queryset(self):
        queryset = EventCategory.objects.all_sort()

        if not parse_bool(self.request.query_params.get("include_inactive")):
            queryset = queryset.filter(is_active=True)
        for q in queryset:
            actions = ("create", "update", "read", "delete")
            permission_name = [f"activity.{q.value}_{action}" for action in actions]
            if not any([self.request.user.has_perm(perm) for perm in permission_name]):
                queryset = queryset.exclude(id=q.id)
        return queryset

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except IntegrityError:
            return return_409_response()


class EventCategoryView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    lookup_url_kwarg = "eventcategory_id"
    permission_classes = (EventCategoryObjectPermissions,)
    serializer_class = EventCategorySerializer
    schema = EventCategoryViewSchema()

    def get_queryset(self):
        return EventCategory.objects.all()

    def get_serializer_context(self):
        query_params = self.request.query_params if self.request and hasattr(self.request, "query_params") else {}

        context = super().get_serializer_context()
        context["include_event_types"] = parse_bool(query_params.get("include_event_types", False))
        context["include_permission_set_changed"] = parse_bool(
            query_params.get("include_permission_set_changed", False)
        )
        return context

    def destroy(self, request, *args, **kwargs):
        keep_permission_sets = parse_bool(request.query_params.get("keep_permission_sets", False))
        instance = self.get_object()
        if instance.eventtype_set.exists():
            return Response(
                {"detail": "Cannot delete event category with associated event types"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not keep_permission_sets:
            related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=instance)
            related_permissions_actions.delete_permissions_sets_and_permissions_related_to_event_category()

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventCategoryRankView(GenericAPIView, RankView):
    lookup_field = "id"
    lookup_url_kwarg = "eventcategory_id"
    permission_classes = (EventCategoryObjectPermissions,)
    serializer_class = RankSerializer

    def get_queryset(self):
        return EventCategory.objects.all().order_by("ordernum")
