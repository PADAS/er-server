import logging

from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from activity.models import Event, EventPhoto
from das_server import celery
from das_server import pubsub

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Event)
def event_post_save(sender, instance, created, **kwargs):

    logger.info("saved event {}, created={}".format(instance.pk, str(created)))
    transaction.on_commit(lambda: pubsub.publish(
        {'event_id': str(instance.pk)},
        'das.event.new' if created else 'das.event.update'))

    transaction.on_commit(lambda:
                          celery.app.send_task(
                              'activity.tasks.evaluate_alert_rules', args=(str(instance.id), created))
                          )


@receiver(post_delete, sender=Event)
def event_post_delete(sender, instance, **kwargs):
    logger.info("delete event {}".format(instance.pk))
    pubsub.publish(
        {'event_id': str(instance.pk)},
        'das.event.delete')


@receiver(post_save, sender=EventPhoto)
def warm_EventPhoto_image(sender, instance, **kwargs):
    transaction.on_commit(lambda:
                          celery.app.send_task(
                              'activity.tasks.warm_eventphotos', args=(str(instance.id),))
                          )


@receiver(post_delete, sender=EventPhoto)
def delete_EventPhoto_products(sender, instance, **kwargs):
    logger.info('delete sized images for EventPhoto.id: {}'.format(instance.pk))
    instance.image.delete_all_created_images()
