import uuid
import logging
import datetime

from django.contrib.auth import get_user_model
from django.contrib.gis.db import models
from django.contrib.gis.geos import Polygon
from django.utils import timezone
from django.contrib.postgres.fields import JSONField

# from django.db.models import ManyToManyField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from core.models import TimestampedModel

import accounts.models

logger = logging.getLogger(__name__)


def get_sentinel_user():
    return get_user_model().objects.get_or_create(username='deleted', is_active=False)[0]


class EventManager(models.Manager):

    def by_bbox(self, bbox, last_days=None):
        geom = Polygon.from_bbox(bbox)
        events = Event.objects.filter(location__within=geom).order_by('-created_at')
        if last_days:
            gt = datetime.datetime.utcnow() - last_days
            lt = datetime.datetime.utcnow()
            events = events.filter(created_at__range=(gt, lt))

        return events


class Event(TimestampedModel):

    objects = EventManager()

    image_url = 'http://tempuri.org/eventimage.jpg'
    ordering = ['-created_at']

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

    ET_SYSTEM = 'system'
    ET_PROXIMITY = 'proximity'
    ET_GEOFENCE = 'geofence'
    ET_IMMOBILITY = 'immobility'
    ET_SPEED = 'speed'

    ET_FENCE_BREACH = 'fence-breach'
    ET_ELEPHANT_SIGHTING = 'elephant-sighting'
    ET_WOUNDED_ANIMAL = 'wounded-animal'
    ET_FIRE = 'fire'
    ET_LIVESTOCK_THEFT = 'livestock-theft'

    EVENT_TYPE_CHOICES = (
        (ET_SYSTEM, 'System'),
        (ET_FENCE_BREACH, 'Fence Breach'),
        (ET_ELEPHANT_SIGHTING, 'Elephant Sighting'),
        (ET_WOUNDED_ANIMAL, 'Wounded Animal'),
        (ET_LIVESTOCK_THEFT, 'Livestock Theft'),
        (ET_FIRE, 'Fire'),
        (ET_PROXIMITY, 'Proximity'),
        (ET_GEOFENCE, 'Geofence'),
        (ET_IMMOBILITY, 'Immobility'),
        (ET_SPEED, 'Speed')

    )

    PRI_URGENT = 300
    PRI_IMPORTANT = 200
    PRI_REFERENCE = 100

    PRI_CHOICES = (
        (PRI_URGENT, 'Urgent'),
        (PRI_IMPORTANT, 'Important'),
        (PRI_REFERENCE, 'Reference'),
    )
    """
    An Event is "something that has happened", recorded in the system.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    name = models.CharField(max_length=80)
    description = models.TextField(default='')
    created_by_user = models.ForeignKey(accounts.models.User, on_delete=models.SET(get_sentinel_user), null=True,
                                        related_name='events',
                                        related_query_name='event')

    event_time = models.DateTimeField(default=timezone.now())
    provenance = models.CharField(max_length=20, choices=PROVENANCE_CHOICES, default=SYSTEM)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default=ET_SYSTEM)
    location = models.PointField(srid=4326, null=True)
    priority = models.PositiveSmallIntegerField(default=PRI_REFERENCE, choices=PRI_CHOICES)
    attributes = JSONField()

    @property
    def coordinates(self):
        return self.location

    @property
    def time(self):
        return self.event_time

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



