from django_filters import rest_framework as filters

from choices.models import Choice
from utils.drf_filters import RestrictToTrueByDefaultFilter


class ChoicesFilter(filters.FilterSet):

    model = filters.ChoiceFilter(field_name="model", choices=Choice.MODEL_REF_CHOICES)
    models = filters.MultipleChoiceFilter(field_name="model", choices=Choice.MODEL_REF_CHOICES)
    field = filters.CharFilter(field_name="field", lookup_expr="iexact")
    fields = filters.BaseInFilter(field_name="field")
    include_inactive = RestrictToTrueByDefaultFilter(field_name="is_active")

    class Meta:
        model = Choice
        fields = ["model", "models", "field", "fields", "include_inactive"]
