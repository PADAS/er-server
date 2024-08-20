import hashlib
import logging
import re
from collections import defaultdict
from typing import Iterator, List, Optional
from uuid import UUID, uuid4

from django_multitenant.utils import get_current_tenant

from django.contrib import auth
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions

from activity.models import EventCategory
from choices.models import Choice
from utils.categories import (
    ACTIONS,
    GEO_ACTIONS,
    GEOGRAPHIC_DISTANCE_SUFIX,
    get_categories_and_geo_categories,
)
from utils.tenant import Tenant, lengthen_tenant_id, shorten_tenant_id

logger = logging.getLogger(__name__)
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


def add_tenant_to_permission_codename(tenant_id: UUID, codename: str) -> str:
    existing_tenant_id, existing_codename = parse_permission_codename(codename)
    if existing_tenant_id:
        if existing_tenant_id == tenant_id:
            return codename
        raise ValueError(f"codename already has different tenant_id. {tenant_id} != {existing_tenant_id}")
    short_id = shorten_tenant_id(tenant_id=tenant_id)
    return f"{short_id}:{codename}"


def parse_permission_codename(codename: str) -> tuple:
    """parse the tenant id from a codename

    Args:
        codename (str): Permission codename
    Returns:
        tuple(uuid.UUID, str): returns tuple(tenant_id or none, codename)

    """
    tenant_regex = r"^([A-Za-z0-9_+/-]{22})(?::)([\sA-Za-z0-9_-]+)"
    match = re.search(tenant_regex, codename)
    return (lengthen_tenant_id(match.group(1)), match.group(2)) if match else (None, codename)


def filter_permissions_by_tenant(tenant_settings: Tenant, queryset):
    """Apply filter to the Permissions queryset, to only return global and tenant specific permissions.

    Args:
        tenant_settings (Tenant): current tenant
        queryset (Permission.objects.all()): the Permissions queryset to filter on
    """
    tenant_id_reqex = r"^([A-Za-z0-9_+/-]{22})(?::)"

    short_id = shorten_tenant_id(tenant_id=tenant_settings.id)
    queryset = queryset.filter(Q(codename__startswith=short_id)) | queryset.exclude(Q(codename__regex=tenant_id_reqex))
    return queryset


def get_category_name_from_perm(perm_name: str) -> str:
    """
    It takes a permission name as a string and returns the name of the category that the permission belongs to

    :param perm_name: The name of the permission
    :type perm_name: str
    :return: The name of the category that the permission is for.
    """

    tenant_id, codename = parse_permission_codename(perm_name)

    # GEOGRAPHIC_DISTANCE_SUFFIX
    geo_perm_regex = r"(?:(?<=add_)|(?<=view_)|(?<=change_)|(?<=delete_))([\sA-Za-z0-9_-]+)(?=_gd)"

    result = re.search(geo_perm_regex, codename)
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
    elif GEOGRAPHIC_DISTANCE_SUFIX in perm and user:
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


def get_user_permissions(user):
    permissions = set()
    for backend in auth.get_backends():
        if hasattr(backend, "get_all_permissions"):
            permissions.update(backend.get_all_permissions(user))
    return permissions


def allowed_permissions(user_instance):
    """
    Get Permission from available backends.
    :param user_instance: The user who's permissions we're resolving.
    :return: a dictionary as content for our API.
    """
    permissions = get_user_permissions(user_instance)

    container = defaultdict(list)
    user_categories_and_geo_categories = get_categories_and_geo_categories(user_instance)
    event_categories = set(EventCategory.objects.values_list("value", flat=True))

    for permission in permissions:
        app_name, perm = permission.split(".", maxsplit=1)
        if perm.endswith(ACTIONS):
            resource, verb = perm.rsplit("_", maxsplit=1)
        else:
            try:
                verb, resource = perm.split("_", maxsplit=1)
            except ValueError:
                logger.warning(f"Permission {perm} is not in the expected format.")
                continue

        if ignore_permission(
            resource, app_name, permission, user_instance, user_categories_and_geo_categories, event_categories
        ):
            continue

        # The non-standard permissions are a bit messy, so limit to CRUD verbs.
        if verb in GEO_ACTIONS + tuple(method_map.keys()):
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
        user = get_object_or_404(User, pk=param)

    etag_string = generate_user_string_etag(user=user)
    return hashlib.md5(etag_string.encode("utf-8")).hexdigest()


def generate_user_field_data(user: User) -> Iterator[str]:
    fields = (
        "accepted_eula",
        "email",
        "first_name",
        "last_name",
        "pin",
        "username",
        "is_staff",
        "is_active",
        "additional",
    )
    for field in fields:
        yield str(getattr(user, field, None))

    if hasattr(user, "linked_subject"):
        yield str(user.linked_subject.id)
        yield str(user.linked_subject.updated_at)


def generate_user_string_etag(user: User, include_profiles: Optional[bool] = True) -> str:
    base_string = ":".join(generate_user_field_data(user))

    if include_profiles:
        profiles = user.act_as_profiles.all()
        for profile in profiles:
            base_string += ":" + generate_user_string_etag(user=profile, include_profiles=False)
    permission_sets = user.permission_sets.all()
    if permission_sets.exists():
        base_string += ":" + ":".join((str(permission_set.id) for permission_set in permission_sets))
    permissions = get_user_permissions(user)
    if permissions:
        base_string += ":" + ":".join((permission for permission in permissions))

    return base_string


def get_profiles(users: List[uuid4]):
    return (
        User.objects.annotate(profiles_count=Count("act_as_profiles"))
        .filter(is_staff=False, is_superuser=False, is_active=True)
        .exclude(Q(id__in=users) | Q(profiles_count__gt=0))
        .order_by("username")
    )


def get_profile_user(user_id: uuid4, profile_user_id: uuid4):
    try:
        # it looks odd but since act_as_profiles does not set "related_name" we have to use the default name which is "user"
        # to know if the user_id is the parent to the profile_user_id
        return User.objects.get(id=profile_user_id, user__id=user_id)
    except User.DoesNotExist:
        message = "User Profile %s not found in act_as_profiles list for user %s" % (profile_user_id, user_id)
        logger.info(message)
        raise exceptions.PermissionDenied(message)


def validate_email_available(value):
    if User.objects.filter(email=value).exists():
        raise ValidationError(
            _("This email address is already in use: '%(value)s'"),
            params={"value": value},
        )


def permission_get_by_natural_key(self, codename, app_label, model):
    """Support retrieving the Permission by our tenant annotated "activity.event" natural key
       This is used during a loaddata django command so that we don't need the
       data to have the tenant_id in the actual json data being loaded.

    Args:
        codename (str): _description_
        app_label (str): _description_
        model (str): _description_

    Returns:
        Permission: the permission
    """
    content_type = ContentType.objects.db_manager(self.db).get_by_natural_key(app_label, model)
    if app_label == "activity" and model == "event":
        das_tenant = get_current_tenant()
        tenant_codename = add_tenant_to_permission_codename(das_tenant.id, codename)
        try:
            return self.get(
                codename=tenant_codename,
                content_type=content_type,
            )
        except Permission.DoesNotExist:
            pass

    return self.get(
        codename=codename,
        content_type=content_type,
    )
