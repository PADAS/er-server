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
