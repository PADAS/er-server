from uuid import UUID

from rest_framework_condition import etag

from django.db import IntegrityError
from rest_framework import status
from rest_framework.generics import (
    GenericAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.response import Response

from activity.models import EventCategory, EventType
from activity.permissions import EventCategoryPermissions
from activity.serializers import EventTypeRankSerializer, EventTypeSerializer
from activity.views.response_headers import (
    build_event_type_etag_header,
    build_event_types_etag_header,
)
from activity.views.schemas import EventTypeViewSchema
from utils.drf import return_409_response
from utils.json import parse_bool
from utils.rank import RankedTool

from .utils import EventTypeQuerysetMixin


class EventTypeView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    lookup_url_kwarg = "eventtype_id"
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeSerializer

    @etag(etag_func=build_event_type_etag_header)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return EventType.objects.all()

    def perform_destroy(self, instance):
        instance.set_to_inactive()

    def put(self, request, *args, **kwargs):
        try:
            return self.update(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

    def patch(self, request, *args, **kwargs):
        try:
            return self.partial_update(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

    def get_serializer_context(self):
        qparams = self.request.query_params
        context = super().get_serializer_context()

        context["include_schema"] = parse_bool(qparams.get("include_schema", False))
        return context


class EventTypesView(EventTypeQuerysetMixin, ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeSerializer
    schema = EventTypeViewSchema()

    @etag(etag_func=build_event_types_etag_header)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_serializer_context(self):
        qparams = self.request.query_params
        context = super().get_serializer_context()

        context["include_schema"] = parse_bool(qparams.get("include_schema", False))
        return context


class EventTypeRankView(GenericAPIView):
    lookup_field = "id"
    lookup_url_kwarg = "eventtype_id"
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeRankSerializer

    def get_queryset(self):
        return EventType.objects.all().order_by("ordernum")

    def post(self, request, *args, **kwargs) -> Response:
        instance = self.get_object()
        if not request.data:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        before_key = request.data.get("before_key")
        category_id = request.data.get("category_id")
        if category_id:
            self._move_to_new_category(category_id)
        qs = self.get_queryset()
        qs = qs.filter(category=instance.category)
        ranked_tool = RankedTool(instance=instance, before_key=before_key)
        ranked_tool.rank()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def _move_to_new_category(self, new_category_id: UUID) -> None:
        instance = self.get_object()
        if instance.category_id != new_category_id:
            try:
                category = EventCategory.objects.get(id=new_category_id)
            except EventCategory.DoesNotExist:
                return Response(status=status.HTTP_400_BAD_REQUEST)
            instance.category = category
            instance.save(update_fields=["category"])
