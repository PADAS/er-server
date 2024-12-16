from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend
from rest_framework.views import APIView, Request


class SpatialFeatureFilter(BaseFilterBackend):
    """
    Filter the list of spatial features based on:

    - feature_type_id (`feature_type` in query params, multiple values allowed)
    - display_category_id (`feature_set` in query params, multiple values allowed)

    Because of the way the data is structured, we can filter by either feature_type_id or display_category_id,
    but not both at the same time.

    If both are provided, a ValidationError is raised.
    """

    def filter_queryset(self, request: Request, queryset: QuerySet, view: APIView) -> QuerySet:

        query_params = request.query_params

        # Filter by feature_type_id xor by display_category_id (`feature_set` in query params)
        feature_sets = query_params.getlist("feature_set")
        feature_types = query_params.getlist("feature_type")

        if feature_sets and feature_types:
            raise ValidationError(detail={"detail": "You can't filter by both feature_set and feature_type."})

        if feature_types:
            queryset = queryset.filter(feature_type_id__in=feature_types)

        if feature_sets:
            queryset = queryset.filter(feature_type__display_category_id__in=feature_sets)

        return queryset
