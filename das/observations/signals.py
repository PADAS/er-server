import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from observations.models import Observation, SubjectStatus, Subject, EMPTY_POINT
from observations.utils import VIEW_END_WINDOWS

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Observation)
def observation_post_save(sender, instance, created, **kwargs):

    # disable the handler during fixture loading
    if kwargs['raw']:
        return

    observation = Observation.objects.get(id=instance.id)

    logger.debug('handling Observation.post_save')
    for delay_hours in VIEW_END_WINDOWS:
        SubjectStatus.objects.update_from_observation(
            observation, delay_hours=delay_hours[1] * 24)


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


from datetime import datetime
import pytz


@receiver(post_save, sender=Subject)
def ensure_subject_status_exists(sender, **kwargs):

    if kwargs.get('created', False):
        subject = kwargs.get('instance')
        create_subjectstatus_records(subject)


def create_subjectstatus_records(subject):

    defaults = {
        'location': EMPTY_POINT,
        'recorded_at': datetime(1970, 1, 1, tzinfo=pytz.utc),
        'radio_state_at': datetime(1970, 1, 1, tzinfo=pytz.utc),

    }

    for delay_hours in VIEW_END_WINDOWS:
        SubjectStatus.objects.get_or_create(
            subject=subject, delay_hours=delay_hours[1] * 24,
            defaults=defaults)
