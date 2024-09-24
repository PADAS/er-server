import logging

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, ListCreateAPIView, get_object_or_404
from rest_framework.response import Response

from das_server.views import CustomSchema
from observations.filters import ObservationsFilter
from observations.models import Observation, Subject
from observations.permissions import StandardObjectPermissions
from observations.serializers import FlattenObservationSerializer, ObservationSerializer
from observations.utils import VIEW_OBSERVATION_PERMS, VIEW_SUBJECT_PERMS, dateparse
from utils.drf import (
    ForbiddenAPIException,
    StandardResultsSetCursorPagination,
    StandardResultsSetPagination,
    return_409_response,
)
from utils.json import parse_bool

logger = logging.getLogger(__name__)


class FlattenObservationsView(ListAPIView):
    serializer_class = FlattenObservationSerializer

    def get_queryset(self):
        subject_id = self.request.query_params.get("subject_id")
        created_after = dateparse(self.request.query_params.get("created_after"))

        subject = get_object_or_404(Subject, pk=subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        queryset = Observation.objects.get_subject_observations(subject)
        queryset = queryset.by_created_after(created_after)

        return queryset.order_by("-recorded_at")


class ObservationsViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
            query_params = [
                {"name": "subject_id", "in": "query", "description": "filter to a single subject"},
                {"name": "source_id", "in": "query", "description": "filter to a single source"},
                {
                    "name": "subjectsource_id",
                    "in": "query",
                    "description": "filter to a subjectsource_id, rather than source_id + time range",
                },
                {
                    "name": "since",
                    "in": "query",
                    "description": "get observations after this ISO8061 date, include timezone",
                },
                {
                    "name": "until",
                    "in": "query",
                    "description": "get observations up to this ISO8061 date, include timezone",
                },
                {
                    "name": "filter",
                    "in": "query",
                    "description": "filter using exclusion_flags for an observation. one of [null, 0, 1, 2  or 3].",
                },
                {
                    "name": "include_details",
                    "in": "query",
                    "description": " one of [true,false], default is false. This brings back the observation additional field",
                },
                {
                    "name": "created_after",
                    "in": "query",
                    "description": "get observations created (saved in EarthRanger) after this ISO8061 date, include timezone",
                },
                {
                    "name": "use_cursor",
                    "in": "query",
                    "description": "default is to use a page based paginator, which does not scale to a large dataset. Set use_cursor=true to employ a paginator that can handle millions of rows by using next/prev urls.",
                },
            ]
            operation["parameters"].extend(query_params)
        return operation


class ObservationsCursorPagination(StandardResultsSetCursorPagination):
    cursor_query_Param = "id"
    ordering = "recorded_at"


class ObservationsView(ListCreateAPIView):
    serializer_class = ObservationSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (ObservationsFilter, OrderingFilter)
    schema = ObservationsViewSchema()
    ordering_fields = ("recorded_at",)
    ordering = "recorded_at"

    @property
    def paginator(self):
        """The paginator instance associated with the view, or `None`.
           API caller can request to use a cursor based paginator.

        Returns:
            paginator: the requested paginator
        """
        if not hasattr(self, "_paginator"):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = (
                    ObservationsCursorPagination()
                    if parse_bool(self.request.query_params.get("use_cursor"))
                    else self.pagination_class()
                )
        return self._paginator

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_OBSERVATION_PERMS):
            raise ForbiddenAPIException

        query_params = self.request.query_params
        created_after = query_params.get("created_after")
        created_after = dateparse(created_after) if created_after else None

        mou_date = self.request.user.additional.get("expiry", None)
        mou_expiry_date = dateparse(mou_date) if mou_date else None

        queryset = Observation.objects.all()

        if mou_expiry_date:
            queryset = queryset.filter(recorded_at__lte=mou_expiry_date)

        if created_after:
            queryset = queryset.by_created_after(created_after)

        queryset = queryset.prefetch_related("source__provider")
        queryset = queryset.annotate_transforms()
        return queryset

    def create(self, request, *args, **kwargs):
        """
         On condition of post body being a list, let it bulk insert.
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        serializer = ObservationSerializer(many=isinstance(request.data, list), data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                self.perform_create(serializer)
        except IntegrityError:
            if not isinstance(request.data, list):
                return return_409_response()

            at_least_one_added = False
            for observation in request.data:
                serializer = ObservationSerializer(data=observation)
                if not serializer.is_valid():
                    return Response(
                        serializer.errors,
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    with transaction.atomic():
                        self.perform_create(serializer)
                    at_least_one_added = True
                except IntegrityError:
                    pass

            if not at_least_one_added:
                return return_409_response()

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_serializer_context(self):
        context = super(ObservationsView, self).get_serializer_context()

        # Check request before accessing params since self.request is None when
        # generating docs schema
        context["include_details"] = (
            parse_bool(self.request.query_params.get("include_details", False)) if self.request else False
        )

        return context
