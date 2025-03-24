from django_filters import rest_framework as filters

from choices.models import Choice
from utils.json import parse_bool


class ChoicesFilter(filters.FilterSet):
    models = filters.MultipleChoiceFilter(field_name="model", choices=Choice.MODEL_REF_CHOICES)
    fields = filters.BaseInFilter(field_name="field")

    model = filters.ChoiceFilter(field_name="model", choices=Choice.MODEL_REF_CHOICES)
    field = filters.CharFilter(field_name="field", lookup_expr="iexact")

    include_inactive = filters.BooleanFilter(method="filter_include_inactive")

    def filter_queryset(self, queryset):
        if "include_inactive" not in self.data:
            return queryset.filter_active_choices()  # Only active default
        return super().filter_queryset(queryset)

    def filter_include_inactive(self, queryset, name, value):
        if value and parse_bool(value):
            return queryset

        return queryset.filter_active_choices()

    class Meta:
        model = Choice
        fields = ["model", "field", "include_inactive", "models", "fields"]
