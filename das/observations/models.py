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
import itertools

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
import pymet
import pytz

from utils.json import zeroout_microseconds
from das_server import settings
from accounts.mixins import PermissionSetHierarchyMixin, PermissionSetGroupMixin
from accounts.models import PermissionSet
from core.models import HierarchyManager, HierarchyModel, TimestampedModel
from core.utils import static_image_finder
from observations.utils import calculate_track_range


SOURCE_TYPES = (
    ('tracking-device', 'Tracking Device'),
    ('trap', 'Trap'),
    ('seismic', 'Seismic sensor'),
    ('firms', 'FIRMS data'),
    ('gps-radio', 'gps radio'),
)


def to_rgb(color):
    try:
        return "#{0:02X}{1:02X}{2:02X}".format(*[int(val) for val in color.split(',')])
    except:
        raise


DEFAULT_COLOR = '255,255,0'

STATUS_COLORS = {'online': 'green', 'offline': 'gray',
                 'alarm': 'red', 'default': 'black'}


def get_radio_color(state, additional):
    color = STATUS_COLORS.get(state, 'black')
    if state == 'online' \
            and False == additional.get('gps_fix', True):
        color = 'blue'
    return color


def random_rgb():
    return ','.join([str(random.randint(0, 255)) for i in range(3)])


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

            provider, created = SourceProvider.objects.get_or_create(
                provider_key=kwargs.get('provider'))

            searchkey = dict(
                manufacturer_id=kwargs['manufacturer_id'], provider=provider)
            defaults = {
                'source_type': kwargs.get('source_type'),
                'model_name': kwargs.get('model_name'),
                'additional': additional
            }

            source, source_created = Source.objects.get_or_create(
                defaults=defaults, **searchkey)

            if source_created:
                source.groups.set((SourceGroup.objects.get_default(),))

            # If we've created a new Source, also create a subject with default
            # values.
            if source_created:
                if not subject:
                    subject = {'name': source.manufacturer_id}
                subject = Subject.objects.create_subject(**subject)
                SubjectSource.objects.create(source=source, subject=subject)

            return source


class SourceProviderManager(models.Manager):
    pass


DEFAULT_SOURCE_PROVIDER_ID = '697f25e4-562c-4305-af86-1333e9081f4c'
DEFAULT_SOURCE_PROVIDER_KEY = 'default'


def get_default_source_provider_id():

    return uuid.UUID(DEFAULT_SOURCE_PROVIDER_ID)


