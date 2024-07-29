from rest_framework.permissions import BasePermission


class UserCanExportDataPermission(BasePermission):

    def has_permission(self, request, view):
        permissions = ("activity.view_export_event_data", "activity.view_export_observation_data")
        return any(request.user.has_perm(perm) for perm in permissions)
