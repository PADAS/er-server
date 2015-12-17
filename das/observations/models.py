"""
DAS DB models

after making changes to a model run migrations to record changes:
* python manage.py makemigrations --name "interesting model change name"

To re-sync your database with changes from others
* python manage.py migrate


GIS
* default geodjango spatial reference system is WGS84 (SRID 4326)
"""
import datetime
import uuid

from django.contrib.gis.db import models
from django.contrib.postgres.fields import DateTimeRangeField, JSONField
from django.db.models import Q
from django.db.models import Max
from django.utils.text import slugify
from django.contrib.gis.geos import Point, Polygon

from .track import Track


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


class SourceManager(models.Manager):
    pass


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

        result = Observation.objects.filter(qs)
        if since:
            result = result.filter(Q(recorded_at__gt=since))
        if until:
            result = result.filter(Q(recorded_at__lte=until))
        result = result.order_by('-recorded_at')
        result = result.exclude(location=EMPTY_POINT)

        return result

    def get_source_range_observations_last(self, subject_sources, last_days):
        """get the last days worth of observations starting from now.
        An animal may switch source devices based on a date range.
        """
        subject_sources = sorted(subject_sources,
                                 key=lambda ss: ss.assigned_range.lower,
                                 reverse=True)

        last_observation = self._get_observation(first=False,
                                                 subject_sources=subject_sources)

        if not last_observation:
            return []

        qs = None
        for ss in subject_sources:
            q = Q(source_id=ss.source_id) &\
                Q(recorded_at__range=[ss.assigned_range.lower, ss.assigned_range.upper])
            qs = qs | q if qs else q

        result = Observation.objects.filter(qs)
        result = result.order_by('-recorded_at')
        result = result.exclude(location=EMPTY_POINT)
        gt = datetime.datetime.utcnow() - last_days
        result = result.filter(recorded_at__gt=gt)
        return result

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
        obs = Observation.objects.create(source_id=observation.source.id, location=location,
                                         recorded_at=observation.recorded_at,
                                         additional=additional)

        return Observation.objects.get(id=obs.id)

    def get_max_recorded_at(self, source):
        '''Get the latest recorded timestamp for the source.'''
        r = Observation.objects.filter(source=source).aggregate(Max('recorded_at'))
        return r.get('recorded_at__max')

    def get_last_observation(self, subject):
        """get the last recorded observation of the subject
        :returns Observation
        """
        return self._get_observation(subject, first=False)

    def get_first_observation(self, subject):
        """get the first recorded observation of the subject
        :returns Observation
        """
        return self._get_observation(subject, first=True)

    def _get_observation(self, subject=None, first=False, subject_sources=None):
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
            r = r.filter(recorded_at__lt=ssource.assigned_range.upper)
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
    source = models.ForeignKey('Source')
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


SUBJECT_TYPES = (
    ('wildlife', 'Wildlife'),
    ('vehicle', 'Vehicle'),
    ('stationary-object', 'Stationary Object'),
    ('person', 'Person')
)


class SubjectSource(models.Model):
    """A Subject is associated with a Source device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assigned_range = DateTimeRangeField('time assigned to subject')
    source = models.ForeignKey('Source')
    subject = models.ForeignKey('Subject')
    additional = JSONField('additional')
    """EXCLUDE USING gist (source_id WITH =, assigned_range WITH &&)"""
    objects = SubjectSourceManager()

    def __str__(self):
        return '%s, %s %s-%s' % (self.subject.name, self.source.model_name,
                                 self.assigned_range.lower, self.assigned_range.upper)


class SubjectManager(models.Manager):
    def by_region(self, region, **kwargs):
        subjects = self.filter(additional__region=region.region)
        subjects.filter(additional__country=region.country, **kwargs)
        return subjects

    def by_bbox(self, bbox):
        geom = Polygon.from_bbox(bbox)
        sources = Observation.objects.filter(location__within=geom)
        sources = sources.values('source').annotate(models.Count('source')).values('source')
        subject_sources = SubjectSource.objects.filter(source__in=sources)
        subjects = subject_sources.values('subject')
        subjects = Subject.objects.filter(pk__in=subjects)
        return subjects


class Subject(models.Model):
    """Person, Animal, Vehicle, etc"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField('name', max_length=100)
    subject_type = models.CharField('subject type', max_length=100, choices=SUBJECT_TYPES, default='wildlife')
    additional = JSONField('additional data')

    objects = SubjectManager()

    @property
    def color(self):
        color = self.additional.get('rgb', DEFAULT_COLOR)
        if color:
            color = to_rgb(color)
        return color

    @property
    def last_observation(self):
        return Observation.objects.get_last_observation(self)

    def observations(self):
        """ returns all observations for this Subject, spanning
        Sources as necessary """
        sds = SubjectSource.objects.filter(subject=self)
        obs = Observation.objects.get_source_range_observations(sds)
        return obs

    @property
    def image_url(self):
        key = self.subject_type
        species = self.additional.get('species', None)
        if species:
            species = species.lower()
            sex = self.additional.get('sex', None)
            if sex:
                key = '-'.join((species, sex.lower()))
            else:
                key = species
        return googlemarkericon(key)

    def __str__(self):
        return '%s, %s' % (self.name,self.subject_type)


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
    'elephant': '/static/Elephant_Male.png',
    'elephant-male': '/static/Elephant_Male.png',
    'elephant-female': '/static/Elephant_Female.png',
    'forest elephant': '/static/Elephant_Male.png',
    'forest elephant-male': '/static/Elephant_Male.png',
    'forest elephant-female': '/static/Elephant_Female.png',
    'lion-male': '/static/Lion_Male.png',
    'lion-female': '/static/Lion_Female.png',
    'ranger': '/static/ranger.png',
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
