from rest_framework.permissions import BasePermission


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

    This permission implements both has_permission() for early request-level checks
    and has_object_permission() for object-level checks that align with queryset filtering.
    """

    def has_permission(self, request, view):
        # Basic authentication check
        if not request.user.is_authenticated:
            return False

        # Superusers have all permissions
        if request.user.is_superuser:
            return True

        # For request-level check, we allow the request to proceed if subject_id is present
        # The actual permission check happens in has_object_permission()
        subject_id = view.kwargs.get("id")
        if not subject_id:
            return False

        return True

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permission based on the SubjectSource object.
        This ensures permission logic aligns with queryset filtering.
        """
        # Superusers have all permissions
        if request.user.is_superuser:
            return True

        # obj is a SubjectSource instance from get_object()
        # Check if this specific SubjectSource has a SourceProvider with matching buoy_post_user_id
        if not hasattr(obj, "source") or not obj.source:
            return False

        provider = obj.source.provider
        if not provider or not hasattr(provider, "additional") or not provider.additional:
            return False

        user_id_str = str(request.user.id)
        buoy_post_user_id = provider.additional.get("buoy_post_user_id")

        return buoy_post_user_id == user_id_str
