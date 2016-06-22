from rest_framework.permissions import DjangoObjectPermissions


class EventObjectPermissions(DjangoObjectPermissions):
    view_perms = ['%(app_label)s.view_event']

    perms_map = {
        'GET': view_perms,
        'OPTIONS': view_perms,
        'HEAD': view_perms,
        'POST': ['%(app_label)s.add_event'],
        'PUT': ['%(app_label)s.change_event'],
        'PATCH': ['%(app_label)s.change_event'],
        'DELETE': ['%(app_label)s.delete_event'],
    }
