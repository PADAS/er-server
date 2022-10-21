from rest_framework.permissions import DjangoModelPermissions


class ModelPermissions(DjangoModelPermissions):
    view_perms = ['%(app_label)s.view_%(model_name)s']

    perms_map = {
        'GET': view_perms,
        'OPTIONS': view_perms,
        'HEAD': view_perms,
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }
