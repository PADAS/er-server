import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import GlobalForestWatchSubscription
from mapping.models import SpatialFeatureGroupStatic, SpatialFeature
from .gfw_service import create_subscription, update_subscription, delete_subscription

logger = logging.getLogger(__name__)


@receiver(post_save, sender=GlobalForestWatchSubscription)
def subscription_post_save(instance, created, **kwargs):
    logger.info(f'subs post_save Signal received from {instance}')
    if created:
        logger.info(f'created new subscription in DB')
        # create_subscription(instance)
        logger.info(f'After GFW subs create {instance.subscription_id}')
        # This will trigger another post_save signal!
        instance.save()
    else:
        logger.info(f'updated new subscription in DB')
        update_subscription(instance)


@receiver(post_delete, sender=GlobalForestWatchSubscription)
def subscription_post_delete(instance, **kwargs):
    logger.info(f'subs post_delete signal received for {instance}')


@receiver(post_save, sender=SpatialFeatureGroupStatic)
def sfgs_post_save(instance, created, **kwargs):
    logger.info(f'Signal received from {instance}')
    sub_inst = GlobalForestWatchSubscription.objects.filter(spatial_feature_group_id=instance.id)
    if sub_inst is not None:
        logger.info(f'will update subscription {sub_inst}')


@receiver(post_save, sender=SpatialFeature)
def sf_post_save(instance, created, **kwargs):
    logger.info(f'Signal received from SpatialFeature {instance}')
