import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import GlobalForestWatchSubscription
from .gfwservice import create_subscription, update_subscription, delete_subscription

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=GlobalForestWatchSubscription)
def subscription_pre_save(sender, instance, **kwargs):
    logger.info('PRE_SAVE')
    try:
        old_instance = sender.objects.get(pk=instance.pk)
        instance.subscription_geometry_pre_save = old_instance.subscription_geometry
    except sender.DoesNotExist:
        # a new record being created if we get here, so this shld be fine
        instance.subscription_geometry_pre_save = instance.subscription_geometry
        pass


@receiver(post_save, sender=GlobalForestWatchSubscription)
def subscription_post_save(instance, created, **kwargs):
    logger.info(f'PRE: {instance.subscription_geometry_pre_save} NOW: {instance.subscription_geometry}')
    if created:
        create_subscription(instance)
        logger.info(f'After GFW subs create {instance.subscription_id}')
        # This will trigger another post_save signal!
        instance.save()
    else:
        logger.info(f'updated new subscription in DB')
        update_subscription(instance)


@receiver(post_delete, sender=GlobalForestWatchSubscription)
def subscription_post_delete(instance, **kwargs):
    logger.info(f'subs post_delete signal received for {instance}')
    delete_subscription(instance)

