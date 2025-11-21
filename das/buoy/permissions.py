from rest_framework.permissions import BasePermission

from observations.models import SubjectSource


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


class GearSourceProviderPermission(BasePermission):
    """
    Custom permission to check if the user making the request has access to the gear
    based on the SourceProvider's buoy_post_user_id matching the requesting user's ID.
    """

    def has_permission(self, request, view):
        # Get the subject_id from the URL kwargs
        if not request.user or not request.user.is_authenticated:
            return False

        # Superusers have all permissions
        if request.user.is_superuser:
            return True

        subject_id = view.kwargs.get("id")
        if not subject_id:
            return False

        # Check if any SubjectSource exists for this subject with a SourceProvider
        # that has buoy_post_user_id matching the requesting user's ID
        user_id_str = str(request.user.id)
        return SubjectSource.objects.filter(
            subject_id=subject_id, source__provider__additional__buoy_post_user_id=user_id_str
        ).exists()
