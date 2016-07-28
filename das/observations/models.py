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

from django.contrib.gis.db import models
from django.contrib.postgres.fields import DateTimeRangeField, JSONField
from django.db.models import Q
from django.db.models import Max
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _
from django.contrib.gis.geos import Point, Polygon
import pytz

from accounts.mixins import PermissionSetHierarchyMixin, PermissionSetGroupMixin
from accounts.models import PermissionSet
from core.models import HierarchyManager, HierarchyModel, TimestampedModel


SOURCE_TYPES = (
    ('tracking-device', 'Tracking Device'),
    ('trap', 'Trap'),
    ('seismic', 'Seismic sensor'),
    ('firms', 'FIRMS data'),
    ('gps-radio', 'gps radio')
)


def to_rgb(color):
    return "#{0:02X}{1:02X}{2:02X}".format(*[int(val) for val in color.split(',')])

DEFAULT_COLOR = '255,255,0'


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

    def get_all_sources(self):
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
    def ensure_source(self, source_type, manufacturer_id=None, model_name=None, additional=None):

        additional = additional or {}
        src, created = Source.objects.get_or_create(source_type=source_type,
                                                    manufacturer_id=manufacturer_id,
                                                    defaults={'model_name': model_name,
                                                              'additional': additional})

        return src, created

    def create_source(self, **kwargs):
        source = super().create(**kwargs)
        source.groups.set((SourceGroup.objects.get_default(),))
        return source


class Source(models.Model):

    objects = SourceManager()

    """Collar, MotoTrbo, sensor, etc"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    source_type = models.CharField('type of data expected', max_length=100,
                                   null=True, choices=SOURCE_TYPES)
    manufacturer_id = models.CharField('device manufacturer id', max_length=100,
                                       null=True)
    model_name = models.CharField('device model name', max_length=100, null=True)
    additional = JSONField('additional data')

    class Meta:
        permissions = (
            ('view_source',
             'Permission to view a source'),
        )

    def __str__(self):
        return '%s:%s' % (self.manufacturer_id, self.model_name)


EMPTY_POINT = Point(0,0)


class ObservationManager(models.GeoManager):
    def get_source_range_observations(self, subject_sources, since=None, until=None):
        """get observations for a set of sources and date ranges.
        An animal may switch source devices based on a date range.
        """
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
                                      until=None):
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

    def add_observation(self, observation, force=False):
        '''
        Add an observation for the given source.
        :param source:
        :param observation: An object with attributes: source, latitude, longitude, recorded_at, additional
        :param force: if True, will insert a potentially redundant record.
        :return: The new Observation
        '''

        # todo: consider changing the Geometry type in the db to accept z-value.
        # loc = Point(x=float(observation.pop('lon')), y=float(observation.pop('lat')),
        #             z=float(observation.get('elevation')))

        location = Point(x=observation.longitude, y=observation.latitude)

        additional = observation.additional or {}

        if force:
            obs = Observation.objects.create(source_id=observation.source.id, location=location,
                                             recorded_at=observation.recorded_at,
                                             additional=additional)
        else:
            obs, created = Observation.objects.get_or_create(source_id=observation.source.id,
                                                recorded_at=observation.recorded_at,
                                                defaults=dict(location=location,
                                                              additional=additional))

        return Observation.objects.get(id=obs.id)

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
    recorded_at = models.DateTimeField('recorded at')  # point in time of object at lat lon
    created_at = models.DateTimeField('row created at', auto_now_add=True)  # date/time this row created
    source = models.ForeignKey('Source', on_delete=models.CASCADE)
    additional = JSONField()

    objects = ObservationManager()

    # def __str__(self):
    #     return self.name

    class Meta:
        index_together = (
            ['source', 'recorded_at']
        )


class SubjectSourceManager(models.GeoManager):
    def get_subject_sources(self, subject):
        sds = SubjectSource.objects.filter(subject_id=subject.id)
        return sds

    def get_subject_source(self, subject, source_id):
        sds = SubjectSource.objects.filter(subject_id=subject.id, source_id=source_id)
        return sds

    def ensure_subject_source(self, source, timestamp=None, subject_type=None, subject_subtype=None, assigned_range=None,
                              additional=None, subject_name=None):

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
                                                                     defaults=dict(assigned_range=assigned_range,
                                                                                   additional=additional))
                
        return subject_source, created


class SubjectSource(models.Model):
    """A Subject is associated with a Source device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assigned_range = DateTimeRangeField('time assigned to subject')
    source = models.ForeignKey('Source', on_delete=models.CASCADE)
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    additional = JSONField('additional')
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

    def get_all_subjects(self):
        """Including descendant group subjects"""
        subgroups = self.get_descendants()
        subjects = set(iter(self.subjects.all()))
        for group in subgroups:
            subjects.update(iter(group.subjects.all()))
        return list(subjects)

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


