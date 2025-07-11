from django_filters import rest_framework as filters
from django_filters.widgets import CSVWidget

from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType


class SpatialFeatureFilterSet(filters.FilterSet):

    feature_class = filters.ModelMultipleChoiceFilter(
        field_name="feature_type",
        queryset=lambda request: SpatialFeatureType.objects.all(),
        widget=CSVWidget(),
        label="Feature Class",
    )
    feature_set = filters.ModelMultipleChoiceFilter(
        field_name="feature_type__display_category",
        queryset=lambda request: DisplayCategory.objects.all(),
        widget=CSVWidget(),
        label="Feature Set (Display Category)",
    )
    external_source = filters.CharFilter(
        field_name="external_source",
        lookup_expr="iexact",
        label="External Source",
    )

    class Meta:
        model = SpatialFeature
        fields = ["feature_class", "feature_set", "external_source"]
