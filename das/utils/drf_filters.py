from django_filters import rest_framework as filters


class RestrictToTrueByDefaultFilter(filters.BooleanFilter):
    """
    Custom BooleanFilter that defaults to filtering `field_name=True`.
    If the query parameter is explicitly set to `true`, no filtering is applied for this field.
    If the query parameter is missing or set to `false`, it filters for `field_name=True`.
    """

    def filter(self, qs, value):
        # If value is explicitly True, return the original queryset (show all)
        if value is True:
            return qs

        # Otherwise (value is None or False), filter by field_name=True
        return qs.filter(**{self.field_name: True})
