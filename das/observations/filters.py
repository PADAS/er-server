import logging
from rest_framework.filters import BaseFilterBackend
from observations.models import Subject
from utils.json import parse_bool


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
        user = request.user

        if user.is_superuser:
            return queryset

        root_ids = set()
        for group in queryset:
            result = self.first_descendant_with_permission(user, self.perms, group, is_visible)
            if result:
                root_ids = root_ids.union(result)
        return queryset.model.objects.filter(id__in=list(root_ids))

    def first_descendant_with_permission(self, user, perms, group, is_visible):
        ids = set()
        if not group:
            return None

        if is_visible:

            if user.has_any_perms(perms, group) and group.is_visible:
                """
                if the user has permissions to view the group, and if the group is
                visible return at that point. user has permissions to all 
                descendants
                """
                return {group.id}
        else:
            if user.has_any_perms(perms, group):
                return {group.id}

        for child in group.children.all():
            result = self.first_descendant_with_permission(user, perms, child, is_visible)
            if result:
                ids = ids.union(result)
        return ids if len(ids) > 0 else None





