from __future__ import annotations

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend

from django.db.models import QuerySet
from django.db.utils import IntegrityError
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from analyzers.models import (
    EnvironmentalSubjectAnalyzerConfig,
    FeatureProximityAnalyzerConfig,
    GeofenceAnalyzerConfig,
    ImmobilityAnalyzerConfig,
    LowSpeedPercentileAnalyzerConfig,
    LowSpeedWilcoxAnalyzerConfig,
    MovementClusterAnalyzerConfig,
    ObservationAttributeAnalyzerConfig,
    SubjectProximityAnalyzerConfig,
)
from analyzers.serializers import (
    EnvironmentalAnalyzerConfigSerializer,
    FeatureProximityAnalyzerConfigListSerializer,
    FeatureProximityAnalyzerConfigSerializer,
    GeofenceAnalyzerConfigListSerializer,
    GeofenceAnalyzerConfigSerializer,
    ImmobilityAnalyzerConfigSerializer,
    LowSpeedPercentileAnalyzerConfigSerializer,
    LowSpeedWilcoxAnalyzerConfigSerializer,
    MovementClusterAnalyzerConfigSerializer,
    ObservationAttributeAnalyzerConfigSerializer,
    SubjectProximityAnalyzerConfigListSerializer,
    SubjectProximityAnalyzerConfigSerializer,
)
from utils.drf import (
    ModelPermissions,
    StandardResultsSetPagination,
    return_409_response,
)
from utils.json import VALID_BOOLEAN_STRINGS, parse_bool


def _parse_active_param(query_params) -> bool | None:
    """Parse the ``active`` query parameter into a bool.

    Returns None when the parameter is absent, and raises a DRF ValidationError
    (→ HTTP 400) when present but not a recognized boolean string.
    """
    if "active" not in query_params:
        return None
    active_str = query_params["active"]
    if active_str.lower() not in VALID_BOOLEAN_STRINGS:
        raise ValidationError({"active": f"Expected a boolean value, got {active_str!r}."})
    return parse_bool(active_str)


class AnalyzerConfigFilterSet(filters.FilterSet):
    """Filter analyzer config querysets by the public ``active`` query parameter.

    The public param name is ``active``; it targets the model field ``is_active``.
    A ``TypedChoiceFilter`` restricted to ``VALID_BOOLEAN_STRINGS`` ensures an
    invalid value (e.g. ``?active=garbage``) raises a DRF ``ValidationError`` →
    HTTP 400 (``DjangoFilterBackend.raise_exception`` is True by default), rather
    than being silently coerced to ``None`` the way a plain ``BooleanFilter`` would.
    An absent param applies no filtering.

    Applied via ``DjangoFilterBackend.filter_queryset`` (after the permission
    check), so a bad ``?active=`` value on an unauthorized request is still
    rejected as 401/403 before the param is ever validated.
    """

    active = filters.TypedChoiceFilter(
        field_name="is_active",
        choices=[(value, value) for value in VALID_BOOLEAN_STRINGS],
        coerce=parse_bool,
        label="Filter by active status (boolean).",
    )

    class Meta:
        fields = ["active"]


class AnalyzerListView(APIView):
    def get(self, request, *args, **kwargs):

        active = _parse_active_param(request.query_params)
        filter = {"is_active": active} if active is not None else None

        results = []
        for spatial_model, spatial_serializer in self.MODEL_TO_SERIALIZER:

            required_perm = f"{spatial_model._meta.app_label}.view_{spatial_model._meta.model_name}"
            if self.request.user.has_perm(required_perm):
                qs = spatial_model.objects.all()
                if filter:
                    qs = qs.filter(**filter)
                for row in qs:
                    serializer = spatial_serializer(row, context={"request": request})
                    results.append(serializer.data)

        return Response(results)


class SpatialAnalyzerListView(AnalyzerListView):

    MODEL_TO_SERIALIZER = (
        (GeofenceAnalyzerConfig, GeofenceAnalyzerConfigListSerializer),
        (FeatureProximityAnalyzerConfig, FeatureProximityAnalyzerConfigListSerializer),
    )


class SubjectAnalyzerListView(AnalyzerListView):
    MODEL_TO_SERIALIZER = ((SubjectProximityAnalyzerConfig, SubjectProximityAnalyzerConfigListSerializer),)


class _BaseAnalyzerConfigViewSet(ModelViewSet):
    permission_classes = [ModelPermissions]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = AnalyzerConfigFilterSet

    def get_queryset(self) -> QuerySet:
        # Build a fresh tenant-filtered queryset from the model at request time;
        # self.queryset is a .none() placeholder used only for DRF introspection.
        # Keep this limited to the base tenant-scoped queryset (plus select_related):
        # DjangoModelPermissions.has_permission calls get_queryset during the permission
        # check, so query-param validation/filtering belongs in the FilterSet applied
        # by DjangoFilterBackend.filter_queryset (which runs after the permission check),
        # not here.
        return self.queryset.model.objects.select_related("subject_group", "feature_group_filter").order_by("name")

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))


class GeofenceAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = GeofenceAnalyzerConfig.objects.none()
    serializer_class = GeofenceAnalyzerConfigSerializer

    def get_queryset(self) -> QuerySet:
        return (
            super()
            .get_queryset()
            .select_related("critical_geofence_group", "warning_geofence_group", "containment_regions")
        )


class FeatureProximityAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = FeatureProximityAnalyzerConfig.objects.none()
    serializer_class = FeatureProximityAnalyzerConfigSerializer

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("proximal_features")


class SubjectProximityAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = SubjectProximityAnalyzerConfig.objects.none()
    serializer_class = SubjectProximityAnalyzerConfigSerializer

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("second_subject_group")


class ImmobilityAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = ImmobilityAnalyzerConfig.objects.none()
    serializer_class = ImmobilityAnalyzerConfigSerializer


class EnvironmentalAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = EnvironmentalSubjectAnalyzerConfig.objects.none()
    serializer_class = EnvironmentalAnalyzerConfigSerializer


class LowSpeedPercentileAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = LowSpeedPercentileAnalyzerConfig.objects.none()
    serializer_class = LowSpeedPercentileAnalyzerConfigSerializer


class LowSpeedWilcoxAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = LowSpeedWilcoxAnalyzerConfig.objects.none()
    serializer_class = LowSpeedWilcoxAnalyzerConfigSerializer


class MovementClusterAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = MovementClusterAnalyzerConfig.objects.none()
    serializer_class = MovementClusterAnalyzerConfigSerializer


class ObservationAttributeAnalyzerConfigViewSet(_BaseAnalyzerConfigViewSet):
    queryset = ObservationAttributeAnalyzerConfig.objects.none()
    serializer_class = ObservationAttributeAnalyzerConfigSerializer
