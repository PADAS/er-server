from django.conf import settings
from accounts.models import PermissionSet, User
from activity.models import Event


def get_alert_users(priority):

    if not isinstance(priority, (list, set)):
        priority = [priority, ]

    priority_to_permissionset = {
        Event.PRI_URGENT: settings.NOTIFY_HIGH_PRIORITY_EVENT,
        Event.PRI_IMPORTANT: settings.NOTIFY_MEDIUM_PRIORITY_EVENT,
        Event.PRI_REFERENCE: settings.NOTIFY_LOW_PRIORITY_EVENT,
    }
    pset_names = [priority_to_permissionset.get(
        int(p), None) for p in priority]
    pset_names = set([v for v in pset_names if v is not None])
    return get_users_in_permission_sets(pset_names)


def get_users_in_permission_sets(permissionset_names):

    if not permissionset_names:
        return User.objects.none()

    permission_sets = PermissionSet.objects.filter(
        name__in=permissionset_names)
    return User.objects.filter(permission_sets__in=permission_sets).distinct().order_by('username')
