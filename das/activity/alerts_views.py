import logging
from rest_framework import generics, status, response, permissions

from activity.models import AlertRule, NotificationMethod, EventType

from activity.serializers import EventTypeSerializer, AlertRuleSerializer, NotificationMethodSerializer

from activity.permissions import EventCategoryPermissions, IsOwner
from activity.alerting.businessrules import render_aggregate_event_variables

from utils.drf import StandardResultsSetPagination
from utils.json import parse_bool
from utils.schema_utils import get_schema_renderer_method
logger = logging.getLogger(__name__)

# Views for Advanced Alert Functionality.


class EventAlertConditionsListView(generics.ListAPIView):

    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventTypeSerializer

    queryset = EventType.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()

        event_types = self.request.query_params.get('event_type', '')
        if event_types:
            qs = qs.by_event_type(event_types)

        # Exclude conditions with eventtypes of invalid schema
        errored_types = []
        for eventype in qs:
            try:
                get_schema_renderer_method()(eventype.schema)
            except Exception:
                logger.exception(f"{eventype} event type skipped, invalid schema")
                errored_types.append(eventype.display)

        qs = qs.exclude(display__in=errored_types)

        return qs

    def get(self, *args, **kwargs):
        only_common_factors = parse_bool(
            self.request.query_params.get('only_common_factors', False))

        rules = render_aggregate_event_variables(
            self.get_queryset(), only_common_factors=only_common_factors, user=self.request.user)

        return response.Response(rules, status=status.HTTP_200_OK)


class AlertRuleListView(generics.ListCreateAPIView):

    permission_classes = [permissions.DjangoModelPermissions & IsOwner]

    serializer_class = AlertRuleSerializer

    queryset = AlertRule.objects.none()  # Required for DjangoModelPermission

    def get_queryset(self):
        return AlertRule.objects.filter(owner=self.request.user).order_by('ordernum', 'title')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class AlertRuleView(generics.RetrieveUpdateDestroyAPIView):

    permission_classes = [permissions.DjangoModelPermissions & IsOwner]

    serializer_class = AlertRuleSerializer
    pagination_class = StandardResultsSetPagination

    queryset = AlertRule.objects.all()

    lookup_field = 'id'

    def get_queryset(self):
        return AlertRule.objects.filter(owner=self.request.user)

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj:
            self.check_object_permissions(self.request, obj)
        return super().get(request, *args, **kwargs)


class NotificationMethodListView(generics.ListCreateAPIView):

    permission_classes = (IsOwner,)
    serializer_class = NotificationMethodSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return NotificationMethod.objects.filter(owner=self.request.user).order_by('method')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class NotificationMethodView(generics.RetrieveUpdateDestroyAPIView):

    permission_class = (IsOwner,)
    serializer_class = NotificationMethodSerializer

    queryset = NotificationMethod.objects.all()

    lookup_field = 'id'

    def get_queryset(self):
        return NotificationMethod.objects.filter(owner=self.request.user)

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj:
            self.check_object_permissions(self.request, obj)
        return super().get(request, *args, **kwargs)
