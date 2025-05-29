from django_filters import rest_framework as filters


class RestrictToTrueByDefaultFilter(filters.BooleanFilter):
    """
    Custom BooleanFilter that defaults to filtering `field_name=True`.
    If the query parameter is explicitly set to `true`, no filtering is applied for this field.
    If the query parameter is missing or set to `false`, it filters for `field_name=True`.
    This filter is only applied for GET requests.
    """

    def filter(self, qs, value):
        # If the method is not GET, do not apply the filter.
        request = getattr(self.parent, "request", None)
        if request and request.method != "GET":
            return qs

        # If value is explicitly True, return the original queryset (show all)
        if value is True:
            return qs

        # Otherwise (value is None or False), filter by field_name=True
        return qs.filter(**{self.field_name: True})
