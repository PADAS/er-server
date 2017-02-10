"""
DAS DB models

after making changes to a model run migrations to record changes:
* python manage.py makemigrations --name "interesting model change name"

To re-sync your database with changes from others
* python manage.py migrate


GIS
* default geodjango spatial reference system is WGS84 (SRID 4326)
"""

from datetime import datetime, timedelta
import uuid
import random
# from collections import namedtuple
#
# from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.gis.db import models
from django.contrib.postgres.fields import DateTimeRangeField, JSONField
from django.db.models import Q
from django.db.models import Max, F, Case, When
from django.db import transaction
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _
from django.contrib.gis.geos import Point, Polygon
import pytz
from das_server import settings
from accounts.mixins import PermissionSetHierarchyMixin, PermissionSetGroupMixin
from accounts.models import PermissionSet
from core.models import HierarchyManager, HierarchyModel, TimestampedModel
from core.utils import static_image_finder

SOURCE_TYPES = (
    ('tracking-device', 'Tracking Device'),
    ('trap', 'Trap'),
    ('seismic', 'Seismic sensor'),
    ('firms', 'FIRMS data'),
    ('gps-radio', 'gps radio'),
)


def to_rgb(color):
    return "#{0:02X}{1:02X}{2:02X}".format(*[int(val) for val in color.split(',')])

DEFAULT_COLOR = '255,255,0'

STATUS_COLORS = {'online': 'green', 'offline': 'gray', 'alarm': 'red', 'default': 'black'}
def get_radio_color(state, additional):
    color = STATUS_COLORS.get(state, 'black')
    if state == 'online' \
            and False == additional.get('gps_fix', True):
        color = 'blue'
    return color


def random_rgb():
    return ','.join([str(random.randint(0,255)) for i in range(3)])


class SourceGroupManager(HierarchyManager):
    def get_default(self):
        return self.get(id=DEFAULT_SOURCE_GROUP_ID)

    def get_by_natural_key(self, name):
        return self.get(**{name: name})


class SourceGroup(HierarchyModel, TimestampedModel, PermissionSetHierarchyMixin):
    """
    Manage Groups of sources so that we can easily set permissions on a group
    rather than each individual Source. Additionally there are requests to
    get a subset of Sources.

    A group can contain other groups as well.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=80, unique=True)
    sources = models.ManyToManyField('Source', related_name='groups',
                                     blank=True)
    objects = SourceGroupManager()

    def get_all_sources(self, user=None, active=None):
        """Including descendant group sources"""
        subgroups = self.get_descendants()
        sources = set(iter(self.sources.all()))
        for group in subgroups:
            sources.update(iter(group.sources.all()))
        return list(sources)

    def natural_key(self):
        return (self.name,)

    class Meta:
        verbose_name = _('source group')
        verbose_name_plural = _('source groups')
        permissions = (
            ('view_sourcegroup',
             'Permission to view a source group'),
        )

    def __str__(self):
        return self.name


class SourceManager(models.Manager):

    # Helper functions for hydrating Source and Subject for the given message.
    def ensure_source(self, *args, **kwargs):

        additional = kwargs.get('additional', {})
        subject = kwargs.get('subject')
        with transaction.atomic():

            provider, created = SourceProvider.objects.get_or_create(name=kwargs.get('provider'))

            searchkey = dict(manufacturer_id=kwargs['manufacturer_id'], provider=provider)
            defaults = {
                'source_type': kwargs.get('source_type'),
                'model_name': kwargs.get('model_name'),
                'additional': additional
            }

            source, source_created = Source.objects.get_or_create(defaults=defaults, **searchkey)

            if source_created:
                source.groups.set((SourceGroup.objects.get_default(),))

            # If we've created a new Source, also create a subject with default values.
            if source_created:
                if not subject:
                    subject = {'name': source.manufacturer_id}
                subject = Subject.objects.create_subject(**subject)
                SubjectSource.objects.create(source=source, subject=subject)

            return source


class SourceProviderManager(models.Manager):
    pass


DEFAULT_SOURCE_PROVIDER_ID = '697f25e4-562c-4305-af86-1333e9081f4c'
def get_default_source_provider_id():
    instance, created = SourceProvider.objects.get_or_create(id=DEFAULT_SOURCE_PROVIDER_ID, name='default')
    return instance.id


class SourceProvider(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField('Friendly name for data provider', max_length=100, null='False', unique=True)

    objects = SourceProviderManager()

    def __str__(self):
        return self.name


class Source(TimestampedModel):

    objects = SourceManager()

    """Collar, MotoTrbo, sensor, etc"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    source_type = models.CharField('type of data expected', max_length=100,
                                   null=True, choices=SOURCE_TYPES)

    # # Delete this after migration occurs for provider attribute.
    # provider_name = models.CharField('unique name for data provider', max_length=100, null='False', default='default')

    provider = models.ForeignKey(SourceProvider, related_name='sources', related_query_name='source',
                                 null=False, default=get_default_source_provider_id)

    manufacturer_id = models.CharField('device manufacturer id', max_length=100,
                                       null=True)
    model_name = models.CharField('device model name', max_length=100, null=True)
    additional = JSONField('additional data', default={})
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sources', related_query_name='source')

    class Meta:
        permissions = (
            ('view_source',
             'Permission to view a source'),
        )
        unique_together = ('provider', 'manufacturer_id')

    def __str__(self):
        return '%s:%s' % (self.manufacturer_id, self.model_name)


