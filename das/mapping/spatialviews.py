from django_filters import rest_framework as filters

from rest_framework import generics
from rest_framework.filters import OrderingFilter

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic, SpatialFeatureType
from mapping.serializers import (
    SpatialFeatureGroupStaticSerializer,
    SpatialFeatureListSerializer,
    SpatialFeatureSerializer,
    SpatialFeatureTypeSerializer,
)
from schemas.view_mixins import DynamicSchemaDataMixin


class SpatialFeatureGroupView(generics.RetrieveAPIView):

    serializer_class = SpatialFeatureGroupStaticSerializer
    lookup_field = "id"

    def get_queryset(self):
        return SpatialFeatureGroupStatic.objects.all()


class SpatialFeatureTypeListView(generics.ListAPIView):

    serializer_class = SpatialFeatureTypeSerializer

    def get_queryset(self):
        return SpatialFeatureType.objects.all()


class SpatialFeatureListView(generics.ListAPIView, DynamicSchemaDataMixin):

    serializer_class = SpatialFeatureListSerializer
    filter_backends = [OrderingFilter, filters.DjangoFilterBackend]
    filterset_class = SpatialFeatureFilterSet
    ordering_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self):
        return SpatialFeature.objects.select_related("feature_type__display_category").all()


class SpatialFeatureView(generics.RetrieveAPIView):

    serializer_class = SpatialFeatureSerializer
    lookup_field = "id"

    def get_queryset(self):
        return SpatialFeature.objects.all()
