from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Polygon
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import BaseFilterBackend

from accounts.models.permissionset import PermissionSet
from observations.models import Subject
from observations.utils import VIEW_SUBJECT_PERMS, check_valid_date_string
from utils.gis import bbox_from_string
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
    Filter the list of groups to what the user is allowed to view.

    Optimized to avoid N+1 queries by:
    1. Fetching user's permission sets once
    2. Prefetching all group relationships and permission sets
    3. Building permission cache in memory
    4. Filtering groups efficiently without per-group queries
    """

    def filter_queryset(self, request, queryset, view):
        is_visible = parse_bool(request.GET.get("isvisible", True))
        include_hidden = parse_bool(request.GET.get("include_hidden", False))
        user = request.user

        if user.is_superuser:
            # Superusers can see everything, just apply visibility filters
            if not include_hidden:
                return queryset.filter(is_visible=is_visible)
            return queryset

        # Get user's permission set IDs once (includes ancestors)
        user_ps_ids = user.get_all_permission_sets(only_ids=True)

        # Prefetch all necessary data in bulk
        # This loads: groups, their permission_sets, parent relationships, and ancestors' permission_sets
        queryset = queryset.prefetch_related("permission_sets", "children", "_parents")

        # Convert to list to evaluate queryset once
        all_groups = list(queryset)

        # Build permission cache: which groups the user has permission to view
        groups_with_permission = self._build_permission_cache(all_groups, user_ps_ids, self.perms)

        # Find groups to return based on permissions and visibility
        root_ids = self._find_accessible_groups(all_groups, groups_with_permission, is_visible, include_hidden)

        return queryset.filter(id__in=list(root_ids))

    def _build_permission_cache(self, groups, user_ps_ids, required_perms):
        """
        Build a set of group IDs that the user has permission to view.
        Uses cached permission_sets data to avoid per-group queries.
        """
        # Get permission sets that grant the required permissions AND user has
        relevant_user_ps_ids = self._get_relevant_permission_sets(user_ps_ids, required_perms)
        if not relevant_user_ps_ids:
            return set()

        # Build maps from prefetched data
        group_ps_map = self._build_group_permission_map(groups)
        child_to_parents = self._build_parent_relationships(groups)

        # Check each group for permissions (including inherited from ancestors)
        return self._find_groups_with_permission(groups, group_ps_map, child_to_parents, relevant_user_ps_ids)

    def _get_relevant_permission_sets(self, user_ps_ids, required_perms):
        """Get permission set IDs that user has AND grant the required permissions."""

        # Get permission IDs matching requirements
        valid_perm_ids = set()
        for perm in required_perms:
            app_label, codename = perm.split(".")
            perm_qs = Permission.objects.filter(
                content_type__app_label=app_label, codename__endswith=codename  # Handle tenant-prefixed permissions
            )
            valid_perm_ids.update(perm_qs.values_list("id", flat=True))

        # Get permission sets with these permissions
        ps_with_required_perms = set(
            PermissionSet.objects.filter(permissions__id__in=valid_perm_ids).values_list("id", flat=True)
        )

        # Return intersection of user's permission sets and required ones
        return user_ps_ids & ps_with_required_perms

    def _build_group_permission_map(self, groups):
        """Build a map of group_id -> permission_set_ids from prefetched data."""
        group_ps_map = {}
        for group in groups:
            group_ps_map[group.id] = set(ps.id for ps in group.permission_sets.all())
        return group_ps_map

    def _build_parent_relationships(self, groups):
        """Build parent relationship map from prefetched data."""
        child_to_parents = {}
        for group in groups:
            child_to_parents[group.id] = [parent.id for parent in group._parents.all()]
        return child_to_parents

    def _get_ancestors_from_cache(self, group_id, child_to_parents):
        """Get all ancestor IDs for a group using cached parent relationships (BFS)."""
        ancestors = set()
        queue = child_to_parents.get(group_id, []).copy()
        visited = {group_id}

        while queue:
            parent_id = queue.pop(0)
            if parent_id not in visited:
                visited.add(parent_id)
                ancestors.add(parent_id)
                queue.extend(child_to_parents.get(parent_id, []))

        return ancestors

    def _find_groups_with_permission(self, groups, group_ps_map, child_to_parents, relevant_user_ps_ids):
        """Find groups where user has permission (directly or inherited from ancestors)."""
        groups_with_permission = set()

        for group in groups:
            # Get permission sets for this group and ancestors
            group_ps_ids = group_ps_map.get(group.id, set()).copy()

            ancestor_ids = self._get_ancestors_from_cache(group.id, child_to_parents)
            for ancestor_id in ancestor_ids:
                ancestor_ps_ids = group_ps_map.get(ancestor_id, set())
                group_ps_ids = group_ps_ids.union(ancestor_ps_ids)

            # Check if any permission sets match
            if group_ps_ids & relevant_user_ps_ids:
                groups_with_permission.add(group.id)

        return groups_with_permission

    def _find_accessible_groups(self, all_groups, groups_with_permission, is_visible, include_hidden):
        """
        Find which groups to return based on permissions and visibility.

        Returns groups where user has permission and visibility criteria are met,
        OR descendants where user has permission even if parent doesn't have permission.
        """
        root_ids = set()

        # Build a mapping of group -> children for efficient lookups
        children_map = {}

        for group in all_groups:
            children = list(group.children.all())
            children_map[group.id] = children

        for group in all_groups:
            result = self._first_descendant_with_permission(
                group, groups_with_permission, children_map, is_visible, include_hidden
            )
            if result:
                root_ids.update(result)

        return root_ids

    def _first_descendant_with_permission(
        self, group, groups_with_permission, children_map, view_visible, include_hidden
    ):
        """
        Recursively find descendants with permission.
        Uses pre-loaded data instead of making database queries.
        """
        ids = set()
        if not group:
            return None

        # Check if user has permission for this group
        has_permission = group.id in groups_with_permission

        # Check visibility criteria
        visibility_match = (group.is_visible == view_visible) or (not group.is_visible and include_hidden)

        if has_permission and visibility_match:
            return {group.id}

        # Check children
        for child in children_map.get(group.id, []):
            result = self._first_descendant_with_permission(
                child, groups_with_permission, children_map, view_visible, include_hidden
            )
            if result:
                ids.update(result)

        return ids if ids else None


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
        sourceprovider_id = query_params.get("sourceprovider_id")
        if bbox := query_params.get("bbox"):
            bbox = bbox_from_string(bbox)
        include_empty_location = parse_bool(query_params.get("include_empty_location", False))

        if len([id for id in (subject_id, source_id, subjectsource_id, sourceprovider_id) if id]) > 1:
            raise ValueError("Can only specify one of: subject_id, source_id, subjectsource_id, and sourceprovider_id")

        filter_flag = query_params.get("filter", 0)
        try:
            filter_flag = int(filter_flag)
        except (ValueError, TypeError):
            filter_flag = None if filter_flag == "null" else 0

        if subject_id:
            try:
                subject = Subject.objects.select_related("subject_subtype__subject_type").get(pk=subject_id)
            except Subject.DoesNotExist:
                raise NotFound

            if not request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
                raise PermissionDenied

            # Check if cursor pagination is being used
            use_cursor = parse_bool(request.query_params.get("use_cursor", False))

            queryset = queryset.get_subject_observations_partitioned(
                subject,
                since=recorded_since,
                until=recorded_until,
                filter_flag=filter_flag,
                bbox=bbox,
                avoid_unions=use_cursor,
                include_empty_location=include_empty_location,
            )
        elif source_id:
            queryset = queryset.get_source_observations(
                source_id,
                since=recorded_since,
                until=recorded_until,
                filter_flag=filter_flag,
                bbox=bbox,
                include_empty_location=include_empty_location,
            )
        elif sourceprovider_id:
            queryset = queryset.get_sourceprovider_observations(
                sourceprovider_id,
                since=recorded_since,
                until=recorded_until,
                filter_flag=filter_flag,
                bbox=bbox,
                include_empty_location=include_empty_location,
            )
        elif subjectsource_id:
            queryset = queryset.get_subjectsource_observations(
                subjectsource_id,
                since=recorded_since,
                until=recorded_until,
                filter_flag=filter_flag,
                bbox=bbox,
                include_empty_location=include_empty_location,
            )
        else:
            queryset = queryset.by_since_until(recorded_since, recorded_until)
            queryset = queryset.by_exclusion_flags(filter_flag, include_empty_location=include_empty_location)
            if bbox:
                geometry = Polygon.from_bbox(bbox)
                queryset = queryset.filter(location__within=geometry)

        return queryset
