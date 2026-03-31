from __future__ import annotations

import logging

from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)

from django.db.models import Prefetch
from django.db.utils import IntegrityError
from django.urls import reverse
from rest_framework import generics
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from buoy import serializers
from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from buoy.permissions import (
    GearLocationPermission,
    GearSubjectPermission,
    HasManufacturerSubjectGroupPermission,
)
from buoy.serializers.query_params import GearsQueryParamsSerializer
from buoy.services.buoy_service import BuoyService, OlderGearsetRejectedError
from buoy.views.helpers import NAUTICAL_MILE_RADIUS, filter_by_bbox
from buoy.views.schemas import GearsViewSchema, gears_list_response_schema
from core.fields import StrictUUIDField
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource
from utils.drf import (
    StandardObjectPermissions,
    StandardResultsSetPagination,
    return_409_response,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    get=extend_schema(
        parameters=[],
        responses={
            200: OpenApiResponse(
                response=gears_list_response_schema,
                description="A list of gears matching the query parameters.",
            )
        },
    ),
    post=extend_schema(
        request=serializers.GearCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    name="GearCreateResponse",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "set_id": StrictUUIDField(),
                    },
                ),
            ),
            400: OpenApiResponse(
                response=inline_serializer(
                    name="GearCreateErrorResponse",
                    fields={
                        "status": inline_serializer(
                            name="GearCreateErrorStatus",
                            fields={
                                "code": drf_serializers.IntegerField(help_text="HTTP status code."),
                                "message": drf_serializers.CharField(help_text="HTTP status text."),
                                "detail": drf_serializers.CharField(
                                    help_text="A description of the error (present for older-gearset rejections).",
                                    required=False,
                                ),
                            },
                        ),
                        "device_id": drf_serializers.CharField(
                            help_text=(
                                "The device ID that triggered the conflict "
                                "(present only when an older gearset is rejected)."
                            ),
                            required=False,
                        ),
                        "newer_gearset_id": drf_serializers.UUIDField(
                            help_text=(
                                "The set_id of the newer gearset that already has the device deployed "
                                "(present only when an older gearset is rejected)."
                            ),
                            required=False,
                        ),
                    },
                ),
                description=(
                    "Bad request. May be a standard serializer validation error (e.g. missing or invalid fields) "
                    "or an older-gearset rejection. For older-gearset rejections, device_id and newer_gearset_id "
                    "are also present; the error detail is nested under status.detail per the API response envelope."
                ),
            ),
            403: OpenApiResponse(
                response=inline_serializer(
                    name="GearCreateForbiddenResponse",
                    fields={
                        "detail": drf_serializers.CharField(
                            help_text="You do not have permission to perform this action."
                        )
                    },
                    required=True,
                ),
                description="Forbidden: You do not have permission to perform this action.",
            ),
            500: OpenApiResponse(
                response=inline_serializer(
                    name="GearCreateServerErrorResponse",
                    fields={
                        "detail": drf_serializers.CharField(
                            help_text="An internal server error occurred. Please try again later."
                        )
                    },
                    required=True,
                ),
                description="Internal Server Error: An error occurred on the server.",
            ),
            401: OpenApiResponse(
                response=inline_serializer(
                    name="GearCreateUnauthorizedResponse",
                    fields={
                        "detail": drf_serializers.CharField(
                            help_text="Authentication credentials were not provided or are invalid."
                        )
                    },
                    required=True,
                ),
                description="Unauthorized: Authentication credentials were not provided or are invalid.",
            ),
        },
        description="Create new gears and send observations to Gundi for processing.",
    ),
)
class GearsListCreateView(generics.ListCreateAPIView, TwoWaySubjectSourceMixin):
    """
    GET: Returns all gears.

    Required query-parameters:
    lat, lon: float
    (Unless the user is edgetech, blueoceangear, or admin)

    Optional query-parameters:
    state, where state is either "deployed" or "hauled".
        example: state=deployed
    updated_since, where updated_since is a date-string to limit on updated_at
    include_empty_location, where include_empty_location is a boolean to include gear with no location data, 0,0 points. Default is false.

    max_nm_range

    page, page number

    page_size, (default is {page_size}, max is {max_page_size})

    POST: This API allows users to submit a single trawl with either single or multiple devices.
    """.format(
        page_size=StandardResultsSetPagination.page_size, max_page_size=StandardResultsSetPagination.max_page_size
    )

    permission_classes = (StandardObjectPermissions, IsAuthenticated, GearSubjectPermission, GearLocationPermission)
    serializer_class = serializers.GearSerializer
    pagination_class = StandardResultsSetPagination
    schema = GearsViewSchema()

    def get_queryset(self):
        # Return SubjectSource so StandardObjectPermissions enforces the correct
        # SubjectSource-related permissions (view_subjectsource, add_subjectsource).
        return SubjectSource.objects.none()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.GearCreateSerializer
        return serializers.GearSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Add include_empty_location from validated query params (set in list method)
        context["include_empty_location"] = getattr(self, "_include_empty_location", False)
        return context

    def list(self, request, *args, **kwargs):
        # Validate query parameters using serializer
        query_serializer = GearsQueryParamsSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        query_params = query_serializer.validated_data

        # Store include_empty_location for get_serializer_context
        self._include_empty_location = query_params.get("include_empty_location", False)

        ss_queryset = SubjectSource.objects.select_related("source").order_by("source_id")
        if query_params.get("state") == "deployed":
            from observations.models import DEFAULT_ASSIGNED_RANGE

            max_upper = DEFAULT_ASSIGNED_RANGE[1]
            ss_queryset = ss_queryset.filter(assigned_range__endswith=max_upper)

        queryset = Subject.objects.filter(
            subject_subtype__in=["ropeless_buoy_device", BUOY_GEAR_SUBJECT_SUBTYPE]
        ).prefetch_related(
            "groups",
            Prefetch(
                "subjectsources",
                queryset=ss_queryset,
                to_attr="all_subjectsources",
            ),
        )

        # Apply filters based on validated parameters
        if query_params.get("updated_since"):
            queryset = queryset.annotate_with_subjectstatus().by_updated_since(query_params["updated_since"])

        # Filter by state (deployed/hauled)
        queryset = queryset.filter(is_active=(query_params.get("state") == "deployed"))

        # Apply location filtering if coordinates provided
        lat = query_params.get("lat")
        lon = query_params.get("lon")
        max_nm_range = query_params.get("max_nm_range", NAUTICAL_MILE_RADIUS)

        if lat is not None and lon is not None:
            queryset = filter_by_bbox(queryset=queryset, latitude=lat, longitude=lon, nautical_miles=int(max_nm_range))

        queryset = queryset.order_by("additional__display_id", "name", "id")

        # Normal ListAPIView.list() code here
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        try:
            subject, observations = BuoyService.process_gearset(validated_data, user=request.user)
        except OlderGearsetRejectedError as e:
            error_detail = {"detail": str(e), "device_id": e.device_id}
            if e.newer_gearset_id:
                error_detail["newer_gearset_id"] = str(e.newer_gearset_id)
            raise ValidationError(error_detail)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

        return Response(
            {
                "detail": "Gears successfully processed",
                "set_id": str(subject.id),
            },
            status=201,
            headers={"Location": reverse("gear-view", args=[str(subject.id)])},
        )


class GearView(generics.RetrieveAPIView):
    permission_classes = (HasManufacturerSubjectGroupPermission,)
    serializer_class = serializers.GearSerializer
    lookup_field = "id"

    def get_queryset(self):
        subject_id = self.kwargs.get("id")
        return Subject.objects.filter(id=subject_id).prefetch_related(
            "groups",
            Prefetch(
                "subjectsources",
                queryset=SubjectSource.objects.select_related("source").order_by("source_id"),
                to_attr="all_subjectsources",
            ),
        )

    def get_object(self):
        subject = self.get_queryset().first()
        if not subject:
            raise NotFound("No gear found for this id")

        self.check_object_permissions(self.request, subject)

        return subject
