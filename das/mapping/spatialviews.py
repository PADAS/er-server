import logging

from rest_framework import generics

from mapping.filters import SpatialFeatureFilter
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic
from mapping.serializers import (
    SpatialFeatureGroupStaticSerializer,
    SpatialFeatureListSerializer,
    SpatialFeatureSerializer,
)

logger = logging.getLogger(__name__)


class SpatialFeatureGroupView(generics.RetrieveAPIView):

    serializer_class = SpatialFeatureGroupStaticSerializer
    lookup_field = "id"

    def get_queryset(self):
        return SpatialFeatureGroupStatic.objects.all()


class SpatialFeatureListView(generics.ListAPIView):

    serializer_class = SpatialFeatureListSerializer
    filter_backends = (SpatialFeatureFilter,)

    def get_queryset(self):
        return SpatialFeature.objects.select_related("feature_type__display_category").all()


class SpatialFeatureView(generics.RetrieveAPIView):

    serializer_class = SpatialFeatureSerializer
    lookup_field = "id"

    queryset = SpatialFeature.objects.all()
