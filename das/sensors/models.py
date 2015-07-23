"""
DAS DB models

after making changes to a model run migrations to record changes:
* python manage.py makemigrations --name "interesting model change name"

To re-sync your database with changes from others
* python manage.py migrate


GIS
* default geodjango spatial reference system is WGS84 (SRID 4326)
"""

from django.contrib.gis.db import models
from django_pgjson.fields import JsonBField
from django.contrib.postgres.fields import DateTimeRangeField, ArrayField
from django.db.models import Q
from django.utils import timezone
import pytz

class Device(models.Model):
    """Collar, MotoTrbo, sensor, etc"""
    id = models.AutoField(primary_key=True)
    device_type = models.ForeignKey('DeviceType')
    manufacturer_id = models.CharField('device manufacturer id', max_length=100,
                                       null=True)
    additional = JsonBField()


class DeviceType(models.Model):
    """Device characteristics"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    categories = ArrayField(models.CharField(max_length=50, blank=True))
    additional = JsonBField()


class ObservationManager(models.GeoManager):
    def get_device_range_observations(self, sds):
        """get observations for a set of devices and date ranges.
        An animal may switch devices based on a date range.
        """
        sds = sorted(sds, key=lambda sd: sd.assigned_range.lower, reverse=True)
        sql = '''SELECT * FROM sensors_observations so WHERE so.device_id = %(device_id)s so.recorded_at in %(range)s'''

        qs = None
        for sd in sds:
            q = Q(device_id=sd.device_id) & Q(recorded_at__range=[sd.assigned_range.lower, sd.assigned_range.upper])
            qs = qs | q if qs else q


        result = Observation.objects.filter(qs)
        result = result.order_by('-recorded_at')
        return result


class Observation(models.Model):
    """observation point

    similar to archive_loc

    """
    id = models.AutoField(primary_key=True)
    location = models.PointField()
    recorded_at = models.DateTimeField() #point in time of object at lat lon
    created_at = models.DateTimeField(auto_now_add=True) #date/time this row created
    device = models.ForeignKey('Device')
    additional = JsonBField()

    objects = ObservationManager()

    def __str__(self):
        return self.name

    class Meta:
        index_together = (
            ['device', 'recorded_at']
        )

class SubjectDeviceManager(models.GeoManager):
    pass


class SubjectDevice(models.Model):
    """A Subject is associated with a Device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """
    id = models.AutoField(primary_key=True)
    assigned_range = DateTimeRangeField()
    device = models.ForeignKey('Device')
    subject = models.ForeignKey('Subject')
    additional = JsonBField()
    """EXCLUDE USING gist (device_id WITH =, assigned_range WITH &&)"""
    objects = SubjectDeviceManager()


class Subject(models.Model):
    """Person, Animal, Vehicle, etc"""
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    additional = JsonBField()


# TODO: should go in Import/Transformer django app
# class CollectionHistory(models.Model):
#     """Input Transformer log"""
#     created_at = models.DateTimeField(auto_now_add=True) #date/time this row created
#     device = models.ForeignKey('Device')
#     outcome = models.CharField(max_length=50)

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