import uuid
from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.response import Response

from accounts.models.permissionset import PermissionSet
from accounts.utils import add_tenant_to_permission_codename
from activity.models import EventCategory
from activity.permissions import EventCategoryPermissions
from utils.categories import (
    ACTIONS,
    GEO_ACTIONS,
    make_eventcategory_permission_codename,
)


def get_er_user():
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(
        username="er_system",
        defaults={
            "first_name": "EarthRanger",
            "last_name": "System",
            "password": user_model.objects.make_random_password(),
        },
    )
    return user


def get_permitted_event_categories(request):
    permitted_categories = []

    for category in EventCategory.objects.filter(is_active=True):
        permission_name = "activity.{0}_{1}".format(category.value, EventCategoryPermissions.http_method_map["GET"])
        if request.user.has_perm(permission_name):
            permitted_categories.append(category)
    return permitted_categories


def return_409_response():
    status_msg = {"error_message": "The request could not be completed due to conflict with existing data."}
    return Response(status_msg, status=status.HTTP_409_CONFLICT)


def ensure_eventcategory_perms_exist(
    category: EventCategory, tenant_id: uuid.UUID, geographic_only: Optional[bool] = False
) -> None:
    """
    Ensures that the necessary permissions for an event category exist.

    Args:
        category (EventCategory): The event category for which to ensure permissions.
        tenant_id (uuid.UUID): The ID of the tenant.
        geographic_only (Optional[bool], optional): Flag indicating whether to create only geographic permissions.
            Defaults to False.

    Returns:
        None
    """
    content_type = ContentType.objects.get(app_label="activity", model="event")
    category_name = category.value

    if not geographic_only:
        permissionset_name = category.auto_permissionset_name
        permissionset, _ = PermissionSet.objects.get_or_create(name=permissionset_name)

        for action in ACTIONS:
            codename = make_eventcategory_permission_codename(category_name, action)
            codename = add_tenant_to_permission_codename(tenant_id=tenant_id, codename=codename)
            defaults = {"name": f"Can {action} {category_name} reports", "content_type": content_type}
            permission, _ = Permission.objects.get_or_create(codename=codename, defaults=defaults)

            permissionset.permissions.add(permission)

    permission_set_name = category.auto_geographic_permission_set_name
    geographic_permission_set, _ = PermissionSet.objects.get_or_create(name=permission_set_name)

    for action in GEO_ACTIONS:
        codename = make_eventcategory_permission_codename(category_name, action, True)
        codename = add_tenant_to_permission_codename(tenant_id=tenant_id, codename=codename)
        defaults = {
            "name": f"Can {action} {category_name} reports in a certain distance",
            "content_type": content_type,
        }
        permission, _ = Permission.objects.get_or_create(codename=codename, defaults=defaults)

        geographic_permission_set.permissions.add(permission)
