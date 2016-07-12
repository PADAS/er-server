import logging
from rest_framework.filters import BaseFilterBackend
from observations.models import Subject

class SubjectObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of subjects to what the user is allowed to view
    """

    view_perms = ['observations.view_real_time', 'observations.view_last_position', 'observations.view_delayed']

    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user.is_superuser:
            return queryset

        allowed = self.get_user_subjects(user)
        values = allowed.values_list('id', flat=True)
        return queryset.filter(id__in=values)

    def get_user_subjects(self, user):
        return Subject.objects.by_user_subjects(user)


class GroupPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of groups to what the user is allowed to view
    """
    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user.is_superuser:
            return queryset

        allowed = self.get_user_subjects(user)
        values = allowed.values_list('id', flat=True)
        return queryset.filter(id__in=values)

