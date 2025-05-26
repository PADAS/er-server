from django_filters import rest_framework as filters
from django_filters.widgets import CSVWidget

from choices.models import Choice
from utils.drf_filters import RestrictToTrueByDefaultFilter

# NOTE:
# QueryArrayWidget instead of CSVWidget would allow us to support multiple formats of array input
# (e.g. ?field=1&field=2 or ?field=1,2)
# but it has a bug in version 23.5 so we use CSVWidget for now, django 4.2 is required to upgrade django-filter


class ChoicesFilter(filters.FilterSet):
    model = filters.ChoiceFilter(field_name="model", choices=Choice.MODEL_REF_CHOICES)
    field = filters.AllValuesMultipleFilter(field_name="field", widget=CSVWidget())
    include_inactive = RestrictToTrueByDefaultFilter(field_name="is_active")

    class Meta:
        model = Choice
        fields = ["model", "field", "include_inactive"]
