import logging
from rest_framework.filters import BaseFilterBackend
from observations.models import Subject
from utils.json import parse_bool


class SubjectObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of subjects to what the user is allowed to view
    """

    view_perms = ['observations.view_real_time',
                  'observations.view_last_position', 'observations.view_delayed']

    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user.is_superuser:
            return queryset

        allowed = self.get_user_subjects(user)
        values = allowed.values_list('id', flat=True)
        queryset._hints['subjects_filtered'] = True
        return queryset.filter(id__in=values)

    def get_user_subjects(self, user):
        return Subject.objects.all().by_user_subjects(user)


def create_gp_filter_class(name, perms, model):
    return type(name, (GroupPermissionsFilter,), {'perms': perms, 'model': model})


class GroupPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of groups to what the user is allowed to view
    """

    def filter_queryset(self, request, queryset, view):
        is_visible = parse_bool(request.GET.get('isvisible', True))
        include_hidden = parse_bool(request.GET.get('include_hidden', False))
        user = request.user

        root_ids = set()
        for group in queryset:
            result = self.first_descendant_with_permission(
                user, self.perms, group, is_visible, include_hidden)
            if result:
                root_ids = root_ids.union(result)
        return queryset.model.objects.filter(id__in=list(root_ids))

    def first_descendant_with_permission(self, user, perms, group, view_visible, include_hidden):
        ids = set()
        if not group:
            return None

        # this is on the assumption that passing True in query params means
        # retrieve only visible subjectgroups and False means retrieve only
        # not visible subjectgroups

        if user.has_any_perms(perms, group) and ((group.is_visible == view_visible) or (not group.is_visible and include_hidden)):
            return {group.id}

        for child in group.children.all():
            result = self.first_descendant_with_permission(
                user, perms, child, view_visible, include_hidden)
            if result:
                ids = ids.union(result)
        return ids if len(ids) > 0 else None
