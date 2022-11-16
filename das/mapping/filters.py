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

    class Meta:
        model = SpatialFeature
        fields = ["feature_class", "feature_set"]
