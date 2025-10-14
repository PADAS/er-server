from drf_spectacular.utils import extend_schema

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from buoy import serializers
from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from buoy.permissions import GearLocationPermission, GearSubjectPermission
from buoy.serializers.query_params import GearsQueryParamsSerializer
from buoy.views.helpers import NAUTICAL_MILE_RADIUS, filter_by_bbox
from buoy.views.schemas import GearsViewSchema
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource
from observations.tasks import send_observations_to_gundi_async
from observations.utils import VIEW_SUBJECT_PERMS, dateparse, get_minimum_allowed_age
from utils.drf import (
    ForbiddenAPIException,
    StandardObjectPermissions,
    StandardResultsSetPagination,
)
from utils.tenant import get_tenant_settings


@extend_schema(parameters=[GearsQueryParamsSerializer])
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

    permission_classes = (StandardObjectPermissions, IsAuthenticated, GearSubjectPermission, GearLocationPermission)
    serializer_class = serializers.GearSerializer
    pagination_class = StandardResultsSetPagination
    schema = GearsViewSchema()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.GearCreateSerializer
        return serializers.GearSerializer

    def get_queryset(self):
        return SubjectSource.objects.none()

    def list(self, request, *args, **kwargs):
        # Validate query parameters using serializer
        query_serializer = GearsQueryParamsSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        query_params = query_serializer.validated_data

        # First get subject-sources with related data
        queryset = (
            SubjectSource.objects.filter(
                subject__subject_subtype__in=["ropeless_buoy_device", BUOY_GEAR_SUBJECT_SUBTYPE]
            )
            .select_related("source", "subject")
            .prefetch_related("source__last_observation_sources")
        )
        queryset = queryset.order_by("id")  # Stable sort for pagination

        # Apply filters based on validated parameters
        if query_params.get("updated_since"):
            queryset = queryset.by_updated_since(query_params["updated_since"])

        # Filter by state (deployed/hauled)
        queryset = queryset.filter(subject__is_active=(query_params.get("state") == "deployed"))

        # Apply location filtering if coordinates provided
        lat = query_params.get("lat")
        lon = query_params.get("lon")
        max_nm_range = query_params.get("max_nm_range", NAUTICAL_MILE_RADIUS)

        if lat and lon:
            lat = float(lat)
            lon = float(lon)
            queryset = filter_by_bbox(queryset=queryset, latitude=lat, longitude=lon, nautical_miles=int(max_nm_range))

        # Filter queryset by removing subjects where the additional field is the same
        queryset = queryset.order_by("subject__additional__display_id", "subject__name").distinct(
            "subject__additional__display_id"
        )

        # Normal ListAPIView.list() code here
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"user_id": request.user.id})
        serializer.is_valid(raise_exception=True)
        observations = serializer.save()

        domain = get_tenant_settings().domain
        task_result = send_observations_to_gundi_async.apply_async(
            args=(observations, settings.BUOY_GUNDI_INTEGRATION_ID), kwargs={"domain": domain}
        )

        return Response(
            {"detail": "Gears created successfully and queued for processing", "task_id": task_result.id}, status=201
        )


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

        queryset = queryset.prefetch_related(
            "subjectsources__source__provider", "subjectsources__source__last_observation_sources"
        )

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
        context["simple_mode"] = True

        return context
