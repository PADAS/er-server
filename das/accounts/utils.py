import re
from collections import defaultdict

from django.contrib import auth
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from activity.models import EventCategory
from utils.categories import get_categories_and_geo_categories


def patrol_mgmt_permissions(modelnames=None):
    modelnames = modelnames or ('patrol', 'patroltype', 'patrolsegment', 'patrolnote',
                                'patrolfile', 'patrolsegmentmembership')

    content_types = [ContentType.objects.get(
        app_label='activity', model=modelname) for modelname in modelnames]
    return Permission.objects.filter(content_type__in=content_types)


def get_category_name_from_perm(perm_name: str) -> str:
    """
    It takes a permission name as a string and returns the name of the category that the permission belongs to

    :param perm_name: The name of the permission
    :type perm_name: str
    :return: The name of the category that the permission is for.
    """

    geo_perm_regex = r"(?:(?<=add_)|(?<=view_)|(?<=change_)|(?<=delete_))([\sa-z0-9_-]+)(?=_geographic_distance)"

    result = re.search(geo_perm_regex, perm_name)
    return result.group() if result else result


def ignore_permission(resource, app_name, perm=None, user=None):
    """state the condition for permission to be ignored or not."""

    geo_category_name = get_category_name_from_perm(perm)

    if resource in ["message"]:
        return False
    elif any(
            [
                resource
                in {"patrolsegment", "patrolnote", "patrolfile", "patrolsegmentmembership"},
                app_name not in {"activity"},
            ]
    ):
        return True
    elif "geographic" in perm and user:
        results = get_categories_and_geo_categories(user)

        if not EventCategory.objects.filter(value=geo_category_name).exists():
            return True

        for category in results["categories"]:
            if category in perm:
                return True
        return False
    else:
        return False


method_map = {
    "read": "view",
    "create": "add",
    "update": "change",
    "delete": "delete",
}


def allowed_permissions(user_instance):
    """
    Get Permission from available backends.
    :param user_instance: The user who's permissions we're resolving.
    :return: a dictionary as content for our API.
    """
    permissions = set()
    for backend in auth.get_backends():
        if hasattr(backend, "get_all_permissions"):
            permissions.update(backend.get_all_permissions(user_instance))

    container = defaultdict(list)
    for permission in permissions:
        app_name, perm = permission.split(".", maxsplit=1)
        if perm.endswith(("create", "read", "update", "delete")):
            resource, verb = perm.rsplit("_", maxsplit=1)
        else:
            verb, resource = perm.split("_", maxsplit=1)

        if ignore_permission(resource, app_name, permission, user_instance):
            continue

        # The non-standard permissions are a bit messy, so limit to CRUD verbs.
        if verb in ("add", "change", "view", "delete") + tuple(method_map.keys()):
            if verb in method_map:
                verb = method_map[verb]
            container[resource].append(verb)

    return container
