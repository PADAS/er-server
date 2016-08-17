import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from observations.models import Observation, SubjectStatus

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Observation)
def observation_post_save(sender, instance, created, **kwargs):

    # disable the handler during fixture loading
    if kwargs['raw']:
        return

    logger.info('handling Observation.post_save')
    for delay_hours in (0, 24):
        SubjectStatus.objects.update_from_observation(instance, delay_hours=delay_hours)

# TODO: Consider the cases for update and delete.