class SourceProvider(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    provider_key = models.CharField('Natural key for source provider',
                                    max_length=100, null='False', unique=True)

    display_name = models.CharField('Display name for source provider.',
                                    max_length=100, null=False,)

    objects = SourceProviderManager()

    def __str__(self):
        return '{} ({})'.format(self.display_name, self.provider_key)


class Source(TimestampedModel):

    objects = SourceManager()

    """Collar, MotoTrbo, sensor, etc"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    source_type = models.CharField('type of data expected', max_length=100,
                                   null=True, choices=SOURCE_TYPES)

    # # Delete this after migration occurs for provider attribute.
    # provider_name = models.CharField('unique name for data provider', max_length=100, null='False', default='default')

    provider = models.ForeignKey(SourceProvider, related_name='sources', related_query_name='source',
                                 null=False, default=get_default_source_provider_id,
                                 on_delete=models.PROTECT)

    manufacturer_id = models.CharField('device manufacturer id', max_length=100,
                                       null=True)
    model_name = models.CharField(
        'device model name', max_length=100, null=True)
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
        return '%s:%s' % (self.provider.provider_key, self.manufacturer_id)

    def observations(self):
        queryset = Observation.objects.filter(source=self)
        return queryset


EMPTY_POINT = Point(0, 0)


class ObservationManager(models.Manager):

    def get_subject_observations(self, subject, since=None, until=None, limit=None, values=None):
        queryset = Observation.objects.filter(source__subjectsource__subject=subject,
                                              source__subjectsource__assigned_range__contains=F(
                                                  'recorded_at'),
                                              exclusion_flags=0)

        if since and until:
            queryset = queryset.filter(Q(recorded_at__range=(since, until)))
        elif since:
            queryset = queryset.filter(Q(recorded_at__gt=since))
        elif until:
            queryset = queryset.filter(Q(recorded_at__lte=until))

        queryset = queryset.exclude(location=EMPTY_POINT)

        if limit:
            queryset = queryset[:limit]

        if values:
            queryset = queryset.values(*values)

        return queryset

    def get_subject_observations_values(self, subject, since=None, until=None, limit=None,
                                        values=('recorded_at', 'location')):
        return self.get_subject_observations(subject, since=since, until=until, limit=limit, values=values)

    def set_flag(self, id_list, flags):
        '''Hide the nuances of manipulating a bitmap associated with an observation.'''
        Observation.objects.filter(id__in=id_list).update(
            exclusion_flags=F('exclusion_flags').bitor(flags))

    def unset_flag(self, id_list, flags):
        '''Hide the nuances of zeroing bits in a bitmap.'''
        Observation.objects.filter(id__in=id_list).update(
            exclusion_flags=F('exclusion_flags').bitand(~flags))

    def add_observation(self, observation):
        '''
        Add an observation for the given source.
        :param source:
        :param observation: An object with attributes: source, latitude, longitude, recorded_at, additional
        :return: The new Observation
        '''
        location = Point(x=observation.longitude, y=observation.latitude)
        additional = observation.additional or {}
        result, created = observations.models.Observation.objects.get_or_create(source_id=observation.source.id,
                                                                                recorded_at=observation.recorded_at,
                                                                                defaults=dict(
                                                                                    location=location,
                                                                                    additional=additional
                                                                                ))
        return result, created

    def get_max_recorded_at(self, source):
        '''Get the latest recorded timestamp for the source.'''
        r = Observation.objects.filter(
            source=source).aggregate(Max('recorded_at'))
        return r.get('recorded_at__max')

    def get_last_source_observation(self, source, delay_hours=0):

        try:
            qs = Observation.objects.filter(
                source=source).exclude(location=EMPTY_POINT)
            if delay_hours:
                end_time = pytz.utc.localize(
                    datetime.utcnow()) - timedelta(hours=delay_hours)
                qs = qs.filter(recorded_at__lt=end_time)
            return qs.latest('recorded_at')

        except Observation.DoesNotExist:
            pass


class Observation(models.Model):

    # Constants for filter bit-map.
    EXCLUDED_MANUALLY = 1
    EXCLUDED_AUTOMATICALLY = 2

    """observation point
    similar to archive_loc
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    location = models.PointField('point location')
    # point in time of object at lat lon
    recorded_at = models.DateTimeField('recorded at', db_index=True)
    created_at = models.DateTimeField(
        'row created at', auto_now_add=True)  # date/time this row created
    source = models.ForeignKey('Source', on_delete=models.CASCADE)
    additional = JSONField()
    exclusion_flags = models.BigIntegerField(
        'Exclusion flags as a bitmap', null=False, default=0)

    objects = ObservationManager()

    def __str__(self):
        return '{}:{}:{:08b}'.format(self.recorded_at.isoformat(), self.location, self.exclusion_flags)

    class Meta:
        unique_together = (
            ['source', 'recorded_at']
        )
        ordering = ['-recorded_at']


DEFAULT_ASSIGNED_RANGE = list((pytz.utc.localize(datetime.min),
                               pytz.utc.localize(datetime.max)))


class SubjectSourceManager(models.Manager):
    def get_subject_sources(self, subject):
        sds = SubjectSource.objects.filter(subject_id=subject.id)
        return sds

    def get_subject_source(self, subject, source_id):
        sds = SubjectSource.objects.filter(
            subject_id=subject.id, source_id=source_id)
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
                                                                      defaults=dict(
                                                                          additional={},)
                                                                      )

        return subject_source

    def ensure_subject_source(self, source, timestamp=None, subject_subtype=None,
                              additional=None, subject_name=None):

        # TODO: Deprecate the use of this function, in favor of the ensure().
        # And let the caller handle creating related objects if necessary.

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
                subject_subtype=subject_subtype,
                name=(subject_name or source.manufacturer_id),
                defaults=dict(additional=dict(
                    region='', country='', rgb=random_rgb()))
            )

            if sub:
                subject_source, created = SubjectSource.objects.get_or_create(source=source, subject=sub,
                                                                              defaults=dict(assigned_range=DEFAULT_ASSIGNED_RANGE,
                                                                                            additional=additional))

        return subject_source, created

    def get_for_source_at_time(self, source, at_time):
        subject_sources = SubjectSource.objects.filter(
            source=source, assigned_range__contains=at_time)
        if subject_sources:
            return subject_sources[0]


