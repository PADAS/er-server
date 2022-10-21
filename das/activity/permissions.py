from django.conf import settings
from django.db import ProgrammingError
from rest_framework import exceptions
from rest_framework.permissions import (SAFE_METHODS, BasePermission,
                                        DjangoModelPermissions,
                                        DjangoObjectPermissions,
                                        IsAuthenticated)

from activity.models import Event, EventCategory, EventType, Patrol, PatrolType
from observations.models import Subject
from observations.utils import get_distance_points, is_banned
from utils.gis import convert_to_point


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
                    'event_type' in request.data or 'id' in view.kwargs or 'eventtype_id' in view.kwargs):
                try:
                    if "event_type" in request.data:
                        event_type = EventType.objects.get_by_natural_key(
                            request.data['event_type'])
                    elif "eventtype_id" in view.kwargs:
                        event_type = EventType.objects.get(
                            id=view.kwargs['eventtype_id'])
                    else:
                        event_type = Event.objects.get(
                            id=view.kwargs["id"]).event_type

                    permission_name = 'activity.{0}_{1}'.format(
                        event_type.category.value, v)

                    permitted = user.has_perm(permission_name)
                    if k == 'GET' and not permitted and user.is_authenticated:
                        return False
                    return permitted
                except EventType.DoesNotExist:
                    pass

        # Otherwise, let it through here and check at the object level later on
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        permission_fmt = 'activity.{0}_{1}'
        is_subject = True
        if isinstance(obj, EventCategory):
            value = obj.value
        elif isinstance(obj, EventType):
            value = obj.category.value
        else:
            try:
                value = obj.event_type.category.value
            except AttributeError as exc:
                raise ProgrammingError(exc)

            else:
                event_subjects = obj.related_subjects.values_list(
                    'id', flat=True)
                if event_subjects:
                    user_subjects = Subject.objects.by_user_subjects(
                        request.user).values_list('id', flat=True)
                    is_subject = set(event_subjects) <= set(user_subjects)

        permission_name = permission_fmt.format(
            value, EventCategoryPermissions.http_method_map[request.method])
        return request.user.has_perm(permission_name) and is_subject


class EventCategoryObjectPermissions(DjangoObjectPermissions):
    def has_object_permission(self, request, view, obj):
        permission_name = 'activity.{0}_{1}'.format(
            obj.value, EventCategoryPermissions.http_method_map[request.method])
        return request.user.has_perm(permission_name)


class EventCategoryGeographicPermission(EventCategoryPermissions):
    http_method_map = {
        "GET": "view",
        "OPTIONS": "view",
        "HEAD": "view",
        "POST": "add",
        "PUT": "change",
        "PATCH": "change",
        "DELETE": "delete"
    }

    def has_permission(self, request, view):
        has_perm = super().has_permission(request, view)
        if not has_perm:
            if request.method in ["OPTIONS", "HEAD"]:
                super().has_permission(request, view)
            user = request.user
            perms = {
                "POST": "create",
                "PATCH": "update",
                "PUT": "update",
                "GET": "read",
                "DELETE": "delete",
            }
            for key, value in perms.items():
                if request.method == key and (
                        "event_type" in request.data
                        or "id" in view.kwargs
                        or "eventtype_id" in view.kwargs
                ):
                    try:
                        if "event_type" in request.data:
                            event_type = EventType.objects.get_by_natural_key(
                                request.data["event_type"]
                            )
                        elif "eventtype_id" in view.kwargs:
                            event_type = EventType.objects.get(
                                id=view.kwargs["eventtype_id"]
                            )
                        else:
                            event_type = Event.objects.get(
                                id=view.kwargs["id"]).event_type
                        geo_perm_name = (
                            f"activity.{self.http_method_map[request.method]}_"
                            f"{event_type.category.value}_geographic_distance"
                        ).lower()
                        permitted = user.has_perm(geo_perm_name) and not is_banned(
                            request.user
                        )
                        if key == "GET" and not permitted and user.is_authenticated:
                            return False
                        elif key == "POST":
                            obj_location = convert_to_point(
                                request.data['location'])
                            location = request.GET.get("location")
                            if not location:
                                return False
                            user_location = convert_to_point(
                                location=request.GET.get("location"))
                            points = [
                                {"position": {"latitude": point.y, "longitude": point.x}}
                                for point in (user_location, obj_location)
                            ]
                            distance = get_distance_points(points)
                            return distance.m <= settings.GEO_PERMISSION_RADIUS_METERS
                        return permitted
                    except EventType.DoesNotExist:
                        pass
        return has_perm

    def has_object_permission(self, request, view, obj):
        has_perm = super().has_object_permission(request, view, obj)
        if not has_perm:
            permission_name = (
                f"activity.{self.http_method_map[request.method]}_"
                f"{obj.event_type.category.value}_geographic_distance"
            )

            if request.user.is_superuser or not request.user.has_perm(permission_name):
                return super().has_object_permission(request, view, obj)

            location = request.GET.get("location")
            if not location:
                return False

            point = convert_to_point(location)
            if (
                    obj.location
                    and request.user.has_perm(permission_name)
                    and not is_banned(request.user)
            ):
                points = [
                    {"position": {"latitude": point.y, "longitude": point.x}}
                    for point in (point, obj.location)
                ]
                distance = get_distance_points(points)
                return distance.m <= settings.GEO_PERMISSION_RADIUS_METERS
            return False
        return has_perm


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


