from rest_framework_condition import condition

from django.db import IntegrityError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from activity.models import EventType
from activity.permissions import EventCategoryPermissions
from activity.serializers import EventTypeSerializer
from activity.util import return_409_response
from activity.views.response_headers import (
    build_event_type_etag_header,
    build_event_type_last_modified_header,
    build_event_types_etag_header,
    build_event_types_last_modified_header,
)
from activity.views.schemas import EventTypeViewSchema
from utils.json import parse_bool

from .utils import EventTypeQuerysetMixin


class EventTypeView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    lookup_url_kwarg = "eventtype_id"
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeSerializer

    @condition(etag_func=build_event_type_etag_header, last_modified_func=build_event_type_last_modified_header)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return EventType.objects.all()

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


class EventTypesView(EventTypeQuerysetMixin, ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeSerializer
    schema = EventTypeViewSchema()

    @condition(etag_func=build_event_types_etag_header, last_modified_func=build_event_types_last_modified_header)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_serializer_context(self):
        qparams = self.request.query_params
        context = super().get_serializer_context()

        context["include_schema"] = parse_bool(qparams.get("include_schema", False))
        return context
