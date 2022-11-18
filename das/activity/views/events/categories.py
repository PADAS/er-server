from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from activity.models import EventCategory
from activity.permissions import EventCategoryObjectPermissions
from activity.serializers import EventCategorySerializer
from utils.json import parse_bool


class EventCategoriesView(ListCreateAPIView):
    permission_classes = (EventCategoryObjectPermissions,)
    serializer_class = EventCategorySerializer

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


class EventCategoryView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    lookup_url_kwarg = "eventcategory_id"
    permission_classes = (EventCategoryObjectPermissions,)
    serializer_class = EventCategorySerializer
    queryset = EventCategory.objects.all()