EMPTY_POINT = Point(0,0)


class ObservationManager(models.GeoManager):
    def get_source_range_observations(self, subject_sources, since=None, until=None):
        # Get observations for a set of sources and date ranges. An animal may
        # switch source devices based on a date range.
        subject_sources = sorted(subject_sources,
                                 key=lambda ss: ss.assigned_range.lower,
                                 reverse=True)
        qs = None
        for ss in subject_sources:
            q = Q(source_id=ss.source_id) &\
                Q(recorded_at__range=[ss.assigned_range.lower, ss.assigned_range.upper])
            qs = qs | q if qs else q

        if qs:
            result = Observation.objects.filter(qs)
            if since:
                result = result.filter(Q(recorded_at__gt=since))
            if until:
                result = result.filter(Q(recorded_at__lte=until))
            result = result.order_by('-recorded_at')
            result = result.exclude(location=EMPTY_POINT)
            return result
        return []

    def get_source_range_observation_values(self, subject_sources, since=None,
                                      until=None, order_by=None, limit=None):
        """get observations for a set of sources and date ranges.
        An animal may switch source devices based on a date range.
        """

        subject_sources = sorted(subject_sources,
                                 key=lambda ss: ss.assigned_range.lower,
                                 reverse=True)
        qs = None
        for ss in subject_sources:
            q = Q(source_id=ss.source_id) & \
                Q(recorded_at__range=[ss.assigned_range.lower,
                                      ss.assigned_range.upper])
            qs = qs | q if qs else q

        if qs:
            result = Observation.objects.filter(qs)
            if since:
                result = result.filter(Q(recorded_at__gt=since))
            if until:
                result = result.filter(Q(recorded_at__lte=until))

            if limit:
                result = result.order_by('-recorded_at')[:limit]
            else:
                result = result.order_by('-recorded_at')

            for observation in result.values('location', 'recorded_at'):
                if observation['location'] != EMPTY_POINT:
                    yield observation


    def get_source_range_observations_last(self, subject_sources, last_days):
        """get the last days worth of observations starting from now.
        An animal may switch source devices based on a date range.
        """
        since = datetime.now(tz=pytz.UTC) - last_days
        return self.get_source_range_observations(subject_sources, since=since)

    def add_observation(self, observation):
        '''
        Add an observation for the given source.
        :param source:
        :param observation: An object with attributes: source, latitude, longitude, recorded_at, additional
        :return: The new Observation
        '''

        # todo: consider changing the Geometry type in the db to accept z-value.
        # loc = Point(x=float(observation.pop('lon')), y=float(observation.pop('lat')),
        #             z=float(observation.get('elevation')))

        location = Point(x=observation.longitude, y=observation.latitude)

        additional = observation.additional or {}


        # Check for matching observation already recorded.
        obs = Observation.objects \
            .filter(source_id=observation.source.id, recorded_at=observation.recorded_at) \
            .first()

        if not obs:
            obs = Observation.objects.create(source_id=observation.source.id, location=location,
                                             recorded_at=observation.recorded_at,
                                             additional=additional)

        return obs

    def get_max_recorded_at(self, source):
        '''Get the latest recorded timestamp for the source.'''
        r = Observation.objects.filter(source=source).aggregate(Max('recorded_at'))
        return r.get('recorded_at__max')

    def get_last_observation(self, subject, newer_than=None):
        """get the last recorded observation of the subject
        subject: subject to get observation for
        newer_than: provide a range to look in
        :returns Observation
        """
        return self._get_observation(subject, first=False,
                                     newer_than=newer_than)

    def get_delayed_observation(self, subject, older_than=None):
        """get the delayed last recorded observation of the subject
        :returns Observation
        """
        if not older_than:
            older_than = datetime.now(tz=pytz.UTC) - timedelta(hours=24)
        return self._get_observation(subject, first=False, older_than=older_than)

    def get_first_observation(self, subject):
        """get the first recorded observation of the subject
        :returns Observation
        """
        return self._get_observation(subject, first=True)

    def _get_observation(self, subject=None, first=False, subject_sources=None, older_than=None, newer_than=None):
        field = '-recorded_at'
        if first:
            field = 'recorded_at'

        if not subject and not subject_sources:
            raise AttributeError('subject or subject_sources must not be None')

        if not subject_sources:
            subject_sources = SubjectSource.objects.get_subject_sources(subject)

        sorted_sources = sorted([s for s in subject_sources],
                                key=lambda s: s.assigned_range.upper,
                                reverse=not first)

        for ssource in sorted_sources:
            r = Observation.objects.filter(source=ssource.source)
            r = r.exclude(location=EMPTY_POINT)
            r = r.filter(recorded_at__gt=ssource.assigned_range.lower)
            upper_range = ssource.assigned_range.upper
            lower_range = ssource.assigned_range.lower
            if newer_than and newer_than > upper_range:
                continue
            if older_than and lower_range > older_than:
                continue
            if older_than and older_than < upper_range:
                upper_range = older_than
            r = r.filter(recorded_at__lt=upper_range)
            if newer_than:
                r = r.filter(recorded_at__gt=newer_than)
            r = r.order_by(field)[:1]
            if r:
                return r[0]


