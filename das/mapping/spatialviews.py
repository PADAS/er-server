from __future__ import annotations

import logging

from django_filters import rest_framework as filters

from django.db.models import Count, QuerySet
from rest_framework import generics
from rest_framework.filters import OrderingFilter
from rest_framework.serializers import BaseSerializer

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import (
    DisplayCategory,
    SpatialFeature,
    SpatialFeatureGroupStatic,
    SpatialFeatureType,
)
from mapping.permissions import LayerObjectPermissions
from mapping.serializers import (
    DisplayCategorySerializer,
    SpatialFeatureGroupDetailSerializer,
    SpatialFeatureGroupListSerializer,
    SpatialFeatureGroupWriteSerializer,
    SpatialFeatureListSerializer,
    SpatialFeatureSerializer,
    SpatialFeatureTypeSerializer,
    SpatialFeatureTypeWriteSerializer,
    SpatialFeatureWriteSerializer,
)
from schemas.view_mixins import DynamicSchemaDataMixin
from utils.drf import DeprecatedEndpointMixin

logger = logging.getLogger(__name__)


class DisplayCategoryListView(generics.ListCreateAPIView, DynamicSchemaDataMixin):
    permission_classes = (LayerObjectPermissions,)
    serializer_class = DisplayCategorySerializer

    def get_queryset(self) -> QuerySet[DisplayCategory]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return DisplayCategory.objects.all()


class DisplayCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (LayerObjectPermissions,)
    serializer_class = DisplayCategorySerializer
    lookup_field = "id"

    def get_queryset(self) -> QuerySet[DisplayCategory]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return DisplayCategory.objects.all()


class SpatialFeatureTypeListView(generics.ListCreateAPIView):
    permission_classes = (LayerObjectPermissions,)
    filter_backends = [OrderingFilter]
    ordering_fields = ("name",)
    ordering = ("name",)

    def get_serializer_class(self) -> type[BaseSerializer]:  # type: ignore[override]  # DRF types as Any; narrower return is correct
        if self.request.method == "POST":
            return SpatialFeatureTypeWriteSerializer
        return SpatialFeatureTypeSerializer

    def get_queryset(self) -> QuerySet[SpatialFeatureType]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return SpatialFeatureType.objects.all()


class SpatialFeatureTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (LayerObjectPermissions,)
    lookup_field = "id"

    def get_serializer_class(self) -> type[BaseSerializer]:  # type: ignore[override]  # DRF types as Any; narrower return is correct
        if self.request.method in ("PUT", "PATCH"):
            return SpatialFeatureTypeWriteSerializer
        return SpatialFeatureTypeSerializer

    def get_queryset(self) -> QuerySet[SpatialFeatureType]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return SpatialFeatureType.objects.all()


# type: ignore[misc] on Deprecated* classes: DeprecatedEndpointMixin intentionally precedes the concrete view in MRO
class DeprecatedSpatialFeatureTypeListView(DeprecatedEndpointMixin, SpatialFeatureTypeListView):  # type: ignore[misc]
    deprecated_use_instead = "/featuretypes/"


class DeprecatedSpatialFeatureTypeDetailView(DeprecatedEndpointMixin, SpatialFeatureTypeDetailView):  # type: ignore[misc]
    deprecated_use_instead = "/featuretypes/<id>/"


class SpatialFeatureGroupListView(generics.ListCreateAPIView):
    permission_classes = (LayerObjectPermissions,)
    filter_backends = [OrderingFilter]
    ordering_fields = ("name", "created_at", "updated_at")
    ordering = ("name",)

    def get_serializer_class(self) -> type[BaseSerializer]:  # type: ignore[override]  # DRF types as Any; narrower return is correct
        if self.request.method == "POST":
            return SpatialFeatureGroupWriteSerializer
        return SpatialFeatureGroupListSerializer

    def get_queryset(self) -> QuerySet[SpatialFeatureGroupStatic]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return SpatialFeatureGroupStatic.objects.annotate(feature_count=Count("features")).all()


class SpatialFeatureGroupDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (LayerObjectPermissions,)
    lookup_field = "id"

    def get_serializer_class(self) -> type[BaseSerializer]:  # type: ignore[override]  # DRF types as Any; narrower return is correct
        if self.request.method in ("PUT", "PATCH"):
            return SpatialFeatureGroupWriteSerializer
        return SpatialFeatureGroupDetailSerializer

    def get_queryset(self) -> QuerySet[SpatialFeatureGroupStatic]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return (
            SpatialFeatureGroupStatic.objects.annotate(feature_count=Count("features"))
            .prefetch_related("features__feature_type__display_category")
            .all()
        )


class DeprecatedSpatialFeatureGroupListView(DeprecatedEndpointMixin, SpatialFeatureGroupListView):  # type: ignore[misc]
    deprecated_use_instead = "/featuregroups/"


class DeprecatedSpatialFeatureGroupDetailView(DeprecatedEndpointMixin, SpatialFeatureGroupDetailView):  # type: ignore[misc]
    deprecated_use_instead = "/featuregroups/<id>/"


class SpatialFeatureListView(generics.ListCreateAPIView, DynamicSchemaDataMixin):
    permission_classes = (LayerObjectPermissions,)
    filter_backends = [OrderingFilter, filters.DjangoFilterBackend]
    filterset_class = SpatialFeatureFilterSet
    ordering_fields = ("name",)
    ordering = ("name",)

    def get_serializer_class(self) -> type[BaseSerializer]:  # type: ignore[override]  # DRF types as Any; narrower return is correct
        if self.request.method == "POST":
            return SpatialFeatureWriteSerializer
        return SpatialFeatureListSerializer

    def get_queryset(self) -> QuerySet[SpatialFeature]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return SpatialFeature.objects.select_related("feature_type__display_category").all()


class SpatialFeatureDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (LayerObjectPermissions,)
    lookup_field = "id"

    def get_serializer_class(self) -> type[BaseSerializer]:  # type: ignore[override]  # DRF types as Any; narrower return is correct
        if self.request.method in ("PUT", "PATCH"):
            return SpatialFeatureWriteSerializer
        return SpatialFeatureSerializer

    def get_queryset(self) -> QuerySet[SpatialFeature]:  # type: ignore[override]  # DRF types as QuerySet[Any]; narrower return is correct
        return SpatialFeature.objects.all()


class DeprecatedSpatialFeatureListView(DeprecatedEndpointMixin, SpatialFeatureListView):  # type: ignore[misc]
    deprecated_use_instead = "/api/v2.0/features/"


class DeprecatedSpatialFeatureDetailView(DeprecatedEndpointMixin, SpatialFeatureDetailView):  # type: ignore[misc]
    deprecated_use_instead = "/api/v2.0/features/<id>/"
