from django.conf import settings
from accounts.models import User
from activity.models import Event

notify_high_priority_event = getattr(
    settings, 'NOTIFY_HIGH_PRIORITY_EVENT', None)
notify_medium_priority_event = getattr(
    settings, 'NOTIFY_MEDIUM_PRIORITY_EVENT', None)
notify_low_priority_event = getattr(
    settings, 'NOTIFY_LOW_PRIORITY_EVENT', None)


class AlertUtils():
    @staticmethod
    def get_alert_users(priority):
        '''
        Identify Users who should be alerted for an event having the given priority.

        :param priority: an event priority or a list of event priority values.
        :return: A Users queryset.
        '''
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