class Observation(models.Model):
    """observation point
    similar to archive_loc
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    location = models.PointField('point location')
    recorded_at = models.DateTimeField('recorded at', db_index=True)  # point in time of object at lat lon
    created_at = models.DateTimeField('row created at', auto_now_add=True)  # date/time this row created
    source = models.ForeignKey('Source', on_delete=models.CASCADE)
    additional = JSONField()

    objects = ObservationManager()

    # def __str__(self):
    #     return self.name

    class Meta:
        unique_together = (
            ['source', 'recorded_at']
        )

DEFAULT_ASSIGNED_RANGE = list((pytz.utc.localize(datetime.min),
                               pytz.utc.localize(datetime.max)))

class SubjectSourceManager(models.GeoManager):
    def get_subject_sources(self, subject):
        sds = SubjectSource.objects.filter(subject_id=subject.id)
        return sds

    def get_subject_source(self, subject, source_id):
        sds = SubjectSource.objects.filter(subject_id=subject.id, source_id=source_id)
        return sds

    def ensure(self, source, subject, assigned_range=None):
        '''
        :param source:
        :param subject:
        :param assigned_range:
        :return:
        '''
        assigned_range = assigned_range or DEFAULT_ASSIGNED_RANGE

        subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=subject,
                                                                      assigned_range=assigned_range,
                                                                      defaults=dict(additional={},)
                                                                      )

        return subject_source

    def ensure_subject_source(self, source, timestamp=None, subject_type=None, subject_subtype=None,
                              additional=None, subject_name=None):

        # TODO: Deprecate the use of this function, in favor of the ensure(). And let the caller handle creating related objects if necessary.

        additional = additional or {}

        # get the most recent Subject for this Source
        subject_source = SubjectSource \
                            .objects \
                            .filter(source=source, assigned_range__contains=timestamp)\
                            .order_by('assigned_range')\
                            .reverse()\
                            .first()

        created = False

        if not subject_source:

            sub, created = Subject.objects.get_or_create(
                subject_type=subject_type, subject_subtype=subject_subtype,
                name=(subject_name or source.manufacturer_id),
                defaults=dict(additional=dict(region='', country='', rgb=random_rgb()))
            )

            if sub:
                subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=sub,
                                                                     defaults=dict(assigned_range=DEFAULT_ASSIGNED_RANGE,
                                                                                   additional=additional))
                
        return subject_source, created

    def get_for_source_at_time(self, source, at_time):
        subject_sources = SubjectSource.objects.filter(source=source, assigned_range__contains=at_time)
        if subject_sources:
            return subject_sources[0]


class SubjectSource(models.Model):
    """A Subject is associated with a Source device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assigned_range = DateTimeRangeField('time assigned to subject', default=DEFAULT_ASSIGNED_RANGE)
    source = models.ForeignKey('Source', on_delete=models.CASCADE)
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    additional = JSONField('additional', default={})
    """EXCLUDE USING gist (source_id WITH =, assigned_range WITH &&)"""
    objects = SubjectSourceManager()

    def __str__(self):
        return '%s, %s %s-%s' % (self.subject.name, self.source.model_name,
                                 self.assigned_range.lower, self.assigned_range.upper)


