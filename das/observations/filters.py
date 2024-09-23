from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import BaseFilterBackend

from observations.models import Subject
from observations.utils import VIEW_SUBJECT_PERMS, check_valid_date_string
from utils.json import parse_bool


class SubjectObjectPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of subjects to what the user is allowed to view
    """

    view_perms = ["observations.view_real_time", "observations.view_last_position", "observations.view_delayed"]

    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user.is_superuser:
            return queryset

        allowed = self.get_user_subjects(user)
        values = allowed.values_list("id", flat=True)
        queryset._hints["subjects_filtered"] = True
        return queryset.filter(id__in=values)

    def get_user_subjects(self, user):
        return Subject.objects.all().by_user_subjects(user)


def create_gp_filter_class(name, perms, model):
    return type(name, (GroupPermissionsFilter,), {"perms": perms, "model": model})


class GroupPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of groups to what the user is allowed to view
    """

    def filter_queryset(self, request, queryset, view):
        is_visible = parse_bool(request.GET.get("isvisible", True))
        include_hidden = parse_bool(request.GET.get("include_hidden", False))
        user = request.user

        root_ids = set()
        for group in queryset:
            result = self.first_descendant_with_permission(user, self.perms, group, is_visible, include_hidden)
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

        if user.has_any_perms(perms, group) and (
            (group.is_visible == view_visible) or (not group.is_visible and include_hidden)
        ):
            return {group.id}

        for child in group.children.all():
            result = self.first_descendant_with_permission(user, perms, child, view_visible, include_hidden)
            if result:
                ids = ids.union(result)
        return ids if len(ids) > 0 else None


class ObservationsFilter(BaseFilterBackend):
    """
    Filter the list of observations to what the user is allowed to view
    """

    def filter_queryset(self, request, queryset, view):
        query_params = request.query_params
        since = query_params.get("since")
        until = query_params.get("until")
        _, recorded_since = check_valid_date_string(since, "since")
        _, recorded_until = check_valid_date_string(until, "until")
        subject_id = query_params.get("subject_id")
        source_id = query_params.get("source_id")
        subjectsource_id = query_params.get("subjectsource_id")

        if len([id for id in (subject_id, source_id, subjectsource_id) if id]) > 1:
            raise ValueError("Can only specify one of: subject_id and source_id and subjectsource_id")

        filter_flag = 0
        filter_qparam = query_params.get("filter", 0)
        try:
            filter_flag = int(filter_qparam)
        except (ValueError, TypeError):
            filter_flag = None if filter_qparam == "null" else filter_flag

        if subject_id:
            try:
                subject = Subject.objects.select_related("subject_subtype__subject_type").get(pk=subject_id)
            except Subject.DoesNotExist:
                raise NotFound

            if not request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
                raise PermissionDenied

            queryset = queryset.get_subject_observations(
                subject, since=recorded_since, until=recorded_until, filter_flag=filter_flag
            )
        elif source_id:
            queryset = queryset.get_source_observations(
                source_id, since=recorded_since, until=recorded_until, filter_flag=filter_flag
            )
        elif subjectsource_id:
            queryset = queryset.get_subjectsource_observations(
                subjectsource_id, since=recorded_since, until=recorded_until, filter_flag=filter_flag
            )
        else:
            queryset = queryset.by_since_until(recorded_since, recorded_until)
            queryset = queryset.by_exclusion_flags(filter_flag)

        return queryset
