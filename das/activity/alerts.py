from django.conf import settings
from accounts.models import PermissionSet, User
from activity.models import Event


def get_alert_users(priority):

    if not isinstance(priority, (list, set)):
        priority = [priority, ]

    map = {Event.PRI_URGENT: settings.NOTIFY_HIGH_PRIORITY_EVENT,
           Event.PRI_IMPORTANT: settings.NOTIFY_MEDIUM_PRIORITY_EVENT,
           }
    pset_names = [map.get(int(p), settings.NOTIFY_LOW_PRIORITY_EVENT) for p in priority]
    pset_names = set([_ for _ in pset_names if _ is not None])
    return get_users_in_permission_sets(pset_names)

def get_users_in_permission_sets(names):
    permission_sets = PermissionSet.objects.filter(name__in=names)
    return User.objects.filter(permission_sets__in=permission_sets).distinct().order_by('username')
