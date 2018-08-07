import itertools

from rest_framework import generics, status, response
from rest_framework.response import Response

from utils.drf import StandardResultsSetPagination
from analyzers.models import GeofenceAnalyzerConfig, ProximityAnalyzerConfig
from analyzers.serializers import GeofenceAnalyzerConfigSerializer, ProximityAnalyzerConfigSerializer
from analyzers.permissions import ModelPermissions


class SpatialAnalyzerListView(generics.ListAPIView):
    #permission_classes = (ModelPermissions,)
    #pagination_class = StandardResultsSetPagination

    MODEL_TO_SERIALIZER = ((GeofenceAnalyzerConfig, GeofenceAnalyzerConfigSerializer),
                           (ProximityAnalyzerConfig, ProximityAnalyzerConfigSerializer))

    def list(self, request, *args, **kwargs):
        results = []
        for spatial_model, spatial_serializer in self.MODEL_TO_SERIALIZER:
            for row in spatial_model.objects.all():
                serializer = spatial_serializer(
                    row, context={'request': request})
                results.append(serializer.data)

        return Response(results)
