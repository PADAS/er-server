from rest_framework.filters import BaseFilterBackend


class EventObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of events to what the user is allowed to view
    """

    view_perms = ('events.view_event',)

    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user.is_superuser:
            return queryset

        return queryset
