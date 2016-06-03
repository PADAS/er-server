from rest_framework.permissions import DjangoObjectPermissions


class EventObjectPermissions(DjangoObjectPermissions):
    view_perms = ['%(app_label)s.view_events']

    perms_map = {
        'GET': view_perms,
        'OPTIONS': view_perms,
        'HEAD': view_perms,
        'POST': ['%(app_label)s.add_events'],
        'PUT': ['%(app_label)s.change_events'],
        'PATCH': ['%(app_label)s.change_events'],
        'DELETE': ['%(app_label)s.delete_events'],
    }
