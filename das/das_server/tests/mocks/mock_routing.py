from activity.models import Event

from django.dispatch import receiver
from django.db.models.signals import post_save

import das_server.tasks as tasks


@receiver(post_save, sender=Event)
def mock_event_post_save(sender, instance, created, **kwargs):
    target = tasks.send_alerts_for_event
    target(str(instance.pk))


def mock_send_task(arg, args):
    if arg == 'das_server.tasks.send_user_event_notification':
        tasks.send_user_event_notification(args[0], args[1], None)
