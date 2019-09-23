from datetime import datetime
import pytz

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from observations.models import Observation, SubjectStatus, Subject, EMPTY_POINT, SubjectSource, SubjectStatus
from observations.utils import VIEW_END_WINDOWS

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Observation)
def observation_post_save(sender, instance, created, **kwargs):

    # disable the handler during fixture loading
    if kwargs['raw']:
        return

    observation = Observation.objects.get(id=instance.id)
    SubjectStatus.objects.update_current_from_source(observation.source)


@receiver(post_save, sender=SubjectStatus)
def subject_status_post_save(sender, instance, created, **kwargs):

    if kwargs['raw']:
        return

    # Looking for name change.
    if instance.delay_hours == 0:
        latest_subject_name = instance.additional.get('subject_name', None)
        if latest_subject_name and latest_subject_name != instance.subject.name:
            logger.debug('Detected subject name change from %s to %s',
                         instance.subject.name, latest_subject_name)
            instance.subject.name = latest_subject_name
            instance.subject.save()


@receiver(post_save, sender=Subject)
def ensure_subject_status_exists(sender, **kwargs):

    if kwargs.get('created', False):
        subject = kwargs.get('instance')
        SubjectStatus.objects.ensure_for_subject(subject)


@receiver(post_save, sender=SubjectSource)
def maintain_subjectstatus(sender, instance, created, **kwargs):

    # This function is triggered when source is updated for subject.
    SubjectStatus.objects.maintain_subject_status(instance.subject_id)

