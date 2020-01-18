import logging

from rest_framework import generics

from mapping.models import SpatialFeatureGroupStatic, SpatialFeature
import mapping.serializers as serializers


logger = logging.getLogger(__name__)


class SpatialFeatureGroupView(generics.RetrieveAPIView):

    serializer_class = serializers.SpatialFeatureGroupStaticSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return SpatialFeatureGroupStatic.objects.all()


class SpatialFeatureView(generics.RetrieveAPIView):

    serializer_class = serializers.SpatialFeatureSerializer
    lookup_field = 'id'

    queryset = SpatialFeature.objects.all()
