import logging

from django.db.models.signals import post_save
from django.db import transaction
from django.dispatch import receiver

from activity.models import Event
from das_server import pubsub


logger = logging.getLogger(__name__)


@receiver(post_save, sender=Event)
def event_post_save(sender, instance, created, **kwargs):
    logger.info("saved event {}, created={}".format(instance.pk, str(created)))
    transaction.on_commit(lambda: pubsub.publish(
        {'event_id': str(instance.pk)},
        'das.event.new' if created else 'das.event.update'))
