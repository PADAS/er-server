from rest_framework.permissions import (SAFE_METHODS, BasePermission,
                                        DjangoModelPermissions,
                                        DjangoObjectPermissions,
                                        IsAuthenticated)
from rest_framework import exceptions

from activity.models import EventType, Event, Patrol
from observations.views import UnauthorizedView


class EventObjectPermissions(DjangoModelPermissions):
    create_perms = ['%(app_label)s.security_create,'
                    '%(app_label)s.monitoring_create,'
                    '%(app_label)s.logistics_create,']
    update_perms = ['%(app_label)s.security_update,'
                    '%(app_label)s.monitoring_update,'
                    '%(app_label)s.logistics_update,']
    read_perms = ['%(app_label)s.security_read,'
                  '%(app_label)s.monitoring_read,'
                  '%(app_label)s.logistics_read,']
    delete_perms = ['%(app_label)s.security_delete,'
                    '%(app_label)s.monitoring_delete,'
                    '%(app_label)s.logistics_delete', ]

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
        user = request.user
        perms = {"POST": 'create', "PATCH": 'update',
                 "PUT": 'update', 'GET': 'read', "DELETE": 'delete'}
        for k, v in perms.items():
            if request.method == k and (
                    'event_type' in request.data or 'id' in view.kwargs):
                try:
                    event_type = EventType.objects.get_by_natural_key(
                        request.data['event_type']
                    ) if 'event_type' in request.data else \
                        Event.objects.get(id=view.kwargs["id"]).event_type
                    permission_name = 'activity.{0}_{1}'.format(
                        event_type.category.value, v
                    )
                    permitted = user.has_perm(permission_name)
                    if k == 'GET' and not permitted and user.is_authenticated:
                        return False
                    return permitted
                except EventType.DoesNotExist:
                    pass

        # Otherwise, let it through here and check at the object level later on
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):

        permission_name = 'activity.{0}_{1}'.format(
            obj.event_type.category.value,
            EventCategoryPermissions.http_method_map[request.method]
        )
        return request.user.has_perm(permission_name)


class EventNotesCategoryPermissions(EventCategoryPermissions):
    def has_permission(self, request, view):
        # These methods are allowed for everyone
        if request.method in ['OPTIONS', 'HEAD']:
            super().has_permission(request, view)

        # If they're trying to make a new note, we need to check the type here
        if request.method == 'POST':
            event = view.get_event()
            event_type = event.event_type
            permission_name = 'activity.{0}_{1}'.format(
                event_type.category.value,
                'create'
            )
            return request.user.has_perm(permission_name)

        return super().has_permission(request, view)


class IsOwnerOrReadOnly(BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the snippet.
        return obj.owner == request.user


class IsOwner(IsAuthenticated):
    """
    Custom permission to only allow owners of an object to see or edit its attributes.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in ('HEAD', 'OPTIONS',):
            return True

        # Write permissions are only allowed to the owner of the snippet.
        return obj.owner == request.user


class IsEventProviderOwnerPermission(BasePermission):

    relation_field = 'eventprovider'

    def has_object_permission(self, request, view, obj):
        if request.method in ('HEAD', 'OPTIONS'):
            return True

        eventprovider = getattr(obj, self.relation_field, None)
        return eventprovider is not None and eventprovider.owner == request.user


class PatrolObjectPermissions(DjangoObjectPermissions):
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

    def get_required_permissions(self, method, model_cls):
        """
        Given a model and an HTTP method, return the list of permission
        codes that the user is required to have.
        """
        model_cls = Patrol
        kwargs = {
            'app_label': model_cls._meta.app_label,
            'model_name': model_cls._meta.model_name
        }

        if method not in self.perms_map:
            raise exceptions.MethodNotAllowed(method)

        return [perm % kwargs for perm in self.perms_map[method]]




