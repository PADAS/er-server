from django_filters import rest_framework as filters

from django.contrib.auth import get_user_model
from rest_framework.filters import BaseFilterBackend

from utils.drf_filters import RestrictToTrueByDefaultFilter

User = get_user_model()


class UserObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of users the current user can see.
    """

    perm_format = "%(app_label)s.view_%(model_name)s"

    def filter_queryset(self, request, queryset, view):
        user = request.user

        perms = ["accounts.change_user"]
        if not user.has_perms(perms):
            queryset = queryset.filter(id=user.id)

        return queryset


class UserFilterSet(filters.FilterSet):

    include_inactive = RestrictToTrueByDefaultFilter(
        field_name="is_active",
        label="Include inactive users when 'true'",
    )

    class Meta:
        model = User
        fields = [
            "include_inactive",
        ]
