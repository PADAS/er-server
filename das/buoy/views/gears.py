from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response

from buoy import serializers
from buoy.views.helpers import (
    NAUTICAL_MILE_RADIUS,
    check_valid_date_string,
    check_valid_state_string,
    filter_by_bbox,
)
from buoy.views.schemas import GearsViewSchema
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource
from observations.permissions import StandardObjectPermissions
from observations.utils import VIEW_SUBJECT_PERMS, dateparse, get_minimum_allowed_age
from utils.drf import ForbiddenAPIException, StandardResultsSetPagination
from utils.gis import check_valid_lat_lon


class GearsView(generics.ListAPIView):
    __doc__ = """
    Returns all gears.

    Required query-parameters:
    lat, lon: float
    (Unless the user is edgetech, blueoceangear, or admin)

    Optional query-parameters:
    state, where state is either "deployed" or "hauled".
        example: state=deployed
    updated_since, where updated_since is a date-string to limit on updated_at
    max_nm_range

    page, page number

    page_size, (default is {page_size}, max is {max_page_size})
    """.format(
        page_size=StandardResultsSetPagination.page_size, max_page_size=StandardResultsSetPagination.max_page_size
    )

    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.GearsSerializer
    pagination_class = StandardResultsSetPagination
    schema = GearsViewSchema()

    def get_queryset(self):
        return SubjectSource.objects.none()

    def list(self, request, *args, **kwargs):
        # NOTE:
        # Code extracted from `get_queryset` method and placed here to preserve operations performed on the
        # original method, requires further analisys from buoy team, for checking business logic.

        query_params = self.request.query_params
        # TODO: Look into using allowed users - need to add subjects to SG in unit tests
        # allowed = Subject.objects.by_user_subjects(self.request.user).values_list("id", flat=True)

        # First get subject-sources.
        queryset = (
            SubjectSource.objects.filter(subject__subject_subtype="ropeless_buoy_device")
            .select_related("source")
            .select_related("subject")
        )

        # Filter queryset by removing subjects where the additional field is the same        
        latest_observations = Observation.objects.filter(
            source_id=OuterRef("source_id"), 
            recorded_at__contained_by=OuterRef('assigned_range')).order_by("-recorded_at")
        
        queryset = queryset.annotate(
            latest_observation_additional=Subquery(latest_observations.values("additional")[:1])
        )

        # Filter queryset by removing subjects where the additional field is the same
        queryset = queryset.order_by("subject__additional__display_id", "subject__name").distinct(
            "subject__additional__display_id"
        )

        # Handling new Subject Subtype for new Data Model
        queryset_gearset = (
            SubjectSource.objects.filter(subject__subject_subtype="ropeless_buoy_gearset")
            .select_related("source")
            .select_related("subject")
        )

        # Apply the same filters to gearset queryset
        if updated_since and is_updated_since_valid:
            queryset_gearset = queryset_gearset.by_updated_since(updated_since)

        queryset_gearset = queryset_gearset.filter(subject__is_active=is_active)

        if lat and lon:
            queryset_gearset = filter_by_bbox(queryset=queryset_gearset, latitude=lat, longitude=lon)

        # Apply same distinct filtering
        queryset_gearset = queryset_gearset.order_by("subject__additional__display_id", "subject__name").distinct(
            "subject__additional__display_id"
        )

        # Union both querysets - need to ensure same ordering for union
        combined_queryset = queryset.union(queryset_gearset).order_by("id")

        # Normal ListAPIView.list() code here
        page = self.paginate_queryset(combined_queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(combined_queryset, many=True)
        return Response(serializer.data)


class GearView(generics.RetrieveUpdateDestroyAPIView, TwoWaySubjectSourceMixin):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.GearSerializer
    lookup_field = "id"

    def check_permissions(self, request):
        subject_id = self.kwargs.get("id")
        self.queryset_linked_user = Subject.objects.filter(linked_user=request.user, id=subject_id)
        if not self.queryset_linked_user.exists():
            for permission in self.get_permissions():
                if not permission.has_permission(request, self):
                    self.permission_denied(request)

    def get_queryset(self):
        subject_id = self.kwargs.get("id")
        subject = generics.get_object_or_404(Subject.objects.all(), pk=subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise ForbiddenAPIException
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = Subject.objects.filter(id=subject_id)
        mou_date = self.request.user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None
        queryset = queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24, mou_expiry_date=mou_date)
        self._get_two_way_sources(queryset)
        return queryset

    def get_object(self):
        if self.queryset_linked_user.exists():
            subject_id = self.kwargs.get("id")
            return get_object_or_404(self.queryset_linked_user, pk=subject_id)
        return super().get_object()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["two_way_subject_sources"] = self.two_way_subject_sources

        return context
