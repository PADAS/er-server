import hashlib
import re
from collections import defaultdict
from typing import List, Optional
from uuid import uuid4

from django.contrib import auth
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q

from activity.models import EventCategory
from choices.models import Choice
from utils.categories import get_categories_and_geo_categories

User = get_user_model()


def patrol_mgmt_permissions(modelnames=None):
    modelnames = modelnames or (
        "patrol",
        "patroltype",
        "patrolsegment",
        "patrolnote",
        "patrolfile",
        "patrolsegmentmembership",
    )

    content_types = [ContentType.objects.get(app_label="activity", model=modelname) for modelname in modelnames]
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


def ignore_permission(
    resource, app_name, perm=None, user=None, user_categories_and_geo_categories=None, event_categories=None
):
    """state the condition for permission to be ignored or not."""

    geo_category_name = get_category_name_from_perm(perm)

    if resource in ["message"]:
        return False
    elif any(
        [
            resource in {"patrolsegment", "patrolnote", "patrolfile", "patrolsegmentmembership"},
            app_name not in {"activity"},
        ]
    ):
        return True
    elif "geographic" in perm and user:
        if geo_category_name not in event_categories:
            return True

        for category in user_categories_and_geo_categories["categories"]:
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
    user_categories_and_geo_categories = get_categories_and_geo_categories(user_instance)
    event_categories = set(EventCategory.objects.values_list("value", flat=True))

    for permission in permissions:
        app_name, perm = permission.split(".", maxsplit=1)
        if perm.endswith(("create", "read", "update", "delete")):
            resource, verb = perm.rsplit("_", maxsplit=1)
        else:
            verb, resource = perm.split("_", maxsplit=1)

        if ignore_permission(
            resource, app_name, permission, user_instance, user_categories_and_geo_categories, event_categories
        ):
            continue

        # The non-standard permissions are a bit messy, so limit to CRUD verbs.
        if verb in ("add", "change", "view", "delete") + tuple(method_map.keys()):
            if verb in method_map:
                verb = method_map[verb]
            container[resource].append(verb)

    return container


def fetch_tech_choices():
    tech_choices = Choice.objects.filter(model="accounts.user.User", field="tech").order_by("ordernum")
    return tuple((obj.value, obj.display) for obj in tech_choices)


def fetch_organization_choices():
    organization_choices = {"": ""}
    for organization in Choice.objects.filter(model="accounts.user.User", field="organization").order_by("ordernum"):
        organization_choices[organization.value] = organization.display
    return tuple([(key, value) for key, value in organization_choices.items()])


def get_user_etag(request, *args, **kwargs) -> str:
    param = kwargs["id"]
    user = request.user
    if param != "me":
        user = User.objects.get(id=param)

    etag_string = generate_user_string_etag(user=user)
    return hashlib.md5(etag_string.encode("utf-8")).hexdigest()


def generate_user_string_etag(user: User, include_profiles: Optional[bool] = True) -> str:
    fields = ("accepted_eula", "email", "first_name", "last_name", "pin", "username")
    base_string = ":".join((str(getattr(user, field)) for field in fields))
    if include_profiles:
        profiles = user.act_as_profiles.all()
        for profile in profiles:
            base_string += ":" + generate_user_string_etag(user=profile, include_profiles=False)
    permissions = user.permission_sets.all()
    if permissions.exists():
        base_string += ":" + ":".join((str(permission.id) for permission in permissions))
    return base_string


def get_profiles(users: List[uuid4]):
    return (
        User.objects.annotate(profiles_count=Count("act_as_profiles"))
        .filter(is_staff=False, is_active=True)
        .exclude(Q(id__in=users) | Q(profiles_count__gt=0))
        .order_by("username")
    )
