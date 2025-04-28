from django_filters import rest_framework as filters

from choices.models import Choice
from utils.drf_filters import RestrictToTrueByDefaultFilter


class CommaSeparatedMultipleChoiceFilter(filters.BaseInFilter, filters.CharFilter):
    def filter(self, qs, value):
        if not value:
            return qs

        if isinstance(value, str):
            values = [v.strip() for v in value.split(",")]
        elif isinstance(value, list):
            values = [v.strip() for v in value]

        return qs.filter(**{f"{self.field_name}__in": values})


class ChoicesFilter(filters.FilterSet):
    model = CommaSeparatedMultipleChoiceFilter(
        field_name="model", label="This can be a list of models comma separated, or a single model"
    )
    field = CommaSeparatedMultipleChoiceFilter(
        field_name="field",
        lookup_expr="iexact",
        label="This can be a list of fields comma separated, or a single field",
    )
    include_inactive = RestrictToTrueByDefaultFilter(
        field_name="is_active", label="Include inactive choices when 'true'"
    )

    class Meta:
        model = Choice
        fields = ["model", "field", "include_inactive"]
