"""
DAS DB models

after making changes to a model run migrations to record changes:
* python manage.py makemigrations --name "interesting model change name"

To re-sync your database with changes from others
* python manage.py migrate


GIS
* default geodjango spatial reference system is WGS84 (SRID 4326)
"""
import uuid
from django.contrib.gis.db import models
from django_pgjson.fields import JsonBField
from django.contrib.postgres.fields import DateTimeRangeField, ArrayField
from django.db.models import Q
from django.db.models import Max
from django.utils import timezone
import pytz
from django.contrib.gis.geos import Point

SOURCE_TYPES = (
    ('tracking-device', 'Tracking Device'),
    ('trap', 'Trap'),
    ('seismic', 'Seismic sensor'),
    ('firms', 'FIRMS data'),
    ('gps-radio', 'gps radio')
)


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
    additional = JsonBField()


class ObservationManager(models.GeoManager):
    def get_source_range_observations(self, subject_sources, since=None, until=None):
        """get observations for a set of sources and date ranges.
        An animal may switch source devices based on a date range.
        """
        subject_sources = sorted(subject_sources, key=lambda ss: ss.assigned_range.lower, reverse=True)
        sql = '''SELECT * FROM observations_oberservation o WHERE o.source_id = %(source_id)s o.recorded_at in %(range)s'''

        qs = None
        for ss in subject_sources:
            q = Q(source_id=ss.source_id) & Q(recorded_at__range=[ss.assigned_range.lower, ss.assigned_range.upper])
            qs = qs | q if qs else q

        result = Observation.objects.filter(qs)
        if since:
            result = result.filter(Q(recorded_at__gt=since))
        if until:
            result = result.filter(Q(recorded_at__lte=until))
        result = result.order_by('-recorded_at')

        return result

    def add_observation(self, source, observation):
        '''
        Add an observation for the given source.
        :param source:
        :param observation: a dict containing observation data. Anything other than lat, lon and timestamp (ts) will
        be saved in additional (as jsonb).
        :return: None
        '''
        loc = Point(float(observation.pop('lat')), float(observation.pop('lon')))
        ts = observation.pop('ts')

        Observation(source_id=source.id, location=loc, recorded_at=ts, additional=observation).save()


    def get_max_recorded_at(self, source):
        '''Get the latest recorded timestamp for the source.'''
        r = Observation.objects.filter(source=source).aggregate(Max('recorded_at'))
        return r.get('recorded_at__max')


class Observation(models.Model):
    """observation point
    similar to archive_loc
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    location = models.PointField()
    recorded_at = models.DateTimeField() #point in time of object at lat lon
    created_at = models.DateTimeField(auto_now_add=True) #date/time this row created
    source = models.ForeignKey('Source')
    additional = JsonBField()

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
)


class SubjectSource(models.Model):
    """A Subject is associated with a Source device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assigned_range = DateTimeRangeField()
    source = models.ForeignKey('Source')
    subject = models.ForeignKey('Subject')
    additional = JsonBField()
    """EXCLUDE USING gist (source_id WITH =, assigned_range WITH &&)"""
    objects = SubjectSourceManager()


class SubjectManager(models.Manager):
    pass


class Subject(models.Model):
    """Person, Animal, Vehicle, etc"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    subject_type = models.CharField(max_length=100, choices=SUBJECT_TYPES, default='wildlife')
    additional = JsonBField()
    objects = SubjectManager()

    @property
    def color(self):
        color = self.additional.get('rgb', None)
        if color:
            color = "#" + "".join(color.split(','))
        return color

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


class WildlifeSubjectManager(models.Manager):
    def get_queryset(self):
        return super(WildlifeSubjectManager, self).get_queryset().filter(
            subject_type='wildlife')

    def create(self, **kwargs):
        kwargs.update({'subject_type': 'wildlife'})
        return super(WildlifeSubjectManager, self).create(**kwargs)


class WildlifeSubject(Subject):
    objects = WildlifeSubjectManager()

    class Meta:
        proxy = True


MARKER_ICONS = {
    'elephant-male': 'http://107.21.94.89/Images/AnimalIcons/Elephant_Male.png',
    'elephant-female': 'http://107.21.94.89/Images/AnimalIcons/Elephant_Female.png',
    'lion-male': 'http://107.21.94.89/Images/AnimalIcons/Lion_Male.png',
    'lion-female': 'http://107.21.94.89/Images/AnimalIcons/Lion_Female.png',
    'vehicle': 'http://maps.google.com/mapfiles/kml/shapes/truck.png',
    'cow': '',
    'cheetah': '',
    'expedition': 'http://maps.google.com/mapfiles/kml/shapes/triangle.png',
    'zebra-male': 'http://107.21.94.89/Images/AnimalIcons/GrevysZebra_Male.png',
    'zebra-female': 'http://107.21.94.89/Images/AnimalIcons/GrevysZebra_Female.png',
    'forest elephant': '',
    'goat': '',
    'sable-male': 'http://107.21.94.89/Images/AnimalIcons/SableAntelopeGraphicMale.png',
    'sable-female': 'http://107.21.94.89/Images/AnimalIcons/SableAntelopeGraphicFemale.png',
    'rhino-male': 'http://107.21.94.89/Images/AnimalIcons/Rhino_Male.png',
    'rhino-female': 'http://107.21.94.89/Images/AnimalIcons/Rhino_Female.png',
    'white rhino': '',
    'black rhino': '',
}

def googlemarkericon(subject_type):
    return MARKER_ICONS.get(subject_type, 'http://maps.google.com/mapfiles/kml/shapes/truck.png')