class EventNotesCategoryGeographicPermissions(EventNotesCategoryPermissions):
    http_method_map = {
        "GET": "view",
        "OPTIONS": "view",
        "HEAD": "view",
        "POST": "add",
        "PUT": "change",
        "PATCH": "change",
        "DELETE": "delete",
    }

    def has_permission(self, request, view):
        has_perm = super().has_permission(request, view)
        if not has_perm:
            if request.method == "POST":
                event = view.get_event()
                event_type = event.event_type

                geo_perm_name = (
                    f"activity.{self.http_method_map[request.method]}_"
                    f"{event_type.category.value}_geographic_distance"
                )
                return request.user.has_perm(geo_perm_name)
        return has_perm


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

    def has_object_permission(self, request, view, obj):
        model_cls = Patrol
        user = request.user

        perms = self.get_required_object_permissions(request.method, model_cls)

        if not user.has_perms(perms, obj):
            # If the user does not have permissions we need to determine if
            # they have read permissions to see 403, or not, and simply raise
            # PermissionDenied.
            if request.method in SAFE_METHODS:
                raise exceptions.PermissionDenied

            read_perms = self.get_required_object_permissions('GET', model_cls)
            if not user.has_perms(read_perms, obj):
                raise exceptions.PermissionDenied
            return False
        if isinstance(obj, Patrol):
            return self.has_tracked_subject_permission(obj, user)
        return True

    def has_tracked_subject_permission(self, obj, user):
        patrol_segments = obj.patrol_segments.last()
        if patrol_segments and self._is_content_type_subject(patrol_segments.leader_content_type):
            return Subject.objects.filter(id__in=[patrol_segments.leader_id]).by_user_subjects(user).exists()
        return True

    def _is_content_type_subject(self, content_type):
        return content_type and content_type.app_label == "observations" and content_type.model == "subject"


class PatrolTypePermissions(DjangoModelPermissions):
    """Verify the api caller has the appropriate PatrolType permissions.
    Specifically a caller can View a patrol type if they have view_patroltype
    or view_patrol. Otherwise for the other operations, they must have patroltype
    permissions
    """
    view_perms = ['%(app_label)s.view_%(model_name)s',
                  '%(app_label)s.view_%(patrol_model_name)s']

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
        model_cls = PatrolType
        kwargs = {
            'app_label': model_cls._meta.app_label,
            'model_name': model_cls._meta.model_name,
            'patrol_model_name': Patrol._meta.model_name

        }

        if method not in self.perms_map:
            raise exceptions.MethodNotAllowed(method)

        return [perm % kwargs for perm in self.perms_map[method]]

    def has_permission(self, request, view):
        model_cls = Patrol
        user = request.user

        perms = self.get_required_permissions(request.method, model_cls)

        # for this, it's any permission, not all
        if not user.has_any_perms(perms):
            # If the user does not have permissions we need to determine if
            # they have read permissions to see 403, or not, and simply raise
            # PermissionDenied.
            if request.method in SAFE_METHODS:
                raise exceptions.PermissionDenied

            read_perms = self.get_required_permissions('GET', model_cls)
            if not user.has_any_perms(read_perms):
                raise exceptions.PermissionDenied
            return False
        return True


class StandardModelPermissions(DjangoModelPermissions):
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


class StandardObjectPermissions(DjangoObjectPermissions):
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
