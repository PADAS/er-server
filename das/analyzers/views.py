import itertools

from rest_framework import generics, status, response
from rest_framework.response import Response

from utils.drf import StandardResultsSetPagination
from analyzers.models import GeofenceAnalyzerConfig, FeatureProximityAnalyzerConfig, SubjectProximityAnalyzerConfig
from analyzers.serializers import GeofenceAnalyzerConfigSerializer, FeatureProximityAnalyzerSerializer, SubjectProximityAnalyzerSerializer
from analyzers.permissions import ModelPermissions

from utils.json import parse_bool

class AnalyzerListView(generics.ListAPIView):
    # permission_classes = (ModelPermissions,)
    # pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):

        if 'active' in request.query_params:
            filter = {'is_active': parse_bool(
                request.query_params.get('active'))}
        else:
            filter = None

        results = []
        for spatial_model, spatial_serializer in self.MODEL_TO_SERIALIZER:

            required_perm = f'{spatial_model._meta.app_label}.view_{spatial_model._meta.model_name}'
            if self.request.user.has_perm(required_perm):
                qs = spatial_model.objects.all()
                if filter:
                    qs = qs.filter(**filter)
                for row in qs:
                    serializer = spatial_serializer(
                        row, context={'request': request})
                    results.append(serializer.data)

        return Response(results)


class SpatialAnalyzerListView(AnalyzerListView):

    MODEL_TO_SERIALIZER = ((GeofenceAnalyzerConfig, GeofenceAnalyzerConfigSerializer),
                           (FeatureProximityAnalyzerConfig, FeatureProximityAnalyzerSerializer),)


class SubjectAnalyzerListView(AnalyzerListView):
    MODEL_TO_SERIALIZER = ((SubjectProximityAnalyzerConfig, SubjectProximityAnalyzerSerializer),)
