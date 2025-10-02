from django_filters import rest_framework as filters

from django.db.models import Count
from rest_framework import generics
from rest_framework.filters import OrderingFilter

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic, SpatialFeatureType
from mapping.serializers import (
    SpatialFeatureGroupDetailSerializer,
    SpatialFeatureGroupListSerializer,
    SpatialFeatureListSerializer,
    SpatialFeatureSerializer,
    SpatialFeatureTypeSerializer,
)
from schemas.view_mixins import DynamicSchemaDataMixin


class SpatialFeatureTypeListView(generics.ListAPIView):
    serializer_class = SpatialFeatureTypeSerializer

    def get_queryset(self):
        return SpatialFeatureType.objects.all()


class SpatialFeatureGroupListView(generics.ListAPIView):
    serializer_class = SpatialFeatureGroupListSerializer
    filter_backends = [
        OrderingFilter,
    ]
    ordering_fields = ("name", "created_at", "updated_at")
    ordering = ("name",)

    def get_queryset(self):
        """Lightweight query with annotated feature count for performance."""
        return SpatialFeatureGroupStatic.objects.select_related().annotate(feature_count=Count("features")).all()


class SpatialFeatureGroupDetailView(generics.RetrieveAPIView):
    """
    Retrieve detailed information about a specific spatial feature group.

    Includes full feature data with optimized prefetching.
    """

    serializer_class = SpatialFeatureGroupDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        """Optimized query for detail view with feature prefetching and count annotation."""
        return (
            SpatialFeatureGroupStatic.objects.annotate(feature_count=Count("features"))
            .prefetch_related("features__feature_type__display_category")
            .all()
        )


class SpatialFeatureListView(generics.ListAPIView, DynamicSchemaDataMixin):

    serializer_class = SpatialFeatureListSerializer
    filter_backends = [OrderingFilter, filters.DjangoFilterBackend]
    filterset_class = SpatialFeatureFilterSet
    ordering_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self):
        return SpatialFeature.objects.select_related("feature_type__display_category").all()


class SpatialFeatureDetailView(generics.RetrieveAPIView):

    serializer_class = SpatialFeatureSerializer
    lookup_field = "id"

    def get_queryset(self):
        return SpatialFeature.objects.all()
