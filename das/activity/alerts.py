import django.contrib.auth
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from accounts.models import PermissionSet, User
from activity.models import Event

notify_high_priority_event = getattr(
    settings, 'NOTIFY_HIGH_PRIORITY_EVENT', None)
notify_medium_priority_event = getattr(
    settings, 'NOTIFY_MEDIUM_PRIORITY_EVENT', None)
notify_low_priority_event = getattr(
    settings, 'NOTIFY_LOW_PRIORITY_EVENT', None)


def get_alert_users(priority):
    """
    Identify Users who should be alerted for an event having the given priority.

    :param priority: an event priority or a list of event priority values.
    :return: A Users queryset.
    """
    if not isinstance(priority, (list, set)):
        priority = [priority, ]

    priority_to_permissionset = {
        Event.PRI_URGENT: notify_high_priority_event,
        Event.PRI_IMPORTANT: notify_medium_priority_event,
        Event.PRI_REFERENCE: notify_low_priority_event,
    }
    permissionset_names = [priority_to_permissionset.get(
        int(p), None) for p in priority]
    permissionset_names = set(
        [v for v in permissionset_names if v is not None])

    # Short-circuit if we have no permission sets to filter by.
    if not permissionset_names:
        return User.objects.none()

    return User.objects.filter(permission_sets__name__in=permissionset_names,
                               is_email_alert=True,
                               is_active=True
                               ).distinct().order_by('username')


def create_alerts_permissionset():
    '''
    Adds the proper permission and permissionset that dentify the users who can
    view, create, update and delete alerts.
    '''
    User = django.contrib.auth.get_user_model()
    content_type = ContentType.objects.get_for_model(User)

    permissions = {
        "read_alertrule": "Can view alert rule",
        "add_alertrule": "Can add alert",
        "change_alertrule": "Can change alert rule",
        "delete_alertrule": "Can delete alert rule"
    }

    permission_set = PermissionSet.objects.create(
                name='Alert Rule Permissions')

    for codename, name in permissions.items():
        perm, created = django.contrib.auth.models.Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            name=name
        )
        permission_set.permissions.add(perm)


def has_alerts_permissionset(user):
    '''
    Check if user has `Alert Rule Permissions` permissionset
    '''
    return "Alert Rule Permissions" in [
                permission.name for permission in
                user.get_all_permission_sets()]
