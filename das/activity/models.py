import uuid
import logging
from django.conf import settings
from django.contrib.auth import get_user_model

from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
# from django.db.models import ManyToManyField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from core.models import TimestampedModel


logger = logging.getLogger(__name__)


def get_sentinel_user():
    return get_user_model().objects.get_or_create(username='deleted')[0]


class Event(TimestampedModel):

    '''
    An Event is something that happened. Maybe an incident, or an analyzer result, or a phone call from an informant.
    '''
    SYSTEM= 'system'
    SENSOR='sensor'
    ANALYZER='analyzer'
    INFORMANT='informant'
    PROVENANCE_CHOICES = (
        (SYSTEM, 'System Process'),
        (SENSOR, 'Sensor'),
        (ANALYZER, 'Analyzer'),
        (INFORMANT, 'Informant'),
    )

    ALERT='alert'
    EVENT_TYPE_CHOICES = (
        ('default', 'System Event'),
        (ALERT, 'Analyzer'),
    )

    """
    An Event is "something that has happened", recorded in the system.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80)
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET(get_sentinel_user), null=True, related_name='events',
                                        related_query_name='event')

    # # Generic foreign key relation to anything that has an id of type UUID.
    # content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # target_id = models.UUIDField()
    # target = GenericForeignKey('content_type', 'target_id')

    provenance = models.CharField(max_length=20, choices=PROVENANCE_CHOICES, default='system')
    attributes = JSONField()
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default='default')
    location = models.PointField(srid=4326)

    def __str__(self):
        return self.name


class EventAttachment(models.Model):

    # An event should allow attaching one or more other model objects. This model accommodates
    # attaching an object for an arbitrary model as long as its id is of type UUID.

    TARGET='target'
    EVENT_ATTACHMENT_REASONS = (
        (TARGET, 'Target'),
    )

    # Foreign Key to event for this attachment.
    event = models.ForeignKey(Event, on_delete=models.CASCADE,
                              related_name='attachments',
                              related_query_name='attachment')

    # Generic foreign key relation to any model within 'limits'. The technical constraint is the related model must
    # have id of type UUID.
    limits = models.Q(app_label='observations', model='subject') | models.Q(app_label='observations', model='source')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    target_id = models.UUIDField()
    target = GenericForeignKey('content_type', 'target_id')

    reason = models.CharField(max_length=20, choices=EVENT_ATTACHMENT_REASONS, default='target')


    def __str__(self):
        # TODO: Devise a better way to represent EventAttachment.
        return '{0}:{1}'.format(self.target.__str__(), self.reason)

