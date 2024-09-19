from rest_framework.permissions import BasePermission


class UserCanExportDataPermission(BasePermission):

    def has_permission(self, request, view):
        permissions = ("activity.can_export_event_data", "activity.can_export_observation_data")
        return any(request.user.has_perm(perm) for perm in permissions)
