import logging

from asgiref.sync import async_to_sync
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from buoy import serializers
from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from buoy.views.helpers import (
    NAUTICAL_MILE_RADIUS,
    check_valid_date_string,
    check_valid_state_string,
    filter_by_bbox,
)
from buoy.views.schemas import GearsViewSchema
from buoy.permissions import GearLocationPermission, GearSubjectPermission
from buoy.serializers.query_params import GearsQueryParamsSerializer
from buoy.views.helpers import NAUTICAL_MILE_RADIUS, filter_by_bbox
from buoy.views.schemas import GearsViewSchema, gears_list_response_schema
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource
from observations.services.gundi import send_observations_to_gundi
from observations.utils import VIEW_SUBJECT_PERMS, dateparse, get_minimum_allowed_age
from utils.drf import (
    ForbiddenAPIException,
    StandardObjectPermissions,
    StandardResultsSetPagination,
)
from utils.gis import check_valid_lat_lon

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
                        "task_id": drf_serializers.UUIDField(),
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
    max_nm_range

    page, page number

    page_size, (default is {page_size}, max is {max_page_size})

    POST: Create new gears and send observations to Gundi for processing.
    """.format(
        page_size=StandardResultsSetPagination.page_size, max_page_size=StandardResultsSetPagination.max_page_size
    )

    permission_classes = (StandardObjectPermissions, IsAuthenticated, GearSubjectPermission, GearLocationPermission)
    serializer_class = serializers.GearSerializer
    pagination_class = StandardResultsSetPagination
    schema = GearsViewSchema()

    def get_queryset(self):
        return SubjectSource.objects.none()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.GearCreateSerializer
        return serializers.GearSerializer

    def list(self, request, *args, **kwargs):
        # Validate query parameters using serializer
        query_serializer = GearsQueryParamsSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        query_params = query_serializer.validated_data

        # First get subject-sources with related data
        queryset = SubjectSource.objects.all().select_related("source", "subject")
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

        # domain = get_tenant_settings().domain
        # task_result = send_observations_to_gundi_async.apply_async(
        #     args=(observations, settings.BUOY_GUNDI_INTEGRATION_ID),
        #     kwargs={"domain": domain, "sensors_api_base_url": settings.SENSORS_API_BASE_URL},
        # )
        try:

            logger.info(
                "Sending %d observations to Gundi with integration_id: %s",
                len(observations),
                "9682ac76-e248-405c-a7f3-bff654460bc3",
            )

            # Convert async function to sync using async_to_sync
            result = async_to_sync(send_observations_to_gundi)(
                observations=observations,
                integration_id="9682ac76-e248-405c-a7f3-bff654460bc3",
                sensors_api_base_url="https://sensors.api.stage.gundiservice.org",
            )

            logger.info("Successfully sent %d observations to Gundi. Result: %s", len(observations), result)

        except Exception as exc:
            logger.error(
                "Failed to send observations to Gundi: %s",
                exc,
            )
            return Response(
                {
                    "detail": f"Failed to send observations to Gundi: {exc}",
                    "traceback": str(exc.__traceback__),
                },
                status=500,
            )

        return Response(
            {
                "detail": f"Gears successfully queued for processing. {settings.SENSORS_API_BASE_URL}",
                "task_id": None,  # task_result.id,
            },
            status=201,
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
