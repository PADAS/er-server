from rest_framework_condition import etag

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
from activity.views.response_headers import EVENT_CATEGORY_FIELDS
from activity.views.schemas import EventCategoriesViewSchema, EventCategoryViewSchema
from utils.categories import EventCategoryRelatedPermissionSetActions
from utils.drf import return_409_response
from utils.etags import get_hash_from_queryset
from utils.json import parse_bool
from utils.rank import RankedTool, RankSerializer


def get_event_category_queryset(user, query_params):
    queryset = EventCategory.objects.all_sort()

    if not parse_bool(query_params.get("include_inactive")):
        queryset = queryset.filter(is_active=True)

    actions = ("create", "update", "read", "delete")
    queryset = queryset.exclude(
        id__in=[q.id for q in queryset if not any(user.has_perm(f"activity.{q.value}_{action}") for action in actions)]
    )

    return queryset


def etag_event_category_hash(request):
    queryset = get_event_category_queryset(user=request.user, query_params=request.GET)
    queryset = queryset.values(*EVENT_CATEGORY_FIELDS)
    return get_hash_from_queryset(queryset=queryset, request=request)


class EventCategoriesView(ListCreateAPIView):
    permission_classes = (EventCategoryObjectPermissions,)
    serializer_class = EventCategorySerializer
    schema = EventCategoriesViewSchema()

    @etag(etag_event_category_hash)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_serializer_context(self):
        query_params = self.request.query_params if self.request and hasattr(self.request, "query_params") else {}

        context = super().get_serializer_context()
        context["include_event_types"] = parse_bool(query_params.get("include_event_types", False))
        context["include_permission_set_changed"] = parse_bool(
            query_params.get("include_permission_set_changed", False)
        )

        return context

    def get_queryset(self):
        return get_event_category_queryset(user=self.request.user, query_params=self.request.query_params)

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))


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

    def patch(self, request, *args, **kwargs):
        new_value = request.data.get("value", None)
        new_display = request.data.get("display", None)
        instance = self.get_object()

        update_permission_sets = parse_bool(request.query_params.get("update_permission_sets", False))

        if instance.value != new_value:
            related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=instance)

            permissions_changed = related_permissions_actions.is_event_category_permission_set_changed_by_user()

            if not permissions_changed or (permissions_changed and update_permission_sets):
                related_permissions_actions.update_permission_sets_and_permissions_related(
                    new_value=new_value, display=new_display
                )

        return super().patch(request, *args, **kwargs)


class EventCategoryRankView(GenericAPIView):
    lookup_field = "id"
    lookup_url_kwarg = "eventcategory_id"
    permission_classes = (EventCategoryObjectPermissions,)
    serializer_class = RankSerializer

    def get_queryset(self):
        return EventCategory.objects.all().order_by("ordernum")

    def post(self, request, *args, **kwargs) -> Response:
        instance = self.get_object()
        if not request.data:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        before_key = request.data.get("before_key")
        ranked_tool = RankedTool(instance=instance, before_key=before_key)
        ranked_tool.rank()

        return Response(status=status.HTTP_204_NO_CONTENT)
