from django.db import IntegrityError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from activity.models import EventCategory, EventType
from activity.permissions import EventCategoryPermissions
from activity.serializers import EventTypeSerializer
from activity.util import return_409_response
from activity.views.schemas import EventTypeViewSchema
from utils.json import parse_bool


class EventTypeView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    lookup_url_kwarg = "eventtype_id"
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeSerializer
    queryset = EventType.objects.all()

    def perform_destroy(self, instance):
        instance.set_to_inactive()

    def put(self, request, *args, **kwargs):
        try:
            return self.update(request, *args, **kwargs)
        except IntegrityError:
            return return_409_response()

    def patch(self, request, *args, **kwargs):
        try:
            return self.partial_update(request, *args, **kwargs)
        except IntegrityError:
            return return_409_response()

    def get_serializer_context(self):
        qparams = self.request.query_params
        context = super().get_serializer_context()

        context["include_schema"] = parse_bool(qparams.get("include_schema", False))
        return context


class EventTypesView(ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeSerializer
    schema = EventTypeViewSchema()

    def get_queryset(self):
        query_params = self.request.query_params
        queryset = EventType.objects.all_sort()

        if parse_bool(query_params.get("include_inactive")):
            queryset = queryset.filter(category__is_active=True)
        else:
            queryset = queryset.filter(category__is_active=True, is_active=True)

        category = query_params.getlist("category", None)
        if category:
            queryset = queryset.by_category(category)
        else:
            allowed_categories = []
            event_categories = EventCategory.objects.values_list("value").distinct()
            event_categories = [ec[0] for ec in event_categories]
            actions = ("create", "update", "read", "delete")
            geo_actions = (
                "view",
                "add",
                "change",
                "delete",
            )

            for event_category in event_categories:
                permission_name = [f"activity.{event_category}_{action}" for action in actions]
                permission_name += [f"activity.{action}_{event_category}_geographic_distance" for action in geo_actions]
                if any([self.request.user.has_perm(perm) for perm in permission_name]):
                    allowed_categories.append(event_category)

            if allowed_categories:
                queryset = queryset.by_category(allowed_categories)
            elif query_params.get("is_collection", None) is None:
                return queryset.none()

        is_collection = query_params.get("is_collection", None)
        if is_collection is not None:
            queryset = queryset.by_is_collection(parse_bool(is_collection))
        return queryset

    def get_serializer_context(self):
        qparams = self.request.query_params
        context = super().get_serializer_context()

        context["include_schema"] = parse_bool(qparams.get("include_schema", False))
        return context
