from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import BasePermission

from observations.models import SubjectGroup


class GearLocationPermission(BasePermission):
    """
    Custom permission to check if user can view gears regardless of location
    or if lat/lon parameters are provided for location-based filtering.
    """

    def has_permission(self, request, view):
        if request.method == "GET":
            lat = request.query_params.get("lat")
            lon = request.query_params.get("lon")

            if lat or lon:
                return True

            return request.user.has_perm("observations.can_view_gear_regardless_location")

        return True


class GearSubjectPermission(BasePermission):
    """
    Custom permission to check if user can add/change subjects for POST operations.
    """

    def has_permission(self, request, view):
        if request.method == "POST":
            return request.user.has_perm("observations.add_subject")

        return True


class HasManufacturerSubjectGroupPermission(BasePermission):
    """
    Custom permission to check if the user making the request has access to the gear.

    For GET requests (viewing gears):
    - This checks if the gear's SubjectGroup is accessible to the user based on their permissions.
    - This ensures users can only view gears from SubjectGroups they have access to.

    This permission is NOT used for POST requests, as SubjectGroup validation
    is handled in the serializer and service layer.
    """

    def has_permission(self, request, view):
        # Basic authentication check
        if not request.user.is_authenticated:
            return False

        # Superusers have all permissions
        if request.user.is_superuser:
            return True

        # For GET requests, we allow the request to proceed to has_object_permission
        # where we'll check SubjectGroup membership
        if request.method == "GET":
            subject_id = view.kwargs.get("id")
            if not subject_id:
                # This permission class is designed for detail views only (retrieve operations).
                # It should NOT be used with list views as it requires a specific object ID
                # to perform SubjectGroup-based access control checks.
                raise ImproperlyConfigured(
                    "HasManufacturerSubjectGroupPermission should not be used with list views. "
                    "This permission requires an 'id' in the URL kwargs to check object-level "
                    "SubjectGroup membership. Use a different permission class for list operations."
                )
            return True

        # For other methods (POST, PUT, DELETE), allow if authenticated
        # (additional validation happens in the serializer/service)
        return True

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permission based on SubjectGroup membership.
        This ensures users can only view gears from SubjectGroups they have access to.
        """
        # Superusers have all permissions
        if request.user.is_superuser:
            return True

        # obj is a SubjectSource instance from get_object()
        if not hasattr(obj, "subject") or not obj.subject:
            return False

        subject = obj.subject

        # Get user's allowed SubjectGroups based on their permission sets
        user_permission_sets = (
            request.user.get_all_permission_sets() if hasattr(request.user, "get_all_permission_sets") else []
        )

        # If user has no permission sets, they can't access any SubjectGroups
        if not user_permission_sets:
            return False

        allowed_subject_groups = SubjectGroup.objects.filter(permission_sets__in=user_permission_sets)

        # Check if the subject belongs to any of the user's allowed SubjectGroups
        # Including descendants of allowed groups
        # Use values_list to fetch only IDs, avoiding N+1 queries
        effective_subject_group_ids = set()
        for subject_group in allowed_subject_groups:
            effective_subject_group_ids.add(subject_group.id)
            # get_descendants() returns a generator, convert to list then extract IDs
            descendants = list(subject_group.get_descendants())
            effective_subject_group_ids.update(desc.id for desc in descendants)

        # Check if subject is in any of the allowed groups
        # Use values_list to get IDs only, avoiding loading full SubjectGroup objects
        subject_group_ids = set(subject.groups.values_list("id", flat=True))
        return bool(subject_group_ids.intersection(effective_subject_group_ids))
