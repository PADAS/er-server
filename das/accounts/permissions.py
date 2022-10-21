from rest_framework.permissions import DjangoObjectPermissions, BasePermission


class UserObjectPermissions(DjangoObjectPermissions):
    """
    Does the user have permission to edit this user record
    """

    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': ['%(app_label)s.view_%(model_name)s'],
        'HEAD': ['%(app_label)s.view_%(model_name)s'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }

    def has_object_permission(self, request, view, obj):
        if obj == request.user:
            return True
        return super(DjangoObjectPermissions, self).has_object_permission(request, view, obj)


class EulaPermission(BasePermission):
    def has_permission(self, request, view):
        user_id = request.data.get("user")
        if str(request.user.id) != user_id:
            return False
        return True
