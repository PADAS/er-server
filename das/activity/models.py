import uuid
import datetime, pytz

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
from django.utils.encoding import force_text
from versatileimagefield.fields import VersatileImageField

from utils.html import clean_user_text
from core.models import TimestampedModel, ChoiceCharField
from observations.models import Subject
from revision.manager import Revision, RevisionMixin


def get_sentinel_user():
    User = get_user_model()
    return User.objects.get_or_create(username='deleted', last_name='account', first_name='deleted',
                                      email='deleted@test.com',
                                      is_active=False,
                                      password=User.objects.make_random_password())[0]


def marker_icon(event_type, priority, state):
    CONVERSION = {0: 'gray', 100: 'med_green', 200: 'amber', 300: 'red'}
    color = CONVERSION.get(priority, 'black')
    if state == Event.SC_RESOLVED:
        color = 'lt_gray'
    if not event_type:
        event_type = 'other'
    return '/static/{0}-{1}.svg'.format(event_type, color)


class CommunityManager(models.Manager):
    def create_member(self, **values):
        return self.create(**values)


class Community(TimestampedModel):
    objects = CommunityManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80)

    class Meta:
        verbose_name_plural = _('communities')

    def __str__(self):
        return self.name


class EventBaseManager(models.Manager):
    def get_by_value(self, value):
        return self.get(value=value)

    def all_sort(self):
        # default order ordernum
        result = self.order_by('ordernum')

        return result

    def get_by_natural_key(self, value):
        return self.get(value=value)


class EventClass(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=40, unique=True)
    display = models.CharField(max_length=100, blank=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)

    objects = EventBaseManager()

    def __str__(self):
        return self.display

    def natural_key(self):
        return (self.value,)


class EventFactor(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=40, unique=True)
    display = models.CharField(max_length=100, blank=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)

    objects = EventBaseManager()

    def __str__(self):
        return self.display

    def natural_key(self):
        return (self.value,)


class EventCategory(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=40, unique=True)
    display = models.CharField(max_length=100, blank=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    objects = EventBaseManager()

    def __str__(self):
        return self.display

    def natural_key(self):
        return (self.value,)


class FilterFieldMixin(object):
    def filter_field(self, field_name, field_data):
        if not field_data:
            return self

        if isinstance(field_data, (list, tuple)):
            field_q = None
            for value in field_data:
                field_q = field_q | models.Q(**{field_name: value}) if field_q\
                    else models.Q(**{field_name: value})
        else:
            field_q = models.Q(**{field_name: field_data})
        return self.filter(field_q)


class EventTypeFilteringQuerySet(models.QuerySet, FilterFieldMixin):
    def by_category(self, category):
        return self.filter_field('category__value', category)


class EventTypeManager(EventBaseManager):
    def create_type(self, **values):
        return self.create(**values)


class EventType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=40, unique=True)
    display = models.CharField(max_length=100, blank=True)
    category = models.ForeignKey(EventCategory, null=True,
                                 on_delete=models.PROTECT)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    schema = models.TextField(blank=True)

    objects = EventTypeManager.from_queryset(EventTypeFilteringQuerySet)()

    def __str__(self):
        return self.display

    def natural_key(self):
        return (self.value,)


class EventFilteringQuerySet(models.QuerySet, FilterFieldMixin):
    def all_sort(self):
        # default order by is by updated_at and (new/active/resolved)
        ordering = [(0, Event.SC_NEW), (0, Event.SC_ACTIVE),
                    (1, Event.SC_RESOLVED)]
        state_ordering = models.Case(*[models.When(state=pk, then=pos)
                                       for pos, pk in ordering])
        result = self.order_by(*[state_ordering, '-sort_at'])

        return result

    def by_bbox(self, bbox, last_days=None):
        geom = Polygon.from_bbox(bbox)
        events = self.filter(location__within=geom).order_by(
            '-created_at')
        if last_days:
            lt = timezone.now()
            gt = lt - last_days
            events = events.filter(created_at__range=(gt, lt))

        return events

    def by_state(self, state):
        return self.filter_field('state', state)

    def by_category(self, category):
        return self.filter_field('event_type__category__value', category)

    def by_event_type(self, event_type):
        return self.filter_field('event_type', event_type)


class EventManager(models.Manager):
    def create_event(self, **values):
        return self.create(**values)

    def get_reported_by_for_provenance(self, provenance):
        if Event.PC_STAFF == provenance:
            for obj in get_user_model().objects.all().filter(
                    is_active=True):
                yield obj
            for obj in Subject.objects.all().get_staff():
                yield obj
        elif Event.PC_COMMUNITY == provenance:
            for obj in Community.objects.all():
                yield obj

    def new_count(self):
        return self.filter(state=Event.SC_NEW).count()


