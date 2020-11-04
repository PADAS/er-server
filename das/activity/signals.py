import logging

from django.db import transaction
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver

from activity.models import Event, EventPhoto, Patrol, PatrolSegment, PatrolNote, PatrolFile
from das_server import celery, pubsub
from usercontent.tasks import imagefile_rendered

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


def send_event_thumbnail_update(sender, usercontent_id, **kwargs):
    for event in Event.objects.filter(file__usercontent_id=usercontent_id):
        pubsub.publish(
            {'event_id': str(event.id)}, 'das.event.update')


imagefile_rendered.connect(send_event_thumbnail_update)


# Patrol signals
@receiver(post_save, sender=Patrol)
def patrol_post_save(sender, instance, created, **kwargs):
    logger.info("saved patrol {}, created={}".format(instance.pk, str(created)))
    patrol_action = 'das.patrol.new' if created else 'das.patrol.update'
    transaction.on_commit(lambda: pubsub.publish({'patrol_id': str(instance.pk)}, patrol_action))


@receiver(post_delete, sender=Patrol)
def patrol_post_delete(sender, instance, **kwargs):
    logger.info("deleted patrol {}".format(instance.pk))
    pubsub.publish({'patrol_id': str(instance.pk)}, 'das.patrol.delete')


def verify_patrol_constituent_for_rt_messaging(instance):
    if instance.patrol:
        patrol_action = 'das.patrol.update'
        transaction.on_commit(lambda: pubsub.publish({'patrol_id': str(instance.patrol.pk)}, patrol_action))


@receiver(post_save, sender=PatrolSegment)
@receiver(post_save, sender=PatrolNote)
@receiver(post_save, sender=PatrolFile)
def patrol_item_post_save(sender, instance, created, **kwargs):
    logger.info(f"saved {sender._meta.verbose_name} {instance.pk}, created={str(created)}")
    verify_patrol_constituent_for_rt_messaging(sender, instance)


@receiver(post_delete, sender=PatrolSegment)
@receiver(post_delete, sender=PatrolNote)
@receiver(post_delete, sender=PatrolFile)
def patrol_item_post_delete(sender, instance, **kwargs):
    logger.info(f"deleted {sender._meta.verbose_name} {instance.pk}")
    verify_patrol_constituent_for_rt_messaging(instance)
