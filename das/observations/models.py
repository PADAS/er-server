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
from django.utils import timezone
import pytz


SOURCE_TYPES = (
    ('tracking-device', 'Tracking Device'),
    ('trap', 'Trap'),
    ('seismic', 'Seismic sensor'),
    ('firms', 'FIRMS data'),
    ('gps-radio', 'gps radio')
)

class Source(models.Model):
    """Collar, MotoTrbo, sensor, etc"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    source_type = models.CharField('type of data expected', max_length=100,
                                   null=True, choices=SOURCE_TYPES)
    manufacturer_id = models.CharField('device manufacturer id', max_length=100,
                                       null=True)
    model_name = models.CharField('device model name', max_length=100, null=True)
    additional = JsonBField()


class ObservationManager(models.GeoManager):
    def get_source_range_observations(self, subject_sources):
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
        result = result.order_by('-recorded_at')
        return result


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

    def __str__(self):
        return self.name

    class Meta:
        index_together = (
            ['source', 'recorded_at']
        )


class SubjectSourceManager(models.GeoManager):
    pass


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


class Subject(models.Model):
    """Person, Animal, Vehicle, etc"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    additional = JsonBField()


MARKER_ICONS = {
    'elephant-male': 'http://107.21.94.89/Images/AnimalIcons/Elephant_Male.png',
    'elephant-female': 'http://107.21.94.89/Images/AnimalIcons/Elephant_Female.png',
    'lion-male': '',
    'vehicle': 'http://maps.google.com/mapfiles/kml/shapes/truck.png',
    'cow': '',
    'cheetah': '',
    'expedition': 'http://maps.google.com/mapfiles/kml/shapes/triangle.png',
    'zebra': 'http://107.21.94.89/Images/AnimalIcons/GrevysZebra_Female.png',
    'forest elephant': '',
    'goat': '',
    'sable': '',
    'white rhino': '',
    'black rhino': '',
}
def googlemarkericon(subject_type):
    return MARKER_ICONS.get(subject_type, 'http://maps.google.com/mapfiles/kml/shapes/truck.png')