DEFAULT_SUBJECT_GROUP_ID = 'b4c8e9f6-1ccb-4e3f-8c07-3b727b9ec057'
DEFAULT_SOURCE_GROUP_ID = '654e592c-fc5a-436d-98dd-fd1b36436a85'



class SubjectGroupManager(HierarchyManager):
    def get_default(self):
        return self.get(id=DEFAULT_SUBJECT_GROUP_ID)

    def get_by_natural_key(self, name):
        return self.get(**{name: name})


class SubjectGroup(HierarchyModel, TimestampedModel, PermissionSetHierarchyMixin):
    """
    Manage Groups of subjects so that we can easily set permissions on a group
    rather than each individual Subject. Additionally there are requests to
    get a subset of subjects.

    A group can contain other groups as well.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=80, unique=True)
    subjects = models.ManyToManyField('Subject', related_name='groups',
                                      blank=True)
    objects = SubjectGroupManager()

    def get_all_subjects(self, user=None, active=None):
        """Including descendant group subjects"""
        sg_all = set(self.get_descendants())
        sg_all.add(self)

        queryset = Subject.objects.all()
        if active is not None:
            queryset = queryset.by_is_active(active=active)
        queryset = queryset.prefetch_related(models.Prefetch('subjectstatus_set'))
        queryset = queryset.filter(groups__in=sg_all)
        return queryset

    def natural_key(self):
        return (self.name,)

    class Meta:
        verbose_name = _('subject group')
        verbose_name_plural = _('subject groups')
        permissions = (
            ('view_subjectgroup',
             'Permission to view a subject group'),
        )

    def __str__(self):
        return self.name


class SubjectQuerySet(models.QuerySet):
    def by_region(self, region, **kwargs):
        subjects = self.filter(additional__region=region.region)
        subjects.filter(additional__country=region.country, **kwargs)
        return subjects

    def by_user_subjects(self, user):
        sg_all = set()
        for sg in SubjectGroup.objects.all().filter(
                permission_sets__in=user.get_all_permission_sets()):
            sg_all.add(sg)
            sg_all.update(sg.get_descendants())

        return self.filter(groups__in=sg_all)

    def by_bbox(self, bbox, last_days=None):
        geom = Polygon.from_bbox(bbox)
        sources = Observation.objects.filter(location__within=geom)
        if last_days:
            lt = datetime.now(tz=pytz.UTC)
            gt = lt - last_days
            sources = sources.filter(recorded_at__range=(gt, lt))
        sources = sources.values('source').annotate(models.Count('source')).values(
            'source')
        subject_sources = SubjectSource.objects.filter(source__in=sources)
        subjects = subject_sources.values('subject')
        return self.filter(pk__in=subjects)

    def get_staff(self):
        return self.filter(subject_type=Subject.TYPE_PERSON)

    def by_group(self, subject_group_id):
        return self.filter(groups__id=subject_group_id)

    def by_is_active(self, active=True):
        return self.filter(is_active=active)


class SubjectManager(models.Manager):
    def create_subject(self, **kwargs):
        #all subjects are added to the default subject group
        subject = super().create(**kwargs)
        subject.groups.set((SubjectGroup.objects.get_default(),))
        return subject


class Subject(TimestampedModel, PermissionSetGroupMixin):
    """Person, Animal, Vehicle, etc"""

    def clean_fields(self, exclude=None):
        return super().clean_fields(exclude)

    TYPE_WILDLIFE = 'wildlife'
    TYPE_PERSON = 'person'
    TYPE_VEHICLE = 'vehicle'
    TYPE_STATIONARY_OBJECT = 'stationary-object'
    TYPE_AIRCRAFT = 'aircraft'
    TYPE_UNASSIGNED = 'unassigned'

    SUBTYPE_ELEPHANT = 'elephant'
    SUBTYPE_ZEBRA = 'zebra'
    SUBTYPE_RHINO = 'rhino'
    SUBTYPE_LION = 'lion'
    SUBTYPE_GIRAFFE = 'giraffe'
    SUBTYPE_ANTELOPE = 'antelope'

    SUBTYPE_SECURITY = 'security_vehicle'
    SUBTYPE_RESEARCH = 'research'
    SUBTYPE_TOURIST_VEHICLE = 'tourist_vehicle'
    SUBTYPE_MOTORCYCLE = 'motorcycle'
    SUBTYPE_BOAT = 'ranger_boat'
    SUBTYPE_CAMERA_TRAP = 'camera-trap'
    SUBTYPE_WEATHER_STATION = 'weather-station'

    SUBTYPE_RANGER = 'ranger'
    SUBTYPE_RANGER_TEAM = 'ranger_team'
    SUBTYPE_DOG_TEAM = 'dog_team'
    SUBTYPE_MANAGER = 'manager'
    SUBTYPE_DRIVER = 'driver'

    SUBTYPE_PLANE = 'plane'
    SUBTYPE_HELICOPTER = 'helicopter'
    SUBTYPE_UNASSIGNED = 'unassigned'

    TYPES_HIERARCHIES = [
        {
            'value': TYPE_WILDLIFE,
            'name': 'Wildlife',
            'subtypes': (
                (SUBTYPE_ELEPHANT, 'Elephant'),
                (SUBTYPE_ZEBRA, 'Zebra'),
                (SUBTYPE_RHINO, 'Rhino'),
                (SUBTYPE_LION, 'Lion'),
                (SUBTYPE_GIRAFFE, 'Giraffe'),
                (SUBTYPE_ANTELOPE, 'Antelope'),
            )

        },
        {
            'value': TYPE_PERSON,
            'name': 'Person',
            'subtypes': (
                (SUBTYPE_RANGER, 'Ranger'),
                (SUBTYPE_RANGER_TEAM, 'Ranger Team'),
                (SUBTYPE_DOG_TEAM, 'Dog Team'),
                (SUBTYPE_DRIVER, 'Driver'),
                (SUBTYPE_MANAGER, 'Manager'),
            )
        },
        {
            'value': TYPE_VEHICLE,
            'name': 'Vehicle',
            'subtypes': (
                (SUBTYPE_SECURITY, 'Security Vehicle'),
                (SUBTYPE_RESEARCH, 'Research Vehicle'),
                (SUBTYPE_TOURIST_VEHICLE, 'Tourist Vehicle'),
                (SUBTYPE_MOTORCYCLE, 'Motorcycle'),
                (SUBTYPE_BOAT, 'Boat'),
            )
        },
        {
            'value': TYPE_STATIONARY_OBJECT,
            'name': 'Stationary Sensor',
            'subtypes': (
                (SUBTYPE_CAMERA_TRAP, 'Camera Trap'),
                (SUBTYPE_WEATHER_STATION, 'Weather Sensor'),
            )
        },
        {
            'value': TYPE_AIRCRAFT,
            'name': 'Aircraft',
            'subtypes': (
                (SUBTYPE_PLANE, 'Plane'),
                (SUBTYPE_HELICOPTER, 'Helicopter'),
            )
        },
        {
            'value': TYPE_UNASSIGNED,
            'name': 'Unassigned',
            'subtypes': (
                (SUBTYPE_UNASSIGNED, 'Unassigned'),
            )
        }
    ]

    TYPE_CHOICES = [(item['value'], item['name']) for item in TYPES_HIERARCHIES]
    SUBTYPE_CHOICES = [(item['name'], item['subtypes']) for item in TYPES_HIERARCHIES]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=100)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subjects', related_query_name='subject')

    subject_type = models.CharField('subject type', max_length=100, default=TYPE_UNASSIGNED, choices=TYPE_CHOICES)
    subject_subtype = models.CharField(db_column='subject_subtype', max_length=100, default=SUBTYPE_UNASSIGNED,
                                       choices=SUBTYPE_CHOICES)
    additional = JSONField('additional data', default={})
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'This subject is actively shown in visualizations.'
        ),
    )
    common_name = models.ForeignKey('CommonName', on_delete=models.PROTECT,
                                    blank=True,
                                    null=True)
    objects = SubjectManager.from_queryset(SubjectQuerySet)()

    class Meta:
        permissions = (
            ('view_last_position', 'Permission to view the last reported position of a Subject only.'),
            ('view_real_time', 'Access to real-time observations.'),
            ('view_delayed', 'Access to a 24 hour delayed observation feed. No real-time or last reported position.'),
            ('view_subject', 'Permission to view subject information excluding location'),
            ('subscribe_alerts', 'Permission to subscribe to an alert on this Subject.'),
            ('change_alerts', 'Permission to configure alerts for subject, includes setting geofences, proximity and immobility settings.'),
            ('change_view', 'An admin permission to change which users can view a Subject and their view permission.'),

        )

    VIEW_POSITION_PERMS = ('observations.view_last_position', 'observations.view_real_time')
    VIEW_DELAYED_PERMS = ('observations.view_delayed',)
    VIEW_SUBJECT_PERMS = ('observations.view_subject',) + VIEW_DELAYED_PERMS + VIEW_POSITION_PERMS

    @property
    def color(self):
        color = self.additional.get('rgb', DEFAULT_COLOR)
        if color:
            color = to_rgb(color)
        return color

    @property
    def last_observation(self):
        return Observation.objects.get_last_observation(self)

    @property
    def source(self):
        subject_source = SubjectSource \
            .objects \
            .filter(subject_id=self.pk) \
            .order_by('-assigned_range') \
            .first()

        return subject_source.source

    def observations(self, last_days=None):
        """ returns all observations for this Subject, spanning
        Sources as necessary """
        subject_sources = SubjectSource.objects.filter(subject=self)
        if last_days:
            until = datetime.now(tz=pytz.UTC)
            since = until - timedelta(days=last_days)
            obs = Observation.objects.get_source_range_observations(subject_sources, since=since, until=until)
        else:
            obs = Observation.objects.get_source_range_observations(subject_sources)

        return obs

    @property
    def image_url(self):
        image_url = static_image_finder.get_marker_icon(self._image_keys())
        if not image_url:
            image_url = '/static/triangle.png'
        return image_url

    def _image_keys(self):
        """return the preferred key first"""
        key = self.subject_subtype.lower()
        sex = self.additional.get('sex', 'male')
        if sex:
            yield '-'.join((key, 'black', sex.lower()))
            yield '-'.join((key, sex.lower()))

        status = self.subjectstatus_set.filter(delay_hours=0)
        if status:
            status = status[0]
            if 'state' in status.additional:
                color = get_radio_color(status.additional['state'],
                                        status.additional)
                yield '-'.join((key, color))

        yield key
        yield '-'.join((key, 'black'))


    def get_users_to_notify(self):
        """
        return a queryset of all users to be notified for this subject
        :return:
        """
        if not self.groups:
            return []
        else:
            users = set()
            ps_ids = self.get_obj_permission_set_ids()
            for ps in PermissionSet.objects.filter(id__in=ps_ids):
                 users.update(ps.user_set.all())
            return users

    def __str__(self):
        return '%s, %s, %s' % (self.name, self.subject_type, self.subject_subtype)


OBSERVATION_DELAY_HRS = 24

class SubjectStatusQuerySet(models.QuerySet):
    def get_last(self):
        for row in self:
            if row.delay_hours == 0:
                return row

    def get_delayed(self):
        for row in self:
            if row.delay_hours == OBSERVATION_DELAY_HRS:
                return row


class SubjectStatusManager(models.Manager):

    def update_from_observation(self, observation, delay_hours=0):

        ss = SubjectSource.objects.get_for_source_at_time(source=observation.source, at_time=observation.recorded_at)

        if not ss: # Coding error
            return
            # raise ValueError('No SubjectSource exists for observation {}'.format(observation))

        if not delay_hours:
            observation = Observation.objects.get_last_observation(ss.subject)
        else:
            ts = datetime.now(tz=pytz.UTC) - timedelta(hours=delay_hours)
            observation = Observation.objects.get_delayed_observation(ss.subject, older_than=ts)

        if not observation:
            return

        substatus, created = SubjectStatus.objects.get_or_create(subject=ss.subject, delay_hours=delay_hours,
                                                        defaults=dict(recorded_at=observation.recorded_at,
                                                                      location=observation.location,
                                                                      additional={}))

        if created or substatus.recorded_at >= observation.recorded_at:
            pass
        else:
            substatus.recorded_at = observation.recorded_at
            substatus.location = observation.location
            substatus.additional = observation.additional
            substatus.save()

        return substatus


class CommonNameManager(models.Manager):
    def get_by_natural_key(self, value):
        return self.get(**{value: value})


class CommonName(TimestampedModel):
    """Common name for an animal, could stretch this to other subtypes as well.
    """
    #value = models.UUIDField(primary_key=True, default=uuid.uuid4)
    subject_subtype = models.CharField(max_length=100,
                                       choices=Subject.SUBTYPE_CHOICES)
    value = models.CharField(primary_key=True, max_length=100)
    display = models.CharField(max_length=100)
    objects = CommonNameManager()

    def __str__(self):
        return self.display


class SubjectStatus(PermissionSetGroupMixin, TimestampedModel):
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    location = models.PointField('location')
    recorded_at = models.DateTimeField('location at')
    delay_hours = models.IntegerField('delay in hours')
    additional = JSONField('additional')

    objects = SubjectStatusManager.from_queryset(SubjectStatusQuerySet)()

    class Meta:
        verbose_name = _('Subject Status')
        verbose_name_plural = _('Subject Statuses')
        unique_together = ('subject', 'delay_hours')


class RegionManager(models.Manager):
    pass


class Region(models.Model):
    """Region of Africa a subject is in"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    slug = models.SlugField('unique id', max_length=100, unique=True)
    region = models.CharField('region or pa', max_length=100)
    country = models.CharField('country mostly containing region', max_length=100)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.region + ' ' + self.country)
        super(Region, self).save(*args, **kwargs)

    objects = RegionManager()

    def _____str__(self):
        return '%s, %s' % (self.region, self.country)


import observations.signals
