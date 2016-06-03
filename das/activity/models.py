import logging
import uuid

import django.utils
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.gis.geos import Polygon
from django.contrib.postgres.fields import JSONField
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _


from core.models import TimestampedModel
from observations.models import Subject
from revision.manager import Revision, RevisionMixin

logger = logging.getLogger(__name__)


def get_sentinel_user():
    return get_user_model().objects.get_or_create(username='deleted', is_active=False)[0]


def marker_icon(*args):
    return '/static/event-marker-{}.svg'.format('-'.join(args))


class CommunityManager(models.Manager):
    def create_member(self, **values):
        return self.create(**values)


class Community(TimestampedModel):
    objects = CommunityManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80)

    def __str__(self):
        return self.name


class EventManager(models.Manager):
    def by_bbox(self, bbox, last_days=None):
        geom = Polygon.from_bbox(bbox)
        events = Event.objects.filter(location__within=geom).order_by('-created_at')
        if last_days:
            lt = timezone.now()
            gt = lt - last_days
            events = events.filter(created_at__range=(gt, lt))

        return events

    def create_event(self, **values):
        return self.create(**values)

    def get_reported_by_for_provenance(self, provenance):
        if Event.PC_STAFF == provenance:
            for obj in get_user_model().objects.all().filter(
                    is_active=True):
                yield obj
            for obj in Subject.objects.get_staff():
                yield obj
        elif Event.PC_COMMUNITY == provenance:
            for obj in Community.objects.all():
                yield obj


