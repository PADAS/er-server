from rest_framework.permissions import AllowAny, DjangoObjectPermissions, DjangoModelPermissions
from rest_framework.filters import DjangoObjectPermissionsFilter


class SubjectObjectPermissions(DjangoObjectPermissions):
    view_perms = ['%(app_label)s.view_real_time', '%(app_label)s.view_last_position', '%(app_label)s.view_delayed']

    perms_map = {
        'GET': view_perms,
        'OPTIONS': view_perms,
        'HEAD': view_perms,
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }
