import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from observations.models import Observation, SubjectStatus

logger = logging.getLogger(__name__)

# @receiver(post_save, sender=Observation)
def observation_post_save(sender, instance, created, **kwargs):

    # disable the handler during fixture loading
    if kwargs['raw']:
        return

    logger.debug('handling Observation.post_save')
    for delay_hours in (0, 24):
        SubjectStatus.objects.update_from_observation(instance, delay_hours=delay_hours)

@receiver(post_save, sender=SubjectStatus)
def subject_status_post_save(sender, instance, created, **kwargs):

    if kwargs['raw']:
        return

    # Looking for name change.
    if instance.delay_hours == 0:
        latest_subject_name = instance.additional.get('subject_name', None)
        if latest_subject_name and latest_subject_name != instance.subject.name:
            logger.debug('Detected subject name change from %s to %s', instance.subject.name, latest_subject_name)
            instance.subject.name = latest_subject_name
            instance.subject.save()


# TODO: Consider the cases for update and delete.