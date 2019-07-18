import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import GlobalForestWatchSubscription
from .gfwservice import create_subscription, update_subscription, delete_subscription

logger = logging.getLogger(__name__)


# @receiver(pre_save, sender=GlobalForestWatchSubscription)
# def subscription_pre_save(sender, instance, **kwargs):
#     try:
#         old_instance = sender.objects.get(pk=instance.pk)
#         instance.subscription_geometry_pre_save = old_instance.subscription_geometry
#         update_subscription(instance)
#     except sender.DoesNotExist:
#         # a new record being created if we get here, doing a pass here shld be fine for our purposes
#         instance.subscription_geometry_pre_save = instance.subscription_geometry
#         create_subscription(instance)
#         pass
@receiver(post_delete, sender=GlobalForestWatchSubscription)
def subscription_post_delete(instance, **kwargs):
    logger.info(f'subs post_delete signal received for {instance}')
    delete_subscription(instance)

