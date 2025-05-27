from django_filters import rest_framework as filters
from django_filters.widgets import CSVWidget

from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType


class SpatialFeatureFilterSet(filters.FilterSet):

    feature_type = filters.ModelMultipleChoiceFilter(
        queryset=lambda request: SpatialFeatureType.objects.all(),
        widget=CSVWidget(),
        label="Feature Type",
    )
    feature_set = filters.ModelMultipleChoiceFilter(
        field_name="feature_type__display_category",
        queryset=lambda request: DisplayCategory.objects.all(),
        widget=CSVWidget(),
        label="Feature Set (Display Category)",
    )

    class Meta:
        model = SpatialFeature
        fields = ["feature_type", "feature_set"]
