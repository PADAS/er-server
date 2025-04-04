import django.contrib.auth
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError

from accounts.models import PermissionSet
from activity.models import AlertRule

notify_high_priority_event = getattr(settings, "NOTIFY_HIGH_PRIORITY_EVENT", None)
notify_medium_priority_event = getattr(settings, "NOTIFY_MEDIUM_PRIORITY_EVENT", None)
notify_low_priority_event = getattr(settings, "NOTIFY_LOW_PRIORITY_EVENT", None)


DEFAULT_ALERT_RULES_PERMISSIONSET_ID = "8a7e0e95-74f5-4012-aaa4-5fd7158a2cdb"
MIN_ALERT_PERMISSION_REQUIRED = "activity.view_alertrule"


def create_alerts_permissionset(tenant=None):
    """
    Adds the proper permission and permissionset that dentify the users who can
    view, create, update and delete alerts.
    """
    content_type = ContentType.objects.get_for_model(AlertRule)

    permissions = {
        "view_alertrule": "Can view alert rule",
        "add_alertrule": "Can add alert rule",
        "change_alertrule": "Can change alert rule",
        "delete_alertrule": "Can delete alert rule",
    }

    try:

        defaults = {"name": "Alert Rule Permissions"}
        permission_set, _ = PermissionSet.objects.get_or_create(
            id=DEFAULT_ALERT_RULES_PERMISSIONSET_ID,
            defaults=defaults,
            das_tenant=tenant,
        )
    except IntegrityError:
        defaults = {"name": "Alert Rule Permissionss"}
        permission_set, _ = PermissionSet.objects.get_or_create(
            id=DEFAULT_ALERT_RULES_PERMISSIONSET_ID,
            defaults=defaults,
            das_tenant=tenant,
        )

    for codename, name in permissions.items():
        perm, created = django.contrib.auth.models.Permission.objects.get_or_create(
            codename=codename, content_type=content_type, defaults={"name": name}
        )
        permission_set.permissions.add(perm)


def has_alerts_permissionset(user):
    """
    Check if user has `Alert Rule Permissions` permissionset
    """
    if user.is_anonymous:
        return False
    return user.is_superuser or user.has_perm(MIN_ALERT_PERMISSION_REQUIRED)


def has_patrol_view_permission(user):
    """Does the user have at least view patrol permissions

    Args:
        user ([type]): [description]

    Returns:
        [bool]: do they?
    """
    if user.is_anonymous:
        return False
    return user.has_perm("activity.view_patrol")
