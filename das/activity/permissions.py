from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions
from activity.models import EventType


class EventObjectPermissions(DjangoModelPermissions):
    create_perms = ['%(app_label)s.security_create,'
                    '%(app_label)s.standard_create,'
                    '%(app_label)s.logistics_create,']
    update_perms = ['%(app_label)s.security_update,'
                    '%(app_label)s.standard_update,'
                    '%(app_label)s.logistics_update,']
    read_perms = ['%(app_label)s.security_read,'
                  '%(app_label)s.standard_read,'
                  '%(app_label)s.logistics_read,']
    delete_perms = ['%(app_label)s.security_delete,'
                    '%(app_label)s.standard_delete,'
                    '%(app_label)s.logistics_delete',]

    perms_map = {
        'GET': read_perms,
        'OPTIONS': read_perms,
        'HEAD': read_perms,
        'POST': create_perms,
        'PUT': update_perms,
        'PATCH': update_perms,
        'DELETE': delete_perms,
    }

class EventCategoryPermissions(IsAuthenticated):

    http_method_map = {
        'GET': 'read',
        'OPTIONS': 'read',
        'HEAD': 'read',
        'POST': 'create',
        'PUT': 'update',
        'PATCH': 'update',
        'DELETE': 'delete',
    }

    def has_permission(self, request, view):
        # These methods are allowed for everyone
        if request.method in ['OPTIONS', 'HEAD']:
            super().has_permission(request, view)

        # If they're trying to make a new event, we need to check the type here
        if request.method == 'POST' and 'event_type' in request.data:
            event_type = EventType.objects.get_by_natural_key(request.data['event_type'])
            permission_name = 'activity.{0}_{1}'.format(
                event_type.category.value,
                'create'
            )
            return request.user.has_perm(permission_name)

        # Otherwise, let it through here and check at the object level later on
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):

        permission_name = 'activity.{0}_{1}'.format(
            obj.event_type.category.value,
            EventCategoryPermissions.http_method_map[request.method]
        )
        return request.user.has_perm(permission_name)
