import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .gfw_outbound import delete_subscription
from .models import GlobalForestWatchSubscription

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=GlobalForestWatchSubscription)
def subscription_post_delete(instance, **kwargs):
    logger.info(f'subs post_delete signal received for {instance}')
    delete_subscription(instance)

