from rest_framework.permissions import DjangoObjectPermissions, DjangoModelPermissions


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

class EventCategoryPermissions(DjangoObjectPermissions):

    http_method_map = {
        'GET': 'read',
        'OPTIONS': 'read',
        'HEAD': 'read',
        'POST': 'create',
        'PUT': 'update',
        'PATCH': 'update',
        'DELETE': 'delete',
    }

    def has_object_permission(self, request, view, obj):

        permission_name = 'activity.{0}_{1}'.format(
            obj.event_type.category.value,
            EventCategoryPermissions.http_method_map[request.method]
        )
        return request.user.has_perm(permission_name)
