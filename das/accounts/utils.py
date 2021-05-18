from collections import defaultdict
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.contrib import auth


def patrol_mgmt_permissions(modelnames=None):
    modelnames = modelnames or ('patrol', 'patroltype', 'patrolsegment', 'patrolnote',
                                'patrolfile', 'patrolsegmentmembership')

    content_types = [ContentType.objects.get(app_label='activity', model=modelname) for modelname in modelnames]
    return Permission.objects.filter(content_type__in=content_types)


def ignore_permission(resource, app_name):
    """state the condition for permission to be ignored or not."""
    if resource in ['message']:
        return False
    elif any([resource in {'patrolsegment', 'patrolnote', 'patrolfile', 'patrolsegmentmembership'}, app_name not in {'activity'}]):
        return True
    else:
        return False


def allowed_permissions(user_instance):
    '''
    Get Permission from available backends.
    :param user_instance: The user who's permissions we're resolving.
    :return: a dictionary as content for our API.
    '''
    permissions = set()
    for backend in auth.get_backends():
        if hasattr(backend, "get_all_permissions"):
            permissions.update(backend.get_all_permissions(user_instance))

    container = defaultdict(list)
    for permission in permissions:
        app_name, perm = permission.split('.', maxsplit=1)
        verb, resource = perm.split('_', maxsplit=1)

        if ignore_permission(resource, app_name):
            continue

        # The non-standard permissions are a bit messy, so limit to CRUD verbs.
        if verb in ('add', 'change', 'view', 'delete'):
            container[resource].append(verb)

    return container

