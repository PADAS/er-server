from drf_spectacular.utils import extend_schema

from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)

from django.db import transaction
from django.db.utils import IntegrityError
from django.urls import reverse
from rest_framework import generics
from rest_framework.response import Response

from buoy import serializers
from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from buoy.permissions import (
    GearLocationPermission,
    GearSubjectPermission,
    HasManufacturerSubjectGroupPermission,
)
from buoy.serializers.query_params import GearsQueryParamsSerializer
from buoy.views.helpers import NAUTICAL_MILE_RADIUS, filter_by_bbox
from buoy.views.schemas import GearsViewSchema
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import SubjectSource
from utils.drf import (
    StandardObjectPermissions,
    StandardResultsSetPagination,
    return_409_response,
)



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
                        "set_id": drf_serializers.UUIDField(),
                    },
                ),
            ),
            400: OpenApiResponse(
                response=inline_serializer(
                    name="GearCreateErrorResponse",
                    fields={"detail": drf_serializers.CharField(help_text="A description of the error that occurred.")},
                ),
                description="Bad request due to invalid input data.",
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

    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.GearSerializer
    pagination_class = StandardResultsSetPagination
    schema = GearsViewSchema()

    def get_queryset(self):
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

        # First get subject-sources with related data
        queryset = (
            SubjectSource.objects.filter(
                subject__subject_subtype__in=["ropeless_buoy_device", BUOY_GEAR_SUBJECT_SUBTYPE]
            )
            .select_related("source", "subject")
            .prefetch_related("source__last_observation_sources", "subject__groups")
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

        if lat is not None and lon is not None:
            queryset = filter_by_bbox(queryset=queryset, latitude=lat, longitude=lon, nautical_miles=max_nm_range)
        elif not self.request.user.has_perm("observations.can_view_gear_regardless_location"):
            raise ForbiddenAPIException("lat and lon are required query parameters")

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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        try:
            with transaction.atomic():
                subject, observations = BuoyService.process_gearset(validated_data, user=request.user)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

        BuoyService.process_gearset(validated_data)
        return Response(
            {
                "detail": "Gears successfully processed",
                "set_id": str(subject.id),
            },
            status=201,
            headers={"Location": reverse("gear-view", args=[str(subject.id)])},
        )


class GearView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (HasManufacturerSubjectGroupPermission,)
    serializer_class = serializers.GearSerializer
    lookup_field = "id"

    def get_queryset(self):
        subject_id = self.kwargs.get("id")

        # Return SubjectSource queryset instead of Subject queryset
        # to work with the new GearSerializer (ModelSerializer)
        queryset = SubjectSource.objects.filter(subject_id=subject_id)

        # Prefetch related data for efficient queries
        queryset = queryset.select_related("subject", "source", "source__provider")
        queryset = queryset.prefetch_related("source__last_observation_sources", "subject__groups")

        return queryset

    def get_object(self):
        # Get the first SubjectSource from the queryset
        subject_source = self.get_queryset().first()
        if not subject_source:
            raise NotFound("No SubjectSource found for this subject")

        # Check object-level permissions
        self.check_object_permissions(self.request, subject_source)

        return subject_source