class Event(RevisionMixin, TimestampedModel):
    objects = EventManager.from_queryset(EventFilteringQuerySet)()
    revision_ignore_fields = ('updated_at', 'sort_at')
    revision_follow_relations = ('activity.EventPhoto',)
    ordering = ['-sort_at']

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

    PRI_URGENT = 300
    PRI_IMPORTANT = 200
    PRI_REFERENCE = 100
    PRI_NONE = 0

    PRIORITY_CHOICES = (
        (0, 'None'),
        (100, 'Green'),
        (200, 'Amber'),
        (300, 'Red')
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
                                  blank=True)
    event_type = models.ForeignKey(EventType, on_delete=models.PROTECT,
                                   blank=True, null=True)
    state = models.CharField(max_length=40, choices=STATE_CHOICES,
                             default=SC_NEW, db_index=True)
    location = models.PointField(srid=4326, null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=PRI_NONE,
                                                choices=PRIORITY_CHOICES)
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

    sort_at = models.DateTimeField(default=django.utils.timezone.now,
                                   blank=True)

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
        return marker_icon(self.event_type.value if self.event_type else None,
                           self.priority, self.state)

    @property
    def subjects(self):
        event_attachments = EventAttachment.objects.filter(
            event_id=self.pk,
            content_type=ContentType.objects.get_for_model(Subject)
        )
        return [event_attachment.target for event_attachment in event_attachments]

    def dependent_table_updated(self):
        self.updated_at = timezone.now()
        self.sort_at = self.updated_at
        self.save()

    def save(self, *args, **kwargs):
        self.full_clean()
        update_fields = kwargs.get('update_fields', [])
        save_fields = set()

        try:
            prev_state = self.revision_original.get('state', None)
        except AttributeError:
            prev_state = None

        if (len(update_fields) == 1 and 'state' in update_fields and
            self.state == self.SC_ACTIVE and prev_state == self.SC_NEW):
                pass
        else:
            self.sort_at = timezone.now()
            save_fields.add('sort_at')

        save_fields.add('updated_at')
        if update_fields:
            update_fields = set(update_fields)
            update_fields.update(save_fields)
            kwargs['update_fields'] = list(update_fields)

        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        """validate reported_by based on provenance"""
        if self.provenance == self.PC_STAFF:
            if self.reported_by and not isinstance(self.reported_by, (get_user_model(), Subject)):
                raise ValidationError(
                    {'reported_by': ValidationError(_('Invalid value for reported_by'), code='invalid')})
        elif self.provenance == self.PC_COMMUNITY:
            if self.reported_by and not isinstance(self.reported_by, (Community,)):
                raise ValidationError(
                    {'reported_by': ValidationError(
                        _('Invalid value for {0} reported_by'.format(self.PC_COMMUNITY)), code='invalid')})
        elif self.provenance and self.reported_by:
            raise ValidationError(
                {'reported_by': ValidationError(
                    _('Invalid value for provenance {0} and reported_by fields'.format(self.provenance)), code='invalid')})

        self.message = clean_user_text(self.message, 'Event.message')

    def get_display_value(self, field_name, value):
        field = self._meta.get_field(field_name)
        if hasattr(self, 'get_{0}_display'.format(field_name)):
            return force_text(dict(field.flatchoices).get(value, value),
                   strings_only=True)
        if field_name == 'event_type':
            try:
                return force_text(EventType.objects.get(pk=value).display,
                              strings_only=True)
            except EventType.DoesNotExist:
                pass
        return value

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

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result

    def __str__(self):
        # TODO: Devise a better way to represent EventAttachment.
        return '{0}:{1}'.format(self.target.__str__(), self.reason)


class EventNoteManager(models.Manager):
    def create_note(self, **kwargs):
        return self.create(**kwargs)


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

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result

    def clean(self):
        super().clean()
        self.text = clean_user_text(self.text, 'EventNote.text')

    def __str__(self):
        return '{0}'.format(self.text[50:])



def upload_to(instance, filename):
    '''
    This is a hook for providing a path to an EventPhoto.image.
    :param instance: EventPhoto instance
    :param filename: default filename.
    :return: relative path for storing uploaded image
    '''
    name, extension = filename.rsplit('.', 1) if '.' in filename else (filename, '')

    d = datetime.datetime.now().replace(tzinfo=pytz.UTC)
    file_path = 'eventphotos/{year:04}/{month:02}/{day:02}/{pk!s}.{extension}'.format(year=d.year, month=d.month,
                                                                                    day=d.day, pk=instance.id,
                                                                                    extension=extension)
    return file_path


from revision.manager import relation_deleted
class EventPhoto(RevisionMixin, TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET(get_sentinel_user),
        null=True, blank=True, related_name='event_photos', related_query_name='event_photo')
    image = VersatileImageField(upload_to=upload_to, null=True, max_length=512)
    filename = models.TextField(verbose_name='Name of uploaded image file.', default='noname')

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='photos', related_query_name='photo')

    revision = Revision()

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result

    def clean(self):
        self.filename = self.image.name
        super().clean()

    def delete(self, using=None, keep_parents=False):
        myid = self.id
        result = super().delete(using, keep_parents)
        self.event.dependent_table_updated()
        self.id = myid
        relation_deleted.send(sender=Event, relation=self, instance=self.event, related_query_name='photo')

        return result


class EventClassFactor(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    eventclass = models.ForeignKey(EventClass, on_delete=models.CASCADE)
    eventfactor = models.ForeignKey(EventFactor, on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField(default=Event.PRI_REFERENCE,
                                                choices=Event.PRIORITY_CHOICES)

    class Meta:
        unique_together = (('eventclass', 'eventfactor'),)

    @property
    def value(self):
        return '{0}_{1}'.format(self.eventclass.value, self.eventfactor.value)

    def __str__(self):
        return self.value
