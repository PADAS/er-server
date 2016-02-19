import logging
from rest_framework.filters import BaseFilterBackend


class SubjectObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of subjects to what the user is allowed to view
    """

    perm_format = '%(app_label)s.view_%(model_name)s'

    def filter_queryset(self, request, queryset, view):
        user = request.user
        model_cls = queryset.model
        kwargs = {
            'app_label': model_cls._meta.app_label,
            'model_name': model_cls._meta.model_name
        }
        permission = self.perm_format % kwargs
        return guardian.shortcuts.get_objects_for_user(user, permission, queryset, **extra)