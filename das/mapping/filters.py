from django_filters import rest_framework as filters
from django_filters.widgets import CSVWidget

from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType


class SpatialFeatureFilterSet(filters.FilterSet):

    feature_class = filters.ModelMultipleChoiceFilter(
        field_name="feature_type",
        queryset=lambda request: SpatialFeatureType.objects.all(),
        widget=CSVWidget(),
        label="Feature Type",
    )
    # Renamed from ``feature_set`` to ``display_category`` so the v2 param name
    # matches its actual semantics (filter by DisplayCategory). The v1
    # ``/features/`` endpoint keeps its own ``feature_set`` param, which filters
    # by SpatialFeatureGroupStatic — different concept, intentionally different
    # name on v2 to avoid silent wrong results during migration.
    display_category = filters.ModelMultipleChoiceFilter(
        field_name="feature_type__display_category",
        queryset=lambda request: DisplayCategory.objects.all(),
        widget=CSVWidget(),
        label="Display Category",
    )

    class Meta:
        model = SpatialFeature
        fields = ["feature_class", "display_category"]
