from rest_framework.filters import BaseFilterBackend


class UserObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of users the current user can see.
    """

    perm_format = '%(app_label)s.view_%(model_name)s'

    def filter_queryset(self, request, queryset, view):
        user = request.user

        perms = ['accounts.change_user']
        if not user.has_perms(perms):
            queryset = queryset.filter(id=user.id)

        return queryset
