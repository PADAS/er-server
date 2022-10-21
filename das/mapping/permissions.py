from observations.permissions import StandardObjectPermissions
from rest_framework.permissions import SAFE_METHODS


class LayerObjectPermissions(StandardObjectPermissions):
    def has_permission(self, request, view):
        if self.authorised_view(request):
            return True
        return super(LayerObjectPermissions, self).has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if self.authorised_view(request):
            return True
        return super(LayerObjectPermissions, self).has_object_permission(request, view, obj)

    def authorised_view(self, request):
        # Allow viewing to all authenticated users
        if (request.method in SAFE_METHODS) and request.user and request.user.is_authenticated:
            return True
