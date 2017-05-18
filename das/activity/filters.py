from rest_framework.filters import BaseFilterBackend


class EventObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of events to what the user is allowed to view
    """

    #
    # TODO: Update this filter to use new category permisisons
    #

    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user.is_superuser:
            return queryset

        return queryset