class SubjectSource(models.Model):
    """A Subject is associated with a Source device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assigned_range = DateTimeRangeField(
        'time assigned to subject', default=DEFAULT_ASSIGNED_RANGE)
    source = models.ForeignKey('Source', on_delete=models.CASCADE)
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    additional = JSONField('additional', default={})
    """EXCLUDE USING gist (source_id WITH =, assigned_range WITH &&)"""
    objects = SubjectSourceManager()

    def __str__(self):
        fmt = '%Y-%m-%d'
        return '%s [%s] %s-%s' % (self.subject.name, self.source.manufacturer_id,
                                  self.assigned_range.lower.strftime(fmt), self.assigned_range.upper.strftime(fmt))


class SubjectTypeManager(models.Manager):

    def get_by_natural_key(self, value):
        return self.get(value=value)

    class Meta:
        verbose_name = _('subject type')
        verbose_name_plural = _('subject types')


class SubjectSubTypeManager(models.Manager):

    def get_by_natural_key(self, value):
        return self.get(value=value)

    class Meta:
        verbose_name = _('subject sub-type')
        verbose_name_plural = _('subject sub-types')


def get_default_subject_subtype():
    subject_subtype, created = SubjectSubType.objects.get_or_create(value='unassigned',
                                                                    defaults={'display': 'Unassigned'})
    return subject_subtype.value


def get_default_subject_type():
    subject_type, created = SubjectType.objects.get_or_create(value='unassigned',
                                                              defaults={'display': 'Unassigned'})
    return subject_type.value


class SubjectType(TimestampedModel):
    id = models.UUIDField(default=uuid.uuid4)
    value = models.CharField(primary_key=True, max_length=40, unique=True)
    display = models.CharField(
        max_length=100, blank=True, verbose_name='Subject Type')
    ordernum = models.SmallIntegerField(blank=True, null=True)

    def natural_key(self):
        return self.value

    def __str__(self):
        return self.display


class SubjectSubType(TimestampedModel):
    id = models.UUIDField(default=uuid.uuid4)
    value = models.CharField(primary_key=True, max_length=40, unique=True)
    display = models.CharField(
        max_length=100, blank=True, verbose_name='Subject Sub-Type')
    subject_type = models.ForeignKey(SubjectType, null=False,
                                     on_delete=models.PROTECT,
                                     default=get_default_subject_type)
    ordernum = models.SmallIntegerField(blank=True, null=True)

    def natural_key(self):
        return self.value

    def __str__(self):
        return self.value


class SubjectTrackSegmentFilterManager(models.Manager):
    pass


class SubjectTrackSegmentFilter(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # TODO Should reference SubjectSubTypes model if it gets created...
    subject_subtype = models.ForeignKey(
        SubjectSubType, on_delete=models.PROTECT)
    speed_KmHr = models.FloatField(default=7.0)
    additional = JSONField(default={})
    objects = SubjectTrackSegmentFilterManager()


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
        queryset = queryset.prefetch_related(
            models.Prefetch('subjectstatus_set'))
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

        # Avoid checking for a user that does not have permission sets (ex.
        # AnonymousUser)
        if not hasattr(user, 'get_all_permission_sets'):
            return self.none()

        if user.is_superuser:
            return self.all()

        allowed_subject_groups = SubjectGroup.objects.all().filter(
            permission_sets__in=user.get_all_permission_sets())

        effective_subject_group_set = set()
        for sg in allowed_subject_groups:
            effective_subject_group_set.add(sg)
            effective_subject_group_set.update(sg.get_descendants())

        return self.filter(groups__in=effective_subject_group_set).distinct('id')

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
        return self.filter(subject_subtype__subject_type__value='person')

    def by_group(self, subject_group_id):
        return self.filter(groups__id=subject_group_id)

    def by_is_active(self, active=True):
        return self.filter(is_active=active)


class SubjectManager(models.Manager):
    def create_subject(self, **kwargs):
        # all subjects are added to the default subject group
        subject = super().create(**kwargs)
        subject.groups.set((SubjectGroup.objects.get_default(),))
        return subject

    def get_subjects_from_observation_id(self, observation_id, values=None):
        '''
        Convenient place to keep rules for identifying a Subject(s) related to an observation.
        :param observation_id:
        :return:
        '''
        subjects = Subject.objects.filter(
            subjectsource__source__observation__id=observation_id,
            subjectsource__assigned_range__contains=F(
                'subjectsource__source__observation__recorded_at')
        )
        if values:
            subjects = subjects.values(*values)
        return subjects

    def get_current_subjects_from_source_id(self, source_id, values=None, dt=None):
        '''
        Convenient place to keep rules for identifying a Subject(s) related to a Source.
        :param source_id:
        :param values: Caller can indicate to return values using a set.
        :param dt: Call can specify the date to use to find subjects assigned to the source. Default is 'now'.
        :return: a queryset (or values) for assigned Subjects.
        '''

        dt = dt or datetime.now(tz=pytz.utc)

        subjects = Subject.objects.filter(subjectsource__source__id=source_id,
                                          subjectsource__assigned_range__contains=dt)

        if values:
            subjects = subjects.values(*values)
        return subjects


class Subject(TimestampedModel, PermissionSetGroupMixin):

    def clean_fields(self, exclude=None):
        return super().clean_fields(exclude)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_('name'), max_length=100)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subjects', related_query_name='subject')

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

    subject_subtype = models.ForeignKey(
        SubjectSubType, default=get_default_subject_subtype, on_delete=models.PROTECT)

    @property
    def subject_type(self):
        return self.subject_subtype.subject_type.value

    class Meta:
        permissions = (
            ('view_last_position',
             'Permission to view the last reported position of a Subject only.'),
            ('view_real_time', 'Access to real-time observations.'),
            ('view_delayed', 'Access to a 24 hour delayed observation feed. No real-time or last reported position.'),
            ('view_subject', 'Permission to view subject information excluding location'),
            ('subscribe_alerts', 'Permission to subscribe to an alert on this Subject.'),
            ('change_alerts', 'Permission to configure alerts for subject, includes setting geofences, proximity and immobility settings.'),
            ('change_view', 'An admin permission to change which users can view a Subject and their view permission.'),

            ('access_begins_7', 'Can view tracks no more than 7 days old'),
            ('access_begins_16', 'Can view tracks no more than 16 days old'),
            ('access_begins_30', 'Can view tracks no more than 30 days old'),
            ('access_begins_60', 'Can view tracks no more than 60 days old'),
            ('access_begins_all', 'Can view all historical tracks'),

            ('access_ends_0', 'Can view tracks no less than 0 days old'),
            ('access_ends_1', 'Can view tracks no less than 1 day old'),
            ('access_ends_3', 'Can view tracks no less than 3 days old'),
            ('access_ends_7', 'Can view tracks no less than 7 days old'),
        )

    @property
    def color(self):
        color = self.additional.get('rgb', DEFAULT_COLOR)
        if color:
            color = to_rgb(color)
        return color

    @property
    def source(self):
        subject_source = SubjectSource \
            .objects \
            .filter(subject_id=self.pk) \
            .order_by('-assigned_range') \
            .first()

        return subject_source.source

    def get_track(self, user, since, until, limit):
        since, until, limit = calculate_track_range(user, since, until, limit)

        qs = Observation.objects.get_subject_observations_values(
            self, since=since, until=until, limit=limit)

        qs = list(qs)
        return [o['location'].coords for o in qs], [zeroout_microseconds(o['recorded_at']) for o in qs]

    def get_subject_state(self):
        for subject_status in self.subjectstatus_set.filter(delay_hours=0):
            return subject_status.additional['state']

    def observations(self, last_hours=None, until=None):
        """ returns all observations for this Subject, spanning
        Sources as necessary """
        since = None

        if last_hours:
            if not until:
                until = datetime.now(tz=pytz.UTC)
            since = until - timedelta(hours=last_hours)

        return Observation.objects.get_subject_observations(self, since=since, until=until)

    def default_trajectory_filter(self):
        # Get trajectory filter based on subject. Might not exist.
        try:
            return SubjectTrackSegmentFilter.objects.filter(subject_subtype=self.subject_subtype.value).first()
        except SubjectTrackSegmentFilter.DoesNotExist:
            pass

    def create_trajectory(self, obs=None, trajectory_filter_params=None):
        """
        Hydrate the trajectory
        """

        if obs is None:
            obs = self.observations()

        def create_fix(observation):
            gp = pymet.base.GeoPoint(
                observation.location.x, observation.location.y, 0.0)
            fix = pymet.base.Fix(gp, observation.recorded_at)
            return fix

        # Create a relocations object
        fixes = [create_fix(x) for x in obs]
        relocs = pymet.base.Relocations(fixes=fixes)

        # Filter the relocations for junk coordinates
        coord_filter = pymet.base.RelocsCoordinateFilter()
        relocs.apply_fix_filter(coord_filter)

        # Create a trajectory from the relocations
        traj = pymet.base.Trajectory(relocs)

        if trajectory_filter_params is not None:

            speed_threshold = trajectory_filter_params.speed_KmHr

            # Create a relocations speed filter
            speed_filter = pymet.base.RelocsSpeedFilter(
                max_speed_kmhr=speed_threshold)
            traj.relocs.apply_fix_filter(speed_filter)

            # Create a trajseg filter
            traj_filt = pymet.base.TrajSegFilter(
                max_speed_kmhr=speed_threshold)
            traj.traj_seg_filter = traj_filt

        return traj

    @property
    def image_url(self):
        image_url = static_image_finder.get_marker_icon(self._image_keys())
        if not image_url:
            image_url = '/static/unassigned-black.svg'
        return image_url

    @property
    def kml_image_url(self):
        image_url = static_image_finder.get_marker_icon(
            self._image_keys(), image_types=('png', 'jpg'))
        if not image_url:
            image_url = '/static/unassigned.png'
        return image_url

    def _image_keys(self):
        """return the preferred key first"""
        key = self.subject_subtype.value.lower()
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
        return '%s, %s, %s' % (self.name, self.subject_subtype.subject_type.value, self.subject_subtype.value)


OBSERVATION_DELAY_HRS = 72


class SubjectStatusQuerySet(models.QuerySet):
    def get_last(self):
        for row in self:
            if row.delay_hours == 0:
                return row

    def get_delayed(self, delay=OBSERVATION_DELAY_HRS):
        for row in self:
            if row.delay_hours == delay:
                return row

    def get_range_endpoints(self, max_delay, min_delay):
        range_start = None
        range_end = None
        for row in self:
            if row.delay_hours > max_delay or row.delay_hours < min_delay:
                continue
            if range_start is None or row.delay_hours > range_start.delay_hours:
                range_start = row
            if range_end is None or row.delay_hours < range_end.delay_hours:
                range_end = row
        return range_start, range_end


class SubjectStatusManager(models.Manager):

    def update_from_observation(self, observation, delay_hours=0):

        observation = Observation.objects.get_last_source_observation(
            observation.source, delay_hours=delay_hours)

        if not observation:
            return

        try:
            # TODO: Account for the case where multiple subjects are returned.
            subject = Subject.objects.filter(subjectsource__source=observation.source,
                                             subjectsource__assigned_range__contains=observation.recorded_at).first()
        except Subject.DoesNotExist:
            return
        if not subject:
            return

        substatus, created = SubjectStatus.objects.get_or_create(subject=subject, delay_hours=delay_hours,
                                                                 defaults=dict(recorded_at=observation.recorded_at,
                                                                               location=observation.location,
                                                                               additional={}))

        if created or substatus.recorded_at >= observation.recorded_at:
            pass
        else:
            # Update subject-status location only for non-empty points.
            if observation.location != EMPTY_POINT:
                substatus.recorded_at = observation.recorded_at
                substatus.location = observation.location
            substatus.additional = observation.additional
            substatus.save()

        return substatus


class CommonNameManager(models.Manager):
    def get_by_natural_key(self, value):
        return self.get(**{value: value})


def get_default_subject_subtype():
    return SubjectSubType.objects.get(value='unassigned').id


class CommonName(TimestampedModel):
    """Common name for an animal, could stretch this to other subtypes as well.
    """
    subject_subtype = models.ForeignKey(SubjectSubType, on_delete=models.PROTECT,
                                        default=get_default_subject_subtype)

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

    @property
    def groups(self):
        return self.subject.groups


class RegionManager(models.Manager):
    pass


class Region(models.Model):
    """Region of Africa a subject is in"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    slug = models.SlugField('unique id', max_length=100, unique=True)
    region = models.CharField('region or pa', max_length=100)
    country = models.CharField(
        'country mostly containing region', max_length=100)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.region + ' ' + self.country)
        super(Region, self).save(*args, **kwargs)

    objects = RegionManager()

    def _____str__(self):
        return '%s, %s' % (self.region, self.country)


class SocketClient(TimestampedModel):
    '''
    Associate a socket ID with a user and a set of session-related data.
    '''
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_column="sid")
    username = models.CharField(
        'Das username associated with session', max_length=30)
    bbox = models.MultiPolygonField(
        'Viewport bounding box.', null=True, blank=True)
    event_filter = JSONField('Event filter', default={})


import observations.signals
