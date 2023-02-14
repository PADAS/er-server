import logging

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, ListCreateAPIView, get_object_or_404
from rest_framework.response import Response

from das_server.views import CustomSchema
from observations.models import Observation, Subject
from observations.permissions import StandardObjectPermissions
from observations.serializers import FlattenObservationSerializer, ObservationSerializer
from observations.utils import VIEW_OBSERVATION_PERMS, VIEW_SUBJECT_PERMS, dateparse
from utils.drf import StandardResultsSetCursorPagination, StandardResultsSetPagination
from utils.json import parse_bool

from .exceptions import UnauthorizedView
from .helpers import check_valid_date_string

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
    schema = ObservationsViewSchema()

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

        output = []
        for item in page:
            output.append(self.serializer_class.dict_to_representation(item, request.query_params))

        return self.get_paginated_response(output)

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_OBSERVATION_PERMS):
            raise UnauthorizedView

        query_params = self.request.query_params
        since = query_params.get("since")
        until = query_params.get("until")
        recorded_since_is_valid, recorded_since = check_valid_date_string(since, "recorded_since")
        recorded_until_is_valid, recorded_until = check_valid_date_string(until, "recorded_until")
        subject_id = query_params.get("subject_id")
        source_id = query_params.get("source_id")
        subjectsource_id = query_params.get("subjectsource_id")
        created_after = query_params.get("created_after")
        sort_by = query_params.get("sort_by", "recorded_at")

        filter_flag = 0
        filter_qparam = query_params.get("filter", 0)
        try:
            filter_flag = int(filter_qparam)
        except (ValueError, TypeError):
            filter_flag = None if filter_qparam == "null" else filter_flag

        if len([id for id in (subject_id, source_id, subjectsource_id) if id]) > 1:
            raise ValueError("Can only specify one of: subject_id and source_id and subjectsource_id")
        elif subject_id:
            subject = get_object_or_404(Subject, pk=subject_id)
            if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
                raise PermissionDenied

            queryset = Observation.objects.get_subject_observations(
                subject, since=recorded_since, until=recorded_until, filter_flag=filter_flag
            )
        elif source_id:
            queryset = Observation.objects.get_source_observations(
                source_id, since=recorded_since, until=recorded_until, filter_flag=filter_flag
            )
        elif subjectsource_id:
            queryset = Observation.objects.get_subjectsource_observations(
                subjectsource_id, since=recorded_since, until=recorded_until, filter_flag=filter_flag
            )
        else:
            queryset = Observation.objects.by_since_until(recorded_since, recorded_until)
            queryset = queryset.by_exclusion_flags(filter_flag)

        mou_date = self.request.user.additional.get("expiry", None)
        mou_expiry_date = dateparse(mou_date) if mou_date else None
        created_after = dateparse(created_after) if created_after else None

        if mou_expiry_date:
            queryset = queryset.filter(recorded_at__lte=mou_expiry_date)

        if created_after:
            queryset = queryset.by_created_after(created_after)

        queryset = queryset.annotate_transforms()
        queryset = queryset.prefetch_related("source__provider__transforms")
        queryset = queryset.order_by(sort_by)

        return queryset.values()

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
        self.perform_create(serializer)
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
