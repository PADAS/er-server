from rest_framework.generics import ListCreateAPIView, get_object_or_404
from rest_framework.pagination import StandardResultsSetPagination

from buoy.serializers.gear import GearSerializer
from observations.models import Observation, Subject
from observations.utils import dateparse
from observations.views.helpers import check_valid_date_string
from utils.drf import StandardResultsSetCursorPagination, StandardResultsSetPagination
from utils.json import parse_bool


class GearCursorPagination(StandardResultsSetCursorPagination):
    cursor_query_Param = "id"
    ordering = "recorded_at"


class GearView(ListCreateAPIView):
    serializer_class = GearSerializer
    pagination_class = StandardResultsSetPagination

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
                    GearCursorPagination()
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
        query_params = self.request.query_params
        updated_since = query_params.get("updated_since")
        recorded_updated_since_is_valid, recorded_updated_since = check_valid_date_string(
            updated_since, "recorded_updated_since"
        )
        subject_id = query_params.get("subject_id")
        latitude = query_params.get("lat")
        longitude = query_params.get("lon")
        state = query_params.get("state")
        sort_by = query_params.get("sort_by", "recorded_at")

        filter_flag = 0
        filter_qparam = query_params.get("filter", 0)
        try:
            filter_flag = int(filter_qparam)
        except (ValueError, TypeError):
            filter_flag = None if filter_qparam == "null" else filter_flag

        if len([id for id in (subject_id, latitude, longitude, state) if id]) > 1:
            raise ValueError("Can only specify one of: subject_id and state and lat and lon")

        elif subject_id:
            subject = get_object_or_404(Subject, pk=subject_id)

            queryset = Observation.objects.get_subject_observations(
                subject, since=recorded_updated_since, filter_flag=filter_flag
            )
        else:
            queryset = Observation.objects.by_since(recorded_updated_since)
            queryset = queryset.by_exclusion_flags(filter_flag)

        mou_date = self.request.user.additional.get("expiry", None)
        mou_expiry_date = dateparse(mou_date) if mou_date else None
        created_after = dateparse(created_after) if created_after else None

        if mou_expiry_date:
            queryset = queryset.filter(recorded_at__lte=mou_expiry_date)

        if created_after:
            queryset = queryset.by_created_after(created_after)

        queryset = queryset.annotate_transforms()
        # Quesion: What is this?
        queryset = queryset.prefetch_related("source__provider__transforms")
        queryset = queryset.order_by(sort_by)

        return queryset.values()

    def get_serializer_context(self):
        context = super(GearView, self).get_serializer_context()

        # Check request before accessing params since self.request is None when
        # generating docs schema
        context["include_details"] = (
            parse_bool(self.request.query_params.get("include_details", False)) if self.request else False
        )

        return context