class Event(RevisionMixin, TimestampedModel):
    objects = EventManager()

    ordering = ['-created_at']

    '''
    An Event is something that happened. Maybe an incident, or an analyzer result, or a phone call from an informant.
    '''
    PC_SYSTEM = 'system'
    PC_SENSOR = 'sensor'
    PC_ANALYZER = 'analyzer'
    PC_COMMUNITY = 'community'
    PC_STAFF = 'staff'

    PROVENANCE_CHOICES = (
        (PC_STAFF, 'Staff'),
        (PC_SYSTEM, 'System Process'),
        (PC_SENSOR, 'Sensor'),
        (PC_ANALYZER, 'Analyzer'),
        (PC_COMMUNITY, 'Community'),
    )

    SC_NEW = 'new'
    SC_ACTIVE = 'active'
    SC_RESOLVED = 'resolved'

    STATE_CHOICES = (
        (SC_NEW, 'New'),
        (SC_ACTIVE, 'Active'),
        (SC_RESOLVED, 'Resolved'),
    )

    ET_SYSTEM = 'system'
    ET_PROXIMITY = 'proximity'
    ET_GEOFENCE = 'geofence'
    ET_IMMOBILITY = 'immobility'
    ET_SPEED = 'speed'

    ET_OTHER = 'other'
    ET_EXCLUSION_ZONE_BREACH = 'exclusion-zone-breach'
    ET_PERIMETER_FENCE_BREACH = 'perimeter-fence-breach'
    ET_ELEPHANT_SIGHTING = 'elephant-sighting'
    ET_WOUNDED_ANIMAL = 'wounded-animal'
    ET_FIRE = 'fire'
    ET_LIVESTOCK_THEFT = 'livestock-theft'
    ET_CONTAINMENT_BREACH = 'containment-breach'
    ET_FOOTPRINTS = 'footprints'
    ET_GUNSHOT_HEARD = 'gunshot-heard'
    ET_RADIO_TEXT_MESSAGE = 'radio-text-message'

    EVENT_TYPE_CHOICES = (
        (ET_SYSTEM, 'System'),
        (ET_PROXIMITY, 'Proximity'),
        (ET_GEOFENCE, 'Geofence'),
        (ET_IMMOBILITY, 'Immobility'),
        (ET_SPEED, 'Speed'),
        (ET_EXCLUSION_ZONE_BREACH, 'Exclusion Zone Breach'),
        (ET_PERIMETER_FENCE_BREACH, 'Perimeter Fence Breach'),
        (ET_ELEPHANT_SIGHTING, 'Elephant Sighting'),
        (ET_WOUNDED_ANIMAL, 'Wounded Animal'),
        (ET_LIVESTOCK_THEFT, 'Livestock Theft'),
        (ET_FIRE, 'Fire'),
        (ET_CONTAINMENT_BREACH, 'Containment Breach'),
        (ET_FOOTPRINTS, 'Suspicious Signs'),
        (ET_GUNSHOT_HEARD, 'Gunshot Heard'),
        (ET_RADIO_TEXT_MESSAGE, 'Radio Text Message'),
        (ET_OTHER, 'Other'),
    )

    PRI_URGENT = 300
    PRI_IMPORTANT = 200
    PRI_REFERENCE = 100

    PRI_DEFAULT_VALUE = PRI_REFERENCE

    PRIORITY_CHOICES = (
        (100, 'Reference'),
        (200, 'Important'),
        (300, 'Urgent')
    )

    PRIORITY_LABELS_MAP = dict((x, y) for (x,y) in PRIORITY_CHOICES)

    class Meta:
        permissions = (
            ('view_event',
             'Permission to view an event'),
            ('admin_event',
             'An admin permission to change which users can view a Subject and their view permission.'),

        )


    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    message = models.TextField(blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET(get_sentinel_user),
        null=True, blank=True, related_name='events', related_query_name='event')

    event_time = models.DateTimeField(default=django.utils.timezone.now)
    provenance = models.CharField(max_length=40, choices=PROVENANCE_CHOICES,
                                  default=PC_SYSTEM)
    event_type = models.CharField(max_length=40, choices=EVENT_TYPE_CHOICES,
                                  default=ET_SYSTEM)
    state = models.CharField(max_length=40, choices=STATE_CHOICES,
                             default=SC_NEW)
    location = models.PointField(srid=4326, null=True, blank=True)
    priority = models.PositiveSmallIntegerField(
        db_column='priority',
        default=PRI_DEFAULT_VALUE, choices=PRIORITY_CHOICES)
    attributes = JSONField(default={}, blank=True)
    revision = Revision()

    _usermodel = settings.AUTH_USER_MODEL.lower().split('.')
    reported_by_limits = models.Q(app_label='observations', model='subject')\
        | models.Q(app_label='observations', model='source') \
        | models.Q(app_label='activity', model='community') \
        | models.Q(app_label=_usermodel[0], model=_usermodel[1])
    reported_by_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to=reported_by_limits,
        null=True, blank=True)
    reported_by_id = models.UUIDField(null=True, blank=True, default=None)
    reported_by = GenericForeignKey('reported_by_content_type',
                                    'reported_by_id')

    @property
    def priority_label(self):
        return self.get_priority_display()

    @property
    def coordinates(self):
        return self.location

    @property
    def time(self):
        return self.event_time

    @property
    def image_url(self):
        return marker_icon(self.event_type, self.get_priority_display().lower())

    @property
    def subjects(self):
        event_attachments = EventAttachment.objects.filter(
            event_id=self.pk,
            content_type=ContentType.objects.get_for_model(Subject)
        )
        return [event_attachment.target for event_attachment in event_attachments]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        """validate reported_by based on provenance"""
        if self.provenance == self.PC_STAFF:
            if not isinstance(self.reported_by, (get_user_model(), Subject)):
                raise ValidationError(
                    {'reported_by': ValidationError(_('Invalid value for reported_by'), code='invalid')})
        elif self.provenance and self.reported_by:
            raise ValidationError(
                {'reported_by': ValidationError(
                    _('Invalid value for provenance and reported_by fields'), code='invalid')})

    def __str__(self):
        return self.message[50:]


class EventAttachmentManager(models.Manager):
    def create_attachment(self, **kwargs):
        return self.create(**kwargs)


class EventAttachment(RevisionMixin, models.Model):
    # An event should allow attaching one or more other model objects. This model accommodates
    # attaching an object for an arbitrary model as long as its id is of type UUID.

    objects = EventAttachmentManager()
    TARGET = 'target'
    EVENT_ATTACHMENT_REASONS = (
        (TARGET, 'Target'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
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

    reason = models.CharField(max_length=20, choices=EVENT_ATTACHMENT_REASONS,
                              default='target')
    revision = Revision()

    def __str__(self):
        # TODO: Devise a better way to represent EventAttachment.
        return '{0}:{1}'.format(self.target.__str__(), self.reason)


class EventNoteManager(models.Manager):
    def create_note(self, *args, **kwargs):
        return self.create(*args, **kwargs)


class EventNote(RevisionMixin, TimestampedModel):
    objects = EventNoteManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    text = models.TextField()
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET(get_sentinel_user),
        null=True)

    event = models.ForeignKey(Event, on_delete=models.CASCADE,
                              related_name='notes',
                              related_query_name='note')
    revision = Revision()

    def __str__(self):
        return '{0}'.format(self.text[50:])