class SubjectManager(models.Manager):
    def create_subject(self, **kwargs):
        #all subjects are added to the default subject group
        subject = super().create(**kwargs)
        subject.groups.set((SubjectGroup.objects.get_default(),))
        return subject

    def by_region(self, region, **kwargs):
        subjects = self.filter(additional__region=region.region)
        subjects.filter(additional__country=region.country, **kwargs)
        return subjects

    def by_bbox(self, bbox, last_days=None):
        geom = Polygon.from_bbox(bbox)
        sources = Observation.objects.filter(location__within=geom)
        if last_days:
            lt = datetime.now(tz=pytz.UTC)
            gt = lt - last_days
            sources = sources.filter(recorded_at__range=(gt, lt))
        sources = sources.values('source').annotate(models.Count('source')).values('source')
        subject_sources = SubjectSource.objects.filter(source__in=sources)
        subjects = subject_sources.values('subject')
        subjects = Subject.objects.filter(pk__in=subjects)
        return subjects

    def by_user_subjects(self, user):
        sg_all = set()
        for sg in SubjectGroup.objects.all().filter(
                permission_sets__in=user.get_all_permission_sets()):
            sg_all.add(sg)
            sg_all.update(sg.get_descendants())

        return Subject.objects.all().filter(groups__in=sg_all)

    def get_staff(self):
        return self.all().filter(subject_type=Subject.TYPE_PERSON)


class Subject(models.Model, PermissionSetGroupMixin):
    """Person, Animal, Vehicle, etc"""

    def clean_fields(self, exclude=None):
        return super().clean_fields(exclude)

    TYPE_WILDLIFE = 'wildlife'
    TYPE_PERSON = 'person'
    TYPE_VEHICLE = 'vehicle'
    TYPE_STATIONARY_OBJECT = 'stationary-object'

    SUBTYPE_ELEPHANT = 'elephant'
    SUBTYPE_ZEBRA = 'zebra'
    SUBTYPE_RHINO = 'rhino'
    SUBTYPE_LION = 'lion'

    SUBTYPE_SECURITY = 'security'
    SUBTYPE_RESEARCH = 'research'
    SUBTYPE_CAMERA_TRAP = 'camera-trap'
    SUBTYPE_WEATHER_STATION = 'weather-station'

    SUBTYPE_RANGER = 'ranger'
    SUBTYPE_MANAGER = 'manager'
    SUBTYPE_DRIVER = 'driver'

    TYPES_HIERARCHIES = [
        {
            'value': TYPE_WILDLIFE,
            'name': 'Wildlife',
            'subtypes': (
                (SUBTYPE_ELEPHANT, 'Elephant'),
                (SUBTYPE_ZEBRA, 'Zebra'),
                (SUBTYPE_RHINO, 'Rhino'),
                (SUBTYPE_LION, 'Lion'),
            )

        },
        {
            'value': TYPE_PERSON,
            'name': 'Person',
            'subtypes': (
                (SUBTYPE_RANGER, 'Ranger'),
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
            )
        },
        {
            'value': TYPE_STATIONARY_OBJECT,
            'name': 'Stationary Sensor',
            'subtypes': (
                (SUBTYPE_CAMERA_TRAP, 'Camera Trap'),
                (SUBTYPE_WEATHER_STATION, 'Weather Sensor'),
            )
        }
    ]

    TYPE_CHOICES = [(item['value'], item['name']) for item in TYPES_HIERARCHIES]
    SUBTYPE_CHOICES = [(item['name'], item['subtypes']) for item in TYPES_HIERARCHIES]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=100)

    subject_type = models.CharField('subject type', max_length=100, default=TYPE_WILDLIFE, choices=TYPE_CHOICES)
    subject_subtype = models.CharField(db_column='subject_subtype', max_length=100, default=SUBTYPE_ELEPHANT,
                                       choices=SUBTYPE_CHOICES)
    additional = JSONField('additional data')
    objects = SubjectManager()

    class Meta:
        permissions = (
            ('view_last_position', 'Allow the user to view the last reported position of a Subject.'),
            ('view_real_time', 'Access to updated observations as they become available, includes view_last_position.'),
            ('view_delayed', 'Access to a time dated observation feed. The delay is 24 hours, i.e. can only see yesterday and older observations. No real-time or last position.'),
            ('view_subject', 'Permission to view a subject, does not include permission to see location'),
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
        # TODO: This is a bit kludgy, so fix it to use subject type and subtype after March demo.
        key = self.subject_subtype
        sex = self.additional.get('sex', None)
        if sex:
            key = '-'.join((key, sex))

        return googlemarkericon(key.lower())

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


MARKER_ICONS = {
    'elephant': '/static/elephant-black-male.svg',
    'elephant-male': '/static/elephant-black-male.svg',
    'elephant-female': '/static/elephant-black-female.svg',
    'forest elephant': '/static/elephant-black-male.svg',
    'forest elephant-male': '/static/elephant-black-male.svg',
    'forest elephant-female': '/static/elephant-black-female.svg',
    'lion-male': '/static/Lion_Male.png',
    'lion-female': '/static/Lion_Female.png',
    'ranger': '/static/patrol_team-black.svg',
    'vehicle': '/static/truck.png',
    'cow': '',
    'cheetah': '',
    'expedition': 'http://maps.google.com/mapfiles/kml/shapes/triangle.png',
    'zebra-male': '/static/GrevysZebra_Male.png',
    'zebra-female': '/static/GrevysZebra_Female.png',
    'goat': '',
    'sable-male': '/static/SableAntelopeGraphicMale.png',
    'sable-female': '/static/SableAntelopeGraphicFemale.png',
    'rhino-male': '/static/Rhino_Male.png',
    'rhino-female': '/static/Rhino_Female.png',
    'white rhino': '',
    'black rhino': '',
}


def googlemarkericon(subject_type):
    url = MARKER_ICONS.get(subject_type, '/static/truck.png')
    return url
